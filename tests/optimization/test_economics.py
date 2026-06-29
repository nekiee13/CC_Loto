# -----------------------
# tests/optimization/test_economics.py
# -----------------------
"""
E1.1 — pure portfolio-economics function.

Why: the per-ticket payout math (`payout_by_hits.get(h) - ticket_cost_eur`, summed) is
currently inlined identically in all four strategy loops in `opt_strategies.py`. Isolating it
as a pure, known-answer-tested function makes the upcoming EV/ROI scoreboard (E1.4) trustworthy
and removes that duplication. These tests pin the exact arithmetic.
"""
from __future__ import annotations

import unittest

from opt.opt_strategies import compute_portfolio_economics


class TestPortfolioEconomics(unittest.TestCase):
    def test_net_eur_known_case(self) -> None:
        # true = all ones; A hits 7, B hits 3, C hits 0.
        true_ticket = (1, 2, 3, 4, 5, 6, 7)
        tickets = [
            (1, 2, 3, 4, 5, 6, 7),  # 7 hits
            (1, 2, 3, 0, 0, 0, 0),  # 3 hits
            (0, 0, 0, 0, 0, 0, 0),  # 0 hits
        ]
        payout = {0: 0.0, 3: 10.0, 7: 1000.0}
        econ = compute_portfolio_economics(
            tickets, true_ticket, payout_by_hits=payout, ticket_cost_eur=2.0
        )
        self.assertEqual(econ["gross_eur"], 1010.0)   # 1000 + 10 + 0
        self.assertEqual(econ["cost_eur"], 6.0)        # 3 tickets * 2.0
        self.assertEqual(econ["net_eur"], 1004.0)      # 1010 - 6
        self.assertEqual(econ["best_hits"], 7)

    def test_zero_hits_is_pure_loss(self) -> None:
        true_ticket = (1, 1, 1, 1)
        tickets = [(0, 0, 0, 0), (2, 2, 2, 2)]  # zero hits each
        payout = {0: 0.0, 3: 10.0, 4: 50.0}
        econ = compute_portfolio_economics(
            tickets, true_ticket, payout_by_hits=payout, ticket_cost_eur=2.0
        )
        self.assertEqual(econ["gross_eur"], 0.0)
        self.assertEqual(econ["cost_eur"], 4.0)
        self.assertEqual(econ["net_eur"], -4.0)  # -K * cost
        self.assertEqual(econ["best_hits"], 0)

    def test_uses_best_hits_per_ticket(self) -> None:
        # Payout must key off EACH ticket's own hit count, not the portfolio max.
        true_ticket = (1, 2, 3, 4)
        tickets = [
            (1, 2, 0, 0),  # 2 hits -> 5
            (1, 2, 3, 4),  # 4 hits -> 50
        ]
        payout = {2: 5.0, 4: 50.0}
        econ = compute_portfolio_economics(
            tickets, true_ticket, payout_by_hits=payout, ticket_cost_eur=1.0
        )
        self.assertEqual(econ["gross_eur"], 55.0)  # 5 + 50, NOT 100 (would be if both used max=4)
        self.assertEqual(econ["cost_eur"], 2.0)
        self.assertEqual(econ["net_eur"], 53.0)
        self.assertEqual(econ["best_hits"], 4)

    def test_empty_portfolio_is_zero(self) -> None:
        econ = compute_portfolio_economics(
            [], (1, 2, 3), payout_by_hits={3: 10.0}, ticket_cost_eur=2.0
        )
        self.assertEqual(econ["gross_eur"], 0.0)
        self.assertEqual(econ["cost_eur"], 0.0)
        self.assertEqual(econ["net_eur"], 0.0)
        self.assertEqual(econ["best_hits"], 0)


if __name__ == "__main__":
    unittest.main()
