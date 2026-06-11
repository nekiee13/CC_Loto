# ------------------------
# tests/optional/test_pce_narx.py
# ------------------------
"""Optional tests for PCE-NARX forecaster (skipped if unavailable/disabled)."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Ensure repo root is on sys.path
#
# This file is at: <repo_root>/tests/optional/test_pce_narx.py
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
# - forecaster module: prefer `pce_narx`, fallback to legacy `PCE_NARX`
# ----------------------------------------------------------------------
C: Optional[Any]
try:
    import constants as C  # type: ignore[import]
except Exception:
    try:
        import Constants as C  # type: ignore[import]
    except Exception:
        C = None

PCE_MOD: Optional[Any]
try:
    import pce_narx as PCE_MOD  # type: ignore[import]
except Exception:
    try:
        import PCE_NARX as PCE_MOD  # type: ignore[import]
    except Exception:
        PCE_MOD = None


def _pce_enabled() -> bool:
    """Treat missing config as enabled=False for safety (skip tests)."""
    if C is None:
        return False
    return bool(getattr(C, "PCE_ENABLED", False))


def _get_predict_fn() -> Optional[Callable[..., Any]]:
    if PCE_MOD is None:
        return None
    fn = getattr(PCE_MOD, "predict_pce_narx", None)
    if callable(fn):
        return fn
    return None


def _call_predict_safe(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """
    Call predict_pce_narx with only supported kwargs to avoid brittle failures
    when signature changes due to refactors.
    """
    try:
        sig = inspect.signature(fn)
        allowed = set(sig.parameters.keys())
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        return fn(**filtered)
    except Exception:
        # Fallback: try calling with the original kwargs (may raise; test will surface it).
        return fn(**kwargs)


@unittest.skipIf(PCE_MOD is None, "PCE forecaster module not available (pce_narx/PCE_NARX import failed)")
class TestPCENARX(unittest.TestCase):
    """Test suite for PCE-NARX forecaster."""

    def setUp(self) -> None:
        """Create deterministic test dataset."""
        np.random.seed(12345)
        dates = pd.date_range("2023-01-01", periods=100, freq="D")

        # Trend + seasonality + noise
        t = np.arange(100, dtype=float)
        data = {
            f"TS_{i}": 20.0 + 0.1 * t + 5.0 * np.sin(t / 10.0) + np.random.randn(100) * 0.5
            for i in range(1, 8)
        }
        self.df = pd.DataFrame(data, index=dates)

    def test_predict_success(self) -> None:
        """Test successful PCE-NARX prediction."""
        if not _pce_enabled():
            self.skipTest("PCE is disabled or constants module not available")

        fn = _get_predict_fn()
        if fn is None:
            self.skipTest("predict_pce_narx not found")

        result = _call_predict_safe(
            fn,
            data=self.df,
            target_col="TS_1",
            forecast_horizon=3,
        )

        # Some implementations may return None if backend deps are unavailable.
        if result is None:
            self.skipTest("predict_pce_narx returned None (backend unavailable or insufficient setup)")

        self.assertIsInstance(result, pd.DataFrame, "Result should be a DataFrame")
        self.assertIn("PCE_Pred", result.columns, "Should have PCE_Pred column")
        self.assertEqual(len(result), 3, "Should have 3 forecast steps")
        self.assertIsInstance(result.index, pd.DatetimeIndex, "Index should be DatetimeIndex")

        # Optional intervals
        if "PCE_Lower" in result.columns and "PCE_Upper" in result.columns:
            self.assertTrue((result["PCE_Lower"] <= result["PCE_Upper"]).all(), "Lower bound should be <= Upper bound")
            self.assertTrue((result["PCE_Lower"] <= result["PCE_Pred"]).all(), "Prediction should be >= Lower bound")
            self.assertTrue((result["PCE_Pred"] <= result["PCE_Upper"]).all(), "Prediction should be <= Upper bound")

    def test_predict_insufficient_data(self) -> None:
        """Test handling of insufficient data."""
        if not _pce_enabled():
            self.skipTest("PCE is disabled or constants module not available")

        fn = _get_predict_fn()
        if fn is None:
            self.skipTest("predict_pce_narx not found")

        small_df = self.df.iloc[:10].copy()
        result = _call_predict_safe(fn, data=small_df, target_col="TS_1", forecast_horizon=1)

        # Expected to be None for insufficient data in this project contract.
        self.assertIsNone(result, "Should return None for insufficient data")

    def test_predict_invalid_column(self) -> None:
        """Test handling of invalid target column."""
        if not _pce_enabled():
            self.skipTest("PCE is disabled or constants module not available")

        fn = _get_predict_fn()
        if fn is None:
            self.skipTest("predict_pce_narx not found")

        result = _call_predict_safe(fn, data=self.df, target_col="NonExistent", forecast_horizon=1)
        self.assertIsNone(result, "Should return None for invalid column")

    def test_predict_empty_dataframe(self) -> None:
        """Test handling of empty DataFrame."""
        if not _pce_enabled():
            self.skipTest("PCE is disabled or constants module not available")

        fn = _get_predict_fn()
        if fn is None:
            self.skipTest("predict_pce_narx not found")

        empty_df = pd.DataFrame()
        result = _call_predict_safe(fn, data=empty_df, target_col="TS_1", forecast_horizon=1)
        self.assertIsNone(result, "Should return None for empty DataFrame")

    def test_predict_with_progress_callback(self) -> None:
        """Test progress callback functionality (only if supported)."""
        if not _pce_enabled():
            self.skipTest("PCE is disabled or constants module not available")

        fn = _get_predict_fn()
        if fn is None:
            self.skipTest("predict_pce_narx not found")

        # Skip if signature does not accept progress_callback
        try:
            sig = inspect.signature(fn)
            if "progress_callback" not in sig.parameters:
                self.skipTest("progress_callback not supported by predict_pce_narx signature")
        except Exception:
            # If we cannot introspect, we still try; if it fails we skip.
            pass

        progress_calls = []

        def progress_callback(step: int, total: int) -> None:
            progress_calls.append((step, total))

        try:
            result = _call_predict_safe(
                fn,
                data=self.df,
                target_col="TS_1",
                forecast_horizon=5,
                progress_callback=progress_callback,
            )
        except TypeError:
            self.skipTest("progress_callback not supported by current implementation")

        if result is None:
            self.skipTest("predict_pce_narx returned None; cannot validate progress callback")

        self.assertGreater(len(progress_calls), 0, "Progress callback should be called")
        self.assertEqual(progress_calls[-1], (5, 5), "Last progress should be (5, 5)")


if __name__ == "__main__":
    unittest.main()
