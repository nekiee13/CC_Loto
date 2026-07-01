# -----------------------
# tests/contract/test_optimizer_choices.py
# -----------------------
"""
E6.1/E6.2 — optimizer selection gate.

Why: `evo` (run_evolutionary) was once a deterministic stub silently included in the
``--optimizer all`` fan-out. E6.1 excluded it from `all` and flagged it; E6.2 replaced the stub
with a real seeded genetic search. `evo` stays out of the default `all` fan-out — not because it's
a stub, but because it's an expensive hyperparameter search — and remains explicitly selectable
(opt-in), with its opt-in status surfaced. This pins:
  (1) `evo` is registered as non-default (``NON_DEFAULT_OPTIMIZERS``),
  (2) `all` never silently includes it,
  (3) it stays explicitly selectable, and the opt-in status surfaces via `non_default_optimizers_selected()`.

Contract-level assertions on the pure selection logic — no torch/darts/grid needed.
"""
from __future__ import annotations

import unittest

from opt.opt_config import OptConfig, NON_DEFAULT_OPTIMIZERS


class TestOptimizerChoices(unittest.TestCase):
    def test_evo_is_non_default_and_opt_in(self) -> None:
        # (1) evo is registered as non-default (opt-in).
        self.assertIn("evo", NON_DEFAULT_OPTIMIZERS)

        # (2) `all` must NOT silently include the opt-in optimizer.
        all_sel = OptConfig(optimizer="all").which_optimizers()
        self.assertNotIn("evo", all_sel)
        self.assertEqual(all_sel, {"greedy", "milp", "bandit"})

        # (3) explicit `evo` is still selectable, and its opt-in status surfaces.
        evo_cfg = OptConfig(optimizer="evo")
        self.assertEqual(evo_cfg.which_optimizers(), {"evo"})
        self.assertEqual(evo_cfg.non_default_optimizers_selected(), {"evo"})

        # A default explicit selection surfaces nothing.
        self.assertEqual(OptConfig(optimizer="greedy").non_default_optimizers_selected(), set())
        # And `all` (evo excluded) surfaces no opt-in optimizers either.
        self.assertEqual(OptConfig(optimizer="all").non_default_optimizers_selected(), set())


if __name__ == "__main__":
    unittest.main()
