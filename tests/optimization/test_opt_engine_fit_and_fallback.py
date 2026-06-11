# -----------------------
# tests/optimization/test_opt_engine_fit_and_fallback.py
# -----------------------
from __future__ import annotations

import unittest

import pandas as pd

from tests._util import seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config


class TestOptEngineFitAndFallback(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def test_fit_requires_non_empty_train_steps(self) -> None:
        spec = SyntheticGridSpec(n_steps=6)
        grid = make_synthetic_statgrid(spec)

        cfg0 = TestOptConfig(exports_dir=".", ts_list=list(spec.ts_list))
        cfg = as_opt_config(cfg0)

        from opt.opt_engine import ConditionalProbEngine  # type: ignore
        from opt.opt_features import build_truth_history_tables  # type: ignore

        train_steps: list[int] = []
        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()

        steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())
        tables = build_truth_history_tables(train_df, ts_list=cfg0.ts_list, steps_ordered=steps_ordered)  # type: ignore

        engine = ConditionalProbEngine(cfg, tables)
        with self.assertRaises(ValueError):
            engine.fit_on_train(grid, train_steps)

    def test_missing_ts_candidates_triggers_fallback_event(self) -> None:
        spec = SyntheticGridSpec(n_steps=10)
        grid = make_synthetic_statgrid(spec)

        cfg0 = TestOptConfig(exports_dir=".", ts_list=list(spec.ts_list))
        cfg = as_opt_config(cfg0)

        from opt.opt_engine import ConditionalProbEngine  # type: ignore
        from opt.opt_features import build_truth_history_tables  # type: ignore

        train_steps = list(range(1, 8))
        eval_step = 8

        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
        steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())
        tables = build_truth_history_tables(train_df, ts_list=cfg0.ts_list, steps_ordered=steps_ordered)  # type: ignore

        engine = ConditionalProbEngine(cfg, tables)
        engine.fit_on_train(grid, train_steps)

        step_df = grid[grid["dataset_index"] == eval_step].copy()
        step_df = step_df[step_df["ts"] != "TS_7"].copy()

        base = cfg0.base_strategy_params()
        shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=int(base["shortlist_m"]))

        self.assertIn("TS_7", shortlists)
        self.assertGreaterEqual(len(shortlists["TS_7"]), 1)

        events = engine.consume_fallback_events()
        self.assertTrue(any(e.get("ts") == "TS_7" for e in events))


if __name__ == "__main__":
    unittest.main()
