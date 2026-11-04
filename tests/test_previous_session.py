from __future__ import annotations

import os
import csv
import json
import re
import subprocess
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PreviousSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / "freeze-monitor"
        self.state.mkdir()
        self.events = self.state / "events.log"
        self.boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()

    def tearDown(self):
        self.temp.cleanup()

    def metrics(self, name, epoch=None):
        path = self.state / f"metrics-{name}.tsv"
        text = "timestamp\tepoch\tuptime_s\n"
        if epoch is not None:
            text += f"{datetime.fromtimestamp(epoch).astimezone().isoformat()}\t{epoch}\t10\n"
        path.write_text(text)
        return path

    def seed(self, start, rotations=(), boot="other-boot", stop=False):
        lines = [f"2026-10-05T00:00:00+08:00\tSTART\tboot={boot} metrics={start}"]
        lines.extend(f"2026-10-05T00:01:00+08:00\tROTATE\tmetrics={path} docker=unused" for path in rotations)
        if stop:
            lines.append("2026-10-05T00:02:00+08:00\tSTOP\tmonitor stopped")
        self.events.write_text("\n".join(lines) + "\n")

    def run_collector(self, **extra):
        env = dict(os.environ, XDG_STATE_HOME=self.temp.name,
                   FREEZE_WATCH_MAX_SAMPLES="1", FREEZE_WATCH_COMPOSE_PROJECT="",
                   FREEZE_WATCH_JOURNALCTL="/bin/false", FREEZE_WATCH_GPU_PROCESSES="0")
        env.update(extra)
        result = subprocess.run([str(ROOT / "src/freeze-monitor")], env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [line.split("\t", 2) for line in self.events.read_text().splitlines()
                if "\tFREEZE\t" in line or "\tUNCLEAN\t" in line or "\tINTERRUPTED\t" in line]

    def test_scn002_multiple_rotations_use_latest_sample(self):
        first = self.metrics("first", 1700000000)
        second = self.metrics("second", 1700086400)
        latest = self.metrics("latest", 1700172800)
        self.seed(first, [second, latest])
        started = int(time.time())
        records = self.run_collector()
        finished = int(time.time())
        self.assertEqual(len(records), 1)
        stamp, _, message = records[0]
        self.assertIn(f"metrics={latest}", message)
        self.assertIn("last_sample=" + datetime.fromtimestamp(1700172800).astimezone().isoformat(), message)
        silence = int(re.search(r"silent_for=(\d+)s", message).group(1))
        self.assertGreaterEqual(silence, started - 1700172800)
        self.assertLessEqual(silence, finished - 1700172800)

    def test_scn003_empty_missing_and_invalid_rotations_fall_back(self):
        first = self.metrics("first", 1700000000)
        valid = self.metrics("valid", 1700086400)
        empty = self.metrics("empty")
        invalid = self.metrics("invalid")
        invalid.write_text("timestamp\tepoch\tuptime_s\nbroken\tno-epoch\t10\n")
        self.seed(first, [valid, empty, self.state / "missing.tsv", invalid])
        message = self.run_collector()[0][2]
        self.assertIn(f"metrics={valid}", message)

    def test_scn003_no_samples_are_unknown(self):
        self.seed(self.metrics("empty"))
        message = self.run_collector()[0][2]
        self.assertIn("last_sample=unknown", message)
        self.assertNotIn("silent_for=", message)

    def test_scn003_stop_does_not_report_an_incident(self):
        self.seed(self.metrics("first", 1700000000), stop=True)
        self.assertEqual(self.run_collector(), [])

    def test_scn003_does_not_borrow_a_previous_session_rotation(self):
        old = self.metrics("old", 1700172800)
        current = self.metrics("current", 1700000000)
        self.seed(old, [old], stop=True)
        with self.events.open("a") as handle:
            handle.write(f"2026-10-05T00:03:00+08:00\tSTART\tboot=other-boot metrics={current}\n")
        message = self.run_collector()[0][2]
        self.assertIn(f"metrics={current}", message)
        self.assertNotIn(str(old), message)

    def test_scn003_session_without_samples_does_not_borrow_an_earlier_session(self):
        old = self.metrics("old", 1700172800)
        current = self.metrics("current")
        self.seed(old, stop=True)
        with self.events.open("a") as handle:
            handle.write(f"2026-10-05T00:03:00+08:00\tSTART\tboot=other-boot metrics={current}\n")
        message = self.run_collector()[0][2]
        self.assertIn("last_sample=unknown", message)
        self.assertNotIn(str(old), message)
        self.assertNotIn(datetime.fromtimestamp(1700172800).astimezone().isoformat(), message)

    def test_scn004_different_boot_reports_uncertainty(self):
        self.seed(self.metrics("first", 1700000000))
        record = self.run_collector()[0]
        self.assertEqual(record[1], "UNCLEAN")
        self.assertIn("cause=unknown", record[2])

    def test_scn004_same_boot_is_collector_interruption(self):
        self.seed(self.metrics("first", 1700000000), boot=self.boot)
        self.assertEqual(self.run_collector()[0][1], "INTERRUPTED")

    def test_scn005_opt_in_is_recorded_and_counter_state_is_private(self):
        proc = Path(self.temp.name) / "proc/123"
        (proc / "fd").mkdir(parents=True)
        (proc / "fdinfo").mkdir()
        (proc / "stat").write_text("123 (gpu) S " + "0 " * 18 + "50")
        (proc / "comm").write_text("gpu-owner\n")
        (proc / "fd/4").symlink_to("/dev/dri/renderD128")
        (proc / "fdinfo/4").write_text("drm-driver: amdgpu\ndrm-client-id: 7\ndrm-engine-render: 100 ns\n")
        self.run_collector(FREEZE_WATCH_GPU_PROCESSES="1",
                           FREEZE_WATCH_GPU_PROC_ROOT=str(proc.parent),
                           FREEZE_WATCH_MAX_SAMPLES="2", FREEZE_WATCH_INTERVAL_SECONDS="1")
        metrics = next(self.state.glob("metrics-*.tsv"))
        with metrics.open() as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        data = json.loads(rows[-1]["gpu_processes"])
        self.assertEqual(data["clients"], [])
        self.assertEqual(data["idle"], ["gpu-owner"])
        self.assertEqual((self.state / "gpu-counters.json").stat().st_mode & 0o777, 0o600)

    def test_scn005_disabled_has_no_scan_state(self):
        self.run_collector()
        self.assertFalse((self.state / "gpu-counters.json").exists())
        with next(self.state.glob("metrics-*.tsv")).open() as handle:
            row = next(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(row["gpu_processes"], "disabled")


if __name__ == "__main__":
    unittest.main()
