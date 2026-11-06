"""Raw Docker samples: boundaries that would otherwise create false evidence."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('container_probe', Path(__file__).resolve().parents[1] / 'src/container_probe.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class CounterTests(unittest.TestCase):
    def test_rates_use_elapsed_time_and_identity(self):
        prev = {'id': 'abc', 'started': 'start', 'epoch': 100, 'read': 1000, 'write': 50}
        self.assertEqual(probe.io_rates(prev, 'abc', 'start', 104, 1400, 90), (100, 10))
        for old in ({}, dict(prev, id='new'), dict(prev, started='restart'), dict(prev, epoch=105)):
            self.assertEqual(probe.io_rates(old, 'abc', 'start', 104, 1400, 90), (None, None))
        self.assertEqual(probe.io_rates(prev, 'abc', 'start', 104, 2, 90), (None, None))
        self.assertEqual(probe.io_rates(prev, 'abc', 'start', 104, None, None), (None, None))

    def test_raw_block_bytes_and_missing_accounting(self):
        self.assertEqual(probe.block_bytes({'blkio_stats': {'io_service_bytes_recursive': [
            {'op': 'Read', 'value': 100}, {'op': 'Read', 'value': 30}, {'op': 'Write', 'value': 70}, {'op': 'Total', 'value': 200}
        ]}}), (130, 70))
        self.assertEqual(probe.block_bytes({}), (None, None))

    def test_bounded_processes_preserve_dstate_and_never_argv(self):
        titles = ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND']
        rows = [[str(n), 'R', str(n), str(40-n), 'worker'] for n in range(1, 25)]
        rows.append(['99', 'D', '0', '0', 'io-worker'])
        processes, count, zombies, dstate = probe.process_sample({'Titles': titles, 'Processes': rows})
        self.assertLessEqual(len(processes), 15)
        self.assertEqual(count, 25)
        self.assertEqual(zombies, 0)
        self.assertEqual(dstate, 1)
        self.assertTrue(any(p['pid'] == '99' for p in processes))
        self.assertEqual(set(processes[0]), {'pid', 'state', 'cpu', 'memory', 'name'})

    def test_no_process_output_is_unknown(self):
        with self.assertRaises(ValueError):
            probe.process_sample({'Titles': [], 'Processes': []})


class SamplingTests(unittest.TestCase):
    def test_unavailable_endpoint_records_explicit_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(probe, 'endpoint', side_effect=OSError('denied')):
                state, rows = probe.collect('2026-11-06T00:00:00Z', 100, 'a,b', Path(td))
        # S4 (2026-11-06): the state names the reason; an unclassified error says so.
        self.assertEqual(state, 'unavailable:error')
        self.assertEqual(rows[0]['container'], '')
        self.assertEqual(rows[0]['sample_status'], 'unavailable')

    def test_multi_project_raw_stats_and_private_cache(self):
        class Engine:
            def get(self, path):
                if path == '/containers/json?all=1':
                    return [{'Id': 'abc', 'State': 'running', 'Names': ['/worker'], 'Labels': {'com.docker.compose.project': 'b', 'com.docker.compose.service': 'worker'}}]
                if path.endswith('/json'):
                    return {'State': {'StartedAt': 'start', 'OOMKilled': False}, 'RestartCount': 0}
                if '/stats?' in path:
                    return {'memory_stats': {'usage': 100, 'limit': 1000}, 'pids_stats': {'current': 2}, 'blkio_stats': {'io_service_bytes_recursive': [{'op': 'Read', 'value': 100}, {'op': 'Write', 'value': 50}]}}
                return {'Titles': ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND'], 'Processes': [['3', 'D', '1', '2', 'worker']]}
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Engine()):
            state, rows = probe.collect('now', 100, 'a,b', Path(td))
            self.assertEqual(state, 'ok')
            self.assertEqual(rows[0]['is_tracked_project'], 1)
            self.assertEqual(rows[0]['read_bytes'], 100)
            self.assertIsNone(rows[0]['read_bps'])
            self.assertEqual(rows[0]['health'], 'not_configured')
            self.assertEqual(rows[0]['dstate'], 1)
            self.assertEqual((Path(td) / 'docker-counters.json').stat().st_mode & 0o777, 0o600)
            _, rows = probe.collect('later', 110, 'a,b', Path(td))
            self.assertEqual(rows[0]['read_bps'], 0)

    def test_deadline_limits_calls(self):
        engine = probe.Engine('/unused', time.monotonic() - 1)
        with self.assertRaises(TimeoutError):
            engine.get('/containers/json')

class CollectorHarness(unittest.TestCase):
    def run_collector(self, root, body):
        import os
        import subprocess
        helper = Path(root) / 'probe.py'
        helper.write_text(body)
        env = dict(os.environ, XDG_STATE_HOME=root, FREEZE_WATCH_CONTAINER_PROBE=str(helper),
                   FREEZE_WATCH_PYTHON='/usr/bin/python3', FREEZE_WATCH_MAX_SAMPLES='1',
                   FREEZE_WATCH_JOURNALCTL='/bin/false')
        result = subprocess.run(['bash', str(Path(__file__).resolve().parents[1] / 'src/freeze-monitor')],
                                env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return Path(root) / 'freeze-monitor'


class CollectorIntegrationTests(CollectorHarness):
    def test_real_shell_writes_compatible_rows_and_anomaly(self):
        import csv
        row = dict.fromkeys(probe.FIELDS, 'NA')
        row.update(container='worker', is_tracked_project=1, cpu_pct=12, tasks=3, processes=2,
                   zombies=0, oom_killed='false', restart_count=0, container_id='abc', project='b',
                   service='worker', health='unhealthy', dstate=1, container_state='running', process_sample=json.dumps([
                       dict(pid='3', state='D', cpu=0, memory=1, name='程式')]), sample_status='ok', process_status='ok')
        body = "import csv, sys\nrow=" + repr(row) + "\nrow.update(timestamp=sys.argv[1],epoch=sys.argv[2])\nprint('ok')\ncsv.writer(sys.stdout, delimiter='\\t',lineterminator='\\n').writerow(row[k] for k in " + repr(probe.FIELDS) + ")\n"
        with tempfile.TemporaryDirectory() as td:
            state = self.run_collector(td, body)
            rows = list(csv.DictReader(next(state.glob('docker-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(rows[0]['container_id'], 'abc')
            self.assertEqual(json.loads(rows[0]['process_sample'])[0]['name'], '程式')
            metrics = list(csv.DictReader(next(state.glob('metrics-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(metrics[0]['tracked_processes'], '2')
            self.assertIn('Docker anomaly: worker:', (state / 'events.log').read_text())

    def test_failed_helper_cannot_stop_host_metrics_or_keep_old_snapshot(self):
        import csv
        with tempfile.TemporaryDirectory() as td:
            state = self.run_collector(td, 'raise SystemExit(1)\n')
            rows = list(csv.DictReader(next(state.glob('docker-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(rows[0]['container'], '')
            self.assertEqual(rows[0]['sample_status'], 'unavailable')
            metrics = list(csv.DictReader(next(state.glob('metrics-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(len(metrics), 1)
            self.assertEqual(metrics[0]['docker_state'], 'unavailable:helper_failed')

class ContainerAlertTests(unittest.TestCase):
    # 2026-11-06 使用者決定（S3）：只警示追蹤中的容器；重啟以相對前一次採樣的增加
    # 判定；D 沿用主機 WARN 門檻 8，事件去重不受 D 數值波動影響。
    def test_events_follow_tracked_restart_increase_and_dstate_threshold(self):
        import os
        import subprocess
        fields = repr(probe.FIELDS)
        body = (
            "import csv, sys\nfrom pathlib import Path\n"
            "calls = Path(sys.argv[4]) / 'calls'\n"
            "n = min(3, int(calls.read_text()) + 1 if calls.exists() else 1)\n"
            "calls.write_text(str(n))\n"
            "def row(**kw):\n"
            "    r = dict.fromkeys(" + fields + ", 'NA')\n"
            "    r.update(timestamp=sys.argv[1], epoch=sys.argv[2], zombies=0, oom_killed='false', health='healthy',\n"
            "             sample_status='ok', process_status='ok', container_state='running')\n"
            "    r.update(kw)\n"
            "    return [r[k] for k in " + fields + "]\n"
            "print('ok')\n"
            "w = csv.writer(sys.stdout, delimiter='\\t', lineterminator='\\n')\n"
            "w.writerow(row(container='worker', container_id='w1', is_tracked_project=1, restart_count=1 if n < 3 else 2, dstate=0))\n"
            "w.writerow(row(container='db', container_id='d1', is_tracked_project=1, restart_count=0, dstate=7 + n))\n"
            "w.writerow(row(container='shallow', container_id='s1', is_tracked_project=1, restart_count=0, dstate=7))\n"
            "w.writerow(row(container='portainer', container_id='p1', is_tracked_project=0, restart_count=9, dstate=9, oom_killed='true'))\n"
        )
        with tempfile.TemporaryDirectory() as td:
            helper = Path(td) / 'probe.py'
            helper.write_text(body)
            env = dict(os.environ, XDG_STATE_HOME=td, FREEZE_WATCH_CONTAINER_PROBE=str(helper),
                       FREEZE_WATCH_PYTHON='/usr/bin/python3', FREEZE_WATCH_MAX_SAMPLES='7',
                       FREEZE_WATCH_INTERVAL_SECONDS='1', FREEZE_WATCH_JOURNALCTL='/bin/false')
            result = subprocess.run(['bash', str(Path(__file__).resolve().parents[1] / 'src/freeze-monitor')],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = Path(td) / 'freeze-monitor'
            self.assertEqual((state / 'calls').read_text(), '3')
            alerts = [line for line in (state / 'events.log').read_text().splitlines() if 'Docker anomaly' in line]
        self.assertEqual(len(alerts), 2, alerts)
        self.assertIn('db:', alerts[0])
        self.assertNotIn('worker', alerts[0])
        self.assertIn('worker:', alerts[1])
        self.assertIn('restarts', alerts[1])
        for line in alerts:
            self.assertNotIn('portainer', line)
            self.assertNotIn('shallow', line)


class FailureAndLimitTests(unittest.TestCase):
    def test_empty_snapshot_and_missing_stats_have_distinct_states(self):
        class Empty:
            def get(self, path):
                return []
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Empty()):
            state, rows = probe.collect('now', 100, 'a,b', Path(td))
            self.assertEqual(state, 'ok')
            self.assertEqual(rows[0]['sample_status'], 'empty')
        class Broken:
            def get(self, path):
                if path == '/containers/json?all=1':
                    return [{'Id': 'abc', 'State': 'running', 'Names': ['/worker'], 'Labels': None}]
                raise TimeoutError('timeout')
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Broken()):
            state, rows = probe.collect('now', 100, 'a,b', Path(td))
            self.assertEqual(state, 'partial')
            self.assertEqual(rows[0]['sample_status'], 'unavailable_or_timeout')
            self.assertIsNone(rows[0]['cpu_pct'])

    def test_more_than_32_containers_do_not_starve_deep_projects(self):
        seen = []
        class Many:
            def get(self, path):
                if path == '/containers/json?all=1':
                    return [{'Id': str(n).zfill(3), 'State':'running', 'Labels': {'com.docker.compose.project': 'tracked'}, 'Names': ['/worker'+str(n)]} for n in range(80)]
                if path.endswith('/json'):
                    return {'State': {'StartedAt': 'start'}}
                if '/stats?' in path:
                    return {}
                seen.append(path.split('/')[2])
                return {'Titles': ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND'], 'Processes': []}
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=Many()):
            for epoch in range(0, 300, 30):
                state, rows = probe.collect('now', epoch, 'tracked', Path(td))
                self.assertEqual(state, 'partial')
                self.assertEqual(len(rows), 32)
                self.assertEqual(sum(r['process_status'] == 'ok' for r in rows), 8)
        self.assertEqual(len(set(seen)), 80)

    def test_engine_rejects_nonlocal_endpoint(self):
        with patch.dict('os.environ', {'DOCKER_HOST': 'tcp://remote:2375'}):
            with self.assertRaises(OSError):
                probe.endpoint()

    def test_exact_fields_match_dashboard_and_shell_header(self):
        text = (Path(__file__).resolve().parents[1] / 'src/freeze-monitor').read_text()
        expected = '\\t'.join(probe.FIELDS) + '\\n'
        self.assertIn(expected, text)

    def test_helper_main_roundtrips_json_without_double_escaping(self):
        import csv
        import io
        row = dict(timestamp='now', epoch=100, container='worker', process_sample=json.dumps([{'name': '程式', 'pid': '2'}]))
        output = io.StringIO()
        with patch.object(probe, 'collect', return_value=('ok', [row])), patch('sys.argv', ['probe', 'now', '100', 'a', '/tmp']), patch('sys.stdout', output):
            probe.main()
        record = next(csv.DictReader(output.getvalue().splitlines()[1:], fieldnames=probe.FIELDS, delimiter='\t'))
        self.assertEqual(json.loads(record['process_sample'])[0]['name'], '程式')

class HardTimeoutTest(CollectorHarness):
    def test_hung_helper_has_hard_limit_and_host_survives(self):
        import csv
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as td:
            state = self.run_collector(td, 'import sys,time\nfrom pathlib import Path\n(Path(sys.argv[4])/"docker-counters.json").write_text("{}")\ntime.sleep(60)\n')
            self.assertTrue(next(state.glob('metrics-*.tsv')).read_text().count('\n') >= 2)
            self.assertFalse((state / 'docker-counters.json').exists())
            metrics = next(csv.DictReader(next(state.glob('metrics-*.tsv')).read_text().splitlines(), delimiter='\t'))
            self.assertEqual(metrics['docker_state'], 'unavailable:timeout')
        self.assertLess(time.monotonic() - started, 11)

class RecoveryRegressionTests(unittest.TestCase):
    class EngineFixture:
        def __init__(self, state='running', read=100, fail_stats=False, cpu=1000, system=10000, started='start', cores=2):
            self.state, self.read, self.fail_stats = state, read, fail_stats
            self.cpu, self.system, self.started, self.cores = cpu, system, started, cores
            self.calls = []

        def get(self, path):
            self.calls.append(path)
            if path.startswith('/containers/json'):
                if self.state != 'running' and 'all=1' not in path:
                    return []
                return [{'Id':'abc','Names':['/worker'],'Labels':{'com.docker.compose.project':'tracked'},'State':self.state}]
            if path.endswith('/json'):
                return {'State':{'StartedAt':self.started,'Status':self.state,'OOMKilled':self.state=='exited'},'RestartCount':2}
            if '/stats?' in path:
                if self.fail_stats:
                    raise OSError('stats unavailable')
                return {'cpu_stats':{'cpu_usage':{'total_usage':self.cpu},'system_cpu_usage':self.system,'online_cpus':self.cores},
                        'blkio_stats':{'io_service_bytes_recursive':[{'op':'Read','value':self.read},{'op':'Write','value':0}]}}
            return {'Titles':['PID','STAT','%CPU','%MEM','COMMAND'],'Processes':[]}

    def sample(self, td, engine, epoch=100):
        with patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=engine):
            return probe.collect('then', epoch, 'tracked', Path(td))

    def test_exited_oom_is_inspected_without_stats_or_top(self):
        engine = self.EngineFixture(state='exited')
        with tempfile.TemporaryDirectory() as td:
            state, rows = self.sample(td, engine)
        self.assertEqual(rows[0]['container'], 'worker')
        self.assertEqual(rows[0]['container_state'], 'exited')
        self.assertEqual(rows[0]['oom_killed'], 'true')
        self.assertEqual(rows[0]['restart_count'], 2)
        self.assertEqual(rows[0]['process_status'], 'stopped')
        self.assertIsNone(rows[0]['cpu_pct'])
        self.assertFalse(any('/stats?' in p or '/top?' in p for p in engine.calls))

    def test_inspect_evidence_survives_stats_failure(self):
        with tempfile.TemporaryDirectory() as td:
            _, rows = self.sample(td, self.EngineFixture(fail_stats=True))
        self.assertEqual(rows[0]['restart_count'], 2)
        self.assertEqual(rows[0]['oom_killed'], 'false')
        self.assertEqual(rows[0]['sample_status'], 'unavailable_or_timeout')

    def test_daemon_outage_invalidates_cpu_and_io_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            self.sample(td, self.EngineFixture(), 100)
            with patch.object(probe, 'endpoint', side_effect=OSError('offline')):
                probe.collect('offline', 130, 'tracked', Path(td))
            _, rows = self.sample(td, self.EngineFixture(read=700,cpu=2000,system=20000), 160)
            self.assertIsNone(rows[0]['read_bps'])
            self.assertIsNone(rows[0]['cpu_pct'])

    def test_cpu_requires_identity_positive_cores_and_forward_time(self):
        for first, second, epoch in [
            (self.EngineFixture(started=''), self.EngineFixture(started='',cpu=2000,system=20000), 130),
            (self.EngineFixture(), self.EngineFixture(cpu=2000,system=20000,cores=0), 130),
            (self.EngineFixture(), self.EngineFixture(cpu=2000,system=20000), 90),
        ]:
            with self.subTest(epoch=epoch,cores=second.cores,started=second.started), tempfile.TemporaryDirectory() as td:
                self.sample(td, first, 100)
                _, rows = self.sample(td, second, epoch)
                self.assertIsNone(rows[0]['cpu_pct'])

    def test_valid_cpu_delta_matches_one_core_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            self.sample(td, self.EngineFixture(), 100)
            _, rows = self.sample(td, self.EngineFixture(cpu=3000,system=20000), 130)
        self.assertEqual(rows[0]['cpu_pct'], 40)

    def test_corrupt_cache_entry_recovers_as_first_sample(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'docker-counters.json').write_text('{"abc": []}')
            _, rows = self.sample(td, self.EngineFixture())
            self.assertEqual(rows[0]['sample_status'], 'ok')
            self.assertIsNone(rows[0]['read_bps'])
            self.assertIsNone(rows[0]['cpu_pct'])

class MixedRotationRegressionTests(unittest.TestCase):
    def test_running_priority_cannot_starve_exited_oom_containers(self):
        inspected=set()
        class Mixed:
            def get(self, path):
                if path.startswith('/containers/json'):
                    return [{'Id':str(n).zfill(3),'Names':['/worker'+str(n)],'Labels':{'com.docker.compose.project':'tracked'},'State':'running' if n<8 else 'exited'} for n in range(64)]
                identity=int(path.split('/')[2])
                if path.endswith('/json'):
                    inspected.add(identity)
                    return {'State':{'Status':'running' if identity<8 else 'exited','StartedAt':'start','OOMKilled':identity>=8},'RestartCount':0}
                if '/stats?' in path:
                    return {}
                return {'Titles':['PID','STAT','%CPU','%MEM','COMMAND'],'Processes':[]}
        with tempfile.TemporaryDirectory() as td, patch.object(probe,'endpoint',return_value='/unused'), patch.object(probe,'Engine',return_value=Mixed()):
            for epoch in range(0,600,30):
                _, rows=probe.collect('now',epoch,'tracked',Path(td))
                self.assertEqual(len(rows),32)
                self.assertEqual(sum(r['container_state']=='running' for r in rows),8)
                self.assertTrue(all(r['oom_killed']=='true' for r in rows if r['container_state']=='exited'))
        self.assertEqual(inspected,set(range(64)))


class ReviewFollowupTests(CollectorHarness):
    """2026-11-06 使用者「2. 一起修」：PR #3 審查的 S2、S4、S8、N2、N3、N4。"""

    class Timed(RecoveryRegressionTests.EngineFixture):
        def __init__(self, read_time, **kw):
            super().__init__(**kw)
            self.read_time = read_time

        def get(self, path):
            result = super().get(path)
            if '/stats?' in path:
                result['read'] = self.read_time
            return result

    def sample(self, td, engine, epoch):
        with patch.object(probe, 'endpoint', return_value='/unused'), patch.object(probe, 'Engine', return_value=engine):
            return probe.collect('then', epoch, 'tracked', Path(td))

    def test_s2_rates_divide_by_each_containers_read_time(self):
        # The loop started 30 s apart, but Docker read the counters 10 s apart.
        with tempfile.TemporaryDirectory() as td:
            self.sample(td, self.Timed('2026-11-06T00:00:00.500000000Z', read=100), 100)
            _, rows = self.sample(td, self.Timed('2026-11-06T00:00:10.500000000Z', read=1100), 130)
        self.assertEqual(rows[0]['read_bps'], 100.0)

    def test_s2_unusable_read_time_falls_back_to_loop_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            self.sample(td, self.Timed('0001-01-01T00:00:00Z', read=100), 100)
            _, rows = self.sample(td, self.Timed('garbage', read=700), 130)
        self.assertEqual(rows[0]['read_bps'], 20.0)

    def test_n2_rates_and_cpu_are_rounded(self):
        with tempfile.TemporaryDirectory() as td:
            self.sample(td, self.Timed('2026-11-06T00:00:00Z', read=100, cpu=1000, system=10000), 100)
            _, rows = self.sample(td, self.Timed('2026-11-06T00:00:03Z', read=1100, cpu=1001, system=10003), 130)
        self.assertEqual(rows[0]['read_bps'], 333.3)
        self.assertEqual(rows[0]['cpu_pct'], 66.67)

    def test_s4_unavailable_state_names_the_reason(self):
        import socket as socket_module
        with tempfile.TemporaryDirectory() as td:
            cases = {'unavailable:no_socket': 'unix://' + td + '/missing.sock',
                     'unavailable:nonlocal': 'tcp://remote:2375'}
            locked = td + '/locked.sock'
            server = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
            server.bind(locked)
            server.listen(1)
            os.chmod(locked, 0)
            if os.geteuid() != 0:
                cases['unavailable:permission'] = 'unix://' + locked
            refused = td + '/refused.sock'
            closed = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
            closed.bind(refused)
            closed.close()
            cases['unavailable:no_daemon'] = 'unix://' + refused
            try:
                for expected, host in cases.items():
                    with self.subTest(host=host), patch.dict('os.environ', {'DOCKER_HOST': host}):
                        state, rows = probe.collect('now', 100, 'a', Path(td))
                        self.assertEqual(state, expected)
                        self.assertEqual(rows[0]['sample_status'], 'unavailable')
            finally:
                server.close()

    def test_s8_slow_daemon_is_cut_at_budget_and_keeps_finished_rows(self):
        import subprocess
        import sys
        script = f"""
import importlib.util, json, socket, threading, time
from pathlib import Path
import tempfile
spec = importlib.util.spec_from_file_location('probe', {str(Path(__file__).resolve().parents[1] / 'src/container_probe.py')!r})
probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
probe.BUDGET_SECONDS = 1.5
td = tempfile.mkdtemp()
path = td + '/docker.sock'
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); server.bind(path); server.listen(16)
listing = [dict(Id=i, State='exited', Names=['/' + i], Labels={{'com.docker.compose.project': 'tracked'}}) for i in ('a1', 'b2')]
def reply(conn, body, drip=False):
    head = b'HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\nContent-Length: ' + str(len(body)).encode() + b'\\r\\n\\r\\n'
    conn.sendall(head)
    for i in range(len(body)):
        if drip:
            time.sleep(0.2)
        conn.sendall(body[i:i + (1 if drip else len(body))])
        if not drip:
            break
def serve():
    while True:
        conn, _ = server.accept()
        request = conn.recv(4096).decode()
        target = request.split()[1]
        try:
            if target.startswith('/containers/json'):
                reply(conn, json.dumps(listing).encode())
            elif '/a1/' in target:
                reply(conn, json.dumps(dict(State=dict(Status='exited', OOMKilled=True), RestartCount=1)).encode())
            else:
                reply(conn, b' ' * 400 + b'{{}}', drip=True)
        except OSError:
            pass
        conn.close()
threading.Thread(target=serve, daemon=True).start()
import os
os.environ['DOCKER_HOST'] = 'unix://' + path
started = time.monotonic()
state, rows = probe.collect('now', 100, 'tracked', Path(td))
print(json.dumps(dict(elapsed=time.monotonic() - started, state=state,
                      rows=[[r['container'], r['sample_status'], r['oom_killed']] for r in rows])))
"""
        try:
            result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=8)
        except subprocess.TimeoutExpired:
            self.fail('helper did not stop at its budget')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertLess(report['elapsed'], 2.5)
        self.assertEqual(report['state'], 'partial')
        self.assertEqual(report['rows'], [['a1', 'stopped', 'true'], ['b2', 'unavailable_or_timeout', None]])

    def test_n3_deep_rotation_reaches_every_tracked_container(self):
        # A 20 s host interval gives a 60 s Docker period: epoch // 30 then
        # advances by two buckets and the old offset repeated forever.
        seen = set()
        class Sixteen:
            def get(self, path):
                if path == '/containers/json?all=1':
                    return [{'Id': f'{n:02}', 'State': 'running', 'Names': [f'/w{n}'],
                             'Labels': {'com.docker.compose.project': 'tracked'}} for n in range(16)]
                if path.endswith('/json'):
                    return {'State': {'StartedAt': 'start', 'Status': 'running'}}
                if '/stats?' in path:
                    return {}
                seen.add(path.split('/')[2])
                return {'Titles': ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND'], 'Processes': []}
        with tempfile.TemporaryDirectory() as td, patch.object(probe, 'endpoint', return_value='/unused'), \
                patch.object(probe, 'Engine', return_value=Sixteen()):
            for epoch in (0, 60):
                probe.collect('now', epoch, 'tracked', Path(td))
        self.assertEqual(len(seen), 16)

    def test_n4_helper_and_shell_write_the_same_unavailable_row(self):
        import csv
        import io
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as td, patch.dict('os.environ', {'DOCKER_HOST': 'unix://' + td + '/missing.sock'}), \
                patch('sys.argv', ['probe', 'now', '100', 'a', td]), patch('sys.stdout', output):
            probe.main()
        helper_row = next(csv.DictReader(output.getvalue().splitlines()[1:], fieldnames=probe.FIELDS, delimiter='\t'))
        with tempfile.TemporaryDirectory() as td:
            state = self.run_collector(td, 'raise SystemExit(1)\n')
            shell_row = next(csv.DictReader(next(state.glob('docker-*.tsv')).read_text().splitlines(), delimiter='\t'))
        for key in ('timestamp', 'epoch'):
            helper_row.pop(key)
            shell_row.pop(key)
        self.assertEqual(helper_row, shell_row)


class IntegratedReviewFollowupTests(unittest.TestCase):
    """2026-11-06 使用者「都依照建議修」：整合後審查的 M1、N1、S1。"""

    def test_m1_n1_failed_rounds_neither_drop_the_restart_baseline_nor_repeat_events(self):
        import os
        import subprocess
        fields = repr(probe.FIELDS)
        # Docker samples 1..5: ok, helper fails, ok, helper fails, ok with one more restart.
        body = (
            "import csv, sys\nfrom pathlib import Path\n"
            "calls = Path(sys.argv[4]) / 'calls'\n"
            "n = int(calls.read_text()) + 1 if calls.exists() else 1\n"
            "calls.write_text(str(n))\n"
            "if n in (2, 4):\n    raise SystemExit(1)\n"
            "def row(**kw):\n"
            "    r = dict.fromkeys(" + fields + ", 'NA')\n"
            "    r.update(timestamp=sys.argv[1], epoch=sys.argv[2], zombies=0, oom_killed='false', health='healthy',\n"
            "             sample_status='ok', process_status='ok', container_state='running', dstate=0, restart_count=0)\n"
            "    r.update(kw)\n"
            "    return [r[k] for k in " + fields + "]\n"
            "print('ok')\n"
            "w = csv.writer(sys.stdout, delimiter='\\t', lineterminator='\\n')\n"
            "w.writerow(row(container='worker', container_id='w1', is_tracked_project=1, restart_count=1 if n < 5 else 2))\n"
            "w.writerow(row(container='db', container_id='d1', is_tracked_project=1, health='unhealthy'))\n"
        )
        with tempfile.TemporaryDirectory() as td:
            helper = Path(td) / 'probe.py'
            helper.write_text(body)
            env = dict(os.environ, XDG_STATE_HOME=td, FREEZE_WATCH_CONTAINER_PROBE=str(helper),
                       FREEZE_WATCH_PYTHON='/usr/bin/python3', FREEZE_WATCH_MAX_SAMPLES='13',
                       FREEZE_WATCH_INTERVAL_SECONDS='1', FREEZE_WATCH_JOURNALCTL='/bin/false')
            result = subprocess.run(['bash', str(Path(__file__).resolve().parents[1] / 'src/freeze-monitor')],
                                    env=env, capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = Path(td) / 'freeze-monitor'
            self.assertEqual((state / 'calls').read_text(), '5')
            alerts = [line for line in (state / 'events.log').read_text().splitlines() if 'Docker anomaly' in line]
        # One event when db turns unhealthy, none after the failed rounds while
        # nothing changed, one when worker restarted across a failed round.
        self.assertEqual(len(alerts), 2, alerts)
        self.assertIn('db:', alerts[0])
        self.assertNotIn('worker', alerts[0])
        self.assertIn('worker:oom=false,restarts=2(new)', alerts[1])

    def test_s1_read_time_parses_rfc3339nano_without_python_311(self):
        # Literal epochs, independent of the parser: 2026-11-06T00:00:00Z = 1793923200.
        for text, expected in [('2026-11-06T00:00:00.1234Z', 1793923200.1234),
                               ('2026-11-06T00:00:00.123456789Z', 1793923200.123456),
                               ('2026-11-06T00:00:00Z', 1793923200.0),
                               ('2026-11-06T08:00:00.5+08:00', 1793923200.5)]:
            with self.subTest(text=text):
                self.assertAlmostEqual(probe.read_time({'read': text}, 0), expected, places=5)
