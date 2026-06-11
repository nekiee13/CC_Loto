# -----------------------
# tests/core_unit/test_opt_engine_math.py
# -----------------------

import unittest

from tests._util import seed_everything


class TestOptEngineMath(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_poisson_binomial_prob_ge_bounds_and_monotonic(self) -> None:
        from opt.opt_engine import ConditionalProbEngine  # type: ignore

        ps = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]

        q0 = ConditionalProbEngine.poisson_binomial_prob_ge(ps, 0)
        q3 = ConditionalProbEngine.poisson_binomial_prob_ge(ps, 3)
        q7 = ConditionalProbEngine.poisson_binomial_prob_ge(ps, 7)

        self.assertGreaterEqual(q0, 0.0)
        self.assertLessEqual(q0, 1.0)
        self.assertGreaterEqual(q3, 0.0)
        self.assertLessEqual(q3, 1.0)
        self.assertGreaterEqual(q7, 0.0)
        self.assertLessEqual(q7, 1.0)

        # monotonic: P(hits>=0) >= P(hits>=3) >= P(hits>=7)
        self.assertGreaterEqual(q0, q3)
        self.assertGreaterEqual(q3, q7)

    def test_overlap_positions(self) -> None:
        from opt.opt_engine import ConditionalProbEngine  # type: ignore

        a = (1, 2, 3, 4, 5, 6, 7)
        b = (1, 2, 3, 0, 0, 0, 0)
        c = (9, 9, 9, 9, 9, 9, 9)

        self.assertEqual(ConditionalProbEngine.overlap_positions(a, b), 3)
        self.assertEqual(ConditionalProbEngine.overlap_positions(a, c), 0)
