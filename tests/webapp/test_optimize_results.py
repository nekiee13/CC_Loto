# -----------------------
# tests/webapp/test_optimize_results.py
# -----------------------
"""
V1.1 — optimize summary/scoreboard parser (`dynamix.webapp.optimize_results`).

Turns the optimizer's `summary_current.json` (the E1.4 honest scoreboard) into tidy per-optimizer
rows with an EDGE / no-edge verdict, plus a locator for the newest summary. Pure and Streamlit-free;
missing/malformed files degrade to an empty view rather than raising.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dynamix.webapp import optimize_results as opt_results

SAMPLE = {
    "generated_at": "2026-07-01T12:00:00",
    "opt_run_id": "opt_1",
    "grid_run_id": "statgrid_x",
    "baseline": {"net_eur": -8.0},
    "scoreboard": {
        "greedy": {
            "realized_ge_H_rate": 0.42, "base_rate_ge_H": 0.30,
            "qany_ece": 0.05, "qany_brier": 0.2,
            "net_eur": -3.0, "baseline_net_eur": -8.0, "edge_eur": 5.0,
        },
        "milp": {
            "realized_ge_H_rate": 0.28, "base_rate_ge_H": 0.30,
            "qany_ece": 0.09, "qany_brier": 0.25,
            "net_eur": -9.0, "baseline_net_eur": -8.0, "edge_eur": -1.0,
        },
    },
}


class TestOptimizeResults(unittest.TestCase):
    def _tmp(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_parses_scoreboard_with_verdicts(self) -> None:
        p = self._tmp() / "summary_current.json"
        p.write_text(json.dumps(SAMPLE), encoding="utf-8")
        view = opt_results.load_summary(p)

        self.assertTrue(view.ok, view.error)
        self.assertEqual(view.grid_run_id, "statgrid_x")
        rows = view.scoreboard_rows()
        self.assertEqual(len(rows), 2)
        by_opt = {r["Optimizer"]: r for r in rows}
        self.assertEqual(by_opt["greedy"]["verdict"], "EDGE")
        self.assertEqual(by_opt["greedy"]["edge_eur"], 5.0)
        self.assertEqual(by_opt["milp"]["verdict"], "no edge")
        self.assertTrue(view.any_edge())

    def test_missing_file(self) -> None:
        view = opt_results.load_summary(self._tmp() / "nope.json")
        self.assertFalse(view.ok)
        self.assertIsNotNone(view.error)
        self.assertEqual(view.scoreboard_rows(), [])

    def test_malformed_json(self) -> None:
        p = self._tmp() / "summary_current.json"
        p.write_text("{bad json", encoding="utf-8")
        self.assertFalse(opt_results.load_summary(p).ok)

    def test_latest_summary_prefers_current(self) -> None:
        d = self._tmp()
        (d / "summary_current.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
        found = opt_results.latest_summary(opt_dir=d)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "summary_current.json")

    def test_latest_summary_none_when_absent(self) -> None:
        self.assertIsNone(opt_results.latest_summary(opt_dir=self._tmp()))


if __name__ == "__main__":
    unittest.main()
