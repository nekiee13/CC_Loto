# -----------------------
# tests/contract/test_grid_dedupe.py
# -----------------------
"""
E7.1 — distinct-value candidate-grid encoding (de-dupe), behind a flag.

Why: the 7 rounding modes mostly produce identical integers (they differ only at .5
boundaries), so the legacy grid stores ~7x more rows than there are distinct candidate values.
Storing one row per distinct ``(ts, model, rounded)`` value — carrying the set of rounding_ids
that produced it — cuts export/disk I/O with no information loss.

Hard constraint: the optimizer's output must be unchanged. The optimizer's candidate features
(`consensus_count`, abs_err percentile, rank) depend on row multiplicity, so `opt_data`
re-expands the deduped grid back to the exact legacy per-rounding rows (same values, same order)
on load. These tests pin: (1) no distinct value lost, (2) row count strictly drops when modes
collide, (3) re-expansion reproduces the legacy grid byte-for-byte (=> identical optimizer input).
"""
from __future__ import annotations

import unittest
from typing import Any, Dict, List

import pandas as pd

from dynamix.candidate_grid import (
    build_candidate_grid_rows,
    build_candidate_grid_rows_deduped,
    TS_LIST,
)
from opt.opt_data import expand_deduped_grid

CMP_COLS = ["dataset_index", "ts", "model", "rounding_id", "rounded", "true", "hit", "pred", "abs_err"]


def _legacy_rows() -> List[Dict[str, Any]]:
    ts0, ts1 = TS_LIST[0], TS_LIST[1]
    model_forecasts = {
        "DynaMix": {ts0: 2.5, ts1: -1.5},
        "PCE": {ts0: 4.49, ts1: 3.5},
    }
    true_row = pd.Series({ts: 0 for ts in TS_LIST})
    true_row[ts0] = 3
    true_row[ts1] = -2
    kw = dict(
        run_id="r", export_mode="full", model_forecasts=model_forecasts, true_row=true_row,
        dataset_index=42, step_num=7, step_date="2026-01-01", effective_window=100,
    )
    return build_candidate_grid_rows(**kw), build_candidate_grid_rows_deduped(**kw)


def _as_tuples(df: pd.DataFrame) -> List[tuple]:
    return [tuple(r) for r in df[CMP_COLS].itertuples(index=False)]


class TestGridDedupe(unittest.TestCase):
    def test_dedupe_preserves_distinct_values(self) -> None:
        legacy, deduped = _legacy_rows()
        legacy_vals = {(r["ts"], r["model"], r["rounded"]) for r in legacy}
        deduped_vals = {(r["ts"], r["model"], r["rounded"]) for r in deduped}
        self.assertEqual(deduped_vals, legacy_vals, "no distinct (ts,model,rounded) value may be lost")

        # Every deduped row carries the rounding_ids that produced it; per cell they cover all 7.
        per_cell: Dict[tuple, set] = {}
        for r in deduped:
            self.assertIn("rounding_ids", r)
            ids = {int(x) for x in str(r["rounding_ids"]).split(",")}
            per_cell.setdefault((r["ts"], r["model"]), set()).update(ids)
        for cell, ids in per_cell.items():
            self.assertEqual(ids, {1, 2, 3, 4, 5, 6, 7}, f"cell {cell} must account for all rounding modes")

    def test_dedupe_row_count_le_legacy(self) -> None:
        legacy, deduped = _legacy_rows()
        self.assertLessEqual(len(deduped), len(legacy))
        # The .5-boundary fixture forces collisions, so the reduction is strict.
        self.assertLess(len(deduped), len(legacy))

    def test_optimizer_results_unchanged_under_dedupe(self) -> None:
        legacy, deduped = _legacy_rows()
        legacy_df = pd.DataFrame(legacy)
        deduped_df = pd.DataFrame(deduped)
        expanded = expand_deduped_grid(deduped_df)
        # Byte-for-byte identical optimizer input: same rows, same order.
        self.assertEqual(_as_tuples(expanded), _as_tuples(legacy_df))

    def test_expand_is_passthrough_for_legacy_grid(self) -> None:
        legacy, _ = _legacy_rows()
        legacy_df = pd.DataFrame(legacy)
        out = expand_deduped_grid(legacy_df)
        self.assertEqual(_as_tuples(out), _as_tuples(legacy_df))


if __name__ == "__main__":
    unittest.main()
