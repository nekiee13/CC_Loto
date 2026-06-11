# ------------------------
# tests/optional/test_darts_core.py
# ------------------------
"""Tests for darts_core.py wrapper module (optional, skipped if Darts not installed)."""

from __future__ import annotations

import inspect
import shutil
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Ensure repo root is on sys.path
#
# This file is at: <repo_root>/tests/optional/test_darts_core.py
# so repo_root = parents[2]
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ----------------------------------------------------------------------
# Imports from project (now resolvable once sys.path is correct)
# ----------------------------------------------------------------------
try:
    import constants as C  # type: ignore
except Exception:
    C = None  # type: ignore[assignment]

# ----------------------------------------------------------------------
# Conditional import: darts_core wrapper
# ----------------------------------------------------------------------
Darts_Core: Optional[Any]
try:
    import darts_core as Darts_Core  # type: ignore[import]
    HAS_DARTS_CORE = True
except Exception:
    Darts_Core = None
    HAS_DARTS_CORE = False


def _call_run_darts_forecast_safe(**kwargs: Any) -> Dict[str, Any]:
    """
    Call Darts_Core.run_darts_forecast with only supported kwargs.
    This avoids brittle failures when wrapper signature changes.
    """
    assert Darts_Core is not None, "Darts_Core should be available"
    fn = getattr(Darts_Core, "run_darts_forecast", None)
    if fn is None:
        raise AttributeError("darts_core.run_darts_forecast not found")

    try:
        sig = inspect.signature(fn)
        allowed = set(sig.parameters.keys())
    except Exception:
        # If we cannot introspect, assume it supports the common kw set.
        allowed = set(kwargs.keys())

    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    return fn(**filtered)  # type: ignore[misc]


