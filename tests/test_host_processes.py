from __future__ import annotations

import csv
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HostProcessTests(unittest.TestCase):
    def test_rankings_exclude_only_the_sampling_ps_and_still_fill_five_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ps = root / "ps"
            ps.write_text('''#!/usr/bin/python3
import os
import sys

args = sys.argv[1:]
if "stat=" in args:
    print("S")
    raise SystemExit
own_pid = os.getpid()
rows = [(own_pid, "ps", 400.0, 80.0),
        (own_pid + 1, "ps", 250.0, 70.0)]
rows += [(own_pid + n + 2, f"worker{n}", 100.0 - n, 60.0 - n)
         for n in range(6)]
if "--pid" in args and "--deselect" in args and "-eo" not in args:
    excluded = int(args[args.index("--pid") + 1])
    rows = [row for row in rows if row[0] != excluded]
column = 3 if "--sort=-%mem" in args else 2
for _, name, cpu, memory in sorted(rows, key=lambda row: row[column], reverse=True):
    print(f"{name} {cpu} {memory}")
''')
            ps.chmod(0o755)
            env = dict(os.environ, XDG_STATE_HOME=directory,
                       FREEZE_WATCH_MAX_SAMPLES="1", FREEZE_WATCH_COMPOSE_PROJECT="",
                       FREEZE_WATCH_JOURNALCTL="/bin/false", FREEZE_WATCH_GPU_PROCESSES="0",
                       FREEZE_WATCH_PS=str(ps), DOCKER_HOST="unix:///nonexistent")
            result = subprocess.run([str(ROOT / "src/freeze-monitor")], env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = next((root / "freeze-monitor").glob("metrics-*.tsv"))
            with metrics.open() as handle:
                row = next(csv.DictReader(handle, delimiter="\t"))
            for field in ("top_processes", "top_memory_processes"):
                with self.subTest(field=field):
                    self.assertEqual(row[field].split(";"), [
                        "ps 250.0 70.0", "worker0 100.0 60.0", "worker1 99.0 59.0",
                        "worker2 98.0 58.0", "worker3 97.0 57.0",
                    ])


if __name__ == "__main__":
    unittest.main()
