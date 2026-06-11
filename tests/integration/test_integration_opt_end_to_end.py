# -----------------------
# tests/integration/test_opt_diagnostics_reliability_plot_optional.py
# -----------------------
from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from tests._util import TempOutputRoot, seed_everything
from tests._builders import SyntheticGridSpec, make_synthetic_statgrid, write_statgrid_run_shards
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config


class TestIntegrationOptEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def _make_cfg(self, root: Path, ts_list):
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
            seed=12345,
            code_version="qa-test",
        )

    def test_end_to_end_greedy_core_flow(self) -> None:
        with TempOutputRoot() as root:
            spec = SyntheticGridSpec(n_steps=12)
            df = make_synthetic_statgrid(spec)

            exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
            run_id = "testrun_integration_001"
            write_statgrid_run_shards(df, exports_dir / run_id, parts=2)

            cfg0 = self._make_cfg(root, spec.ts_list)
            cfg = as_opt_config(cfg0)

            from opt.opt_data import compute_grid_fingerprint, load_statgrid_run, resolve_slices  # type: ignore
            from opt.opt_features import build_truth_history_tables  # type: ignore
            from opt.opt_engine import ConditionalProbEngine  # type: ignore
            from opt.opt_strategies import run_greedy  # type: ignore

            grid = load_statgrid_run(cfg, run_id)
            fp = compute_grid_fingerprint(grid, ts_list=cfg0.ts_list, sample_steps=3)

            steps = sorted(grid["dataset_index"].unique().tolist())
            slice_info = resolve_slices(
                steps,
                train_frac=None,
                train_end_step=8,
                eval_start_step=9,
                eval_end_step=12,
                slice_mode="pos",
            )
            train_steps = slice_info["train_steps_dataset_index"]
            eval_steps = slice_info["eval_steps_dataset_index"]

            train_df = grid[grid["dataset_index"].isin(train_steps)].copy()
            steps_ordered = sorted(pd.unique(grid["dataset_index"]).tolist())
            tables = build_truth_history_tables(train_df, ts_list=cfg0.ts_list, steps_ordered=steps_ordered)  # type: ignore

            engine = ConditionalProbEngine(cfg, tables)
            engine.fit_on_train(grid, train_steps)

            state = {
                "grid_run_id": run_id,
                "grid_fingerprint": fp,
                "config_identity": cfg0.config_identity(),
                "slice": slice_info,
                "stages": {},
                "results": {},
                "notes": [],
            }

            res = run_greedy(cfg, "opt_run_test", state, grid, engine, eval_steps)
            self.assertGreater(len(res.diag_rows), 0)
            self.assertIn("roi_total", res.summary)


if __name__ == "__main__":
    unittest.main()
