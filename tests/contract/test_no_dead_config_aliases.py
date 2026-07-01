# -----------------------
# tests/contract/test_no_dead_config_aliases.py
# -----------------------
"""
E8.2 — prune dead configuration aliases.

Why: ``constants.py`` carried backward-compat aliases (``PROJECT_ROOT``, ``OUTPUT_PLOTS_DIR``,
``DARTS_EPOCHS``) that duplicate canonical names (``REPO_ROOT``, ``OUTPUT_GRAPHS_DIR``,
``DARTS_N_EPOCHS``). Dead/duplicate config misleads readers about what actually drives behavior.

Acceptance (from the plan): each removed name has **zero references repo-wide** before deletion.
This test pins both halves: (1) the constants module no longer defines the aliases, and (2) no
application source (``opt/``, ``src/dynamix/``, ``tools/``) reads them by name. The readers were
repointed to the canonical constants (behavior-identical), so nothing is lost.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import List, Tuple

from dynamix import constants as C

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOVED_ALIASES = ["PROJECT_ROOT", "OUTPUT_PLOTS_DIR", "DARTS_EPOCHS"]

SOURCE_DIRS = [REPO_ROOT / "opt", REPO_ROOT / "src" / "dynamix", REPO_ROOT / "tools"]
THIS_FILE = Path(__file__).resolve()


class TestNoDeadConfigAliases(unittest.TestCase):
    def test_aliases_not_defined_on_constants(self) -> None:
        for name in REMOVED_ALIASES:
            self.assertFalse(
                hasattr(C, name),
                f"constants.{name} is a pruned alias and must not be defined (use the canonical name)",
            )

    def test_aliases_have_zero_references_in_sources(self) -> None:
        offenders: List[Tuple[str, int, str]] = []
        patterns = {name: re.compile(rf"\b{name}\b") for name in REMOVED_ALIASES}
        for base in SOURCE_DIRS:
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.py")):
                if path.resolve() == THIS_FILE:
                    continue
                for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    for name, pat in patterns.items():
                        if pat.search(line):
                            offenders.append((str(path.relative_to(REPO_ROOT)), i, name))
        self.assertEqual(
            offenders,
            [],
            "Pruned aliases still referenced (repoint to canonical names):\n"
            + "\n".join(f"  {p}:{ln}  {name}" for p, ln, name in offenders),
        )


if __name__ == "__main__":
    unittest.main()