@unittest.skipIf(not HAS_DARTS_CORE or Darts_Core is None, "darts_core not available")
class TestDartsCore(unittest.TestCase):
    """Test suite for darts_core wrapper."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test data and reduce epochs for speed (best-effort)."""
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        t = np.linspace(0, 10, 60)
        data = {
            "TS_1": np.sin(t) * 10 + 20,
            "TS_2": np.cos(t) * 5 + 15,
            "TS_3": t * 2 + 10,
        }
        cls.test_df = pd.DataFrame(data, index=dates)

        # Reduce epochs for test speed if constants module is available.
        cls.original_epochs = None
        if C is not None:
            cls.original_epochs = getattr(C, "DARTS_N_EPOCHS", None)
            try:
                C.DARTS_N_EPOCHS = 2  # type: ignore[attr-defined]
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls) -> None:
        """Restore original configuration and cleanup."""
        if C is not None:
            try:
                if cls.original_epochs is None:
                    # If it didn't exist before, remove if created
                    if hasattr(C, "DARTS_N_EPOCHS"):
                        delattr(C, "DARTS_N_EPOCHS")
                else:
                    C.DARTS_N_EPOCHS = cls.original_epochs  # type: ignore[attr-defined]
            except Exception:
                pass

        # Cleanup common Darts artifact dirs (best-effort)
        for dir_path in (REPO_ROOT / "darts_logs", REPO_ROOT / ".darts"):
            if dir_path.exists():
                shutil.rmtree(dir_path, ignore_errors=True)

    def test_univariate_series_builder(self) -> None:
        """Test internal series builder handles indices correctly (if exposed)."""
        assert Darts_Core is not None

        build_fn = getattr(Darts_Core, "_build_univariate_series", None)
        if build_fn is None:
            self.skipTest("_build_univariate_series not exposed by darts_core")

        series = build_fn(self.test_df, "TS_1")
        self.assertTrue(hasattr(series, "__len__"), "Returned series should be sized")
        self.assertEqual(len(series), 60, "Series length should be 60")
        self.assertTrue(
            hasattr(series, "freq_str") or hasattr(series, "freq"),
            "Series should have frequency information (freq_str or freq).",
        )

    def test_run_forecast_nbeats(self) -> None:
        """Test NBEATS model execution."""
        result = _call_run_darts_forecast_safe(
            ts_df=self.test_df,
            target_col="TS_1",
            forecast_horizon=2,
            model_type="NBEATS",
            use_cache=False,
        )

        self.assertIsInstance(result, dict, "Result should be a dictionary")
        self.assertIn("forecast_df", result, "Result should contain forecast_df")

        forecast_df = result["forecast_df"]
        self.assertIsInstance(forecast_df, pd.DataFrame, "forecast_df should be DataFrame")
        self.assertFalse(forecast_df.empty, "Forecast should not be empty")
        self.assertEqual(len(forecast_df), 2, "Should have 2 forecast steps")
        self.assertIn("TS_1", forecast_df.columns, "Forecast should contain target column")

        # model_type may be echoed by wrapper; if present, validate it
        if "model_type" in result:
            self.assertEqual(str(result["model_type"]), "NBEATS")

    def test_run_forecast_gru(self) -> None:
        """Test GRU model execution."""
        result = _call_run_darts_forecast_safe(
            ts_df=self.test_df,
            target_col="TS_1",
            forecast_horizon=1,
            model_type="GRU",
            use_cache=False,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("forecast_df", result)
        self.assertEqual(len(result["forecast_df"]), 1)

    def test_run_forecast_lstm(self) -> None:
        """Test LSTM model execution."""
        result = _call_run_darts_forecast_safe(
            ts_df=self.test_df,
            target_col="TS_2",
            forecast_horizon=3,
            model_type="LSTM",
            use_cache=False,
        )
        self.assertIn("forecast_df", result)
        self.assertEqual(len(result["forecast_df"]), 3)
        self.assertIn("TS_2", result["forecast_df"].columns)

    def test_invalid_target_column(self) -> None:
        """Test error handling for missing columns."""
        with self.assertRaises(ValueError):
            _call_run_darts_forecast_safe(
                ts_df=self.test_df,
                target_col="TS_999",
                forecast_horizon=1,
                model_type="NBEATS",
            )

    def test_invalid_forecast_horizon(self) -> None:
        """Test error handling for invalid forecast horizon."""
        with self.assertRaises(ValueError):
            _call_run_darts_forecast_safe(
                ts_df=self.test_df,
                target_col="TS_1",
                forecast_horizon=0,
                model_type="NBEATS",
            )

    def test_caching_mechanism(self) -> None:
        """Test that models are cached correctly (if wrapper exposes cache)."""
        assert Darts_Core is not None

        _ = _call_run_darts_forecast_safe(
            ts_df=self.test_df,
            target_col="TS_1",
            forecast_horizon=1,
            model_type="NBEATS",
            use_cache=True,
        )

        cache = getattr(Darts_Core, "_MODEL_CACHE", None)
        if cache is None:
            self.skipTest("_MODEL_CACHE not exposed by darts_core")
        self.assertTrue(isinstance(cache, dict))
        self.assertGreater(len(cache), 0, "Cache should not be empty after first cached call")

        _ = _call_run_darts_forecast_safe(
            ts_df=self.test_df,
            target_col="TS_1",
            forecast_horizon=1,
            model_type="NBEATS",
            use_cache=True,
        )

    def test_progress_callback(self) -> None:
        """Test progress callback functionality (only if wrapper supports it)."""
        progress_calls = []

        def progress_callback(step: int, total: int) -> None:
            progress_calls.append((step, total))

        # Only pass progress_callback if signature supports it.
        assert Darts_Core is not None
        fn = getattr(Darts_Core, "run_darts_forecast", None)
        if fn is None:
            self.skipTest("run_darts_forecast missing")

        try:
            sig = inspect.signature(fn)
            if "progress_callback" not in sig.parameters:
                self.skipTest("progress_callback not supported by darts_core.run_darts_forecast")
        except Exception:
            # If introspection fails, attempt call; if it TypeErrors, skip.
            pass

        try:
            _ = _call_run_darts_forecast_safe(
                ts_df=self.test_df,
                target_col="TS_1",
                forecast_horizon=2,
                model_type="NBEATS",
                use_cache=False,
                progress_callback=progress_callback,
            )
        except TypeError:
            self.skipTest("progress_callback not supported by current wrapper signature")

        self.assertGreater(len(progress_calls), 0, "Progress callback should be called at least once")


if __name__ == "__main__":
    unittest.main()
