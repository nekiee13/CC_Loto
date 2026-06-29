# -----------------------
# tests/core_unit/test_poisson_binomial.py
# -----------------------
"""
E5.1 — Poisson-binomial known-answer tests.

Why: `poisson_binomial_prob_ge` is the exact-probability heart of every ticket score `q`. An
off-by-one in its DP would silently bias every selection. These tests pin it against closed
forms (reduces to the binomial when all p are equal; exact hand-computed small cases; the
H<=0 and H>n boundaries).
"""
from __future__ import annotations

import unittest

from scipy.stats import binom

from opt.opt_engine import ConditionalProbEngine

pb = ConditionalProbEngine.poisson_binomial_prob_ge


class TestPoissonBinomial(unittest.TestCase):
    def test_all_equal_p_reduces_to_binomial(self) -> None:
        # ps = [p]*n collapses the Poisson-binomial to an ordinary Binomial(n, p).
        for p in (0.1, 0.37, 0.5, 0.8):
            n = 7
            ps = [p] * n
            for H in range(0, n + 1):
                # P(X >= H) == sf(H-1) for a Binomial(n, p).
                expected = float(binom.sf(H - 1, n, p))
                self.assertAlmostEqual(pb(ps, H), expected, places=12,
                                       msg=f"p={p} H={H}")

    def test_H_zero_is_one(self) -> None:
        # P(hits >= 0) is certain.
        self.assertAlmostEqual(pb([0.1, 0.9, 0.3], 0), 1.0, places=12)
        self.assertAlmostEqual(pb([], 0), 1.0, places=12)

    def test_H_gt_n_is_zero(self) -> None:
        # You cannot get more hits than there are positions.
        ps = [0.5, 0.5, 0.5]
        self.assertEqual(pb(ps, 4), 0.0)
        self.assertEqual(pb(ps, 10), 0.0)

    def test_two_position_hand_computation(self) -> None:
        ps = [0.5, 0.5]
        # P(>=1) = 1 - P(0) = 1 - 0.25 = 0.75
        self.assertAlmostEqual(pb(ps, 1), 0.75, places=12)
        # P(>=2) = 0.5 * 0.5 = 0.25
        self.assertAlmostEqual(pb(ps, 2), 0.25, places=12)
        # P(>=0) = 1.0
        self.assertAlmostEqual(pb(ps, 0), 1.0, places=12)

    def test_asymmetric_three_position_hand_computation(self) -> None:
        # ps = [0.2, 0.5, 0.9]; P(>=2) computed by hand.
        # P(exactly 2) = 0.2*0.5*0.1 + 0.2*0.5*0.9 + 0.8*0.5*0.9 = 0.01 + 0.09 + 0.36 = 0.46
        # P(exactly 3) = 0.2*0.5*0.9 = 0.09  ->  P(>=2) = 0.55
        self.assertAlmostEqual(pb([0.2, 0.5, 0.9], 2), 0.55, places=12)


if __name__ == "__main__":
    unittest.main()
