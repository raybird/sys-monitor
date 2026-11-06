from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gpu_sample", ROOT / "src/freeze_gpu.py")
gpu = importlib.util.module_from_spec(SPEC)
if (ROOT / "src/freeze_gpu.py").exists():
    SPEC.loader.exec_module(gpu)


class GpuSampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.proc = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def client(self, pid=123, fd=4, busy=100, start=50, extra="", client=7):
        root = self.proc / str(pid)
        (root / "fd").mkdir(parents=True, exist_ok=True)
        (root / "fdinfo").mkdir(exist_ok=True)
        (root / "stat").write_text(f"{pid} (gpu owner) S " + "0 " * 18 + str(start))
        (root / "comm").write_text("gpu-owner\n")
        link = root / "fd" / str(fd)
        if not link.is_symlink():
            link.symlink_to("/dev/dri/renderD128")
        (root / "fdinfo" / str(fd)).write_text(
            f"drm-driver: amdgpu\ndrm-pdev: 0000:01:00.0\ndrm-client-id: {client}\n"
            f"drm-engine-render: {busy} ns\n" + extra)

    def test_scn005_holder_baseline_then_active_delta_and_idle(self):
        self.client(busy=100)
        report, previous = gpu.sample_gpu(self.proc, {}, 1000)
        self.assertEqual(report["clients"][0]["engines"]["render"], "baseline")
        self.client(busy=600)
        report, previous = gpu.sample_gpu(self.proc, previous, 2000)
        self.assertEqual(report["clients"][0]["engines"]["render"], 50.0)
        report, _ = gpu.sample_gpu(self.proc, previous, 3000)
        # An idle holder is kept apart from activity, by name only.
        self.assertEqual(report["clients"], [])
        self.assertEqual(report["idle"], ["gpu-owner"])

    def test_scn005_shared_and_duplicate_descriptors_are_not_double_counted(self):
        self.client(fd=4)
        self.client(fd=5)
        self.client(pid=456)
        report, _ = gpu.sample_gpu(self.proc, {}, 1000)
        self.assertEqual(len(report["clients"]), 1)
        self.assertEqual(sorted(report["clients"][0]["pids"]), [123, 456])

    def test_scn005_regressed_counter_holds_baseline_until_catch_up(self):
        self.client(busy=100)
        _, previous = gpu.sample_gpu(self.proc, {}, 1000)
        self.client(busy=50)
        report, previous = gpu.sample_gpu(self.proc, previous, 2000)
        self.assertEqual(report["clients"][0]["engines"]["render"], "counter_regressed")
        self.client(busy=150)
        report, _ = gpu.sample_gpu(self.proc, previous, 3000)
        self.assertEqual(report["clients"][0]["engines"]["render"], 5.0)

    def test_scn005_reused_pid_is_a_new_baseline(self):
        self.client(busy=100, start=50)
        _, previous = gpu.sample_gpu(self.proc, {}, 1000)
        self.client(busy=600, start=60)
        report, _ = gpu.sample_gpu(self.proc, previous, 2000)
        self.assertEqual(report["clients"][0]["engines"]["render"], "baseline")

    def test_scn005_missing_counters_exited_fd_and_capacity(self):
        self.client(extra="drm-engine-capacity-render: 2\n")
        _, previous = gpu.sample_gpu(self.proc, {}, 1000)
        self.client(busy=600, extra="drm-engine-capacity-render: 2\n")
        report, _ = gpu.sample_gpu(self.proc, previous, 2000)
        self.assertEqual(report["clients"][0]["engines"]["render"], 25.0)
        (self.proc / "123/fdinfo/4").write_text("drm-driver: amdgpu\ndrm-client-id: 7\n")
        report, _ = gpu.sample_gpu(self.proc, {}, 3000)
        # A holder without counters is listed by name under its driver.
        self.assertEqual(report["clients"], [])
        self.assertEqual(report["unsupported"], {"amdgpu": ["gpu-owner"]})
        (self.proc / "123/fdinfo/4").unlink()
        report, _ = gpu.sample_gpu(self.proc, {}, 4000)
        self.assertEqual(report["clients"], [])
        self.assertGreater(report["unavailable"], 0)

    def test_scn005_scan_budget_is_visible(self):
        self.client()
        report, _ = gpu.sample_gpu(self.proc, {}, 1000, budget_ns=0)
        self.assertTrue(report["truncated"])

    def test_scn005_permission_denied_is_partial_and_does_not_raise(self):
        self.client()
        path = self.proc / "123/fdinfo/4"
        path.chmod(0)
        try:
            report, _ = gpu.sample_gpu(self.proc, {}, 1000)
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["clients"], [])
            self.assertEqual(report["unavailable"], 1)
        finally:
            path.chmod(0o600)

    def test_scn005_protected_own_process_is_counted_apart(self):
        self.client(pid=123, client=7)
        self.client(pid=456, client=8)
        fd_dir = self.proc / "456/fd"
        fd_dir.chmod(0)
        try:
            report, _ = gpu.sample_gpu(self.proc, {}, 1000)
        finally:
            fd_dir.chmod(0o700)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["protected"], 1)
        self.assertEqual(report["unavailable"], 0)
        self.assertEqual([client["pids"] for client in report["clients"]], [[123]])

    def test_scn005_driver_without_client_ids_is_listed_by_name(self):
        # NVIDIA's proprietary driver gives no drm-client-id, so every
        # descriptor would otherwise become a client of its own.
        for pid in range(100, 106):
            root = self.proc / str(pid)
            (root / "fd").mkdir(parents=True)
            (root / "fdinfo").mkdir()
            (root / "stat").write_text(f"{pid} (game) S " + "0 " * 18 + "50")
            (root / "comm").write_text("game\n")
            for fd in range(3, 15):
                (root / "fd" / str(fd)).symlink_to("/dev/nvidia0")
                (root / "fdinfo" / str(fd)).write_text("pos: 0\nflags: 02\n")
        report, _ = gpu.sample_gpu(self.proc, {}, 1000)
        self.assertEqual(report["status"], "ok")
        self.assertFalse(report["truncated"])
        self.assertEqual(report["clients"], [])
        self.assertEqual(report["unsupported"], {"nvidia": ["game"]})
        self.assertLess(len(json.dumps(report)), 200)

    def test_scn005_active_name_is_not_also_listed_idle(self):
        self.client(pid=123, fd=4, client=7, busy=100)
        self.client(pid=123, fd=5, client=8, busy=100)
        _, previous = gpu.sample_gpu(self.proc, {}, 1000)
        self.client(pid=123, fd=4, client=7, busy=600)
        report, _ = gpu.sample_gpu(self.proc, previous, 2000)
        self.assertEqual([client["client"] for client in report["clients"]], ["7"])
        self.assertEqual(report["idle"], [])

    def test_scn005_unmeasured_holder_is_not_listed_idle(self):
        # Idle on the Intel GPU while holding an NVIDIA device: its activity
        # is unknown, not idle, just as on a first sample.
        self.client(pid=123, fd=4, client=7, busy=100)
        (self.proc / "123/fd/5").symlink_to("/dev/nvidia0")
        (self.proc / "123/fdinfo/5").write_text("pos: 0\n")
        _, previous = gpu.sample_gpu(self.proc, {}, 1000)
        report, _ = gpu.sample_gpu(self.proc, previous, 2000)
        self.assertEqual(report["unsupported"], {"nvidia": ["gpu-owner"]})
        self.assertEqual(report["idle"], [])

    def test_scn005_other_users_are_skipped_not_unavailable(self):
        self.client()
        with mock.patch.object(gpu.os, "getuid", return_value=os.getuid() + 1):
            report, _ = gpu.sample_gpu(self.proc, {}, 1000)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["unavailable"], 0)
        self.assertEqual(report["clients"], [])

    def test_scn005_newest_processes_are_scanned_first_when_capped(self):
        self.client(pid=123, client=7)
        self.client(pid=456, client=8)
        with mock.patch.object(gpu, "MAX_PROCESSES", 1):
            report, _ = gpu.sample_gpu(self.proc, {}, 1000)
        self.assertTrue(report["truncated"])
        self.assertEqual([client["pids"] for client in report["clients"]], [[456]])

    def test_scn005_non_utf8_process_name_does_not_fail_the_sample(self):
        self.client()
        (self.proc / "123/comm").write_bytes(("a" + "測試程式測試").encode()[:15] + b"\n")
        report, _ = gpu.sample_gpu(self.proc, {}, 1000)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(len(report["clients"]), 1)
        self.assertTrue(report["clients"][0]["names"][0].startswith("a測試程式"))
        json.dumps(report)


if __name__ == "__main__":
    unittest.main()
