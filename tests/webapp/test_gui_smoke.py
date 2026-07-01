# -----------------------
# tests/webapp/test_gui_smoke.py
# -----------------------
"""
G7.2 — headless GUI smoke test.

Catches breakage without manual clicking: (1) the webapp helper modules import (always, no
Streamlit needed), and (2) if Streamlit is installed (the ``[gui]`` extra), the app renders once
via ``streamlit.testing.v1.AppTest`` with no exception. The render check is skipped when Streamlit
is absent so the core suite still passes without the extra.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "src" / "dynamix" / "webapp" / "app.py"


class TestGuiSmoke(unittest.TestCase):
    def test_helper_modules_import(self) -> None:
        from dynamix.webapp import data_io, launch, results, runner, state

        self.assertTrue(hasattr(runner, "build_command"))
        self.assertTrue(hasattr(state, "read_project_status"))
        self.assertTrue(hasattr(results, "load_forecast"))
        self.assertTrue(hasattr(data_io, "validate_row"))
        self.assertTrue(hasattr(launch, "main"))

    def test_app_renders_when_streamlit_present(self) -> None:
        try:
            from streamlit.testing.v1 import AppTest
        except Exception:
            self.skipTest("streamlit ([gui] extra) not installed")
        at = AppTest.from_file(str(APP), default_timeout=60).run()
        self.assertFalse(at.exception, f"app raised on render: {at.exception}")
        # Home is the default page; it always has the app title.
        self.assertTrue(any("DynaMix" in t.value for t in at.title))


if __name__ == "__main__":
    unittest.main()
