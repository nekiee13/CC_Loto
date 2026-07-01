# -----------------------
# tests/contract/test_logging_unified.py
# -----------------------
"""
E8.1 — unify long-run output on the ``logging`` module.

Why: progress/status output for long backtests was emitted via bare
``print("[OPT] …")`` / ``print("[STAT] …")`` calls. That output is not level-controlled
(``--quiet`` can't silence it) and mixes with real stdout. Routing it through module loggers
makes it greppable, level-controlled, and lets ``--quiet`` map to a log level.

This test scans the application sources (``opt/`` and ``src/dynamix/``) and fails if any
``print(...)`` call emits an ``[OPT]`` or ``[STAT]`` progress line. The tags must be exact
(closing ``]`` required), so ``[STAT-REPORT]`` — which is genuine report *content* captured to a
file via ``sys.stdout`` redirection in ``stat_report.py``, not level-controlled progress — is out
of scope. The regex allows ``\\s*`` between ``print(`` and the string literal so multi-line
``print(\\n  "[OPT] …")`` calls are caught too.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# Source trees that must be logging-only for these tags (tests are exempt).
SOURCE_GLOBS = [
    (REPO_ROOT / "opt", "*.py"),
    (REPO_ROOT / "src" / "dynamix", "*.py"),
]

# print( [ optional f ] [ quote ] [OPT] or [STAT] (exact tag, closing ] required) — whitespace
# (incl. newlines) allowed between the paren and the string literal so multi-line calls match.
BRACKET_PRINT = re.compile(r"""print\(\s*f?["']\[(?:OPT|STAT)\]""")


def _iter_sources() -> List[Path]:
    files: List[Path] = []
    for base, pattern in SOURCE_GLOBS:
        files.extend(sorted(base.rglob(pattern)))
    return files


class TestLoggingUnified(unittest.TestCase):
    def test_no_bare_bracket_prints_in_sources(self) -> None:
        offenders: List[Tuple[str, int]] = []
        for path in _iter_sources():
            text = path.read_text(encoding="utf-8")
            for m in BRACKET_PRINT.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                offenders.append((str(path.relative_to(REPO_ROOT)), line_no))

        self.assertEqual(
            offenders,
            [],
            "Tagged [OPT]/[STAT] output must go through logging, not print(). Offenders:\n"
            + "\n".join(f"  {p}:{ln}" for p, ln in offenders),
        )


if __name__ == "__main__":
    unittest.main()
