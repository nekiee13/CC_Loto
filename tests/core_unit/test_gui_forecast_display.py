# -----------------------
# tests/core_unit/test_gui_forecast_display.py
# -----------------------
"""The Tkinter GUI forecast table clamps values into each series' valid domain
and drops missing/non-finite values (so they render as '-', never a fake 0).

Guarded: the GUI module imports tkinter, which is optional on headless boxes;
the test skips when tkinter is unavailable rather than failing.
"""
from __future__ import annotations

import math
import unittest


def _load():
    from dynamix.entrypoints.gui import _round_clamp_ball  # noqa: WPS433

    return _round_clamp_ball


class TestGuiForecastDisplay(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.fn = _load()
        except Exception as e:  # tkinter (or other GUI dep) missing
            self.skipTest(f"GUI module not importable: {e}")

    def test_undershoot_and_overshoot_clamp(self) -> None:
        self.assertEqual(self.fn(0.4, "TS_1"), 1)     # the reported 0 becomes 1
        self.assertEqual(self.fn(-3.0, "TS_1"), 1)
        self.assertEqual(self.fn(52.3, "TS_5"), 50)
        self.assertEqual(self.fn(40.0, "TS_6"), 12)   # bonus ball ceiling

    def test_rounds_half_up(self) -> None:
        self.assertEqual(self.fn(7.83, "TS_1"), 8)
        self.assertEqual(self.fn(9.2, "TS_7"), 9)

    def test_missing_and_non_finite_return_none(self) -> None:
        self.assertIsNone(self.fn(None, "TS_1"))
        self.assertIsNone(self.fn(float("nan"), "TS_3"))
        self.assertIsNone(self.fn(float("inf"), "TS_2"))

    def test_always_in_domain(self) -> None:
        from dynamix import constants as C

        for ts, (lo, hi) in C.TS_VALUE_DOMAINS.items():
            for raw in (-9.0, 0.0, 0.49, lo + 0.2, (lo + hi) / 2.0, hi + 15.0):
                n = self.fn(raw, ts)
                self.assertIsNotNone(n)
                self.assertTrue(lo <= n <= hi, f"{ts}: {raw} -> {n} outside [{lo},{hi}]")


if __name__ == "__main__":
    unittest.main()
