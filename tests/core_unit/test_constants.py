# ------------------------
# tests/core_unit/test_constants.py
# ------------------------
"""Tests for constants configuration module (supports legacy and src layouts)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Optional


def _bootstrap_import_paths() -> Path:
    """
    Ensure imports work for both legacy root-module layout and new src/ package layout.

    File location:
      repo_root/tests/core_unit/test_constants.py

    Therefore:
      repo_root = parents[2]
      src_dir   = repo_root / "src"
    """
    repo_root = Path(__file__).resolve().parents[2]
    src_dir = repo_root / "src"

    # Prepend so local project modules win over site-packages
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    return repo_root


def _import_constants_module() -> ModuleType:
    """
    Import constants module under any of these names:
      - Constants (legacy)
      - constants (new root-level)
      - dynamix.constants (src package)
    """
    last_err: Optional[BaseException] = None

    for name in ("Constants", "constants", "dynamix.constants"):
        try:
            __import__(name)
            return sys.modules[name]
        except Exception as e:  # pragma: no cover (import-probing)
            last_err = e

    raise ImportError(
        "Failed to import constants module. Tried: Constants, constants, dynamix.constants. "
        f"Last error: {last_err!r}"
    )


REPO_ROOT = _bootstrap_import_paths()
C = _import_constants_module()


class TestConstants(unittest.TestCase):
    """Test suite for constants configuration."""

    def test_repo_root_exists(self) -> None:
        """Verify REPO_ROOT path is valid."""
        self.assertTrue(hasattr(C, "REPO_ROOT"), "Constants should define REPO_ROOT")
        repo_root = Path(getattr(C, "REPO_ROOT"))
        self.assertTrue(repo_root.exists(), "REPO_ROOT should exist")
        self.assertTrue(repo_root.is_dir(), "REPO_ROOT should be a directory")

    def test_required_paths_defined(self) -> None:
        """Verify all required path constants are defined."""
        required_paths = [
            "REPO_ROOT",
            "DATA_FILE",
            "OUTPUT_DIR",
            "OUTPUT_GRAPHS_DIR",
            "OUTPUT_LOGS_DIR",
        ]
        for path_name in required_paths:
            self.assertTrue(hasattr(C, path_name), f"Constants should define {path_name}")

    def test_ts_columns_structure(self) -> None:
        """Verify TS_COLUMNS is properly configured."""
        self.assertTrue(hasattr(C, "TS_COLUMNS"), "Constants should define TS_COLUMNS")
        ts_cols = list(getattr(C, "TS_COLUMNS"))
        self.assertEqual(len(ts_cols), 7, "Should have exactly 7 time series columns")
        self.assertEqual(ts_cols[0], "TS_1", "First column should be TS_1")
        self.assertEqual(ts_cols[-1], "TS_7", "Last column should be TS_7")

    def test_model_flags(self) -> None:
        """Verify model enable/disable flags are boolean when present."""
        for flag in ("PCE_ENABLED", "DARTS_ENABLED"):
            if hasattr(C, flag):
                self.assertIsInstance(getattr(C, flag), bool, f"{flag} should be a boolean")

    def test_forecast_horizon_range(self) -> None:
        """Verify forecast horizon is within valid range when present."""
        # Some variants use FH/FH_MAX; keep the checks conditional.
        if hasattr(C, "FH"):
            self.assertGreater(getattr(C, "FH"), 0, "FH should be positive")
        if hasattr(C, "FH") and hasattr(C, "FH_MAX"):
            self.assertLessEqual(getattr(C, "FH"), getattr(C, "FH_MAX"), "FH should not exceed FH_MAX")

    def test_device_configuration(self) -> None:
        """Verify device configuration is valid when present."""
        if not hasattr(C, "DYNAMIX_DEVICE"):
            self.skipTest("DYNAMIX_DEVICE not defined in constants module.")
        valid_devices = {"cpu", "cuda"}
        dev = str(getattr(C, "DYNAMIX_DEVICE")).lower().strip()
        self.assertIn(dev, valid_devices, f"DYNAMIX_DEVICE should be one of {sorted(valid_devices)}")


if __name__ == "__main__":
    unittest.main()
