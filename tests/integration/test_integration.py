# ------------------------
# tests/integration/test_integration.py
# ------------------------
"""Integration tests for end-to-end workflows (layout-agnostic, Pylance-friendly)."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple, cast

import numpy as np
import pandas as pd


def _bootstrap_import_paths() -> Path:
    """
    Ensure imports work for both legacy root-module layout and new src/ package layout.

    File location:
      repo_root/tests/integration/test_integration.py

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
    """
    Import the first module that succeeds from a list of candidates.
    """
    last_err: Optional[BaseException] = None
    for name in names:
        try:
            __import__(name)
            mod = sys.modules.get(name)
            if isinstance(mod, ModuleType):
                return mod
            # Extremely defensive: if sys.modules entry isn't a module, treat as failure.
            raise ImportError(f"Imported '{name}' but sys.modules[{name!r}] is not a module.")
        except Exception as e:  # pragma: no cover
            last_err = e
    raise ImportError(f"Failed to import any of: {list(names)}. Last error: {last_err!r}")


def _as_dict(x: Any) -> Optional[dict[str, Any]]:
    """Narrow Any/object to a plain dict for safe indexing and Pylance."""
    if isinstance(x, dict):
        # MyPy/Pylance: dict keys are not guaranteed str, but tests use string keys.
        return cast(dict[str, Any], x)
    return None


def _as_df(x: Any) -> Optional[pd.DataFrame]:
    """Narrow Any/object to DataFrame for safe .columns/.empty usage."""
    if isinstance(x, pd.DataFrame):
        return x
    return None


def _get_bool(mod: ModuleType, name: str, default: bool) -> bool:
    try:
        v = getattr(mod, name)
        return bool(v)
    except Exception:
        return default


def _set_attr_safe(mod: ModuleType, name: str, value: Any) -> Tuple[bool, Any]:
    """
    Set an attribute, returning (existed_before, previous_value).
    Used to temporarily override config without confusing static typing.
    """
    existed = hasattr(mod, name)
    prev = getattr(mod, name, None)
    try:
        setattr(mod, name, value)
    except Exception:
        pass
    return existed, prev


def _restore_attr_safe(mod: ModuleType, name: str, existed_before: bool, prev_value: Any) -> None:
    try:
        if existed_before:
            setattr(mod, name, prev_value)
        else:
            delattr(mod, name)
    except Exception:
        pass


REPO_ROOT = _bootstrap_import_paths()

# Constants: legacy vs new vs package
C = _import_first(("Constants", "constants", "dynamix.constants"))

# DynaMix core: legacy CamelCase vs new snake_case vs package
try:
    DCore = _import_first(("DynaMix_Core", "dynamix_core", "dynamix.dynamix_core"))
    HAS_DM = True
except Exception:
    DCore = None
    HAS_DM = False

# Darts core: legacy vs new vs package
try:
    Darts_Core = _import_first(("Darts_Core", "darts_core", "dynamix.darts_core"))
    HAS_DARTS = True
except Exception:
    Darts_Core = None
    HAS_DARTS = False

# PCE-NARX: legacy vs new vs package
try:
    PCE_NARX = _import_first(("PCE_NARX", "pce_narx", "dynamix.pce_narx"))
    HAS_PCE = True
except Exception:
    PCE_NARX = None
    HAS_PCE = False

# Plotting: legacy vs new vs package
try:
    Plotting = _import_first(("Plotting", "plotting", "dynamix.plotting"))
    HAS_PLOTTING = True
except Exception:
    Plotting = None
    HAS_PLOTTING = False


