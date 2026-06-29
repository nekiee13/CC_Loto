# -----------------------
# tests/integration/test_orchestrator_uses_module.py
# -----------------------
"""
E4.2 — the forecasting-collection logic is a first-class importable module.

Why: `collect_model_forecasts_for_step` / `build_candidate_grid_rows` were extracted from the
~1600-line `dynamix.stat` god-module into `dynamix.candidate_grid`. The orchestrator must import
them directly from that package module (never a path-loaded copy), and `dynamix.stat` must keep
re-exporting the *same* objects for backward compatibility.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import dynamix.candidate_grid as cg
import dynamix.entrypoints.orchestrator as orch
import dynamix.stat as stat

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCH_SRC = REPO_ROOT / "src" / "dynamix" / "entrypoints" / "orchestrator.py"


class TestOrchestratorUsesModule(unittest.TestCase):
    def test_orchestrator_imports_collector_from_package(self) -> None:
        # The names the orchestrator calls resolve to dynamix.candidate_grid, not a path-loaded copy.
        self.assertIs(orch.collect_model_forecasts_for_step, cg.collect_model_forecasts_for_step)
        self.assertIs(orch.build_candidate_grid_rows, cg.build_candidate_grid_rows)

    def test_stat_reexports_are_same_objects(self) -> None:
        for name in (
            "collect_model_forecasts_for_step",
            "build_candidate_grid_rows",
            "apply_round",
            "RoundingMode",
            "rounding_mode_id",
            "TS_LIST",
            "MODEL_NAMES",
        ):
            self.assertIs(getattr(stat, name), getattr(cg, name), f"stat.{name} must re-export cg.{name}")

    def test_orchestrator_has_no_load_by_path(self) -> None:
        src = ORCH_SRC.read_text(encoding="utf-8")
        self.assertNotIn("spec_from_file_location", src)
        self.assertNotIn("_import_project_stat_module", src)
        self.assertFalse(re.search(r"\bsys\.path\.(insert|append)\b", src),
                         "orchestrator must not manipulate sys.path")


if __name__ == "__main__":
    unittest.main()
