"""Tests for konkrd's placement of msm's gpu-worker thread on SM8550. Run:
    python3 -m unittest tests.test_gpu_worker_pin
"""
import importlib.machinery
import importlib.util
import os
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
loader = importlib.machinery.SourceFileLoader("konkrd", os.path.join(ROOT, "sm8650-overlay/usr/lib/konkr/konkrd"))
spec = importlib.util.spec_from_loader("konkrd", loader)
k = importlib.util.module_from_spec(spec)
loader.exec_module(k)

# SM8550: three A510s, four middle cores, one X3.
CAPS = {0: 222, 1: 222, 2: 222, 3: 657, 4: 657, 5: 657, 6: 657, 7: 1024}


class GpuWorkerPin(unittest.TestCase):
    def setUp(self):
        self.files = {f"/sys/devices/system/cpu/cpu{c}/cpu_capacity": str(v) for c, v in CAPS.items()}
        self.files.update({"/proc/1/comm": "systemd", "/proc/151/comm": "gpu-worker",
                           "/proc/152/comm": "kworker/0:1H"})
        self.aff = {151: set(range(8))}
        self.set_calls = []

    def setaffinity(self, pid, mask):
        self.set_calls.append((pid, set(mask)))
        self.aff[pid] = set(mask)

    def run_pin(self, sm8550=True, big=None):
        procs = [p for p in self.files if p.startswith("/proc/")]
        with mock.patch.object(k, "is_sm8550", return_value=sm8550), \
                mock.patch.object(k, "big_cpus", return_value=big or {3, 4, 5, 6, 7}), \
                mock.patch.object(k, "rd", side_effect=lambda p, d="": self.files.get(p, d)), \
                mock.patch.object(k.glob, "glob", return_value=procs), \
                mock.patch.object(k.os, "sched_getaffinity", side_effect=lambda pid: set(self.aff[pid])), \
                mock.patch.object(k.os, "sched_setaffinity", side_effect=self.setaffinity), \
                mock.patch.object(k, "log"):
            k.pin_gpu_worker()

    def test_moves_to_the_middle_cores(self):
        self.run_pin()
        self.assertEqual(self.set_calls, [(151, {3, 4, 5, 6})])

    def test_leaves_a_placed_thread_alone(self):
        self.aff[151] = {3, 4, 5, 6}
        self.run_pin()
        self.assertEqual(self.set_calls, [])

    def test_other_socs_untouched(self):
        self.run_pin(sm8550=False)
        self.assertEqual(self.set_calls, [])

    def test_one_big_cluster_keeps_all_of_it(self):
        self.run_pin(big={3, 4, 5, 6})
        self.assertEqual(self.set_calls, [(151, {3, 4, 5, 6})])

    def test_no_thread_no_write(self):
        del self.files["/proc/151/comm"]
        self.run_pin()
        self.assertEqual(self.set_calls, [])


if __name__ == "__main__":
    unittest.main()
