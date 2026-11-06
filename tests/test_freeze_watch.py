from __future__ import annotations

import importlib.util
import json
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

    def test_reads_a_file_written_before_the_newest_columns(self) -> None:
        """Columns are appended, so an older file just stops short of them."""
        older_fields = freeze_watch.METRICS_FIELDS[
            : freeze_watch.METRICS_FIELDS.index("top_processes") + 1
        ]
        row = {field: "NA" for field in older_fields}
        row.update({"timestamp": "2026-01-01T00:00:00+00:00", "cpu_temp_mC": "51000"})
        path = freeze_watch.STATE_DIR / "metrics-older.tsv"
        path.write_text(
            "\t".join(older_fields)
            + "\n"
            + "\t".join(row[field] for field in older_fields)
            + "\n",
            encoding="utf-8",
        )

        rows = freeze_watch.read_tsv_tail("metrics-*.tsv", freeze_watch.METRICS_FIELDS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cpu_temp_mC"], "51000")
        # Absent rather than None, so the dashboard renders it as missing data.
        self.assertEqual(rows[0]["dstate_count"], "NA")
        self.assertEqual(rows[0]["io_psi_full_avg10"], "NA")


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

    def write_metrics(self, name: str, start_epoch: int, count: int, pad: int = 0) -> Path:
        path = self.state / name
        lines = ["\t".join(freeze_watch.METRICS_FIELDS)]
        for index in range(count):
            row = {field: "NA" for field in freeze_watch.METRICS_FIELDS}
            epoch = start_epoch + index * 10
            row["timestamp"] = datetime.fromtimestamp(epoch).isoformat()
            row["epoch"] = str(epoch)
            row["cpu_temp_mC"] = str(50000 + index * 100)
            if pad:
                # Uneven widths, like real GPU JSON, so a byte cut lands mid-row.
                row["gpu_processes"] = "g" * (pad + index % 97)
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

    def test_scn004_old_and_new_unclean_events_use_uncertain_labels(self):
        for kind in ("FREEZE", "UNCLEAN"):
            incident = freeze_watch.Incident("2026-10-05T00:00:00+00:00", kind, "", None)
            self.assertIn("疑似當機", incident.label)

    def test_scn002_review_anchors_on_last_sample_and_crosses_rotation(self):
        first = self.write_metrics("metrics-first.tsv", 1700000000, 3)
        second = self.write_metrics("metrics-second.tsv", 1700000030, 3)
        last = datetime.fromtimestamp(1700000050).isoformat()
        restart = datetime.fromtimestamp(1700100000).isoformat()
        self.write_events(
            f"{last}\tSTART\tboot=old metrics={first}",
            f"{last}\tROTATE\tmetrics={second}",
            f"{restart}\tUNCLEAN\tlast_sample={last} metrics={second}",
        )
        incidents = freeze_watch.read_incidents()
        self.assertEqual(len(incidents), 1)
        rows = freeze_watch.incident_rows(incidents[0])
        self.assertEqual([int(row["epoch"]) for row in rows],
                         [1700000000, 1700000010, 1700000020, 1700000030, 1700000040, 1700000050])

    def test_scn006_old_stall_still_has_data_after_the_file_grows(self):
        metrics = self.write_metrics("metrics-grown.tsv", 1700000000, 40000)
        stamp = datetime.fromtimestamp(1700001000).isoformat()
        self.write_events(f"{stamp}\tGAP\tsampling stalled")
        incident = freeze_watch.read_incidents()[0]
        self.assertEqual(incident.metrics_path, metrics)
        rows = freeze_watch.incident_rows(incident)
        self.assertEqual(int(rows[0]["epoch"]), 1700000000)
        self.assertEqual(int(rows[-1]["epoch"]), 1700001000)
        report = freeze_watch.diagnostic_report(incident)
        self.assertIn("\t50000.0\t", report)
        self.assertIn("\t63000.0\t", report)
        self.assertNotIn("\t63100.0\t", report)


    def test_review_survives_a_tail_cut_inside_a_row(self):
        metrics = self.write_metrics("metrics-ragged.tsv", 1700000000, 2000, pad=4400)
        data = metrics.read_bytes()
        self.assertNotEqual(data[len(data) - 4_000_000 - 1:len(data) - 4_000_000], b"\n")
        stamp = datetime.fromtimestamp(1700003000).isoformat()
        self.write_events(f"{stamp}\tGAP\tsampling stalled")
        incident = freeze_watch.read_incidents()[0]
        rows = freeze_watch.incident_rows(incident)
        self.assertEqual(len(rows), 181)
        self.assertEqual(int(rows[0]["epoch"]), 1700001200)
        self.assertEqual(int(rows[-1]["epoch"]), 1700003000)

    def test_live_tail_keeps_half_an_hour_of_wide_rows(self):
        self.write_metrics("metrics-wide.tsv", 1700000000, 360, pad=4400)
        rows = freeze_watch.read_tsv_tail("metrics-*.tsv", freeze_watch.METRICS_FIELDS)
        self.assertGreaterEqual(len(rows), 180)
        self.assertTrue(all(row["epoch"].isdigit() for row in rows))
        self.assertEqual(int(rows[-1]["epoch"]), 1700003590)

    def test_invalid_bytes_do_not_stop_the_review(self):
        metrics = self.write_metrics("metrics-bad.tsv", 1700000000, 200)
        with metrics.open("ab") as handle:
            handle.write(b"\xff\xfe broken\n")
        stamp = datetime.fromtimestamp(1700001000).isoformat()
        self.write_events(f"{stamp}\tGAP\tsampling stalled")
        incident = freeze_watch.read_incidents()[0]
        self.assertEqual(incident.metrics_path, metrics)
        self.assertTrue(freeze_watch.incident_rows(incident))
        self.assertIn("\t60000.0\t", freeze_watch.diagnostic_report(incident))


class GpuSummaryTests(unittest.TestCase):
    def test_activity_unmeasured_engines_and_idle_holders_read_apart(self):
        raw = json.dumps({
            "status": "ok", "truncated": False, "unavailable": 0,
            "clients": [
                {"driver": "i915", "device": "0000:00:02.0", "client": "21", "pids": [6926],
                 "names": ["gnome-shell"], "state": "sampled",
                 "engines": {"render": 1.66, "video": "baseline"}},
            ],
            "idle": ["Xwayland"], "unsupported": {"nvidia": ["game", "Xorg"]}, "protected": 3,
        })
        text = freeze_watch.gpu_summary(raw)
        self.assertIn("6926 gnome-shell · i915 · render 1.66%, video 活動未知", text)
        self.assertIn("nvidia 計數器不支援，僅確認持有裝置：game, Xorg", text)
        self.assertIn("持有裝置、取樣期間無活動：Xwayland", text)
        self.assertIn("3 個受保護的程序無法檢查", text)
        self.assertNotIn("不完整", text)
        self.assertEqual(freeze_watch.gpu_summary("[]"), "GPU 程序資料無法讀取")


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


class SystemMetricLevelTests(unittest.TestCase):
    def test_memory_levels(self) -> None:
        self.assertEqual(freeze_watch.memory_level(8 * 1024 * 1024, 0), "safe")
        self.assertEqual(freeze_watch.memory_level(1500 * 1024, 0), "warm")
        self.assertEqual(freeze_watch.memory_level(800 * 1024, 0), "hot")
        self.assertEqual(freeze_watch.memory_level(300 * 1024, 0), "danger")
        self.assertEqual(freeze_watch.memory_level(8 * 1024 * 1024, 12000), "danger")

    def test_load_levels(self) -> None:
        self.assertEqual(freeze_watch.load_level(1.5, 0, cpu_count=8), "safe")
        self.assertEqual(freeze_watch.load_level(1.5, 1, cpu_count=8), "warm")
        self.assertEqual(freeze_watch.load_level(1.5, 4, cpu_count=8), "hot")
        self.assertEqual(freeze_watch.load_level(1.5, 8, cpu_count=8), "danger")
        self.assertEqual(freeze_watch.load_level(12.0, 0, cpu_count=8), "hot")

    def test_pressure_levels(self) -> None:
        self.assertEqual(freeze_watch.pressure_level(0.0, 0.0, 0.0), "safe")
        self.assertEqual(freeze_watch.pressure_level(6.0, 0.0, 0.0), "warm")
        self.assertEqual(freeze_watch.pressure_level(22.0, 0.0, 0.0), "hot")
        self.assertEqual(freeze_watch.pressure_level(5.0, 12.0, 0.0), "danger")

    def test_disk_levels(self) -> None:
        self.assertEqual(freeze_watch.disk_level(60.0, 0, 100.0, 10), "safe")
        self.assertEqual(freeze_watch.disk_level(86.0, 0, 100.0, 10), "warm")
        self.assertEqual(freeze_watch.disk_level(60.0, 0, 8000.0, 10), "hot")
        self.assertEqual(freeze_watch.disk_level(96.0, 0, 100.0, 10), "danger")

    def test_process_parsing_and_formatting(self) -> None:
        raw = "opencode 75.1 1.7;Web Content 12.0 4.5"
        self.assertEqual(
            freeze_watch.parse_process_entries(raw),
            [
                ("opencode", "75.1%", "1.7%"),
                ("Web Content", "12.0%", "4.5%"),
            ],
        )
        self.assertIn("CPU 75.1%", freeze_watch.format_process_listing(raw))
        self.assertEqual(freeze_watch.format_process_listing("NA"), "尚無程序資料")

    def test_ribbon_tooltip_and_incident_summary(self) -> None:
        tooltip = freeze_watch.ribbon_sample_tooltip(
            {"timestamp": "2026-10-23T07:00:00+08:00", "cpu": 65.0, "gpu": 55.0, "nvme": 42.0},
            stalled=True,
        )
        self.assertIn("2026-10-23 07:00:00", tooltip)
        self.assertIn("採樣停擺", tooltip)
        self.assertIn("CPU 65°C", tooltip)

        freeze_inc = freeze_watch.Incident(
            "2026-10-23T06:29:52+08:00",
            "FREEZE",
            "previous session ended without shutting down; last_sample=2026-10-22T22:04:49+08:00 silent_for=30303s metrics=/tmp/m.tsv",
            None,
        )
        summary = freeze_watch.format_incident_summary(freeze_inc)
        self.assertIn("最後取樣 2026-10-22 22:04:49", summary)
        self.assertIn("中斷 30303s", summary)
        self.assertIn("原因未確認", summary)
        self.assertNotIn("凍結", summary)


if __name__ == "__main__":
    unittest.main()

class ContainerEvidenceTests(unittest.TestCase):
    def test_snapshot_does_not_resurrect_stopped_containers(self):
        rows = [{'timestamp': 'a', 'container': 'worker'}, {'timestamp': 'b', 'container': '', 'sample_status': 'empty'}]
        self.assertEqual(freeze_watch.latest_containers(rows), [])

    def test_details_align_host_without_using_future_samples(self):
        row = {'epoch': '100', 'timestamp': 'then', 'container': 'worker', 'process_sample': '[{"pid":"5","name":"worker","state":"D","cpu":1,"memory":2}]', 'process_status': 'ok'}
        text = freeze_watch.container_detail(row, [{'epoch': '99', 'cpu_temp_mC': '42000', 'io_psi_avg10': '3'}, {'epoch': '101', 'cpu_temp_mC': '99000'}])
        self.assertIn('42°C', text)
        self.assertNotIn('99°C', text)
        self.assertIn('worker', text)
        self.assertIn('PID 5', text)
        self.assertIn('生命週期平均', text)

    def test_stale_host_data_is_explicit(self):
        text = freeze_watch.container_detail({'epoch': '100'}, [{'epoch': '1', 'cpu_temp_mC': '42000'}])
        self.assertIn('主機資料缺口', text)

    def test_old_and_malformed_process_samples_show_unknown(self):
        self.assertIn('未知', freeze_watch.container_detail({'process_sample': 'broken'}, []))
        self.assertIn('未知', freeze_watch.container_detail({}, []))

class ContainerBackwardCompatibilityTests(unittest.TestCase):
    def test_old_docker_schema_loads_as_unknown_new_fields(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'docker-old.tsv'
            path.write_text('timestamp\tepoch\tcontainer\tis_tracked_project\tcpu_pct\tmemory_usage\ttasks\tprocesses\tzombies\toom_killed\trestart_count\nnow\t100\told\t1\t5%\t1MiB / 2GiB\t2\t1\t0\tfalse\t0\n')
            row = freeze_watch.read_tsv_path(path, freeze_watch.DOCKER_FIELDS)[0]
            self.assertEqual(row['container_id'], 'NA')
            self.assertIn('CPU：5%', freeze_watch.container_detail(row, []))
            self.assertIn('未知', freeze_watch.container_detail(row, []))

    def test_known_anomalies_only_are_flagged(self):
        for key, value in [('oom_killed','true'), ('health','unhealthy'), ('dstate','4'), ('zombies','1')]:
            self.assertTrue(freeze_watch.container_warning({'is_tracked_project': '1', key: value}))
        self.assertFalse(freeze_watch.container_warning({k:'NA' for k in freeze_watch.DOCKER_FIELDS}))

    def test_dstate_uses_host_elevated_threshold(self):
        # 2026-11-06 使用者決定（S3）：容器 D 沿用主機門檻，4 起才醒目。
        self.assertFalse(freeze_watch.container_warning({'is_tracked_project': '1', 'dstate': '3'}))
        self.assertTrue(freeze_watch.container_warning({'is_tracked_project': '1', 'dstate': '4'}))

    def test_untracked_containers_are_never_flagged(self):
        row = {'is_tracked_project': '0', 'oom_killed': 'true', 'health': 'unhealthy', 'dstate': '9', 'restart_count': '5'}
        self.assertFalse(freeze_watch.container_warning(row, {'is_tracked_project': '0', 'restart_count': '1'}))

    def test_restart_flags_only_an_increase_over_previous_sample(self):
        row = {'is_tracked_project': '1', 'restart_count': '2'}
        self.assertFalse(freeze_watch.container_warning(row))
        self.assertFalse(freeze_watch.container_warning(row, {'restart_count': '2'}))
        self.assertFalse(freeze_watch.container_warning(row, {'restart_count': 'NA'}))
        self.assertTrue(freeze_watch.container_warning(row, {'restart_count': '1'}))


class ContainerReviewFollowupTests(unittest.TestCase):
    """2026-11-06 使用者「2. 一起修」：PR #3 審查的 S4、S5、S6、S9、N1。"""

    def test_s9_helper_fields_match_dashboard_fields(self):
        spec = importlib.util.spec_from_file_location("container_probe", REPO_ROOT / "src" / "container_probe.py")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        self.assertEqual(probe.FIELDS, freeze_watch.DOCKER_FIELDS)

    def test_s5_unknown_rows_look_different_from_normal_rows(self):
        normal = {'is_tracked_project': '1', 'container_state': 'running', 'sample_status': 'ok',
                  'cpu_pct': '12.0', 'memory_usage': '300MiB / 2GiB'}
        self.assertEqual(freeze_watch.container_summary(normal), ('running · 12.0% · 300MiB', 'muted'))
        timed_out = dict(normal, sample_status='unavailable_or_timeout', cpu_pct='NA', memory_usage='NA')
        text, css = freeze_watch.container_summary(timed_out)
        self.assertEqual(css, 'unknown')
        self.assertIn('查詢逾時或失敗', text)
        self.assertNotIn('NA', text)
        stopped = dict(normal, container_state='exited', sample_status='stopped', cpu_pct='NA', memory_usage='NA')
        text, css = freeze_watch.container_summary(stopped)
        self.assertEqual(css, 'unknown')
        self.assertIn('已停止', text)
        # A known anomaly still wins over missing load figures.
        self.assertEqual(freeze_watch.container_summary(dict(stopped, oom_killed='true'))[1], 'warm')
        # Running with one figure missing is still unknown, not normal.
        text, css = freeze_watch.container_summary(dict(normal, cpu_pct='NA'))
        self.assertEqual(css, 'unknown')
        self.assertIn('CPU 未知', text)

    def test_s4_docker_state_shows_the_reason(self):
        self.assertEqual(freeze_watch.docker_state_label('ok'), 'ok')
        self.assertEqual(freeze_watch.docker_state_label('unavailable:permission'), '不可用（Docker socket 權限不足）')
        self.assertEqual(freeze_watch.docker_state_label('unavailable:timeout'), '不可用（查詢逾時）')
        self.assertEqual(freeze_watch.docker_state_label('unavailable'), '不可用（原因未記錄）')
        self.assertEqual(freeze_watch.docker_state_label('unavailable:something_new'), '不可用（something_new）')

    def write_docker_file(self, path: Path, rows: int) -> None:
        sample = json.dumps([{'pid': '1', 'state': 'S', 'cpu': 1.0, 'memory': 1.0, 'name': 'x' * 40}] * 8)
        with path.open('w') as handle:
            handle.write('\t'.join(freeze_watch.DOCKER_FIELDS) + '\n')
            for n in range(rows):
                values = dict.fromkeys(freeze_watch.DOCKER_FIELDS, 'NA')
                values.update(timestamp=f't{n}', epoch=str(1000 + n), container='worker',
                              process_sample='"' + sample.replace('"', '""') + '"')
                handle.write('\t'.join(values[key] for key in freeze_watch.DOCKER_FIELDS) + '\n')

    def test_s6_incident_review_finds_rows_before_the_end_anywhere_in_the_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'docker.tsv'
            self.write_docker_file(path, 20_000)
            self.assertGreater(path.stat().st_size, 8_000_000)
            rows = freeze_watch.read_tsv_before(path, freeze_watch.DOCKER_FIELDS, 1000 + 1500, 200_000)
            self.assertEqual(rows[-1]['epoch'], '2500')
            self.assertLess(len(rows), 1501)
            self.assertGreater(len(rows), 100)
            self.assertEqual(int(rows[-1]['epoch']) - int(rows[0]['epoch']), len(rows) - 1)
            # Before the first sample nothing is returned; past the last, the tail.
            self.assertEqual(freeze_watch.read_tsv_before(path, freeze_watch.DOCKER_FIELDS, 999, 200_000), [])
            self.assertEqual(freeze_watch.read_tsv_before(path, freeze_watch.DOCKER_FIELDS, 10**9, 200_000)[-1]['epoch'], str(1000 + 19_999))

    def test_n1_a_cut_inside_a_quoted_field_does_not_swallow_the_next_row(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'docker.tsv'
            self.write_docker_file(path, 50)
            data = path.read_bytes()
            # Cut in the middle of row t10's quoted JSON field; t10 is partial.
            row_starts = [i + 1 for i, byte in enumerate(data) if byte == 0x0A][:-1]
            cut = row_starts[10] + data[row_starts[10]:].index(b'"') + 20
            rows = freeze_watch.read_tsv_path(path, freeze_watch.DOCKER_FIELDS, len(data) - cut)
        self.assertEqual(rows[0]['timestamp'], 't11')
        self.assertEqual(len(rows), 39)
