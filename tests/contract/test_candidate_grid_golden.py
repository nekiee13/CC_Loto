# -----------------------
# tests/contract/test_candidate_grid_golden.py
# -----------------------
"""
E4.1 — golden characterization test for the candidate-grid row builder.

Why: before E4 moves the forecasting-collection / candidate-grid logic out of the ~1600-line
`dynamix.stat` god-module, we lock its current output exactly. `build_candidate_grid_rows` is
pure given an injected `model_forecasts` map (the model runtime is irrelevant here), so a
committed golden snapshot makes the upcoming move provably behavior-preserving.

The golden file is written on first run, then frozen; later runs compare against it.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from dynamix.stat import build_candidate_grid_rows, TS_LIST, MODEL_NAMES
from opt.opt_data import REQUIRED_COLS

GOLDEN = Path(__file__).resolve().parent / "golden" / "candidate_grid_golden.json"

SORT_KEYS = ("ts", "model", "rounding_id")


def _fixture_inputs():
    # Two TS positions exercised (others in TS_LIST get no forecast -> no rows).
    ts0, ts1 = TS_LIST[0], TS_LIST[1]
    # Preds chosen to differentiate all 7 rounding modes (.5 boundaries) incl. a negative value.
    model_forecasts: Dict[str, Dict[str, float]] = {
        "DynaMix": {ts0: 2.5, ts1: -1.5},
        "PCE": {ts0: 4.49, ts1: 3.5},
    }
    true_row = pd.Series({ts: 0 for ts in TS_LIST})
    true_row[ts0] = 3
    true_row[ts1] = -2
    return model_forecasts, true_row


def _produce_rows() -> List[Dict[str, Any]]:
    model_forecasts, true_row = _fixture_inputs()
    rows = build_candidate_grid_rows(
        run_id="golden_run",
        export_mode="full",
        model_forecasts=model_forecasts,
        true_row=true_row,
        dataset_index=42,
        step_num=7,
        step_date="2026-01-01",
        effective_window=100,
    )
    return sorted(rows, key=lambda r: tuple(r[k] for k in SORT_KEYS))


class TestCandidateGridGolden(unittest.TestCase):
    def test_grid_rows_match_golden(self) -> None:
        rows = _produce_rows()
        # 2 TS x 2 models x 7 rounding modes.
        self.assertEqual(len(rows), 2 * 2 * 7)

        if not GOLDEN.exists():
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
            self.skipTest(f"golden written to {GOLDEN}; re-run to compare")

        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        # JSON round-trips ints/floats; normalize both sides via json for stable comparison.
        got = json.loads(json.dumps(rows))
        self.assertEqual(got, expected)

    def test_grid_schema_matches_required_cols(self) -> None:
        rows = _produce_rows()
        self.assertTrue(rows)
        cols = set(rows[0].keys())
        missing = REQUIRED_COLS - cols
        self.assertEqual(missing, set(), f"grid rows missing optimizer-required cols: {missing}")
        # Every row carries the same schema.
        for r in rows:
            self.assertEqual(set(r.keys()), cols)

    def test_rounding_modes_all_present_per_cell(self) -> None:
        # Each (ts, model) cell must emit exactly the 7 rounding ids 1..7.
        rows = _produce_rows()
        by_cell: Dict[tuple, list] = {}
        for r in rows:
            by_cell.setdefault((r["ts"], r["model"]), []).append(int(r["rounding_id"]))
        for cell, rids in by_cell.items():
            self.assertEqual(sorted(rids), [1, 2, 3, 4, 5, 6, 7], f"cell {cell}")


if __name__ == "__main__":
    unittest.main()
