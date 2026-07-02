# -----------------------
# tests/optimization/test_candidate_value_clamp.py
# -----------------------
"""Regression: forecast candidate ball values must stay inside each series' valid
domain, so a ticket can never contain an out-of-range number such as 0.

Root cause (fixed): rounded model forecasts were used verbatim as candidate
values with no clamp, so an undershoot rounding to 0 (below every series
minimum) could be selected into a ticket. The synthetic StatGrid naturally
produces ``rounded == 0`` candidates, which makes it a faithful fixture.
"""
from __future__ import annotations

import unittest

import pandas as pd

from tests._util import seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid

from opt.opt_config import OptConfig
from opt.opt_engine import ConditionalProbEngine
from opt.opt_features import build_truth_history_tables


class TestCandidateValueClamp(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_shortlist_values_are_clamped_into_domain(self) -> None:
        spec = SyntheticGridSpec(n_steps=12)
        grid = make_synthetic_statgrid(spec)

        # Guard against a vacuous test: the raw grid must actually contain a
        # candidate value below the series minimum (0), otherwise clamping is
        # never exercised.
        self.assertTrue(
            (pd.to_numeric(grid["rounded"], errors="coerce") <= 0).any(),
            "fixture no longer produces out-of-domain (<=0) candidates",
        )

        cfg = OptConfig(ts_list=list(spec.ts_list))

        train_steps = list(range(1, 9))
        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
        steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())
        tables = build_truth_history_tables(
            train_df, ts_list=cfg.ts_list, steps_ordered=steps_ordered
        )

        engine = ConditionalProbEngine(cfg, tables)
        engine.fit_on_train(grid, train_steps)

        # Check every eval step: no shortlist value may fall outside its domain.
        for eval_step in range(9, spec.n_steps + 1):
            step_df = grid[grid["dataset_index"] == eval_step].copy()
            shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=8)
            for ts, items in shortlists.items():
                lo, hi = cfg.domain_for(ts)
                for it in items:
                    self.assertGreaterEqual(
                        it.value, lo, f"{ts} shortlist value {it.value} below domain min {lo}"
                    )
                    self.assertLessEqual(
                        it.value, hi, f"{ts} shortlist value {it.value} above domain max {hi}"
                    )

    def test_fallback_never_returns_out_of_domain(self) -> None:
        # An empty step forces a fallback for every TS; the fallback must be a
        # valid ball number (never the old 0 sentinel).
        spec = SyntheticGridSpec(n_steps=8)
        grid = make_synthetic_statgrid(spec)
        cfg = OptConfig(ts_list=list(spec.ts_list))

        train_steps = list(range(1, 7))
        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
        steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())
        tables = build_truth_history_tables(
            train_df, ts_list=cfg.ts_list, steps_ordered=steps_ordered
        )
        engine = ConditionalProbEngine(cfg, tables)
        engine.fit_on_train(grid, train_steps)

        empty_step = grid.iloc[0:0].copy()
        shortlists = engine.build_shortlists_for_step(empty_step, shortlist_m=8)
        for ts, items in shortlists.items():
            lo, hi = cfg.domain_for(ts)
            self.assertGreaterEqual(len(items), 1)
            for it in items:
                self.assertTrue(lo <= it.value <= hi, f"{ts} fallback value {it.value} out of [{lo},{hi}]")


if __name__ == "__main__":
    unittest.main()
