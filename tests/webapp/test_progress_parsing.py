# -----------------------
# tests/webapp/test_progress_parsing.py
# -----------------------
"""Regression tests for the webapp progress bar's log parsing.

Covers the three fixes: (1) the real training loop line is a canonical
``progress:`` line with a parseable ``eta=``; (2) the latest progress line
supersedes a stale one (so a finished full-rebuild pass can't pin the bar at
100%); (3) date-like ``d/d/d`` pairs never hijack the fallback; and the coarse
forecast-stage progress lines parse.
"""
from __future__ import annotations

import unittest

from dynamix.webapp import runner


class TestProgressParsingFixes(unittest.TestCase):
    def test_stat_main_loop_line_parses_with_eta(self) -> None:
        # Mirrors the exact format emitted by dynamix.stat's backtest loop.
        line = "[STAT] progress: 5/613 (dataset index=239,   0.8%) | elapsed=0:12 | eta=25:03"
        self.assertEqual(runner.parse_progress(line), (5, 613))
        self.assertEqual(runner.parse_eta(line), "25:03")

    def test_latest_progress_supersedes_stale_rebuild(self) -> None:
        # After the full-rebuild pass hits 100%, the main loop restarts at step 1;
        # the newer progress line must win so the bar doesn't stick at 100%.
        text = (
            "[STAT] Full export rebuild progress: 512/512 (100.0%) | Elapsed:    42.0s\n"
            "[STAT] progress: 3/613 (dataset index=61,   0.5%) | elapsed=0:03 | eta=10:11\n"
        )
        self.assertEqual(runner.parse_progress(text), (3, 613))

    def test_date_like_pairs_are_ignored(self) -> None:
        # A bare date must not be read as progress.
        self.assertIsNone(runner.parse_progress("[STAT] loaded draws through 30/05/2017\n"))
        # A real pair on a date-bearing line is still found.
        text = "processed up to 30/05/2017 — step 7/613\n"
        self.assertEqual(runner.parse_progress(text), (7, 613))

    def test_forecast_stage_progress_parses(self) -> None:
        text = (
            "[OPT][forecast] progress: 4/6 (candidate grid built) | elapsed=0:03\n"
            "[OPT][forecast] progress: 6/6 (report written) | elapsed=0:05\n"
        )
        self.assertEqual(runner.parse_progress(text), (6, 6))


if __name__ == "__main__":
    unittest.main()
