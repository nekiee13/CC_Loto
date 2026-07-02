# -----------------------
# tests/core_unit/test_forecast_display.py
# -----------------------
"""Stage-1 console table renders forecasts as integers clamped into each
series' valid domain (C.TS_VALUE_DOMAINS), so it can never show an impossible
ball number such as 0 or a value above the series maximum.
"""
from __future__ import annotations

import math
import unittest

from dynamix import constants as C
from dynamix.entrypoints.run_cli import format_ball_val


class TestFormatBallVal(unittest.TestCase):
    def test_undershoot_clamps_to_series_minimum(self) -> None:
        # The reported bug: a value rounding below 1 must not render as 0.
        self.assertEqual(format_ball_val(0.4, "TS_1"), "1")
        self.assertEqual(format_ball_val(-3.0, "TS_1"), "1")
        self.assertEqual(format_ball_val(0.0, "TS_6"), "1")

    def test_overshoot_clamps_to_series_maximum(self) -> None:
        self.assertEqual(format_ball_val(52.3, "TS_5"), "50")
        self.assertEqual(format_ball_val(40.0, "TS_6"), "12")  # bonus ball ceiling

    def test_rounds_half_up_to_integer(self) -> None:
        self.assertEqual(format_ball_val(7.83, "TS_1"), "8")
        self.assertEqual(format_ball_val(6.5, "TS_2"), "7")
        self.assertEqual(format_ball_val(9.2, "TS_7"), "9")

    def test_missing_values_render_na(self) -> None:
        self.assertEqual(format_ball_val(None, "TS_1"), "N/A")
        self.assertEqual(format_ball_val(float("nan"), "TS_3"), "N/A")

    def test_output_is_always_integer_in_domain(self) -> None:
        for ts, (lo, hi) in C.TS_VALUE_DOMAINS.items():
            for raw in (-10.0, 0.0, 0.49, lo + 0.2, (lo + hi) / 2.0, hi - 0.4, hi + 25.0):
                s = format_ball_val(raw, ts)
                n = int(s)
                self.assertEqual(float(n), float(n))  # integral
                self.assertTrue(lo <= n <= hi, f"{ts}: {raw} -> {n} outside [{lo},{hi}]")

    def test_unknown_series_passes_through_rounded(self) -> None:
        # No domain entry -> round only, no clamp (defensive fallback).
        self.assertEqual(format_ball_val(123.6, "TS_UNKNOWN"), str(int(math.floor(123.6 + 0.5))))


if __name__ == "__main__":
    unittest.main()
