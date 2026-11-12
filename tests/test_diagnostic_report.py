from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("report_watch", ROOT / "src/freeze_watch.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


class DiagnosticReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = watch.STATE_DIR
        watch.STATE_DIR = Path(self.temp.name)

    def tearDown(self):
        watch.STATE_DIR = self.old
        self.temp.cleanup()

    def test_scn006_sensitive_data_removed_but_diagnostic_values_kept(self):
        path = watch.STATE_DIR / "metrics-secret.tsv"
        row = dict.fromkeys(watch.METRICS_FIELDS, "NA")
        row.update(timestamp="2026-10-05T00:00:00+00:00", epoch="1791158400",
                   cpu_temp_mC="52000", cpu_psi_avg10="1.5",
                   memory_psi_full_avg10="2.5", io_psi_avg10="3.5",
                   top_processes="/home/private/job --password=secret")
        path.write_text("\t".join(watch.METRICS_FIELDS) + "\n" +
                        "\t".join(row[field] for field in watch.METRICS_FIELDS) + "\n")
        (watch.STATE_DIR / "events.log").write_text(
            "2026-10-05T00:00:01+00:00\tKERNEL\tGPU HANG in /home/private/job --password=secret\n")
        incident = watch.Incident(row["timestamp"], "UNCLEAN", f"metrics={path} cause=unknown", path)
        report = watch.diagnostic_report(incident)
        for secret in (str(path), "/home/private", "--password", "secret"):
            self.assertNotIn(secret, report)
        for evidence in ("52000", "1.5", "2.5", "3.5", "GPU HANG"):
            self.assertIn(evidence, report)

    def test_scn006_file_matches_preview_and_is_private(self):
        path = watch.STATE_DIR / "export.txt"
        text = "已遮蔽的預覽\nGPU HANG\n"
        watch.write_diagnostic_report(path, text)
        self.assertEqual(path.read_text(), text)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(OSError):
            watch.write_diagnostic_report(watch.STATE_DIR, text)

    def test_scn006_window_includes_after_rotation_excludes_outside_and_other_session(self):
        def metric(name, epoch, value):
            path = watch.STATE_DIR / name
            row = dict.fromkeys(watch.METRICS_FIELDS, "NA")
            row.update(timestamp="unused", epoch=str(epoch), cpu_temp_mC=str(value))
            path.write_text("\t".join(watch.METRICS_FIELDS) + "\n" +
                            "\t".join(row[field] for field in watch.METRICS_FIELDS) + "\n")
            return path
        before = metric("metrics-before.tsv", 1791158390, 51001)
        after = metric("metrics-after.tsv", 1791158410, 52002)
        outside = metric("metrics-outside.tsv", 1791158701, 53003)
        other = metric("metrics-other.tsv", 1791158401, 54004)
        stamp = "2026-10-05T00:00:00+00:00"
        message = "sampling stalled"
        (watch.STATE_DIR / "events.log").write_text(
            f"{stamp}\tSTART\tmetrics={before}\n{stamp}\tGAP\t{message}\n"
            f"{stamp}\tROTATE\tmetrics={after}\n{stamp}\tROTATE\tmetrics={outside}\n"
            f"{stamp}\tSTOP\tstopped\n{stamp}\tSTART\tmetrics={other}\n")
        incident = watch.Incident(stamp, "GAP", message, before)
        text = watch.diagnostic_report(incident)
        self.assertIn("51001", text)
        self.assertIn("52002", text)
        self.assertNotIn("53003", text)
        self.assertNotIn("54004", text)

    def test_scn006_previous_boot_kernel_evidence_and_missing_after_data(self):
        stamp = "2026-10-05T12:00:00+00:00"
        (watch.STATE_DIR / "events.log").write_text(
            f"{stamp}\tKERNEL\tprevious boot: NVRM: Xid for /home/private/driver --token=secret\n")
        incident = watch.Incident(stamp, "UNCLEAN", "last_sample=2026-10-05T00:00:00+00:00", None)
        text = watch.diagnostic_report(incident)
        self.assertIn("NVRM: Xid", text)
        self.assertIn("事件後沒有", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("/home", text)

    def test_issue6_report_distinguishes_observation_states(self):
        stamp = "2026-10-05T00:00:00+00:00"
        path = watch.STATE_DIR / "metrics-observation.tsv"
        row = dict.fromkeys(watch.METRICS_FIELDS, "NA")
        row.update(timestamp=stamp, epoch="1791158400", gpu_processes="disabled")
        path.write_text("\t".join(watch.METRICS_FIELDS) + "\n" +
                        "\t".join(row[field] for field in watch.METRICS_FIELDS) + "\n")
        (watch.STATE_DIR / "events.log").write_text(
            f"{stamp}\tSTART\tboot=x metrics={path} version=0.9.1 kernel=ok\n"
            f"{stamp}\tGAP\tsampling stalled\n")
        incident = watch.Incident(stamp, "GAP", "sampling stalled", path)
        report = watch.diagnostic_report(incident)
        self.assertIn("版本：0.9.1", report)
        self.assertIn("GPU 程序採樣：未啟用", report)
        self.assertIn("核心紀錄：可讀，未命中", report)
        self.assertNotIn(str(path), report)
        (watch.STATE_DIR / "events.log").write_text(
            f"{stamp}\tSTART\tboot=x metrics={path} version=0.9.1 kernel=unavailable\n"
            f"{stamp}\tGAP\tsampling stalled\n")
        self.assertIn("核心紀錄：不可讀", watch.diagnostic_report(incident))


if __name__ == "__main__":
    unittest.main()
