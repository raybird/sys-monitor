from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "freeze_watch", REPO_ROOT / "src" / "freeze_watch.py"
)
assert SPEC and SPEC.loader
freeze_watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze_watch)


class FreezeWatchDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_state_dir = freeze_watch.STATE_DIR
        freeze_watch.STATE_DIR = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        freeze_watch.STATE_DIR = self.old_state_dir
        self.temp_dir.cleanup()

    def test_temperature_levels(self) -> None:
        self.assertEqual(
            freeze_watch.temperature_level({"cpu": 55.0, "gpu": 50.0}), "safe"
        )
        self.assertEqual(
            freeze_watch.temperature_level({"cpu": 72.0, "gpu": 50.0}), "warm"
        )
        self.assertEqual(
            freeze_watch.temperature_level({"cpu": 88.0, "gpu": 50.0}), "hot"
        )
        self.assertEqual(
            freeze_watch.temperature_level({"cpu": 96.0, "gpu": 50.0}), "danger"
        )

    def test_reads_latest_metrics_row(self) -> None:
        path = freeze_watch.STATE_DIR / "metrics-test.tsv"
        first = {field: "NA" for field in freeze_watch.METRICS_FIELDS}
        second = dict(first)
        first.update({"timestamp": "2026-01-01T00:00:00+00:00", "cpu_temp_mC": "51000"})
        second.update({"timestamp": "2026-01-01T00:00:10+00:00", "cpu_temp_mC": "52000"})
        lines = [
            "\t".join(freeze_watch.METRICS_FIELDS),
            "\t".join(first[field] for field in freeze_watch.METRICS_FIELDS),
            "\t".join(second[field] for field in freeze_watch.METRICS_FIELDS),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        rows = freeze_watch.read_tsv_tail("metrics-*.tsv", freeze_watch.METRICS_FIELDS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["cpu_temp_mC"], "52000")

    def test_formats_missing_values(self) -> None:
        self.assertEqual(freeze_watch.format_temperature(None), "—")
        self.assertEqual(freeze_watch.format_gib(None), "—")


class IncidentTests(unittest.TestCase):
    """Finding an incident and the samples that led to it."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state = Path(self.temp_dir.name)
        self.old_state_dir = freeze_watch.STATE_DIR
        freeze_watch.STATE_DIR = self.state

    def tearDown(self) -> None:
        freeze_watch.STATE_DIR = self.old_state_dir
        self.temp_dir.cleanup()

    def write_metrics(self, name: str, start_epoch: int, count: int) -> Path:
        path = self.state / name
        lines = ["\t".join(freeze_watch.METRICS_FIELDS)]
        for index in range(count):
            row = {field: "NA" for field in freeze_watch.METRICS_FIELDS}
            epoch = start_epoch + index * 10
            row["timestamp"] = datetime.fromtimestamp(epoch).isoformat()
            row["epoch"] = str(epoch)
            row["cpu_temp_mC"] = str(50000 + index * 100)
            lines.append("\t".join(row[field] for field in freeze_watch.METRICS_FIELDS))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def write_events(self, *lines: str) -> None:
        (self.state / "events.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def test_reads_a_freeze_and_the_file_it_names(self) -> None:
        metrics = self.write_metrics("metrics-old.tsv", 1_700_000_000, 5)
        self.write_events(
            f"2026-08-09T03:14:22+08:00\tFREEZE\tcut off; metrics={metrics} more=1",
            "2026-08-09T03:15:00+08:00\tINFO\tDocker monitor state: ok",
        )

        incidents = freeze_watch.read_incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].kind, "FREEZE")
        self.assertEqual(incidents[0].metrics_path, metrics)

    def test_finds_the_file_covering_a_stall(self) -> None:
        self.write_metrics("metrics-a.tsv", 1_700_000_000, 5)
        wanted = self.write_metrics("metrics-b.tsv", 1_700_010_000, 5)
        moment = datetime.fromtimestamp(1_700_010_020).isoformat()
        self.write_events(f"{moment}\tGAP\tsampling stalled for 47s, expected 10s")

        incidents = freeze_watch.read_incidents()
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].metrics_path, wanted)

    def test_returns_only_the_window_before_the_incident(self) -> None:
        # Two hours of samples, so most of them fall outside the window.
        metrics = self.write_metrics("metrics-long.tsv", 1_700_000_000, 720)
        end = 1_700_000_000 + 400 * 10
        moment = datetime.fromtimestamp(end).isoformat()
        self.write_events(f"{moment}\tFREEZE\tcut off; metrics={metrics}")

        rows = freeze_watch.incident_rows(freeze_watch.read_incidents()[0])
        epochs = [int(row["epoch"]) for row in rows]
        self.assertLessEqual(max(epochs), end)
        self.assertGreaterEqual(min(epochs), end - freeze_watch.INCIDENT_WINDOW_SECONDS)

    def test_newest_incident_comes_first(self) -> None:
        self.write_events(
            "2026-08-09T01:00:00+08:00\tGAP\tearlier",
            "2026-08-09T05:00:00+08:00\tFREEZE\tlater",
        )
        self.assertEqual(
            [incident.timestamp for incident in freeze_watch.read_incidents()],
            ["2026-08-09T05:00:00+08:00", "2026-08-09T01:00:00+08:00"],
        )

    def test_ignores_routine_entries(self) -> None:
        self.write_events(
            "2026-08-09T01:00:00+08:00\tSTART\tboot=x metrics=y",
            "2026-08-09T01:00:01+08:00\tINFO\tDocker monitor state: ok",
            "2026-08-09T01:00:02+08:00\tROTATE\tmetrics=y docker=z",
        )
        self.assertEqual(freeze_watch.read_incidents(), [])

    def test_derives_the_docker_path_from_the_metrics_path(self) -> None:
        self.assertEqual(
            freeze_watch.docker_path_for(Path("/s/metrics-2026-08-09T10-00-00-ab.tsv")),
            Path("/s/docker-2026-08-09T10-00-00-ab.tsv"),
        )
        self.assertIsNone(freeze_watch.docker_path_for(None))


class StallPositionTests(unittest.TestCase):
    """Stalls are derived from the samples, not from a separate log."""

    @staticmethod
    def rows(*epochs: int) -> list[dict[str, str]]:
        return [{"epoch": str(epoch)} for epoch in epochs]

    def test_marks_a_late_sample(self) -> None:
        self.assertEqual(
            freeze_watch.stall_positions(self.rows(0, 10, 20, 90, 100)), [3]
        )

    def test_leaves_regular_sampling_unmarked(self) -> None:
        self.assertEqual(freeze_watch.stall_positions(self.rows(0, 10, 20, 30)), [])

    def test_handles_too_few_samples(self) -> None:
        self.assertEqual(freeze_watch.stall_positions(self.rows(0)), [])
        self.assertEqual(freeze_watch.stall_positions([]), [])


class HwmonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.old_root = freeze_watch.HWMON_ROOT
        freeze_watch.HWMON_ROOT = self.root

    def tearDown(self) -> None:
        freeze_watch.HWMON_ROOT = self.old_root
        self.temp_dir.cleanup()

    def add_device(self, index: int, name: str, milli_celsius: int) -> None:
        device = self.root / f"hwmon{index}"
        device.mkdir()
        (device / "name").write_text(f"{name}\n", encoding="utf-8")
        (device / "temp1_input").write_text(f"{milli_celsius}\n", encoding="utf-8")

    def test_reads_intel_package_sensor(self) -> None:
        self.add_device(0, "acpitz", 27800)
        self.add_device(1, "coretemp", 49000)
        self.assertEqual(
            freeze_watch.read_hwmon_temperature(*freeze_watch.CPU_TEMP_SENSORS), 49.0
        )

    def test_prefers_earlier_candidate_over_lower_device_number(self) -> None:
        self.add_device(0, "coretemp", 49000)
        self.add_device(1, "k10temp", 61000)
        self.assertEqual(
            freeze_watch.read_hwmon_temperature(*freeze_watch.CPU_TEMP_SENSORS), 61.0
        )

    def test_ignores_unrecognised_devices(self) -> None:
        self.add_device(0, "acpitz", 27800)
        self.assertIsNone(
            freeze_watch.read_hwmon_temperature(*freeze_watch.CPU_TEMP_SENSORS)
        )

    def test_sensor_lists_match_the_collector(self) -> None:
        lines = (
            (REPO_ROOT / "src" / "freeze-monitor")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        for variable, names in (
            ("cpu_temp_sensors", freeze_watch.CPU_TEMP_SENSORS),
            ("gpu_temp_sensors", freeze_watch.GPU_TEMP_SENSORS),
        ):
            declared = [
                line for line in lines if line.startswith(f"readonly {variable}=")
            ]
            self.assertEqual(
                declared,
                [f"readonly {variable}=({' '.join(names)})"],
                f"{variable} has drifted from the dashboard",
            )


if __name__ == "__main__":
    unittest.main()
