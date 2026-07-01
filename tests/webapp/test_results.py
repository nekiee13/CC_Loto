# -----------------------
# tests/webapp/test_results.py
# -----------------------
"""
G6.1 — forecast.json parser (`dynamix.webapp.results`).

Turns the raw `forecast.json` the orchestrator writes into a tidy, friendly view: up-to-5 tickets
(TS_1..TS_7 per ticket) with per-ticket q, plus metadata (run id, timestamp, q_any). Pure and
Streamlit-free; tolerates missing/partial/malformed files by returning an "empty" view rather than
raising.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dynamix.webapp import results

SAMPLE = {
    "forecast_dataset_index": 561,
    "generated_at": "2026-07-01T10:00:00",
    "max_tickets": 5,
    "tickets_count": 2,
    "tickets": [[3, 10, 25, 32, 43, 1, 3], [6, 12, 35, 39, 49, 4, 9]],
    "q_per_ticket": [0.0123, 0.0098],
    "q_any": 0.0219,
    "grid_run_id": "statgrid_x_full",
    "opt_run_id": "opt_123",
}


class TestResults(unittest.TestCase):
    def _tmp(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_parses_full_forecast(self) -> None:
        p = self._tmp() / "forecast.json"
        p.write_text(json.dumps(SAMPLE), encoding="utf-8")
        view = results.load_forecast(p)

        self.assertTrue(view.ok, view.error)
        self.assertEqual(len(view.tickets), 2)
        self.assertEqual(view.tickets[0], [3, 10, 25, 32, 43, 1, 3])
        self.assertEqual(view.q_any, 0.0219)
        self.assertEqual(view.grid_run_id, "statgrid_x_full")
        self.assertEqual(view.opt_run_id, "opt_123")
        self.assertEqual(view.generated_at, "2026-07-01T10:00:00")

    def test_ticket_rows_shape(self) -> None:
        p = self._tmp() / "forecast.json"
        p.write_text(json.dumps(SAMPLE), encoding="utf-8")
        rows = results.load_forecast(p).ticket_rows()
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["Ticket"], 1)
        for i in range(1, 8):
            self.assertIn(f"TS_{i}", first)
        self.assertEqual(first["TS_1"], 3)
        self.assertAlmostEqual(first["q"], 0.0123, places=6)

    def test_missing_file(self) -> None:
        view = results.load_forecast(self._tmp() / "nope.json")
        self.assertFalse(view.ok)
        self.assertIsNotNone(view.error)
        self.assertEqual(view.tickets, [])

    def test_malformed_json(self) -> None:
        p = self._tmp() / "forecast.json"
        p.write_text("{not valid json", encoding="utf-8")
        view = results.load_forecast(p)
        self.assertFalse(view.ok)
        self.assertIsNotNone(view.error)

    def test_partial_forecast_is_empty_view_not_error(self) -> None:
        p = self._tmp() / "forecast.json"
        p.write_text(json.dumps({"generated_at": "2026-07-01T10:00:00"}), encoding="utf-8")
        view = results.load_forecast(p)
        self.assertTrue(view.ok, "a parseable file with no tickets is a valid (empty) view")
        self.assertEqual(view.tickets, [])
        self.assertIsNone(view.q_any)


if __name__ == "__main__":
    unittest.main()
