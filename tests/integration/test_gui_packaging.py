# -----------------------
# tests/integration/test_gui_packaging.py
# -----------------------
"""
G1.1 — the Streamlit GUI package, dependency extra, and launcher.

Streamlit is an *optional* dependency (the ``[gui]`` extra). The webapp package and its launcher
must therefore import **without** Streamlit installed — only ``app.py`` (run via ``streamlit run``)
may import it. This keeps the core test suite runnable without the extra and keeps all GUI *logic*
in Streamlit-free helper modules.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestGuiPackaging(unittest.TestCase):
    def test_webapp_imports_without_streamlit(self) -> None:
        import dynamix.webapp as webapp  # noqa: F401
        import dynamix.webapp.launch as launch

        self.assertTrue(hasattr(launch, "main"), "launcher must expose main()")
        # Importing our package/launcher must not require or pull in streamlit.
        self.assertNotIn(
            "streamlit", sys.modules,
            "dynamix.webapp / launch must not import streamlit at import time",
        )

    def test_pyproject_declares_gui_extra_and_script(self) -> None:
        txt = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("dynamix-gui", txt, "pyproject must declare the dynamix-gui console script")
        self.assertIn("streamlit", txt, "pyproject [gui] extra must include streamlit")

    def test_root_app_shim_exists(self) -> None:
        self.assertTrue(
            (REPO_ROOT / "app.py").exists(),
            "a repo-root app.py shim must exist so `streamlit run app.py` works",
        )


if __name__ == "__main__":
    unittest.main()
