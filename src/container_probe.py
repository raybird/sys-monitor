#!/usr/bin/env python3
"""Bounded, read-only local Docker evidence. No exec, logs, argv or environment."""
from __future__ import annotations

import csv
from datetime import datetime
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import quote

FIELDS = [
    'timestamp', 'epoch', 'container', 'is_tracked_project', 'cpu_pct',
    'memory_usage', 'tasks', 'processes', 'zombies', 'oom_killed', 'restart_count',
    'container_id', 'project', 'service', 'health', 'read_bytes', 'write_bytes',
    'read_bps', 'write_bps', 'dstate', 'process_sample', 'sample_status', 'process_status', 'container_state',
]
BUDGET_SECONDS = 6
MAX_CONTAINERS = 32
MAX_DEEP = 8


class Engine:
    def __init__(self, path: str, deadline: float):
        self.path = path
        self.deadline = deadline

    def get(self, path: str):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('budget')
        connection = http.client.HTTPConnection('localhost', timeout=min(0.5, remaining))
        # Socket timeouts apply per operation, so a daemon that trickles bytes
        # would never trip them. The alarm bounds the request as a whole.
        previous = signal.signal(signal.SIGALRM, _budget_expired)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            connection.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.sock.settimeout(min(0.5, remaining))
            connection.sock.connect(self.path)
            connection.request('GET', path)
            response = connection.getresponse()
            if response.status != 200:
                raise OSError(f'HTTP {response.status}')
            payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise ValueError('response_limit')
            return json.loads(payload)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
            connection.close()


def _budget_expired(_signum, _frame):
    raise TimeoutError('budget')


def unavailable_reason(error: BaseException) -> str:
    if isinstance(error, TimeoutError):
        return 'timeout'
    if isinstance(error, FileNotFoundError):
        return 'no_socket'
    if isinstance(error, PermissionError):
        return 'permission'
    if isinstance(error, ConnectionRefusedError):
        return 'no_daemon'
    if str(error) == 'nonlocal_endpoint':
        return 'nonlocal'
    return 'error'


def read_time(stats: dict, fallback: float) -> float:
    """When Docker read the counters; the loop start only if that is unusable."""
    try:
        # Docker reports nanoseconds; older Pythons parse at most microseconds.
        value = datetime.fromisoformat(re.sub(r'(\.\d{6})\d+', r'\1', stats['read'])).timestamp()
    except (KeyError, TypeError, ValueError):
        return fallback
    # A stopped container reports year 1, which is no sample time at all.
    return value if value > 946_684_800 else fallback


