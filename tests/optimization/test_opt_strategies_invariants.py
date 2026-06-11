# -----------------------
# tests/optimization/test_opt_strategies_invariants.py
# -----------------------
from __future__ import annotations

import unittest

import pandas as pd

from tests._util import seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config


class TestOptStrategiesInvariants(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def _make_engine(self):
        spec = SyntheticGridSpec(n_steps=10)
        grid = make_synthetic_statgrid(spec)

        cfg0 = TestOptConfig(exports_dir=".", ts_list=list(spec.ts_list))
        cfg = as_opt_config(cfg0)

        from opt.opt_engine import ConditionalProbEngine  # type: ignore
        from opt.opt_features import build_truth_history_tables  # type: ignore

        train_steps = list(range(1, 8))
        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
        steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())

        tables = build_truth_history_tables(train_df, ts_list=cfg0.ts_list, steps_ordered=steps_ordered)  # type: ignore
        engine = ConditionalProbEngine(cfg, tables)
        engine.fit_on_train(grid, train_steps)

        return cfg0, cfg, engine, grid

    def test_milp_falls_back_when_pulp_missing(self) -> None:
        cfg0, cfg, engine, grid = self._make_engine()

        from opt.opt_strategies import select_milp_sum_q  # type: ignore

        eval_step = 8
        step_df = grid[grid["dataset_index"] == eval_step]
        base = cfg0.base_strategy_params()

        shortlists = engine.build_shortlists_for_step(step_df, shortlist_m=int(base["shortlist_m"]))
        pool = engine.build_ticket_pool_beam(shortlists, beam=int(base["beam"]))

        tickets, q_list, q_any = select_milp_sum_q(
            cfg,
            engine,
            pool,
            shortlists,
            max_tickets=int(cfg0.max_tickets_per_draw),
            max_overlap_k=int(base["max_overlap_k"]),
            hit_threshold=int(base["hit_threshold"]),
        )

        self.assertIsInstance(tickets, list)
        self.assertIsInstance(q_list, list)
        self.assertIsInstance(q_any, float)

    def test_greedy_selection_avoids_high_overlap_when_possible(self) -> None:
        cfg0, cfg, engine, _grid = self._make_engine()

        from opt.opt_strategies import select_portfolio_greedy  # type: ignore

        t1 = (1, 2, 3, 4, 5, 6, 7)
        t2 = (1, 2, 3, 4, 5, 6, 8)  # overlap 6 with t1
        t3 = (9, 9, 9, 9, 9, 9, 9)  # overlap 0 with t1
        pool = [(t1, 0.0), (t2, -0.01), (t3, -0.02)]

        shortlists = {ts: [] for ts in cfg0.ts_list}

        tickets, _q_list, _q_any = select_portfolio_greedy(
            cfg,
            engine,
            pool,
            shortlists,
            max_tickets=2,
            max_overlap_k=2,
            hit_threshold=3,
        )

        self.assertIn(t1, tickets)
        self.assertIn(t3, tickets)
        self.assertNotIn(t2, tickets)


if __name__ == "__main__":
    unittest.main()
