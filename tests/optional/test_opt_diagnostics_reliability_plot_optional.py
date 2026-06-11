# -----------------------
# tests/optional/test_opt_diagnostics_reliability_plot_optional.py
# -----------------------
from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from tests._util import TempOutputRoot, seed_everything
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config


class TestOptDiagnosticsReliabilityPlotOptional(unittest.TestCase):
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
            calibration_bins=10,
            reliability_plot_title="QA Optional Reliability Plot Test",
        )

    def test_reliability_plot_written_when_plotly_available(self) -> None:
        try:
            import plotly  # noqa: F401
        except Exception:
            self.skipTest("plotly not installed; reliability plot generation is optional")

        with TempOutputRoot() as root:
            cfg0 = self._make_cfg(root)
            cfg = as_opt_config(cfg0)

            diag_rows = [
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

            from opt.opt_diagnostics import (  # type: ignore
                ensure_dirs,
                write_diagnostics_current_and_history,
                write_calibration_current_and_history,
            )

            ensure_dirs(cfg)

            opt_run_id = "opt_20990101_000000"
            grid_run_id = "testrun_grid_000001"

            diag_df = write_diagnostics_current_and_history(cfg, opt_run_id, grid_run_id, diag_rows)
            self.assertIsInstance(diag_df, pd.DataFrame)
            self.assertFalse(diag_df.empty)

            cal_df = write_calibration_current_and_history(cfg, opt_run_id, grid_run_id, diag_df)
            self.assertIsInstance(cal_df, pd.DataFrame)

            html_files = list(Path(cfg0.graphs_dir).glob("reliability_*_current.html"))
            self.assertTrue(html_files, "Expected reliability plot HTML files under graphs_dir")

            self.assertTrue((Path(cfg0.diag_dir) / "diagnostics_current.csv").exists())
            self.assertTrue((Path(cfg0.diag_dir) / "calibration_current.csv").exists())


if __name__ == "__main__":
    unittest.main()
