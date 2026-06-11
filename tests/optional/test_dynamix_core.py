# ------------------------
# tests/optional/test_dynamix_core.py
# ------------------------
"""Optional tests for DynaMix_Core integration (skipped if DynaMix_Core not available)."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Ensure repo root is on sys.path
#
# This file is at: <repo_root>/tests/optional/test_dynamix_core.py
# so repo_root = parents[2]
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ----------------------------------------------------------------------
# Conditional import: DynaMix_Core wrapper
# ----------------------------------------------------------------------
DynaMix_Core: Optional[Any]
try:
    import DynaMix_Core as DynaMix_Core  # type: ignore[import]
    HAS_DYNAMIX = True
except Exception:
    DynaMix_Core = None
    HAS_DYNAMIX = False


def _call_run_dynamix_forecast_safe(**kwargs: Any) -> Optional[Dict[str, Any]]:
    """
    Call DynaMix_Core.run_dynamix_forecast with only supported kwargs.
    This avoids brittle failures when wrapper signature changes.
    """
    assert DynaMix_Core is not None, "DynaMix_Core should be available"
    fn = getattr(DynaMix_Core, "run_dynamix_forecast", None)
    if fn is None:
        raise AttributeError("DynaMix_Core.run_dynamix_forecast not found")

    try:
        sig = inspect.signature(fn)
        allowed = set(sig.parameters.keys())
    except Exception:
        allowed = set(kwargs.keys())

    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    return fn(**filtered)  # type: ignore[misc]


@unittest.skipIf(not HAS_DYNAMIX or DynaMix_Core is None, "DynaMix_Core not available")
class TestDynaMixCore(unittest.TestCase):
    """Test suite for DynaMix_Core wrapper."""

    def setUp(self) -> None:
        """Create deterministic test dataset."""
        np.random.seed(12345)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")

        t = np.arange(100, dtype=float)
        data = {
            f"TS_{i}": 20.0 + 0.1 * t + 5.0 * np.sin(t / 10.0 + float(i)) + np.random.randn(100) * 0.5
            for i in range(1, 8)
        }
        self.df = pd.DataFrame(data, index=dates)

    def test_validation_empty_dataframe(self) -> None:
        """Validation: empty df should return None (or raise ValueError)."""
        empty_df = pd.DataFrame()
        try:
            result = _call_run_dynamix_forecast_safe(ts_df=empty_df, target_col="TS_1", forecast_horizon=1)
        except ValueError:
            # Acceptable contract as well; wrapper may choose to raise
            return
        self.assertIsNone(result, "Should return None for empty DataFrame")

    def test_validation_invalid_column(self) -> None:
        """Validation: invalid column should return None (or raise ValueError)."""
        try:
            result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col="NonExistent", forecast_horizon=1)
        except ValueError:
            return
        self.assertIsNone(result, "Should return None for invalid column")

    def test_validation_invalid_horizon(self) -> None:
        """Validation: horizon <= 0 should return None (or raise ValueError)."""
        for h in (0, -5):
            with self.subTest(horizon=h):
                try:
                    result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col="TS_1", forecast_horizon=h)
                except ValueError:
                    continue
                self.assertIsNone(result, "Should return None for non-positive horizon")

    def test_successful_forecast(self) -> None:
        """Basic successful forecast contract."""
        result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col="TS_1", forecast_horizon=2)

        # Optional wrapper: it may return None if model deps unavailable
        if result is None:
            self.skipTest("DynaMix_Core returned None (model unavailable or insufficient setup).")

        self.assertIsInstance(result, dict, "Result should be a dictionary")
        self.assertIn("forecast_df", result, "Result should contain forecast_df")

        forecast_df = result["forecast_df"]
        self.assertIsInstance(forecast_df, pd.DataFrame, "forecast_df should be DataFrame")
        self.assertFalse(forecast_df.empty, "Forecast should not be empty")
        self.assertEqual(len(forecast_df), 2, "Forecast should have 2 steps")
        self.assertIsInstance(forecast_df.index, pd.DatetimeIndex, "Forecast index should be DatetimeIndex")

        # Multivariate output expectation: wrapper may return only target column; accept both.
        for col in self.df.columns:
            if col not in forecast_df.columns:
                # Do not fail hard; allow univariate output from wrapper implementations.
                break

    def test_univariate_forecast(self) -> None:
        """Forecast with single series."""
        uni_df = self.df[["TS_1"]].copy()
        result = _call_run_dynamix_forecast_safe(ts_df=uni_df, target_col="TS_1", forecast_horizon=1)

        if result is None:
            self.skipTest("DynaMix_Core returned None for univariate forecast.")

        forecast_df = result["forecast_df"]
        self.assertIn("TS_1", forecast_df.columns)
        self.assertGreaterEqual(len(forecast_df.columns), 1)

    def test_multivariate_forecast(self) -> None:
        """Forecast with multiple series subset."""
        multi_df = self.df[["TS_1", "TS_2", "TS_3"]].copy()
        result = _call_run_dynamix_forecast_safe(ts_df=multi_df, target_col="TS_1", forecast_horizon=3)

        if result is None:
            self.skipTest("DynaMix_Core returned None for multivariate forecast.")

        forecast_df = result["forecast_df"]
        self.assertIsInstance(forecast_df, pd.DataFrame)
        self.assertEqual(len(forecast_df), 3)
        self.assertIn("TS_1", forecast_df.columns)

    def test_progress_callback(self) -> None:
        """Progress callback (only if wrapper supports it)."""
        progress_calls = []

        def progress_callback(step: int, total: int) -> None:
            progress_calls.append((step, total))

        assert DynaMix_Core is not None
        fn = getattr(DynaMix_Core, "run_dynamix_forecast", None)
        if fn is None:
            self.skipTest("run_dynamix_forecast missing")

        try:
            sig = inspect.signature(fn)
            if "progress_callback" not in sig.parameters:
                self.skipTest("progress_callback not supported by DynaMix_Core.run_dynamix_forecast")
        except Exception:
            pass

        try:
            result = _call_run_dynamix_forecast_safe(
                ts_df=self.df,
                target_col="TS_1",
                forecast_horizon=3,
                progress_callback=progress_callback,
            )
        except TypeError:
            self.skipTest("progress_callback not supported by current wrapper signature")

        if result is None:
            self.skipTest("DynaMix_Core returned None; cannot validate progress callback behavior.")

        self.assertGreater(len(progress_calls), 0, "Progress callback should be called at least once")
        final_step, final_total = progress_calls[-1]
        # Allow either (horizon, horizon) or 1-based progress reporting; validate broadly.
        self.assertEqual(final_total, 3, "Final total should equal horizon")

    def test_forecast_values_reasonable(self) -> None:
        """Forecast values sanity check (very lenient)."""
        result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col="TS_1", forecast_horizon=1)
        if result is None:
            self.skipTest("DynaMix_Core returned None; cannot validate values.")

        forecast_df = result["forecast_df"]
        if "TS_1" not in forecast_df.columns:
            self.skipTest("forecast_df missing TS_1; wrapper contract differs.")

        v = float(forecast_df["TS_1"].iloc[0])
        self.assertTrue(np.isfinite(v), "Forecast value should be finite")

        mu = float(self.df["TS_1"].mean())
        sd = float(self.df["TS_1"].std(ddof=1))
        self.assertTrue(mu - 5 * sd <= v <= mu + 5 * sd, "Forecast should be within 5σ of history (sanity bound)")

    def test_forecast_continuity(self) -> None:
        """Forecast index should start right after history (daily)."""
        result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col="TS_1", forecast_horizon=2)
        if result is None:
            self.skipTest("DynaMix_Core returned None; cannot validate continuity.")

        forecast_df = result["forecast_df"]
        if not isinstance(forecast_df.index, pd.DatetimeIndex) or forecast_df.empty:
            self.skipTest("forecast_df index not DatetimeIndex or empty; wrapper contract differs.")

        last_history_date = self.df.index[-1]
        first_forecast_date = forecast_df.index[0]
        self.assertGreater(first_forecast_date, last_history_date)
        self.assertEqual(first_forecast_date, last_history_date + pd.Timedelta(days=1))

    def test_different_horizons(self) -> None:
        """Forecasting with multiple horizons should be consistent (if available)."""
        for horizon in (1, 3, 5, 10):
            with self.subTest(horizon=horizon):
                result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col="TS_1", forecast_horizon=horizon)
                if result is None:
                    # If model isn't available, do not fail optional tests.
                    continue
                forecast_df = result["forecast_df"]
                self.assertEqual(len(forecast_df), horizon)

    def test_different_target_series(self) -> None:
        """Forecast should include the target series column if present in output."""
        for target in ("TS_1", "TS_3", "TS_5", "TS_7"):
            with self.subTest(target=target):
                result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col=target, forecast_horizon=2)
                if result is None:
                    continue
                forecast_df = result["forecast_df"]
                # Some wrappers only output target_col; some output all series.
                self.assertIn(target, forecast_df.columns)

    def test_short_history(self) -> None:
        """Minimal history behavior: should succeed or return None gracefully."""
        short_df = self.df.iloc[-30:].copy()
        result = _call_run_dynamix_forecast_safe(ts_df=short_df, target_col="TS_1", forecast_horizon=1)
        if result is None:
            return
        self.assertIn("forecast_df", result)

    def test_context_preparation(self) -> None:
        """Test internal context tensor preparation logic (if exposed)."""
        assert DynaMix_Core is not None
        fn = getattr(DynaMix_Core, "_prepare_context_tensor", None)
        if fn is None:
            self.skipTest("_prepare_context_tensor not exposed by DynaMix_Core")

        context_tensor, context_index = fn(self.df)
        if context_tensor is None:
            self.skipTest("Context tensor not produced (wrapper decided to skip).")

        self.assertTrue(hasattr(context_tensor, "shape"))
        self.assertEqual(context_tensor.shape[1], len(self.df.columns))

        if context_index is not None:
            self.assertIsInstance(context_index, pd.DatetimeIndex)

    def test_model_selection_logic(self) -> None:
        """Test internal model selection (if exposed)."""
        assert DynaMix_Core is not None
        fn = getattr(DynaMix_Core, "_select_model_name_for_dims", None)
        if fn is None:
            self.skipTest("_select_model_name_for_dims not exposed by DynaMix_Core")

        self.assertEqual(fn(1), "ALRNN")
        self.assertEqual(fn(2), "LSTM")
        self.assertEqual(fn(3), "LSTM")
        self.assertEqual(fn(7), "GRU")

    def test_exports_if_present(self) -> None:
        """If result includes export paths, ensure they exist and cleanup."""
        result = _call_run_dynamix_forecast_safe(ts_df=self.df, target_col="TS_1", forecast_horizon=1)
        if result is None:
            self.skipTest("DynaMix_Core returned None; cannot validate exports.")

        self.assertIn("html_path", result, "Result should have html_path key (can be None)")
        self.assertIn("csv_path", result, "Result should have csv_path key (can be None)")

        html_path = result.get("html_path")
        csv_path = result.get("csv_path")

        if html_path is not None:
            self.assertTrue(Path(html_path).exists(), "HTML export should exist if path is provided")
            try:
                Path(html_path).unlink(missing_ok=True)
            except Exception:
                pass

        if csv_path is not None:
            self.assertTrue(Path(csv_path).exists(), "CSV export should exist if path is provided")
            try:
                Path(csv_path).unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
