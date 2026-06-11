# ------------------------
# tests/core_unit/test_data_utils.py
# ------------------------
"""Tests for data_utils / Data_Utils data loading and preprocessing (supports legacy and src layouts)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Optional, Sequence, Tuple, Any

import numpy as np
import pandas as pd


def _bootstrap_import_paths() -> Path:
    """
    Ensure imports work for both legacy root-module layout and new src/ package layout.

    File location:
      repo_root/tests/core_unit/test_data_utils.py

    Therefore:
      repo_root = parents[2]
      src_dir   = repo_root / "src"
    """
    repo_root = Path(__file__).resolve().parents[2]
    src_dir = repo_root / "src"

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    return repo_root


def _import_first(names: Sequence[str]) -> ModuleType:
    last_err: Optional[BaseException] = None
    for name in names:
        try:
            __import__(name)
            return sys.modules[name]
        except Exception as e:  # pragma: no cover
            last_err = e
    raise ImportError(f"Failed to import any of: {list(names)}. Last error: {last_err!r}")


REPO_ROOT = _bootstrap_import_paths()

# Support both module naming conventions:
# - Data_Utils (legacy)
# - data_utils (new root)
# - dynamix.data_utils (src package)
DU = _import_first(("Data_Utils", "data_utils", "dynamix.data_utils"))

# Support both constants naming conventions:
# - Constants (legacy)
# - constants (new root)
# - dynamix.constants (src package)
C = _import_first(("Constants", "constants", "dynamix.constants"))


class TestDataUtils(unittest.TestCase):
    """Test suite for data utility functions."""

    def setUp(self) -> None:
        """Create temporary test data file."""
        # Generate realistic test data
        dates = pd.date_range("2023-01-01", periods=100, freq="D")

        # Create CSV content with proper format
        self.csv_content = "Date,TS_1,TS_2,TS_3,TS_4,TS_5,TS_6,TS_7\n"
        rng = np.random.default_rng(12345)  # deterministic tests

        for i, d in enumerate(dates):
            date_str = d.strftime("%d/%m/%Y")
            # Generate values roughly in a lottery-like range; keep deterministic
            base = 10 + 5 * np.sin(i / 10.0)
            values = [str(int(base + float(rng.random()) * 5.0)) for _ in range(7)]
            row = [date_str] + values
            self.csv_content += ",".join(row) + "\n"

        # Create temp file
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            delete=False,
            encoding="utf-8",
        )
        self.tmp.write(self.csv_content)
        self.tmp.close()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self) -> None:
        """Clean up temporary files."""
        try:
            if getattr(self, "tmp_path", None) is not None and self.tmp_path.exists():
                self.tmp_path.unlink()
        except Exception:
            pass

    def test_load_lottery_data_success(self) -> None:
        """Test successful data loading."""
        ts_arr, dt_idx, df = DU.load_lottery_data(  # type: ignore[attr-defined]
            csv_path=self.tmp_path,
            min_history=10,
        )

        # Verify structure
        self.assertEqual(df.shape[1], 7, "Should have 7 TS columns by default")
        self.assertEqual(len(df), 100, "Should have 100 rows")
        self.assertIsInstance(df.index, pd.DatetimeIndex, "Index should be DatetimeIndex in calendar mode")

        # Verify array matches DataFrame for TS-only layout
        self.assertEqual(ts_arr.shape, df.shape, "Array and DataFrame shapes should match")
        self.assertTrue(
            np.allclose(ts_arr, df.values, rtol=1e-5, atol=1e-6),
            "Array values should match DataFrame values",
        )

        # Verify returned dt_idx matches df.index
        self.assertTrue((dt_idx == df.index).all(), "Returned DatetimeIndex should match df.index")

    def test_load_lottery_data_min_history(self) -> None:
        """Test minimum history length validation."""
        with self.assertRaises(ValueError):
            DU.load_lottery_data(  # type: ignore[attr-defined]
                csv_path=self.tmp_path,
                min_history=200,  # More than available
            )

    def test_load_lottery_data_missing_file(self) -> None:
        """Test handling of missing file."""
        with self.assertRaises(FileNotFoundError):
            DU.load_lottery_data(csv_path="nonexistent_file.csv")  # type: ignore[attr-defined]

    def test_load_lottery_data_column_validation(self) -> None:
        """Test validation of expected columns."""
        wrong_csv = "Date,Wrong1,Wrong2\n01/01/2023,1,2\n"
        tmp2 = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
        tmp2.write(wrong_csv)
        tmp2.close()
        tmp2_path = Path(tmp2.name)

        try:
            with self.assertRaises(ValueError):
                DU.load_lottery_data(csv_path=tmp2_path)  # type: ignore[attr-defined]
        finally:
            try:
                tmp2_path.unlink()
            except Exception:
                pass

    def test_markdown_table_formatting(self) -> None:
        """Test markdown table printer does not raise."""
        headers = ["Model", "TS_1", "TS_2"]
        rows = [
            ["DynaMix", "10.5", "20.3"],
            ["PCE", "11.2", "19.8"],
        ]
        try:
            DU.print_markdown_table(headers, rows)  # type: ignore[attr-defined]
        except Exception as e:
            self.fail(f"print_markdown_table raised exception: {e!r}")

    def test_ensure_output_dirs(self) -> None:
        """Test output directory creation."""
        try:
            DU.ensure_output_dirs()  # type: ignore[attr-defined]

            # OUTPUT_DIR may be configured as Path-like; normalize
            out_dir = Path(getattr(C, "OUTPUT_DIR"))
            self.assertTrue(out_dir.exists(), "OUTPUT_DIR should exist after ensure_output_dirs()")
            self.assertTrue(out_dir.is_dir(), "OUTPUT_DIR should be a directory")

            # Optional: check standard subdirs if defined
            for name in ("OUTPUT_GRAPHS_DIR", "OUTPUT_LOGS_DIR"):
                if hasattr(C, name):
                    p = Path(getattr(C, name))
                    self.assertTrue(p.exists(), f"{name} should exist after ensure_output_dirs()")
        except Exception as e:
            self.fail(f"ensure_output_dirs raised exception: {e!r}")


if __name__ == "__main__":
    unittest.main()
