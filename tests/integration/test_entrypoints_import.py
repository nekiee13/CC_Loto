# -----------------------
# tests/integration/test_entrypoints_import.py
# -----------------------
"""
E3.1 — Import/exec smoke tests for the user-facing entrypoints.

Why: a hard import failure in an entrypoint (e.g. a wrong/legacy module name, or a
missing sys.path bootstrap) is invisible to the rest of the suite, which exercises
library internals rather than the scripts a user actually runs. This guards exactly
that class of breakage (the kind that previously reached orchestrator.py / stat_report.py).

How: each repo-root entrypoint is loaded *by file path* and its module body is executed,
then we assert it exposes a callable ``main``. We load by path (not ``import stat``)
because ``import stat`` resolves to the Python standard-library ``stat`` module, and
because ``python <script>`` executes the file directly anyway.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# Repo layout: <root>/tests/integration/this_file.py  ->  parents[2] == <root>
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
for _p in (str(REPO_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_by_path(module_name: str, filename: str):
    """Execute a repo-root script as a module and return it."""
    path = REPO_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Entrypoints that must import cleanly with only the core dependencies installed.
# (Optional model deps — torch/darts/chaospy/pulp — are import-guarded and fail soft.)
CORE_ENTRYPOINTS = [
    ("dynamix_entry_run_cli", "run_cli.py"),
    ("dynamix_entry_stat", "stat.py"),
    ("dynamix_entry_orchestrator", "orchestrator.py"),
    ("dynamix_entry_stat_report", "stat_report.py"),
]


class TestEntrypointsImport(unittest.TestCase):
    def test_core_entrypoints_import_and_expose_main(self) -> None:
        for module_name, filename in CORE_ENTRYPOINTS:
            with self.subTest(entrypoint=filename):
                module = _load_by_path(module_name, filename)
                self.assertTrue(
                    callable(getattr(module, "main", None)),
                    f"{filename} must import cleanly and expose a callable main()",
                )

    def test_gui_imports_or_skips_without_display(self) -> None:
        # gui.py needs tkinter (a system package) which may be absent in headless
        # environments; a missing display/tkinter is an environment condition, not a defect.
        try:
            module = _load_by_path("dynamix_entry_gui", "gui.py")
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"gui.py not importable in this environment: {exc!r}")
        self.assertTrue(
            callable(getattr(module, "main", None)),
            "gui.py must expose a callable main()",
        )


if __name__ == "__main__":
    unittest.main()
