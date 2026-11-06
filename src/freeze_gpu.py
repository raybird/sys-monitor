#!/usr/bin/env python3
"""可選的 DRM fdinfo 採樣，限制掃描成本且不讀取程序參數。"""

from __future__ import annotations

import argparse
import errno
import json
import os
import time
from itertools import islice
from pathlib import Path

# The scan budget bounds the cost; these caps only bound memory and output.
# A full desktop (about 350 own processes, 13 500 descriptors) scans in about
# 30 ms, so the per-process and total descriptor caps sit well above it.
MAX_PROCESSES = 512
MAX_FDS_PER_PROCESS = 1024
MAX_FDS = 16_384
MAX_CLIENTS = 64


def sample_gpu(proc: Path, previous: dict, now_ns: int,
               budget_ns: int = 100_000_000) -> tuple[dict, dict]:
    deadline = time.monotonic_ns() + budget_ns
    report = {"status": "ok", "truncated": False, "unavailable": 0, "protected": 0,
              "clients": [], "idle": []}
    clients: dict[str, dict] = {}
    identities: dict[str, set[str]] = {}
    unsupported: dict[str, list[str]] = {}
    idle: list[str] = []
    scanned_fds = 0
    uid = os.getuid()
    processes = []
    try:
        with os.scandir(proc) as entries:
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                # Other users' processes (kernel threads, system daemons) are
                # unreadable by design; they are not a failed read of ours.
                try:
                    if entry.stat().st_uid != uid:
                        continue
                except OSError:
                    continue
                processes.append((int(entry.name), entry.path))
    except OSError:
        report["status"] = "unavailable"
        return report, {"time_ns": now_ns, "clients": {}}
    def is_protected(error: OSError) -> bool:
        # A process that exited mid-scan is gone, not missing data. EACCES on
        # one's own process means it made itself non-dumpable (browser
        # sandboxes, keyrings): unreadable by design, counted on its own.
        if error.errno == errno.EACCES:
            return True
        if error.errno not in (errno.ENOENT, errno.ESRCH):
            report["unavailable"] += 1
        return False

    # Newest first, so a cap never hides the program that was just started.
    for index, (pid, process) in enumerate(sorted(processes, reverse=True)):
        if index >= MAX_PROCESSES or time.monotonic_ns() >= deadline or scanned_fds >= MAX_FDS:
            report["truncated"] = True
            break
        protected = False
        try:
            with open(f"{process}/stat", "rb") as handle:
                start = handle.read().decode(errors="replace").rsplit(")", 1)[1].split()[19]
            identity = f"{pid}:{start}"
            # comm is cut at 15 bytes, often inside a multi-byte character.
            with open(f"{process}/comm", "rb") as handle:
                name = handle.read().decode(errors="replace")[:32].strip()
            name = name.replace("\t", " ").replace("\n", " ")
            with os.scandir(f"{process}/fd") as entries:
                descriptors = [(entry.name, entry.path) for entry in islice(entries, MAX_FDS_PER_PROCESS + 1)]
        except IndexError:
            report["unavailable"] += 1
            continue
        except OSError as error:
            report["protected"] += is_protected(error)
            continue
        for fd_index, (fd_name, fd_path) in enumerate(descriptors):
            if fd_index >= MAX_FDS_PER_PROCESS or scanned_fds >= MAX_FDS or time.monotonic_ns() >= deadline:
                report["truncated"] = True
                break
            scanned_fds += 1
            try:
                device = os.readlink(fd_path)
            except OSError as error:
                protected = is_protected(error) or protected
                continue
            if not (device.startswith("/dev/dri/") or device.startswith("/dev/nvidia")):
                continue
            # The descriptor is known to be a GPU; failing to read its usage is
            # a real gap in the data, whatever the reason.
            try:
                with open(f"{process}/fdinfo/{fd_name}") as handle:
                    text = handle.read(16_384)
            except OSError:
                report["unavailable"] += 1
                continue
            fields = dict(line.split(":", 1) for line in text.splitlines() if ":" in line)
            fields = {key: value.strip() for key, value in fields.items()}
            driver = fields.get("drm-driver") or ("nvidia" if device.startswith("/dev/nvidia") else "unsupported")
            client_id = fields.get("drm-client-id", "")
            if not client_id.isdigit():
                # Without a client id (NVIDIA's proprietary driver) descriptors
                # cannot be told apart or measured; list the holder by name.
                names = unsupported.setdefault(driver, [])
                if name not in names:
                    names.append(name)
                continue
            device_id = fields.get("drm-pdev", f"global:{driver}")
            key = f"{device_id}:{client_id}"
            if key not in clients:
                if len(clients) >= MAX_CLIENTS:
                    report["truncated"] = True
                    continue
                engines, capacity = {}, {}
                for field, value in fields.items():
                    if field.startswith("drm-engine-capacity-") and value.isdigit():
                        capacity[field[len("drm-engine-capacity-"):]] = max(1, int(value))
                    elif field.startswith("drm-engine-"):
                        parts = value.split()
                        if len(parts) == 2 and parts[0].isdigit() and parts[1] == "ns" and len(engines) < 8:
                            engines[field[len("drm-engine-"):]] = int(parts[0])
                client_state = "sampled" if engines else "unsupported_counters"
                clients[key] = {"driver": driver, "device": device_id,
                                "client": client_id, "pids": [], "names": [],
                                "counters": engines, "capacity": capacity,
                                "state": client_state}
                identities[key] = set()
            identities[key].add(identity)
            client = clients[key]
            if pid not in client["pids"] and len(client["pids"]) < 4:
                client["pids"].append(pid)
                client["names"].append(name)
        report["protected"] += protected

    elapsed = now_ns - previous.get("time_ns", now_ns)
    state = {"time_ns": now_ns, "clients": {}}
    for key, client in clients.items():
        before = previous.get("clients", {}).get(key, {})
        same_owner = bool(identities[key].intersection(before.get("owners", [])))
        values = {}
        engines = {}
        for engine, value in client.pop("counters").items():
            old_value = before.get("engines", {}).get(engine)
            counter_state = "baseline"
            busy = pct = None
            if same_owner and elapsed > 0 and old_value is not None and client["state"] == "sampled":
                if value < old_value:
                    counter_state = "counter_regressed"
                    value = old_value
                else:
                    counter_state = "sampled"
                    busy = value - old_value
                    pct = round(100 * busy / elapsed / client["capacity"].get(engine, 1), 2)
            values[engine] = value
            engines[engine] = {"busy_ns": busy, "pct": pct, "state": counter_state}
        client.pop("capacity")
        state["clients"][key] = {"owners": sorted(identities[key]), "engines": values}
        # Compact row: a measured engine is its percentage, an unmeasured one
        # its state; idle engines are left out, and holders with no activity
        # or no counters are listed by name only, because this JSON lands in
        # every sample row.
        if client["state"] == "unsupported_counters":
            names = unsupported.setdefault(client["driver"], [])
            names.extend(name for name in client["names"] if name not in names)
            continue
        readings = {}
        for engine, reading in engines.items():
            if reading["state"] != "sampled":
                readings[engine] = reading["state"]
            elif reading["pct"]:
                readings[engine] = reading["pct"]
        if not readings:
            idle.extend(name for name in client["names"] if name not in idle)
            continue
        client["engines"] = readings
        report["clients"].append(client)
    # A program with one busy client and another idle one is busy; one whose
    # other device cannot be measured is unknown, not idle.
    active = {name for client in report["clients"] for name in client["names"]}
    active.update(name for names in unsupported.values() for name in names)
    report["idle"] = [name for name in idle if name not in active]
    report["unsupported"] = unsupported
    if report["unavailable"] or report["truncated"]:
        report["status"] = "partial"
    return report, state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"))
    args = parser.parse_args()
    os.umask(0o077)
    try:
        previous = json.loads(args.state.read_text())
    except (OSError, ValueError):
        previous = {}
    if previous.get("session") != args.session:
        previous = {}
    report, state = sample_gpu(args.proc_root, previous, time.monotonic_ns())
    state["session"] = args.session
    temporary = args.state.with_suffix(".new")
    try:
        temporary.write_text(json.dumps(state, separators=(",", ":")))
        temporary.replace(args.state)
    except OSError:
        report["status"] = "state_unavailable"
    print(json.dumps(report, separators=(",", ":")))


if __name__ == "__main__":
    main()
