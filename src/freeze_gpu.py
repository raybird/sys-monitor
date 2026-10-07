#!/usr/bin/env python3
"""可選的 DRM fdinfo 採樣，限制掃描成本且不讀取程序參數。"""

from __future__ import annotations

import argparse
import json
import os
import time
from itertools import islice
from pathlib import Path


def sample_gpu(proc: Path, previous: dict, now_ns: int,
               budget_ns: int = 100_000_000) -> tuple[dict, dict]:
    deadline = time.monotonic_ns() + budget_ns
    report = {"status": "ok", "truncated": False, "unavailable": 0, "clients": []}
    clients: dict[str, dict] = {}
    identities: dict[str, set[str]] = {}
    scanned_fds = 0
    try:
        with os.scandir(proc) as entries:
            processes = [Path(entry.path) for entry in islice((e for e in entries if e.name.isdigit()), 513)]
    except OSError:
        report["status"] = "unavailable"
        return report, {"time_ns": now_ns, "clients": {}}
    for index, process in enumerate(sorted(processes, key=lambda p: int(p.name))):
        if index >= 512 or time.monotonic_ns() >= deadline or scanned_fds >= 2048:
            report["truncated"] = True
            break
        try:
            start = process.joinpath("stat").read_text().rsplit(")", 1)[1].split()[19]
            identity = f"{process.name}:{start}"
            name = process.joinpath("comm").read_text()[:32].strip().replace("\t", " ").replace("\n", " ")
            with os.scandir(process / "fd") as entries:
                descriptors = [Path(entry.path) for entry in islice(entries, 65)]
        except (OSError, IndexError):
            report["unavailable"] += 1
            continue
        for fd_index, fd in enumerate(descriptors):
            if fd_index >= 64 or scanned_fds >= 2048 or time.monotonic_ns() >= deadline:
                report["truncated"] = True
                break
            scanned_fds += 1
            try:
                device = os.readlink(fd)
                if not (device.startswith("/dev/dri/") or device.startswith("/dev/nvidia")):
                    continue
                with process.joinpath("fdinfo", fd.name).open() as handle:
                    text = handle.read(16_384)
            except OSError:
                report["unavailable"] += 1
                continue
            fields = dict(line.split(":", 1) for line in text.splitlines() if ":" in line)
            fields = {key: value.strip() for key, value in fields.items()}
            driver = fields.get("drm-driver", "unsupported")
            client_id = fields.get("drm-client-id", "")
            device_id = fields.get("drm-pdev", f"global:{driver}")
            key = f"{device_id}:{client_id}" if client_id.isdigit() else f"unknown:{identity}:{fd.name}"
            if key not in clients:
                if len(clients) >= 16:
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
                if not client_id.isdigit():
                    client_state = "unsupported_identity"
                elif not engines:
                    client_state = "unsupported_counters"
                else:
                    client_state = "sampled"
                clients[key] = {"driver": driver, "device": device_id,
                                "client": client_id, "pids": [], "names": [],
                                "counters": engines, "capacity": capacity,
                                "state": client_state}
                identities[key] = set()
            identities[key].add(identity)
            client = clients[key]
            pid = int(process.name)
            if pid not in client["pids"] and len(client["pids"]) < 4:
                client["pids"].append(pid)
                client["names"].append(name)

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
        client["engines"] = engines
        report["clients"].append(client)
        state["clients"][key] = {"owners": sorted(identities[key]), "engines": values}
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