def endpoint() -> str:
    host = os.environ.get('DOCKER_HOST', '')
    # Respect the CLI context rather than silently querying a different daemon.
    if not host:
        try:
            result = subprocess.run(
                ['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
                capture_output=True, text=True, timeout=0.5, check=True,
            )
            host = result.stdout.strip()
        except FileNotFoundError:
            host = 'unix:///var/run/docker.sock'
    if not host.startswith('unix://'):
        raise OSError('nonlocal_endpoint')
    return host[7:]


def block_bytes(stats: dict) -> tuple[int | None, int | None]:
    entries = stats.get('blkio_stats', {}).get('io_service_bytes_recursive')
    if not entries:
        return None, None
    return tuple(sum(int(e['value']) for e in entries if e.get('op', '').lower() == op)
                 for op in ('read', 'write'))


def io_rates(previous: dict, identity: str, started: str, epoch: float,
             read: int | None, write: int | None) -> tuple[float | None, float | None]:
    if (not started or previous.get('id') != identity or previous.get('started') != started
            or epoch <= previous.get('epoch', epoch)):
        return None, None
    old_read, old_write = previous.get('read'), previous.get('write')
    if any(v is None for v in (read, write, old_read, old_write)):
        return None, None
    if read < old_read or write < old_write:
        return None, None
    elapsed = epoch - previous['epoch']
    return (read - old_read) / elapsed, (write - old_write) / elapsed


def process_sample(data: dict) -> tuple[list[dict], int, int, int]:
    titles = [title.upper() for title in data.get('Titles', [])]
    required = ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND']
    if not all(title in titles for title in required):
        raise ValueError('unsupported_process_columns')
    positions = [titles.index(title) for title in required]
    processes = []
    for row in data.get('Processes', []):
        pid, state, cpu, memory, name = (row[i] for i in positions)
        # comm is requested, never args; control characters cannot break the TSV.
        processes.append(dict(pid=pid, state=state, cpu=float(cpu), memory=float(memory), name=name[:80]))
    selected = {}
    groups = [sorted(processes, key=lambda p: p['cpu'], reverse=True)[:5],
              sorted(processes, key=lambda p: p['memory'], reverse=True)[:5],
              [p for p in processes if p['state'].startswith('D')][:5]]
    for group in groups:
        for process in group:
            selected[process['pid']] = process
    return (list(selected.values()), len(processes),
            sum(p['state'].startswith('Z') for p in processes),
            sum(p['state'].startswith('D') for p in processes))


def invalidate_cache(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def cpu_percent(previous: dict, stats: dict, started: str, epoch: float) -> float | None:
    cpu_stats = stats.get('cpu_stats', {})
    cpu = cpu_stats.get('cpu_usage', {}).get('total_usage')
    system = cpu_stats.get('system_cpu_usage')
    cores = cpu_stats.get('online_cpus') or len(cpu_stats.get('cpu_usage', {}).get('percpu_usage', []))
    if (not started or previous.get('started') != started or epoch <= previous.get('epoch', epoch)
            or not cores or cores <= 0 or cpu is None or system is None
            or previous.get('cpu') is None or previous.get('system') is None):
        return None
    cpu_delta = cpu - previous['cpu']
    system_delta = system - previous['system']
    if cpu_delta < 0 or system_delta <= 0:
        return None
    return cpu_delta / system_delta * cores * 100


def collect(timestamp: str, epoch: int, projects: str, state_dir: Path) -> tuple[str, list[dict]]:
    deadline = time.monotonic() + BUDGET_SECONDS
    empty = dict.fromkeys(FIELDS)
    # Same values as the collector's own empty row when the helper fails.
    empty.update(timestamp=timestamp, epoch=epoch, container='', is_tracked_project=0,
                 sample_status='unavailable', process_status='unavailable')
    cache_path = state_dir / 'docker-counters.json'
    try:
        engine = Engine(endpoint(), deadline)
        containers = engine.get('/containers/json?all=1')
        if not isinstance(containers, list):
            raise ValueError('invalid_listing')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        invalidate_cache(cache_path)
        return 'unavailable:' + unavailable_reason(error), [empty]
    try:
        cache = json.loads(cache_path.read_text())
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    wanted = set(projects.split(',')) - {''}
    containers = [c for c in containers if c.get('State') == 'running'
                  or (c.get('Labels') or {}).get('com.docker.compose.project') in wanted]
    tracked = sorted(c['Id'] for c in containers if c.get('State') == 'running'
                     and (c.get('Labels') or {}).get('com.docker.compose.project') in wanted)
    # A persistent cursor, like the overview one below: a time bucket repeats
    # the same offset whenever the sampling period is a multiple of it.
    deep_cursor = cache.get('__deep_cursor', 0)
    if not isinstance(deep_cursor, int):
        deep_cursor = 0
    offset = deep_cursor % max(1, len(tracked))
    deep = set((tracked + tracked)[offset:offset + min(MAX_DEEP, len(tracked))])
    # Advance through the entire sorted list, skipping only deep candidates
    # already selected. Truncating a separately rotated list can starve its tail.
    containers.sort(key=lambda c: c['Id'])
    ordered = [c for c in containers if c['Id'] in deep]
    cursor = cache.get('__overview_cursor', 0)
    if not isinstance(cursor, int):
        cursor = 0
    cursor %= max(1, len(containers))
    next_cursor = cursor
    for visited in range(len(containers)):
        index = (cursor + visited) % len(containers)
        next_cursor = (index + 1) % len(containers)
        if containers[index]['Id'] not in deep:
            ordered.append(containers[index])
        if len(ordered) >= MAX_CONTAINERS:
            break
    rows = []
    counters = {'__overview_cursor': next_cursor,
                '__deep_cursor': (offset + MAX_DEEP) % max(1, len(tracked))}
    partial = len(containers) > MAX_CONTAINERS
    for container in ordered:
        identity = container['Id']
        labels = container.get('Labels') or {}
        project = labels.get('com.docker.compose.project', '')
        row = dict.fromkeys(FIELDS)
        row.update(timestamp=timestamp, epoch=epoch, container=(container.get('Names') or [identity[:12]])[0].lstrip('/'),
                   container_id=identity, project=project, service=labels.get('com.docker.compose.service', ''),
                   is_tracked_project=int(project in wanted), sample_status='ok', container_state=container.get('State'),
                   process_status='not_tracked' if project not in wanted else 'budget_or_limit')
        try:
            inspect = engine.get(f'/containers/{identity}/json')
            state = inspect.get('State', {})
            row.update(container_state=state.get('Status', container.get('State')),
                       oom_killed=str(state.get('OOMKilled')).lower() if 'OOMKilled' in state else None,
                       restart_count=inspect.get('RestartCount'),
                       health=state.get('Health', {}).get('Status', 'not_configured'))
            if row['container_state'] != 'running':
                row.update(sample_status='stopped', process_status='stopped')
                rows.append(row)
                continue
            stats = engine.get(f'/containers/{identity}/stats?stream=false&one-shot=true')
            started = state.get('StartedAt', '')
            previous = cache.get(identity, {})
            if not isinstance(previous, dict) or previous.get('id') != identity:
                previous = {}
            read, write = block_bytes(stats)
            at = read_time(stats, epoch)
            read_bps, write_bps = io_rates(previous, identity, started, at, read, write)
            cpu_stats = stats.get('cpu_stats', {})
            cpu = cpu_stats.get('cpu_usage', {}).get('total_usage')
            system = cpu_stats.get('system_cpu_usage')
            cpu_pct = cpu_percent(previous, stats, started, at)
            memory = stats.get('memory_stats', {})
            usage, limit = memory.get('usage'), memory.get('limit')
            row.update(cpu_pct=None if cpu_pct is None else round(cpu_pct, 2), memory_usage=f'{usage / 1048576:.1f}MiB / {limit / 1048576:.1f}MiB' if usage is not None and limit else None,
                       tasks=stats.get('pids_stats', {}).get('current'), read_bytes=read, write_bytes=write,
                       read_bps=None if read_bps is None else round(read_bps, 1),
                       write_bps=None if write_bps is None else round(write_bps, 1))
            counters[identity] = dict(id=identity, started=started, epoch=at, read=read, write=write,
                                      cpu=cpu, system=system)
            if identity in deep:
                try:
                    data = engine.get(f'/containers/{identity}/top?ps_args=' + quote('-eo pid,stat,pcpu,pmem,comm'))
                    processes, count, zombies, dstate = process_sample(data)
                    row.update(processes=count, zombies=zombies, dstate=dstate,
                               process_sample=json.dumps(processes, ensure_ascii=True, separators=(',', ':')), process_status='ok')
                except (OSError, ValueError, IndexError, TypeError):
                    row['process_status'] = 'unavailable_or_timeout'
        except (OSError, ValueError, TypeError, KeyError):
            row['sample_status'] = 'unavailable_or_timeout'
            partial = True
        rows.append(row)
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(counters, handle)
        temporary.replace(cache_path)
    except OSError:
        invalidate_cache(cache_path)
        for row in rows:
            row.update(cpu_pct=None, read_bps=None, write_bps=None)
        partial = True
    if not rows:
        empty.update(sample_status='empty', process_status='empty')
        rows = [empty]
    return 'partial' if partial else 'ok', rows


def main() -> None:
    timestamp, epoch, projects, state_dir = sys.argv[1:]
    state, rows = collect(timestamp, int(epoch), projects, Path(state_dir))
    # Shell reads the first line; every other line preserves the legacy TSV prefix.
    print(state)
    writer = csv.writer(sys.stdout, delimiter='\t', lineterminator='\n')
    for row in rows:
        writer.writerow('NA' if row.get(key) is None else str(row[key]).replace('\t', ' ').replace('\n', ' ').replace('\r', ' ') for key in FIELDS)


if __name__ == '__main__':
    main()
