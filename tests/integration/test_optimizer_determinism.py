# -----------------------
# tests/integration/test_optimizer_determinism.py
# -----------------------
"""
E8.4 — scope the determinism guarantee (SRS NFR-9) to the *optimizer* only.

NFR-9 promises reproducible **optimizer** outputs given identical inputs + config (fixed seeds,
deterministic feature ordering, deterministic fill-to-K). It deliberately does NOT promise
bit-reproducible *forecasting*: Stage-1 models (torch) and the multiprocessing backtest are not
bit-reproducible across runs/hardware. This test pins the part we actually guarantee — running
the optimizer twice over the same candidate grid, with the same config/seed, yields identical
results — and asserts the seeded random baseline is reproducible under its seed.

It exercises the real optimizer path (grid → truth tables → conditional-prob engine → greedy
strategy) over a synthetic, deterministically-generated StatGrid, so it needs no torch/darts.
"""
from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from tests._util import TempOutputRoot, seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid, write_statgrid_run_shards
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config

SEED = 4242


class TestOptimizerDeterminism(unittest.TestCase):
    def _make_cfg(self, root: Path, ts_list) -> TestOptConfig:
        exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
        opt_dir = root / "Output" / "Reports" / "Optimization"
        state_dir = opt_dir / "State"
        diag_dir = opt_dir / "Diagnostics"
        diag_hist = diag_dir / "history"
        graphs_dir = opt_dir / "Graphs"
        for d in [exports_dir, opt_dir, state_dir, diag_dir, diag_hist, graphs_dir]:
            d.mkdir(parents=True, exist_ok=True)
        return TestOptConfig(
            exports_dir=str(exports_dir),
            ts_list=list(ts_list),
            opt_dir=opt_dir,
            state_dir=state_dir,
            diag_dir=diag_dir,
            diag_history_dir=diag_hist,
            graphs_dir=graphs_dir,
            seed=SEED,
            code_version="qa-test",
        )

    def _run_optimizer_once(self, root: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Full optimizer path over a fixed synthetic grid; returns (summary, diag_rows)."""
        from opt.opt_data import load_statgrid_run, resolve_slices  # type: ignore
        from opt.opt_features import build_truth_history_tables  # type: ignore
        from opt.opt_engine import ConditionalProbEngine  # type: ignore
        from opt.opt_strategies import run_greedy  # type: ignore

        seed_everything(SEED)
        spec = SyntheticGridSpec(n_steps=12)
        df = make_synthetic_statgrid(spec)

        exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
        run_id = "det_run"
        write_statgrid_run_shards(df, exports_dir / run_id, parts=2)

        cfg0 = self._make_cfg(root, spec.ts_list)
        cfg = as_opt_config(cfg0)

        grid = load_statgrid_run(cfg, run_id)
        steps = sorted(grid["dataset_index"].unique().tolist())
        slice_info = resolve_slices(
            steps, train_frac=None, train_end_step=8, eval_start_step=9,
            eval_end_step=12, slice_mode="pos",
        )
        train_steps = slice_info["train_steps_dataset_index"]
        eval_steps = slice_info["eval_steps_dataset_index"]

        train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
        steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())
        tables = build_truth_history_tables(train_df, ts_list=cfg0.ts_list, steps_ordered=steps_ordered)

        engine = ConditionalProbEngine(cfg, tables)
        engine.fit_on_train(grid, train_steps)

        state = {
            "grid_run_id": run_id, "grid_fingerprint": "fp", "config_identity": cfg0.config_identity(),
            "slice": slice_info, "stages": {}, "results": {}, "notes": [],
        }
        res = run_greedy(cfg, "opt_run_det", copy.deepcopy(state), grid, engine, eval_steps)
        return res.summary, res.diag_rows

    def test_greedy_optimizer_is_reproducible_under_fixed_seed(self) -> None:
        with TempOutputRoot() as r1:
            summary_a, diag_a = self._run_optimizer_once(r1)
        with TempOutputRoot() as r2:
            summary_b, diag_b = self._run_optimizer_once(r2)

        self.assertGreater(len(diag_a), 0, "sanity: the run must produce diagnostics")
        self.assertEqual(summary_a, summary_b, "optimizer summary must be reproducible under fixed seed/config")
        self.assertEqual(diag_a, diag_b, "optimizer per-step diagnostics must be byte-identical across runs")

    def test_random_baseline_is_reproducible_and_seed_controlled(self) -> None:
        from opt.opt_strategies import build_value_pools_from_grid, random_ticket_baseline  # type: ignore

        with TempOutputRoot() as root:
            spec = SyntheticGridSpec(n_steps=12)
            df = make_synthetic_statgrid(spec)
            cfg = as_opt_config(self._make_cfg(root, spec.ts_list))
            pools = build_value_pools_from_grid(df, cfg.ts_list)

            a = random_ticket_baseline(cfg, pools, seed=SEED, n_tickets=5, n_draws=64)
            b = random_ticket_baseline(cfg, pools, seed=SEED, n_tickets=5, n_draws=64)
            c = random_ticket_baseline(cfg, pools, seed=SEED + 1, n_tickets=5, n_draws=64)

        self.assertEqual(a, b, "same seed must reproduce the baseline exactly")
        self.assertNotEqual(a, c, "the seed must actually drive the baseline RNG (different seed -> different result)")


if __name__ == "__main__":
    unittest.main()
