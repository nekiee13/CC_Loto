# -----------------------
# tests/optimization/test_engine_scoring.py
# -----------------------
"""
E5.2 — ticket/portfolio scoring known-answer tests.

Why: `score_ticket_q` (q x exp(bonus), clipped), `compatibility_log_bonus` (pair/triple
log-count math), `portfolio_q_any` (1 - prod(1-q)) and `build_ticket_pool_beam` (rank by
sum log p, dedupe, respect beam width) compose into every selection decision. Locking their
semantics with hand-computed answers prevents silent regressions during the E4/E6 refactors.

These tests inject p_hit / counts directly and never require torch/darts/chaospy/pulp.
"""
from __future__ import annotations

import math
import unittest

import numpy as np

from opt.opt_config import OptConfig
from opt.opt_engine import ConditionalProbEngine, TSShortlistItem
from opt.opt_features import TruthHistoryTables, _canonical_pair, _canonical_triple


def _empty_tables(pair_counts=None, triple_counts=None) -> TruthHistoryTables:
    return TruthHistoryTables(
        n_steps=0,
        steps_ordered=[],
        global_value_counts={},
        ts_value_counts={},
        last_seen_global={},
        last_seen_ts={},
        pair_counts=pair_counts or {},
        triple_counts=triple_counts or {},
    )


def _engine(ts_list, *, pair_counts=None, triple_counts=None, **cfg_kw) -> ConditionalProbEngine:
    cfg = OptConfig(ts_list=list(ts_list), **cfg_kw)
    return ConditionalProbEngine(cfg, _empty_tables(pair_counts, triple_counts))


def _item(value: int, p: float) -> TSShortlistItem:
    return TSShortlistItem(value=value, model="m", rounding_id=0, pred=float(value),
                           abs_err=0.0, p_hit=float(p))


class TestPortfolioQAny(unittest.TestCase):
    def setUp(self) -> None:
        self.eng = _engine(["TS_1", "TS_2"])

    def test_qany_formula(self) -> None:
        # 1 - prod(1 - q)
        self.assertAlmostEqual(self.eng.portfolio_q_any([0.5, 0.5]), 0.75, places=12)
        self.assertAlmostEqual(self.eng.portfolio_q_any([0.2, 0.3, 0.5]), 0.72, places=12)

    def test_qany_edge_cases(self) -> None:
        self.assertAlmostEqual(self.eng.portfolio_q_any([]), 0.0, places=12)      # empty -> 0
        self.assertAlmostEqual(self.eng.portfolio_q_any([1.0]), 1.0, places=12)   # a sure win
        self.assertAlmostEqual(self.eng.portfolio_q_any([0.0, 0.0]), 0.0, places=12)


class TestCompatibilityLogBonus(unittest.TestCase):
    def test_compat_bonus_uses_log1p_counts(self) -> None:
        ts = ["TS_1", "TS_2", "TS_3"]
        ticket = (1, 2, 3)
        pair_counts = {
            _canonical_pair("TS_1", 1, "TS_2", 2): 3,
            _canonical_pair("TS_1", 1, "TS_3", 3): 0,
            _canonical_pair("TS_2", 2, "TS_3", 3): 0,
        }
        triple_counts = {
            _canonical_triple(("TS_1", 1), ("TS_2", 2), ("TS_3", 3)): 4,
        }
        eng = _engine(ts, pair_counts=pair_counts, triple_counts=triple_counts,
                      use_pair_triple_compat=True, pair_weight=0.1, triple_weight=0.2)
        # bonus = 0.1*(log(1+3)+log(1+0)+log(1+0)) + 0.2*log(1+4)
        expected = 0.1 * (math.log(4.0) + math.log(1.0) + math.log(1.0)) + 0.2 * math.log(5.0)
        self.assertAlmostEqual(eng.compatibility_log_bonus(ticket), expected, places=12)

    def test_compat_disabled_returns_zero(self) -> None:
        eng = _engine(["TS_1", "TS_2"],
                      pair_counts={_canonical_pair("TS_1", 1, "TS_2", 2): 100},
                      use_pair_triple_compat=False, pair_weight=0.1)
        self.assertEqual(eng.compatibility_log_bonus((1, 2)), 0.0)