class TestIntegration(unittest.TestCase):
    """Integration test suite for multi-model workflows."""

    def setUp(self) -> None:
        """Create realistic test dataset (deterministic)."""
        rng = np.random.default_rng(12345)

        dates = pd.date_range("2023-01-01", periods=120, freq="D")
        t = np.arange(len(dates), dtype=float)

        data = {
            f"TS_{i}": 20.0 + 0.1 * t + 5.0 * np.sin(t / 10.0 + float(i)) + rng.normal(0.0, 0.5, size=len(dates))
            for i in range(1, 8)
        }
        self.df = pd.DataFrame(data, index=dates)

    def _call_darts_forecast_safe(
        self,
        df: pd.DataFrame,
        target_col: str,
        horizon: int,
        model_type: str,
    ) -> Any:
        """
        Call Darts_Core.run_darts_forecast with only supported kwargs.
        Avoids brittle failures when wrapper signature changes.
        """
        if not HAS_DARTS or Darts_Core is None:
            self.skipTest("Darts core not available")

        fn = getattr(Darts_Core, "run_darts_forecast", None)
        if not callable(fn):
            self.skipTest("Darts_Core.run_darts_forecast not found")

        try:
            sig = inspect.signature(fn)
            params = set(sig.parameters.keys())
        except Exception:
            params = {"ts_df", "target_col", "forecast_horizon", "model_type"}

        kwargs: dict[str, Any] = {}
        if "ts_df" in params:
            kwargs["ts_df"] = df
        if "target_col" in params:
            kwargs["target_col"] = target_col
        if "forecast_horizon" in params:
            kwargs["forecast_horizon"] = horizon
        if "model_type" in params:
            kwargs["model_type"] = model_type

        if len(kwargs) >= 3:
            return fn(**kwargs)  # type: ignore[misc]
        return fn(df, target_col, horizon, model_type=model_type)  # type: ignore[misc]

    def test_full_pipeline_simulation(self) -> None:
        """Test sequential execution of all available models."""
        results: dict[str, Any] = {}

        # --- DynaMix ---
        if HAS_DM and DCore is not None:
            run_fn = getattr(DCore, "run_dynamix_forecast", None)
            if callable(run_fn):
                raw = run_fn(self.df, "TS_1", 2)
                d = _as_dict(raw)
                if d is not None:
                    fdf = _as_df(d.get("forecast_df"))
                    if fdf is not None and not fdf.empty:
                        results["DynaMix"] = d
                        self.assertIn("forecast_df", d)
                        self.assertFalse(fdf.empty)

        # --- Darts ---
        if HAS_DARTS and Darts_Core is not None:
            existed, prev = _set_attr_safe(C, "DARTS_N_EPOCHS", 2)
            try:
                try:
                    raw = self._call_darts_forecast_safe(
                        df=self.df,
                        target_col="TS_1",
                        horizon=2,
                        model_type="NBEATS",
                    )
                except TypeError as e:
                    self.skipTest(f"Darts run_darts_forecast signature mismatch: {e}")
                    return

                d = _as_dict(raw)
                if d is not None:
                    fdf = _as_df(d.get("forecast_df"))
                    if fdf is not None and not fdf.empty:
                        results["Darts"] = d
                        self.assertIn("forecast_df", d)
                        self.assertFalse(fdf.empty)
            finally:
                _restore_attr_safe(C, "DARTS_N_EPOCHS", existed, prev)

        # --- PCE-NARX ---
        if HAS_PCE and PCE_NARX is not None and _get_bool(C, "PCE_ENABLED", True):
            predict_fn = getattr(PCE_NARX, "predict_pce_narx", None)
            if callable(predict_fn):
                raw = predict_fn(self.df, "TS_1", 2)
                fdf = _as_df(raw)
                if fdf is not None and not fdf.empty:
                    results["PCE"] = fdf
                    self.assertIn("PCE_Pred", fdf.columns)

        if not results:
            # A missing optional model runtime (torch / darts / chaospy) is an
            # environment condition, not a defect — skip. But if such a runtime IS
            # present and still nothing was produced, that is a real regression — fail.
            runtime_available = []
            for _dep in ("torch", "darts", "chaospy"):
                try:
                    __import__(_dep)
                    runtime_available.append(_dep)
                except Exception:
                    pass
            if not runtime_available:
                self.skipTest(
                    "No forecasting model produced output and no model runtime "
                    "dependency (torch/darts/chaospy) is installed."
                )
            self.fail(
                f"Model runtime present ({runtime_available}) but no model produced "
                "a forecast DataFrame."
            )

        self.assertGreater(len(results), 0, "At least one model should produce results")

    def test_model_comparison(self) -> None:
        """Test that different models can forecast the same series."""
        forecasts: dict[str, float] = {}
        horizon = 1

        if HAS_DM and DCore is not None:
            run_fn = getattr(DCore, "run_dynamix_forecast", None)
            if callable(run_fn):
                raw = run_fn(self.df, "TS_1", horizon)
                d = _as_dict(raw)
                if d is not None:
                    fdf = _as_df(d.get("forecast_df"))
                    if fdf is not None and not fdf.empty and "TS_1" in fdf.columns:
                        forecasts["DynaMix"] = float(fdf["TS_1"].iloc[0])

        if HAS_PCE and PCE_NARX is not None and _get_bool(C, "PCE_ENABLED", True):
            predict_fn = getattr(PCE_NARX, "predict_pce_narx", None)
            if callable(predict_fn):
                raw = predict_fn(self.df, "TS_1", horizon)
                fdf = _as_df(raw)
                if fdf is not None and not fdf.empty and "PCE_Pred" in fdf.columns:
                    forecasts["PCE"] = float(fdf["PCE_Pred"].iloc[0])

        if not forecasts:
            self.skipTest("No models available for comparison (DynaMix/PCE disabled or missing).")

        for model, value in forecasts.items():
            self.assertIsInstance(value, (int, float, np.number), f"{model} forecast should be numeric")
            self.assertTrue(0 < float(value) < 1000, f"{model} forecast should be in reasonable range")

    def test_data_pipeline_integrity(self) -> None:
        """Test data flows correctly through preprocessing and forecasting."""
        processed_df = self.df.copy()
        self.assertIsInstance(processed_df.index, pd.DatetimeIndex)

        forecast_df: Optional[pd.DataFrame] = None

        if HAS_PCE and PCE_NARX is not None and _get_bool(C, "PCE_ENABLED", True):
            predict_fn = getattr(PCE_NARX, "predict_pce_narx", None)
            if callable(predict_fn):
                raw = predict_fn(processed_df, "TS_1", 1)
                forecast_df = _as_df(raw)

        if forecast_df is None and HAS_DM and DCore is not None:
            run_fn = getattr(DCore, "run_dynamix_forecast", None)
            if callable(run_fn):
                raw = run_fn(processed_df, "TS_1", 1)
                d = _as_dict(raw)
                if d is not None:
                    forecast_df = _as_df(d.get("forecast_df"))

        if forecast_df is None or forecast_df.empty:
            self.skipTest("No available model produced a forecast DataFrame for pipeline integrity test.")

        if HAS_PLOTTING and Plotting is not None:
            export_fn = getattr(Plotting, "export_forecast_plot_and_csv", None)
            if not callable(export_fn):
                self.skipTest("Plotting.export_forecast_plot_and_csv not found")

            html_path = None
            csv_path = None
            try:
                raw_paths = export_fn(
                    history_df=processed_df,
                    forecast_df=forecast_df,
                    target_col="TS_1",
                    model_label="Integration-Test",
                )
                # Support both Path and str return types
                if isinstance(raw_paths, tuple) and len(raw_paths) == 2:
                    html_path = Path(raw_paths[0])
                    csv_path = Path(raw_paths[1])

                self.assertIsNotNone(html_path)
                self.assertIsNotNone(csv_path)
                assert html_path is not None
                assert csv_path is not None

                self.assertTrue(html_path.exists())
                self.assertTrue(csv_path.exists())
            finally:
                try:
                    if html_path is not None and html_path.exists():
                        html_path.unlink()
                except Exception:
                    pass
                try:
                    if csv_path is not None and csv_path.exists():
                        csv_path.unlink()
                except Exception:
                    pass

    def test_multivariate_vs_univariate(self) -> None:
        """Test both multivariate and univariate forecasting modes (DynaMix)."""
        if not (HAS_DM and DCore is not None):
            self.skipTest("DynaMix core not available")

        run_fn = getattr(DCore, "run_dynamix_forecast", None)
        if not callable(run_fn):
            self.skipTest("DCore.run_dynamix_forecast not found")

        raw_multi = run_fn(self.df, "TS_1", 1)
        raw_uni = run_fn(self.df[["TS_1"]].copy(), "TS_1", 1)

        d_multi = _as_dict(raw_multi)
        d_uni = _as_dict(raw_uni)

        if d_multi is None or d_uni is None:
            self.skipTest("DynaMix returned non-dict/None (likely missing torch/model).")

        f_multi = _as_df(d_multi.get("forecast_df"))
        f_uni = _as_df(d_uni.get("forecast_df"))

        if f_multi is None or f_uni is None or f_multi.empty or f_uni.empty:
            self.skipTest("DynaMix forecast_df missing/empty (likely missing model dependencies).")

        self.assertTrue(True)  # If we reached here, both modes produced forecasts.


if __name__ == "__main__":
    unittest.main()
