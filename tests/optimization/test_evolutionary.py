# -----------------------
# tests/optimization/test_evolutionary.py
# -----------------------
"""
E6.2 — real evolutionary hyper-strategy search.

``run_evolutionary`` used to be a deterministic stub that just re-ran greedy with the default
params. It is now a seeded genetic algorithm over the strategy hyperparameters
``{max_overlap_k, shortlist_m, beam, hit_threshold}``; fitness is the EVAL portfolio economics
(total ``net_eur``, which ranks identically to ``edge_eur`` since the random baseline is a
genome-independent constant). These tests pin the two guarantees from the plan:

  1. Deterministic under ``seed`` — same cfg/grid/engine ⇒ identical best params, summary, diags.
  2. Elitism holds — the returned best fitness is never worse than the initial population's best.

Runs the real optimizer path over a deterministically-generated synthetic StatGrid, so it needs
no torch/darts.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any, List, Tuple

import pandas as pd

from tests._util import TempOutputRoot, seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid, write_statgrid_run_shards
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config

SEED = 20260701


class TestEvolutionary(unittest.TestCase):
    def _prepare(self, root: Path) -> Tuple[Any, Any, List[int]]:
        """Build (cfg, engine, eval_steps) over a fixed synthetic StatGrid."""
        from opt.opt_data import load_statgrid_run, resolve_slices  # type: ignore
        from opt.opt_features import build_truth_history_tables  # type: ignore
        from opt.opt_engine import ConditionalProbEngine  # type: ignore

        seed_everything(SEED)
        spec = SyntheticGridSpec(n_steps=14)
        df = make_synthetic_statgrid(spec)

        exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
        opt_dir = root / "Output" / "Reports" / "Optimization"
        for d in [exports_dir, opt_dir, opt_dir / "State", opt_dir / "Diagnostics",
                  opt_dir / "Diagnostics" / "history", opt_dir / "Graphs"]:
            d.mkdir(parents=True, exist_ok=True)
        run_id = "evo_run"
        write_statgrid_run_shards(df, exports_dir / run_id, parts=2)

        cfg0 = TestOptConfig(
            exports_dir=str(exports_dir), ts_list=list(spec.ts_list), opt_dir=opt_dir,
            state_dir=opt_dir / "State", diag_dir=opt_dir / "Diagnostics",
            diag_history_dir=opt_dir / "Diagnostics" / "history", graphs_dir=opt_dir / "Graphs",
            seed=SEED, code_version="qa-test",
        )
        cfg = as_opt_config(cfg0)
        # Keep the search small so the test is fast but still multi-generational.
        cfg = replace(cfg, evo_generations=4, evo_pop_size=6)

        grid = load_statgrid_run(cfg, run_id)
        steps = sorted(grid["dataset_index"].unique().tolist())
        slice_info = resolve_slices(
            steps, train_frac=None, train_end_step=9, eval_start_step=10,
            eval_end_step=14, slice_mode="pos",
        )
        train_steps = slice_info["train_steps_dataset_index"]
        eval_steps = slice_info["eval_steps_dataset_index"]

        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
        steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())
        tables = build_truth_history_tables(train_df, ts_list=cfg0.ts_list, steps_ordered=steps_ordered)
        engine = ConditionalProbEngine(cfg, tables)
        engine.fit_on_train(grid, train_steps)
        return cfg, engine, grid, eval_steps, train_steps

    def _new_state(self, run_id: str = "evo_run") -> dict:
        return {"grid_run_id": run_id, "stages": {}, "results": {}, "notes": []}

    def test_evolution_is_deterministic_under_seed(self) -> None:
        from opt.opt_strategies import run_evolutionary  # type: ignore

        with TempOutputRoot() as r1:
            cfg, engine, grid, eval_steps, train_steps = self._prepare(r1)
            res_a = run_evolutionary(cfg, "opt_a", self._new_state(), grid, engine, eval_steps, train_steps)
        with TempOutputRoot() as r2:
            cfg, engine, grid, eval_steps, train_steps = self._prepare(r2)
            res_b = run_evolutionary(cfg, "opt_b", self._new_state(), grid, engine, eval_steps, train_steps)

        self.assertEqual(res_a.summary.get("best_params"), res_b.summary.get("best_params"),
                         "best params must be identical under a fixed seed")
        self.assertEqual(res_a.summary.get("best_fitness"), res_b.summary.get("best_fitness"),
                         "best fitness must be identical under a fixed seed")
        self.assertEqual(res_a.diag_rows, res_b.diag_rows,
                         "per-step diagnostics of the winning genome must be byte-identical")

    def test_evolution_improves_or_matches_initial_fitness(self) -> None:
        from opt.opt_strategies import run_evolutionary  # type: ignore

        with TempOutputRoot() as root:
            cfg, engine, grid, eval_steps, train_steps = self._prepare(root)
            res = run_evolutionary(cfg, "opt_e", self._new_state(), grid, engine, eval_steps, train_steps)

        best = res.summary.get("best_fitness")
        initial = res.summary.get("initial_best_fitness")
        self.assertIsNotNone(best)
        self.assertIsNotNone(initial)
        self.assertGreaterEqual(
            float(best), float(initial),
            "elitism must guarantee the returned best fitness is never worse than the initial best",
        )
        # The winning params must be a valid genome over the four searched hyperparameters.
        params = res.summary.get("best_params") or {}
        for key in ("max_overlap_k", "shortlist_m", "beam", "hit_threshold"):
            self.assertIn(key, params)
            self.assertIsInstance(params[key], int)


if __name__ == "__main__":
    unittest.main()
