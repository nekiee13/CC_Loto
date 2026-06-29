# -----------------------
# tests/contract/test_final_summary_scoreboard.py
# -----------------------
"""
E1.4 — honest EV/ROI + calibration scoreboard wired into the final summary.

Why: insight nobody reads is worthless. The verdict — did each strategy beat a random control,
and does it make or lose money — must be impossible to miss in the JSON artifact. These tests
pin that the summary carries a per-strategy scoreboard with every key numeric, and that the
edge identity (edge_eur = net_eur - baseline_net_eur) holds.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from tests._util import TempOutputRoot, seed_everything
from tests._cfg import TestOptConfig
from tests._typing import as_opt_config

from opt.opt_diagnostics import build_strategy_scoreboard

SCOREBOARD_KEYS = (
    "realized_ge_H_rate",
    "base_rate_ge_H",
    "qany_ece",
    "qany_brier",
    "net_eur",
    "baseline_net_eur",
    "edge_eur",
)


def _diag_rows() -> List[Dict[str, Any]]:
    return [
        {"optimizer": "greedy", "dataset_index": 101, "tickets_count": 2, "tickets": "x",
         "q_per_ticket": "[0.1]", "q_any": 0.20, "hit_threshold": 3,
         "realized_max_hits": 2, "success_ge_H": 0, "profit": -2.0, "arm": ""},
        {"optimizer": "greedy", "dataset_index": 102, "tickets_count": 2, "tickets": "x",
         "q_per_ticket": "[0.2]", "q_any": 0.30, "hit_threshold": 3,
         "realized_max_hits": 3, "success_ge_H": 1, "profit": 10.0, "arm": ""},
        {"optimizer": "milp", "dataset_index": 103, "tickets_count": 1, "tickets": "y",
         "q_per_ticket": "[0.05]", "q_any": 0.05, "hit_threshold": 3,
         "realized_max_hits": 0, "success_ge_H": 0, "profit": -1.0, "arm": ""},
    ]


def _baseline() -> Dict[str, Any]:
    # net_eur aggregate plus per-draw best hits so base_rate_ge_H can be computed for any H.
    return {"net_eur": -8.0, "best_hits_per_draw": [0, 1, 3, 2]}


class TestScoreboardFunction(unittest.TestCase):
    def test_edge_eur_is_net_minus_baseline(self) -> None:
        df = pd.DataFrame(_diag_rows())
        board = build_strategy_scoreboard(df, baseline=_baseline(), n_bins=10)
        self.assertIn("greedy", board)
        g = board["greedy"]
        # greedy net = -2 + 10 = 8; baseline net = -8 -> edge = 16
        self.assertEqual(g["net_eur"], 8.0)
        self.assertEqual(g["baseline_net_eur"], -8.0)
        self.assertEqual(g["edge_eur"], g["net_eur"] - g["baseline_net_eur"])
        self.assertEqual(g["edge_eur"], 16.0)
        # greedy realized >=H over its 2 draws = 0.5
        self.assertEqual(g["realized_ge_H_rate"], 0.5)
        # baseline best hits [0,1,3,2] >= H=3 -> 1/4
        self.assertEqual(g["base_rate_ge_H"], 0.25)

    def test_all_keys_numeric(self) -> None:
        df = pd.DataFrame(_diag_rows())
        board = build_strategy_scoreboard(df, baseline=_baseline(), n_bins=10)
        for opt, row in board.items():
            for key in SCOREBOARD_KEYS:
                self.assertIn(key, row, f"{opt} missing {key}")
                self.assertIsInstance(row[key], float, f"{opt}.{key} must be numeric")


class TestSummaryArtifactScoreboard(unittest.TestCase):
    def setUp(self) -> None:
        seed_everything(12345)

    def _make_cfg(self, root: Path) -> TestOptConfig:
        opt_dir = root / "Output" / "Reports" / "Optimization"
        diag_dir = opt_dir / "Diagnostics"
        for d in [opt_dir, opt_dir / "State", diag_dir, diag_dir / "history", opt_dir / "Graphs"]:
            d.mkdir(parents=True, exist_ok=True)
        return TestOptConfig(
            exports_dir=str(root / "Output" / "Reports" / "Exports" / "StatGrid"),
            ts_list=["TS_1", "TS_2", "TS_3"],
            opt_dir=opt_dir,
            state_dir=opt_dir / "State",
            diag_dir=diag_dir,
            diag_history_dir=diag_dir / "history",
            graphs_dir=opt_dir / "Graphs",
            calibration_bins=8,
            code_version="qa-test",
            seed=12345,
        )

    def test_summary_contains_scoreboard_keys(self) -> None:
        with TempOutputRoot() as root:
            cfg0 = self._make_cfg(root)
            cfg = as_opt_config(cfg0)
            from opt.opt_diagnostics import ensure_dirs, write_final_summary

            ensure_dirs(cfg)
            diag_df = pd.DataFrame(_diag_rows())
            calib_df = pd.DataFrame()
            results = {"greedy": {"roi_total": 0.1}, "milp": {"roi_total": -0.5}}

            write_final_summary(
                cfg, "opt_x", "grid_x", {}, {}, results, diag_df, calib_df,
                baseline=_baseline(),
            )

            summary = json.loads((cfg0.opt_dir / "summary_current.json").read_text(encoding="utf-8"))
            self.assertIn("scoreboard", summary)
            board = summary["scoreboard"]
            for opt in ("greedy", "milp"):
                self.assertIn(opt, board)
                for key in SCOREBOARD_KEYS:
                    self.assertIn(key, board[opt])
                    self.assertIsInstance(board[opt][key], (int, float))


if __name__ == "__main__":
    unittest.main()
