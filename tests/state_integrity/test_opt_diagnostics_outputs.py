# -----------------------
# tests/state_integrity/test_opt_diagnostics_outputs.py
# -----------------------
from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from tests._util import TempOutputRoot, seed_everything
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config


class TestOptDiagnosticsOutputs(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def _make_cfg(self, root: Path) -> TestOptConfig:
        exports_dir = root / "Output" / "Reports" / "Exports" / "StatGrid"
        opt_dir = root / "Output" / "Reports" / "Optimization"
        state_dir = opt_dir / "State"
        diag_dir = opt_dir / "Diagnostics"
        diag_history_dir = diag_dir / "history"
        graphs_dir = opt_dir / "Graphs"

        for d in [exports_dir, opt_dir, state_dir, diag_dir, diag_history_dir, graphs_dir]:
            d.mkdir(parents=True, exist_ok=True)

        return TestOptConfig(
            exports_dir=str(exports_dir),
            ts_list=["TS_1", "TS_2", "TS_3", "TS_4", "TS_5", "TS_6", "TS_7"],
            opt_dir=opt_dir,
            state_dir=state_dir,
            diag_dir=diag_dir,
            diag_history_dir=diag_history_dir,
            graphs_dir=graphs_dir,
            calibration_bins=8,
            reliability_plot_title="QA State Integrity Diagnostics Outputs",
            code_version="qa-test",
            seed=12345,
        )

    def test_diagnostics_calibration_and_summary_outputs(self) -> None:
        with TempOutputRoot() as root:
            cfg0 = self._make_cfg(root)
            cfg = as_opt_config(cfg0)

            from opt.opt_diagnostics import (  # type: ignore
                ensure_dirs,
                write_diagnostics_current_and_history,
                write_calibration_current_and_history,
                write_final_summary,
            )

            opt_run_id = "opt_20990101_000000"
            grid_run_id = "grid_20990101_000000"

            diag_rows: List[Dict[str, Any]] = [
                {
                    "optimizer": "greedy",
                    "dataset_index": 101,
                    "tickets_count": 2,
                    "tickets": "1-2-3-4-5-6-7 | 9-9-9-9-9-9-9",
                    "q_per_ticket": "[0.100000,0.050000]",
                    "q_any": 0.145,
                    "hit_threshold": 3,
                    "realized_max_hits": 2,
                    "success_ge_H": 0,
                    "profit": -2.0,
                    "arm": "",
                },
                {
                    "optimizer": "greedy",
                    "dataset_index": 102,
                    "tickets_count": 2,
                    "tickets": "1-2-3-4-5-6-7 | 9-9-9-9-9-9-9",
                    "q_per_ticket": "[0.200000,0.050000]",
                    "q_any": 0.240,
                    "hit_threshold": 3,
                    "realized_max_hits": 3,
                    "success_ge_H": 1,
                    "profit": 10.0,
                    "arm": "",
                },
                {
                    "optimizer": "milp",
                    "dataset_index": 103,
                    "tickets_count": 1,
                    "tickets": "1-1-1-1-1-1-1",
                    "q_per_ticket": "[0.050000]",
                    "q_any": 0.050,
                    "hit_threshold": 3,
                    "realized_max_hits": 0,
                    "success_ge_H": 0,
                    "profit": -1.0,
                    "arm": "",
                },
            ]

            grid_fp = {
                "n_rows": 999,
                "n_steps": 12,
                "min_dataset_index": 1,
                "max_dataset_index": 12,
                "steps_hash": "dummy_steps_hash",
                "schema_hash": "dummy_schema_hash",
                "sample_true_hash": "dummy_true_hash",
            }
            slice_info = {
                "slice_mode": "pos",
                "N_steps_total": 12,
                "train_end_step_pos": 8,
                "eval_start_step_pos": 9,
                "eval_end_step_pos": 12,
                "train_steps_dataset_index": list(range(1, 9)),
                "eval_steps_dataset_index": list(range(9, 13)),
            }
            results = {"greedy": {"roi_total": 0.123, "rows": 4}}

            ensure_dirs(cfg)

            diag_df = write_diagnostics_current_and_history(cfg, opt_run_id, grid_run_id, diag_rows)
            self.assertIsInstance(diag_df, pd.DataFrame)
            self.assertFalse(diag_df.empty)

            cal_df = write_calibration_current_and_history(cfg, opt_run_id, grid_run_id, diag_df)
            self.assertIsInstance(cal_df, pd.DataFrame)

            write_final_summary(cfg, opt_run_id, grid_run_id, grid_fp, slice_info, results, diag_df, cal_df)

            self.assertTrue((cfg0.diag_dir / "diagnostics_current.csv").exists())
            self.assertTrue((cfg0.diag_dir / "calibration_current.csv").exists())
            self.assertTrue((cfg0.opt_dir / "summary_current.json").exists())

            hist_diag = list(cfg0.diag_history_dir.glob(f"diagnostics_{opt_run_id}_{grid_run_id}_*.csv"))
            hist_cal = list(cfg0.diag_history_dir.glob(f"calibration_{opt_run_id}_{grid_run_id}_*.csv"))
            hist_sum = list(cfg0.opt_dir.glob(f"summary_{opt_run_id}_{grid_run_id}_*.json"))

            self.assertTrue(hist_diag)
            self.assertTrue(hist_cal)
            self.assertTrue(hist_sum)


if __name__ == "__main__":
    unittest.main()
