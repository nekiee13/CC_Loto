# ------------------------
# tests/optional/test_plotting.py
# ------------------------
"""Optional tests for plotting/Plotting visualization and export."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Ensure repo root is on sys.path
#
# This file is at: <repo_root>/tests/optional/test_plotting.py
# so repo_root = parents[2]
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ----------------------------------------------------------------------
# Conditional imports:
# - config module: prefer `constants`, fallback to legacy `Constants`
# - plotting module: prefer `plotting`, fallback to legacy `Plotting`
# ----------------------------------------------------------------------
C: Optional[Any]
try:
    import constants as C  # type: ignore[import]
except Exception:
    try:
        import Constants as C  # type: ignore[import]
    except Exception:
        C = None

PlotMod: Optional[Any]
try:
    import plotting as PlotMod  # type: ignore[import]
except Exception:
    try:
        import Plotting as PlotMod  # type: ignore[import]
    except Exception:
        PlotMod = None


def _resolve_graphs_dir() -> Optional[Path]:
    """
    Resolve output graphs directory robustly across old/new constants layouts.
    Priority:
      1) constants.OUTPUT_GRAPHS_DIR
      2) constants.OUTPUT_DIR / "Graphs"
      3) <repo_root>/Output/Graphs
    """
    if C is not None:
        gd = getattr(C, "OUTPUT_GRAPHS_DIR", None)
        if gd is not None:
            try:
                return Path(gd)
            except Exception:
                pass

        od = getattr(C, "OUTPUT_DIR", None)
        if od is not None:
            try:
                return Path(od) / "Graphs"
            except Exception:
                pass

    # last-resort (repo-local)
    return REPO_ROOT / "Output" / "Graphs"


@unittest.skipIf(PlotMod is None, "Plotting module not available (plotting/Plotting import failed)")
class TestPlotting(unittest.TestCase):
    """Test suite for Plotting module."""

    def setUp(self) -> None:
        """Create deterministic test data."""
        np.random.seed(12345)

        self.history_dates = pd.date_range("2024-01-01", periods=10, freq="D")
        self.forecast_dates = pd.date_range("2024-01-11", periods=3, freq="D")

        self.history_df = pd.DataFrame(
            {
                "TS_1": np.random.randn(10) * 5 + 20,
                "TS_2": np.random.randn(10) * 3 + 15,
            },
            index=self.history_dates,
        )

        self.forecast_df = pd.DataFrame(
            {
                "TS_1": np.random.randn(3) * 5 + 20,
            },
            index=self.forecast_dates,
        )

    def tearDown(self) -> None:
        """Clean up generated files (best-effort)."""
        graphs_dir = _resolve_graphs_dir()
        if graphs_dir is None:
            return

        try:
            graphs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # If we can't create/access it, nothing to clean.
            return

        # Match prior naming convention used by these tests.
        # Keep patterns broad enough to catch both HTML and CSV exports.
        patterns = [
            "TS_1_*_Test_*",
            "TS_1_*_PCE-Test_*",
            "*Integration-Test*",
        ]
        for pat in patterns:
            for file in graphs_dir.glob(pat):
                try:
                    file.unlink()
                except Exception:
                    pass

    def test_export_basic(self) -> None:
        """Test basic export functionality."""
        assert PlotMod is not None

        fn = getattr(PlotMod, "export_forecast_plot_and_csv", None)
        if fn is None:
            self.skipTest("export_forecast_plot_and_csv not found in plotting module")

        html_path, csv_path = fn(
            history_df=self.history_df,
            forecast_df=self.forecast_df,
            target_col="TS_1",
            model_label="Test",
        )

        self.assertIsInstance(html_path, Path, "html_path should be a Path")
        self.assertIsInstance(csv_path, Path, "csv_path should be a Path")

        self.assertTrue(html_path.exists(), "HTML file should exist")
        self.assertTrue(csv_path.exists(), "CSV file should exist")

        self.assertEqual(html_path.suffix.lower(), ".html", "Should be HTML file")
        self.assertEqual(csv_path.suffix.lower(), ".csv", "Should be CSV file")

        # HTML content should be non-trivial
        self.assertGreater(html_path.stat().st_size, 500, "HTML file should have content")

        # CSV should be readable
        csv_df = pd.read_csv(csv_path)
        self.assertGreater(len(csv_df), 0, "CSV should have rows")

    def test_export_with_prediction_intervals(self) -> None:
        """Test export with PCE-style prediction intervals."""
        assert PlotMod is not None

        fn = getattr(PlotMod, "export_forecast_plot_and_csv", None)
        if fn is None:
            self.skipTest("export_forecast_plot_and_csv not found in plotting module")

        forecast_with_intervals = self.forecast_df.copy()
        forecast_with_intervals["PCE_Pred"] = forecast_with_intervals["TS_1"]
        forecast_with_intervals["PCE_Lower"] = forecast_with_intervals["TS_1"] - 2
        forecast_with_intervals["PCE_Upper"] = forecast_with_intervals["TS_1"] + 2

        html_path, csv_path = fn(
            history_df=self.history_df,
            forecast_df=forecast_with_intervals,
            target_col="TS_1",
            model_label="PCE-Test",
        )

        self.assertTrue(html_path.exists())
        self.assertTrue(csv_path.exists())

    def test_export_invalid_target(self) -> None:
        """Test error handling for invalid target column."""
        assert PlotMod is not None

        fn = getattr(PlotMod, "export_forecast_plot_and_csv", None)
        if fn is None:
            self.skipTest("export_forecast_plot_and_csv not found in plotting module")

        with self.assertRaises(ValueError):
            fn(
                history_df=self.history_df,
                forecast_df=self.forecast_df,
                target_col="NonExistent",
                model_label="Test",
            )

    def test_export_empty_history(self) -> None:
        """Test error handling for empty history."""
        assert PlotMod is not None

        fn = getattr(PlotMod, "export_forecast_plot_and_csv", None)
        if fn is None:
            self.skipTest("export_forecast_plot_and_csv not found in plotting module")

        empty_df = pd.DataFrame()

        with self.assertRaises(ValueError):
            fn(
                history_df=empty_df,
                forecast_df=self.forecast_df,
                target_col="TS_1",
                model_label="Test",
            )

    def test_export_empty_forecast(self) -> None:
        """Test error handling for empty forecast."""
        assert PlotMod is not None

        fn = getattr(PlotMod, "export_forecast_plot_and_csv", None)
        if fn is None:
            self.skipTest("export_forecast_plot_and_csv not found in plotting module")

        empty_forecast = pd.DataFrame()

        with self.assertRaises(ValueError):
            fn(
                history_df=self.history_df,
                forecast_df=empty_forecast,
                target_col="TS_1",
                model_label="Test",
            )

    def test_csv_structure(self) -> None:
        """Test CSV output structure."""
        assert PlotMod is not None

        fn = getattr(PlotMod, "export_forecast_plot_and_csv", None)
        if fn is None:
            self.skipTest("export_forecast_plot_and_csv not found in plotting module")

        _, csv_path = fn(
            history_df=self.history_df,
            forecast_df=self.forecast_df,
            target_col="TS_1",
            model_label="Test",
        )

        csv_df = pd.read_csv(csv_path)

        self.assertIn("Segment", csv_df.columns, "CSV should have Segment column")

        segments = csv_df["Segment"].astype(str).unique().tolist()
        self.assertTrue(any("History" in s for s in segments), "CSV should have History segment")
        self.assertTrue(any("Forecast" in s for s in segments), "CSV should have Forecast segment")


if __name__ == "__main__":
    unittest.main()
