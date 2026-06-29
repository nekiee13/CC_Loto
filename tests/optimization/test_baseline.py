# -----------------------
# tests/optimization/test_baseline.py
# -----------------------
"""
E1.2 — random-ticket control baseline.

Why: "net EUR" is meaningless without a control. A seeded random portfolio drawn from the same
per-position observed-value distribution is the fair, negative-EV baseline the strategy must
beat. These tests pin determinism, that samples stay inside the observed pools, and that the
aggregate reuses the E1.1 economics.
"""
from __future__ import annotations

import random
import unittest

from opt.opt_config import OptConfig
from opt.opt_strategies import (
    random_ticket_baseline,
    sample_random_ticket,
)


def _pools() -> dict:
    # Frequency-weighted observed pools (duplicates encode empirical frequency).
    return {
        "TS_1": [1, 2, 2, 3],
        "TS_2": [10, 11, 12],
        "TS_3": [7, 7, 8],
    }


def _cfg() -> OptConfig:
    return OptConfig(ts_list=["TS_1", "TS_2", "TS_3"], ticket_cost_eur=2.0)


class TestRandomTicketBaseline(unittest.TestCase):
    def test_baseline_is_deterministic_under_seed(self) -> None:
        pools, ts_list = _pools(), ["TS_1", "TS_2", "TS_3"]
        # Sampler is reproducible given the same seed.
        r1, r2 = random.Random(7), random.Random(7)
        seq1 = [sample_random_ticket(r1, pools, ts_list) for _ in range(5)]
        seq2 = [sample_random_ticket(r2, pools, ts_list) for _ in range(5)]
        self.assertEqual(seq1, seq2)
        # And the whole aggregate is reproducible.
        cfg = _cfg()
        a = random_ticket_baseline(cfg, pools, seed=42, n_tickets=3, n_draws=8)
        b = random_ticket_baseline(cfg, pools, seed=42, n_tickets=3, n_draws=8)
        self.assertEqual(a, b)

    def test_baseline_values_within_observed_pools(self) -> None:
        pools, ts_list = _pools(), ["TS_1", "TS_2", "TS_3"]
        rng = random.Random(1)
        for _ in range(100):
            ticket = sample_random_ticket(rng, pools, ts_list)
            self.assertEqual(len(ticket), len(ts_list))
            for ts, value in zip(ts_list, ticket):
                self.assertIn(value, pools[ts])

    def test_baseline_economics_shape(self) -> None:
        cfg = _cfg()
        summary = random_ticket_baseline(cfg, _pools(), seed=3, n_tickets=2, n_draws=10)
        for key in ("gross_eur", "cost_eur", "net_eur", "best_hits"):
            self.assertIn(key, summary)
        # Aggregated over draws: cost = n_draws * n_tickets * ticket_cost_eur.
        self.assertEqual(summary["cost_eur"], 10 * 2 * 2.0)
        self.assertEqual(summary["net_eur"], summary["gross_eur"] - summary["cost_eur"])
        self.assertEqual(summary["draws"], 10)


if __name__ == "__main__":
    unittest.main()
