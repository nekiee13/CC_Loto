# -----------------------
# tests/contract/test_optimizer_choices.py
# -----------------------
"""
E6.1 — decision gate + honesty fix for the evolutionary optimizer.

Why: ``run_evolutionary`` is a deterministic stub, but ``evo`` was presented as a first-class
optimizer and silently included in the ``--optimizer all`` fan-out. Shipping a stub as a real
feature is misleading. Until a genuine implementation lands (E6.2), ``evo`` must be:
  (1) registered as experimental (``EXPERIMENTAL_OPTIMIZERS``),
  (2) excluded from ``all`` so it never runs unless explicitly requested,
  (3) still explicitly selectable (opt-in), but with its experimental status surfaced.

These are contract-level assertions on the pure selection logic — no torch/darts/grid needed.
"""
from __future__ import annotations

import unittest

from opt.opt_config import OptConfig, EXPERIMENTAL_OPTIMIZERS


class TestOptimizerChoices(unittest.TestCase):
    def test_evo_marked_experimental(self) -> None:
        # (1) evo is registered as experimental.
        self.assertIn("evo", EXPERIMENTAL_OPTIMIZERS)

        # (2) `all` must NOT silently include the experimental stub.
        all_sel = OptConfig(optimizer="all").which_optimizers()
        self.assertNotIn("evo", all_sel)
        self.assertEqual(all_sel, {"greedy", "milp", "bandit"})

        # (3) explicit `evo` is still selectable (opt-in), and its experimental status surfaces.
        evo_cfg = OptConfig(optimizer="evo")
        self.assertEqual(evo_cfg.which_optimizers(), {"evo"})
        self.assertEqual(evo_cfg.experimental_optimizers_selected(), {"evo"})

        # A non-experimental explicit selection surfaces nothing.
        self.assertEqual(OptConfig(optimizer="greedy").experimental_optimizers_selected(), set())
        # And `all` (evo excluded) surfaces no experimental optimizers either.
        self.assertEqual(OptConfig(optimizer="all").experimental_optimizers_selected(), set())


if __name__ == "__main__":
    unittest.main()
