# -----------------------
# tests/webapp/test_charts_data.py
# -----------------------
"""
V4.1 — chart-data readers (`dynamix.webapp.charts_data`).

Pure, Streamlit-free readers that turn the optimizer's written `calibration_current.csv`
(columns: optimizer, hit_threshold, bin_lo, bin_hi, n, empirical, avg_p) into tidy frames for a
reliability curve. Missing files degrade to empty frames rather than raising.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dynamix.webapp import charts_data

SAMPLE_CSV = (
    "optimizer,hit_threshold,bin_lo,bin_hi,n,empirical,avg_p\n"
    "greedy,3,0.0,0.1,10,0.05,0.04\n"
    "greedy,3,0.1,0.2,8,0.20,0.15\n"
    "milp,3,0.0,0.1,12,0.02,0.03\n"
)


class TestChartsData(unittest.TestCase):
    def _tmp(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_load_calibration(self) -> None:
        p = self._tmp() / "calibration_current.csv"
        p.write_text(SAMPLE_CSV, encoding="utf-8")
        df = charts_data.load_calibration(p)
        self.assertEqual(len(df), 3)
        for c in ["optimizer", "hit_threshold", "bin_lo", "bin_hi", "n", "empirical", "avg_p"]:
            self.assertIn(c, df.columns)
        # numeric coercion
        self.assertAlmostEqual(float(df.iloc[1]["avg_p"]), 0.15, places=6)

    def test_load_calibration_missing_is_empty(self) -> None:
        df = charts_data.load_calibration(self._tmp() / "nope.csv")
        self.assertTrue(df.empty)
        self.assertIn("avg_p", df.columns)  # expected columns even when empty

    def test_reliability_curve_filtered_sorted(self) -> None:
        p = self._tmp() / "calibration_current.csv"
        p.write_text(SAMPLE_CSV, encoding="utf-8")
        df = charts_data.load_calibration(p)
        curve = charts_data.reliability_curve(df, optimizer="greedy", hit_threshold=3)
        self.assertEqual(list(curve.columns), ["avg_p", "empirical"])
        self.assertEqual(len(curve), 2)
        self.assertTrue(curve["avg_p"].is_monotonic_increasing)

    def test_latest_calibration_locator(self) -> None:
        d = self._tmp()
        self.assertIsNone(charts_data.latest_calibration(diag_dir=d))
        (d / "calibration_current.csv").write_text(SAMPLE_CSV, encoding="utf-8")
        found = charts_data.latest_calibration(diag_dir=d)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "calibration_current.csv")


if __name__ == "__main__":
    unittest.main()