class TestScoreTicketQ(unittest.TestCase):
    def test_score_combines_q_and_exp_bonus(self) -> None:
        # bonus disabled -> score == q (in range). H=1, both positions near-certain.
        eng = _engine(["TS_1", "TS_2"], use_pair_triple_compat=False)
        shortlists = {"TS_1": [_item(1, 0.6)], "TS_2": [_item(2, 0.7)]}
        ps = [0.6, 0.7]
        q = eng.poisson_binomial_prob_ge(ps, 1)  # 1 - 0.4*0.3 = 0.88
        self.assertAlmostEqual(eng.score_ticket_q((1, 2), shortlists, 1), q, places=9)
        self.assertAlmostEqual(q, 0.88, places=9)

    def test_score_is_clipped_high(self) -> None:
        # q ~ 1 and a large positive bonus -> q*exp(bonus) >> 1 -> clipped to 1 - 1e-9.
        eng = _engine(
            ["TS_1", "TS_2"],
            pair_counts={_canonical_pair("TS_1", 1, "TS_2", 2): 10_000},
            use_pair_triple_compat=True, pair_weight=5.0,
        )
        shortlists = {"TS_1": [_item(1, 0.999999)], "TS_2": [_item(2, 0.999999)]}
        score = eng.score_ticket_q((1, 2), shortlists, 1)
        self.assertAlmostEqual(score, 1.0 - 1e-9, places=12)
        self.assertLess(score, 1.0)

    def test_score_is_clipped_low(self) -> None:
        # Impossible threshold (H > n) -> q = 0 -> clipped up to 1e-9 (never exactly 0).
        eng = _engine(["TS_1", "TS_2"], use_pair_triple_compat=False)
        shortlists = {"TS_1": [_item(1, 0.5)], "TS_2": [_item(2, 0.5)]}
        score = eng.score_ticket_q((1, 2), shortlists, 5)
        self.assertAlmostEqual(score, 1e-9, places=12)
        self.assertGreater(score, 0.0)


class TestBuildTicketPoolBeam(unittest.TestCase):
    def test_beam_respects_width_and_orders_by_logp(self) -> None:
        eng = _engine(["TS_1", "TS_2"])
        shortlists = {
            "TS_1": [_item(10, 0.9), _item(11, 0.1)],
            "TS_2": [_item(20, 0.8), _item(21, 0.2)],
        }
        out = eng.build_ticket_pool_beam(shortlists, beam=2)
        self.assertEqual(len(out), 2)  # width respected
        tickets = [t for (t, _) in out]
        scores = [s for (_, s) in out]
        self.assertEqual(tickets[0], (10, 20))  # highest sum log p
        self.assertAlmostEqual(scores[0], math.log(0.9) + math.log(0.8), places=12)
        self.assertEqual(scores, sorted(scores, reverse=True))  # descending

    def test_beam_dedupes_keeping_best_score(self) -> None:
        # Same value 10 appears twice for TS_1 (e.g. two models) with different p.
        eng = _engine(["TS_1", "TS_2"])
        shortlists = {
            "TS_1": [_item(10, 0.9), _item(10, 0.3)],
            "TS_2": [_item(20, 0.8)],
        }
        out = eng.build_ticket_pool_beam(shortlists, beam=5)
        self.assertEqual(len(out), 1)  # (10,20) collapsed to one entry
        ticket, score = out[0]
        self.assertEqual(ticket, (10, 20))
        self.assertAlmostEqual(score, math.log(0.9) + math.log(0.8), places=12)  # best kept


if __name__ == "__main__":
    unittest.main()
