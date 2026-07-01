# -----------------------
# tests/core_unit/test_device.py
# -----------------------
"""
Device helpers (`dynamix.device`): GPU availability + a Darts accelerator guard.

`resolve_darts_accelerator` is pure (takes availability as an argument) so it is fully testable
without torch/darts installed. `gpu_available` / `describe_device` are checked for type/shape only,
since the real value depends on the machine.
"""
from __future__ import annotations

import unittest

from dynamix import device


class TestDevice(unittest.TestCase):
    def test_resolve_darts_accelerator_matrix(self) -> None:
        # 'gpu' only when forced AND a GPU is actually available; otherwise 'cpu'.
        self.assertEqual(device.resolve_darts_accelerator(True, True), "gpu")
        self.assertEqual(device.resolve_darts_accelerator(True, False), "cpu")
        self.assertEqual(device.resolve_darts_accelerator(False, True), "cpu")
        self.assertEqual(device.resolve_darts_accelerator(False, False), "cpu")

    def test_gpu_available_returns_bool(self) -> None:
        self.assertIsInstance(device.gpu_available(), bool)

    def test_describe_device_shape(self) -> None:
        d = device.describe_device()
        self.assertIsInstance(d, str)
        self.assertTrue(d.startswith("CPU") or d.startswith("GPU"), d)


if __name__ == "__main__":
    unittest.main()
