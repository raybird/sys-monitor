from __future__ import annotations

import importlib.util
import tempfile
import unittest
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
