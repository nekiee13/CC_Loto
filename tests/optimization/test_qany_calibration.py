# -----------------------
# tests/optimization/test_qany_calibration.py
# -----------------------
"""
E1.3 — q_any calibration on EVAL.

Why: a strategy can "win" on a lucky EVAL while being badly miscalibrated. Surfacing the ECE /
Brier of the predicted portfolio success probability (q_any) versus realized success tells us
whether the probabilities themselves are trustworthy. This adapter just assembles
(q_any, success) pairs and reuses opt_calibration's Brier/ECE — these tests pin the two extreme
cases (perfect vs. overconfident).
"""
from __future__ import annotations

import unittest

from opt.opt_calibration import qany_calibration


class TestQAnyCalibration(unittest.TestCase):
    def test_perfect_calibration_zero_ece(self) -> None:
        # Half the draws predicted certain-success and succeeded; half certain-failure, failed.
        q_any = [1.0] * 5 + [0.0] * 5
        success = [1] * 5 + [0] * 5
        out = qany_calibration(q_any, success, n_bins=10)
        self.assertAlmostEqual(out["qany_ece"], 0.0, places=9)
        self.assertAlmostEqual(out["qany_brier"], 0.0, places=9)
        self.assertEqual(out["n"], 10)

    def test_overconfident_has_positive_ece(self) -> None:
        # Predicted 0.9 every draw but only 1/10 actually succeeded (empirical 0.1).
        q_any = [0.9] * 10
        success = [1] + [0] * 9
        out = qany_calibration(q_any, success, n_bins=10)
        # All mass lands in one bin: |acc - conf| = |0.1 - 0.9| = 0.8.
        self.assertAlmostEqual(out["qany_ece"], 0.8, places=6)
        # Brier = mean((0.9 - y)^2) = (9*0.81 + 0.01)/10 = 0.73.
        self.assertAlmostEqual(out["qany_brier"], 0.73, places=6)

    def test_empty_is_safe(self) -> None:
        out = qany_calibration([], [], n_bins=10)
        self.assertEqual(out["n"], 0)
        self.assertEqual(out["qany_ece"], 0.0)
        self.assertEqual(out["qany_brier"], 0.0)


if __name__ == "__main__":
    unittest.main()
