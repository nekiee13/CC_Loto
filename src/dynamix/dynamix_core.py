# ------------------------
# src/dynamix/dynamix_core.py
# ------------------------
"""
Core forecasting pipeline for the DynaMix Lottery Forecasting System.

Responsibilities:
- Provide a DynaMix-based multivariate forecasting pipeline usable from CLI and GUI.
- Abstract model import/loading (installed package or local DynaMix-python repo).
- Respect global configuration from constants.py, including:
  INDEX_MODE, FREQ, CONTEXT_MAX_STEPS, TRAINING_WINDOW_ROUNDS, timing constraints.
- Integrate with plotting.py for HTML/CSV export when available.

Key fixes (v1.3 refactor compatibility):
- Robust intra-package imports (src/dynamix/*).
- Robust resolution of DynaMix repo path even if constants.REPO_ROOT points to src/dynamix.
- Event-mode forecast index uses relative steps (ForecastStep=1..H) by default, with an optional
  anchor-to-last-event-id behavior if enabled in constants.

Public API:
    run_dynamix_forecast(ts_df, target_col, forecast_horizon, progress_callback=None) -> dict | None
    main()  # optional CLI self-test
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Robust imports after refactor
# ----------------------------------------------------------------------
try:
    from . import constants as C  # type: ignore
except Exception:  # pragma: no cover
    import constants as C  # type: ignore

try:
    from . import data_utils as DU  # type: ignore
except Exception:  # pragma: no cover
    DU = None  # type: ignore

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Optional imports
# ----------------------------------------------------------------------
try:
    import torch  # type: ignore
    HAS_TORCH = True
except Exception:  # pragma: no cover
    torch = None  # type: ignore
    HAS_TORCH = False
    log.warning("PyTorch is not installed. DynaMix forecasting is disabled.")

# Plotting integration (package-first, fallback to flat import)
try:
    from . import plotting as Plotting  # type: ignore
    HAS_PLOTTING = True
except Exception:  # pragma: no cover
    try:
        import plotting as Plotting  # type: ignore
        HAS_PLOTTING = True
    except Exception:
        Plotting = None  # type: ignore
        HAS_PLOTTING = False
        log.warning("plotting.py not found. DynaMix outputs will not be exported.")


# ----------------------------------------------------------------------
# Small utilities
# ----------------------------------------------------------------------
def _repo_root() -> Path:
    """
    Compute repository root robustly:
      <repo>/src/dynamix/dynamix_core.py -> parents[2] == <repo>
    """
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()


def _resolve_dynamix_repo_dir() -> Path:
    """
    Robustly resolve the DynaMix-python repo path.

    Why this exists:
    - If constants.REPO_ROOT is set to src/dynamix, then constants.DYNAMIX_REPO_DIR
      defined as REPO_ROOT / "DynaMix-python" would incorrectly point to:
        <repo>/src/dynamix/DynaMix-python
      instead of:
        <repo>/DynaMix-python

    Priority:
      1) constants.DYNAMIX_REPO_DIR if it exists on disk
      2) <repo_root>/DynaMix-python if exists
      3) the raw constants.DYNAMIX_REPO_DIR value as last resort
    """
    try:
        c_dir = Path(getattr(C, "DYNAMIX_REPO_DIR"))
        if c_dir.is_dir():
            return c_dir
    except Exception:
        c_dir = None  # type: ignore

    rr = _repo_root()
    candidate = rr / "DynaMix-python"
    if candidate.is_dir():
        return candidate

    # last resort: return something sensible
    if c_dir is not None:
        return c_dir
    return rr / "DynaMix-python"


def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


def _safe_to_numeric_series(values: pd.Series) -> pd.Series:
    """
    Stub-compliant numeric coercion helper (avoids errors='ignore').
    """
    try:
        return pd.to_numeric(values, errors="coerce")
    except Exception:
        return pd.Series([np.nan] * len(values), index=values.index, dtype="float64")


# ----------------------------------------------------------------------
# 1. DynaMix import and wrapper
# ----------------------------------------------------------------------
@dataclass
class DynaMixModelWrapper:
    """
    Small wrapper so the rest of the code does not depend on concrete forecaster implementation.
    """
    model_name: str
    dims: int
    forecaster: Any

    def forecast(
        self,
        context_tensor: Any,
        horizon: int,
        standardize: bool,
        preprocessing_method: str,
        fit_nonstationary: bool,
    ) -> Any:
        return self.forecaster.forecast(
            context_tensor,
            horizon=horizon,
            standardize=standardize,
            preprocessing_method=preprocessing_method,
            fit_nonstationary=fit_nonstationary,
        )


_dynamix_cache: Dict[Tuple[str, int], DynaMixModelWrapper] = {}

_DYNAMIX_IMPORTED = False
_DYNAMIX_AVAILABLE = False
_DYNAMIX_ForecasterClass: Any = None
_DYNAMIX_load_hf_model: Any = None


def _import_dynamix() -> None:
    """
    Lazily import the DynaMix components from:
    1) installed 'dynamix' package, or
    2) local DynaMix-python repo.

    This function is intentionally defensive because local repo layouts differ.
    """
    global _DYNAMIX_IMPORTED, _DYNAMIX_AVAILABLE
    global _DYNAMIX_ForecasterClass, _DYNAMIX_load_hf_model

    if _DYNAMIX_IMPORTED:
        return

    _DYNAMIX_IMPORTED = True
    repo_dir = _resolve_dynamix_repo_dir()
    last_error: Optional[BaseException] = None

    # 1) Installed package layout
    try:
        from dynamix.model.forecaster import DynaMixForecaster  # type: ignore
        from dynamix.utilities.utilities import load_hf_model  # type: ignore

        _DYNAMIX_ForecasterClass = DynaMixForecaster
        _DYNAMIX_load_hf_model = load_hf_model
        _DYNAMIX_AVAILABLE = True
        log.info("Imported DynaMix from installed package.")
        return
    except Exception as e:  # pragma: no cover
        last_error = e

    # 2) Local repo layout: add <repo>/src and/or <repo> to sys.path
    if repo_dir.is_dir():
        src_dir = repo_dir / "src"
        if src_dir.is_dir() and str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
            log.info("Added DynaMix repo src to sys.path: %s", src_dir)

        if str(repo_dir) not in sys.path:
            sys.path.insert(0, str(repo_dir))
            log.info("Added DynaMix repo root to sys.path: %s", repo_dir)

        # Try common local layouts
        try:
            from model.forecaster import DynaMixForecaster  # type: ignore
            _DYNAMIX_ForecasterClass = DynaMixForecaster
        except Exception as e1:  # pragma: no cover
            last_error = e1
            _DYNAMIX_ForecasterClass = None

        try:
            from utilities.utilities import load_hf_model  # type: ignore
            _DYNAMIX_load_hf_model = load_hf_model
        except Exception as e2:  # pragma: no cover
            last_error = e2
            _DYNAMIX_load_hf_model = None
            # fallback seen in some repo variants
            try:
                from src.utilities.utilities import load_hf_model  # type: ignore
                _DYNAMIX_load_hf_model = load_hf_model
            except Exception as e3:  # pragma: no cover
                last_error = e3
                _DYNAMIX_load_hf_model = None

        if _DYNAMIX_ForecasterClass is not None and _DYNAMIX_load_hf_model is not None:
            _DYNAMIX_AVAILABLE = True
            log.info("Successfully imported DynaMix from local repo: %s", repo_dir)
            return

    _DYNAMIX_AVAILABLE = False
    log.error("Failed to import DynaMix components. repo_dir=%s last_error=%r", repo_dir, last_error)


def _select_model_name_for_dims(dims: int) -> str:
    if dims <= int(getattr(C, "ALRNN_MAX_DIMS", 1)):
        return str(getattr(C, "MODEL_NAME_ALRNN", "ALRNN"))
    if dims <= int(getattr(C, "LSTM_MAX_DIMS", 3)):
        return str(getattr(C, "MODEL_NAME_LSTM", "LSTM"))
    if dims <= int(getattr(C, "GRU_MAX_DIMS", 100)):
        return str(getattr(C, "MODEL_NAME_GRU", "GRU"))
    return str(getattr(C, "MODEL_NAME_GRU", "GRU"))


def _load_dynamix_model(dims: int) -> Optional[DynaMixModelWrapper]:
    _import_dynamix()
    if not _DYNAMIX_AVAILABLE or _DYNAMIX_ForecasterClass is None or _DYNAMIX_load_hf_model is None:
        return None
    if not HAS_TORCH:
        return None

    hf_model_name = str(getattr(C, "DYNAMIX_HF_MODEL_NAME", "dynamix-3d-alrnn-v1.0"))
    key = (hf_model_name, int(dims))
    if key in _dynamix_cache:
        return _dynamix_cache[key]

    try:
        log.info("Loading DynaMix model '%s' for dims=%d...", hf_model_name, dims)
        dynamix_model = _DYNAMIX_load_hf_model(model_name=hf_model_name)  # type: ignore[call-arg]

        device = str(getattr(C, "DYNAMIX_DEVICE", "cpu"))
        # Model object is expected to be torch.nn.Module-like
        try:
            dynamix_model.to(device)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            dynamix_model.eval()  # type: ignore[attr-defined]
        except Exception:
            pass

        forecaster = _DYNAMIX_ForecasterClass(dynamix_model)  # type: ignore[call-arg]
        wrapper = DynaMixModelWrapper(model_name=hf_model_name, dims=int(dims), forecaster=forecaster)
        _dynamix_cache[key] = wrapper
        return wrapper
    except Exception as exc:  # pragma: no cover
        log.exception("Failed to load DynaMix forecaster: %r", exc)
        return None


# ----------------------------------------------------------------------
# 2. Context preparation and core forecasting
# ----------------------------------------------------------------------
def _apply_training_window_rounds(ts_df: pd.DataFrame) -> pd.DataFrame:
    if ts_df is None or ts_df.empty:
        return ts_df

    try:
        w = int(getattr(C, "TRAINING_WINDOW_ROUNDS", 0) or 0)
    except Exception:
        w = 0

    if w <= 0:
        return ts_df

    try:
        wcap = int(getattr(C, "TRAINING_WINDOW_MAX_ROUNDS", 0) or 0)
    except Exception:
        wcap = 0
    if wcap > 0:
        w = min(w, wcap)

    if w <= 0 or len(ts_df) <= w:
        return ts_df

    return ts_df.tail(w).copy()


def _prepare_context_tensor(ts_df: pd.DataFrame) -> Tuple[Optional[Any], Optional[pd.Index]]:
    """
    Prepare the context tensor.

    Calendar mode:
      - enforces datetime index
      - optional asfreq + ffill (legacy behavior)

    Event mode:
      - does not expand dates
      - does not forward-fill
      - drops rows with any NaNs (integrity)
      - preserves ordering by default
    """
    if not HAS_TORCH:
        log.error("PyTorch not available.")
        return None, None

    if ts_df is None or ts_df.empty:
        log.error("Empty ts_df passed to _prepare_context_tensor.")
        return None, None

    # Apply training window early (row-based)
    ts_df = _apply_training_window_rounds(ts_df)

    if not _is_event_mode():
        df = ts_df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")
        df = df.sort_index()

        freq = getattr(C, "FREQ", "D")
        if isinstance(freq, str) and freq.strip():
            # Calendar semantics: regular grid + forward fill
            df = df.asfreq(freq).ffill()

        df = df.dropna(how="any")
        ts_df_ctx = df
        ctx_index: pd.Index = pd.DatetimeIndex(ts_df_ctx.index)
    else:
        df = ts_df.copy()

        preserve = bool(getattr(C, "EVENT_PRESERVE_FILE_ORDER", True))
        if not preserve:
            event_id_col = str(getattr(C, "EVENT_ID_COL", "EventID"))
            if event_id_col in df.columns:
                df[event_id_col] = _safe_to_numeric_series(df[event_id_col])
                try:
                    df = df.sort_values(by=event_id_col, kind="stable")
                except Exception:
                    pass
            else:
                # If index is integer-like, sort by index, else leave unchanged
                try:
                    df = df.sort_index()
                except Exception:
                    pass

        before = len(df)
        df = df.dropna(how="any")
        dropped = before - len(df)
        if dropped > 0:
            log.warning("Event mode: dropped %d rows with NaNs in DynaMix context.", dropped)

        ts_df_ctx = df
        ctx_index = ts_df_ctx.index

    # Cap context length for model performance
    try:
        max_steps = int(getattr(C, "CONTEXT_MAX_STEPS", 2048) or 2048)
    except Exception:
        max_steps = 2048

    if len(ts_df_ctx) > max_steps:
        ts_df_ctx = ts_df_ctx.iloc[-max_steps:].copy()
        ctx_index = ts_df_ctx.index

    # Conservative minimum length check (kept compatible with previous behavior)
    min_len = max(10, int(getattr(C, "PCE_LAGS", 5) or 5) + 5)
    if len(ts_df_ctx) < min_len:
        log.error("Context too short for DynaMix: %d rows (min required=%d).", len(ts_df_ctx), min_len)
        return None, None

    values = ts_df_ctx.values.astype("float32")
    device = str(getattr(C, "DYNAMIX_DEVICE", "cpu"))
    context_tensor = torch.from_numpy(values).to(device)  # type: ignore

    return context_tensor, ctx_index


def _make_future_index(context_index: pd.Index, forecast_horizon: int) -> pd.Index:
    """
    Construct forecast index depending on INDEX_MODE.

    Calendar mode:
      - date_range continuing from last timestamp using FREQ

    Event mode:
      - default: ForecastStep=1..H (relative step index)
      - optional: if constants.EVENT_FORECAST_ANCHOR_TO_LAST_EVENT_ID=True and
                 context_index is integer-like, use (last_id+1 .. last_id+H) with name EVENT_INDEX_NAME.
    """
    fh = max(1, int(forecast_horizon))

    if not _is_event_mode():
        try:
            last_date = context_index[-1]
        except Exception:
            last_date = None

        freq = getattr(C, "FREQ", "D")
        off = pd.tseries.frequencies.to_offset(freq) if isinstance(freq, str) else pd.tseries.frequencies.to_offset("D")

        if last_date is None:
            # fallback: create an arbitrary date range starting "now"
            start = pd.Timestamp.utcnow().normalize()
        else:
            try:
                start = pd.Timestamp(last_date) + off
            except Exception:
                start = pd.Timestamp.utcnow().normalize()

        return pd.DatetimeIndex(pd.date_range(start=start, periods=fh, freq=off))

    # Event mode
    anchor = bool(getattr(C, "EVENT_FORECAST_ANCHOR_TO_LAST_EVENT_ID", False))
    idx_name = str(getattr(C, "EVENT_INDEX_NAME", "EventID") or "EventID")

    if anchor:
        # If index is integer-like, continue it
        try:
            last_int = int(context_index[-1])  # type: ignore[arg-type]
            return pd.RangeIndex(start=last_int + 1, stop=last_int + 1 + fh, step=1, name=idx_name)
        except Exception:
            pass

    # Default: relative horizon steps
    return pd.RangeIndex(start=1, stop=fh + 1, step=1, name=str(getattr(C, "FORECAST_STEP_INDEX_NAME", "ForecastStep")))


def _dynamix_forecast_core(
    ts_df: pd.DataFrame,
    forecast_horizon: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Optional[pd.DataFrame]:
    """
    Core DynaMix forecast routine.
    Returns a multivariate forecast DataFrame indexed appropriately for INDEX_MODE.
    """
    if not HAS_TORCH:
        return None

    fh = int(forecast_horizon) if int(forecast_horizon) > 0 else 1

    context_tensor, context_index = _prepare_context_tensor(ts_df)
    if context_tensor is None or context_index is None:
        return None

    dims = int(getattr(context_tensor, "shape", [0, 0])[1])
    model_wrapper = _load_dynamix_model(dims)
    if model_wrapper is None:
        return None

    if progress_callback:
        progress_callback(0, fh)

    time_start = time.time()
    max_seconds = int(getattr(C, "MAX_FORECAST_TIME_SECONDS", 20) or 20)

    with torch.no_grad():  # type: ignore
        y_pred = model_wrapper.forecast(
            context_tensor,
            horizon=fh,
            standardize=bool(getattr(C, "DYNAMIX_STANDARDIZE", False)),
            preprocessing_method=str(getattr(C, "DYNAMIX_PREPROCESSING_METHOD", "pos_embedding")),
            fit_nonstationary=bool(getattr(C, "DYNAMIX_FIT_NONSTATIONARY", False)),
        )

    elapsed = time.time() - time_start
    if elapsed > max_seconds:
        log.warning("DynaMix runtime %.2f s exceeded limit (%d s).", elapsed, max_seconds)

    if not isinstance(y_pred, torch.Tensor):  # type: ignore
        log.error("DynaMix forecaster returned non-tensor output: %r", type(y_pred))
        return None

    y_pred_np = y_pred.detach().cpu().numpy()

    future_index = _make_future_index(context_index, fh)

    # Columns must be TS columns; caller is responsible for passing TS-only frames if desired.
    cols = list(ts_df.columns)
    if y_pred_np.ndim != 2 or y_pred_np.shape[1] != len(cols):
        # Defensive: some implementations may return (fh, dims) matching context_tensor dims;
        # ensure we don't crash, but make mismatch visible.
        log.warning(
            "Forecast output shape mismatch: y_pred.shape=%s expected_cols=%d. Proceeding with min dims.",
            getattr(y_pred_np, "shape", None),
            len(cols),
        )
        min_dims = min(int(y_pred_np.shape[1]) if y_pred_np.ndim == 2 else 0, len(cols))
        cols = cols[:min_dims]
        y_pred_np = y_pred_np[:, :min_dims] if y_pred_np.ndim == 2 else y_pred_np

    forecast_df = pd.DataFrame(y_pred_np, index=future_index, columns=cols)

    if progress_callback:
        progress_callback(fh, fh)

    return forecast_df


# ----------------------------------------------------------------------
# 3. Public API
# ----------------------------------------------------------------------
def run_dynamix_forecast(
    ts_df: pd.DataFrame,
    target_col: str,
    forecast_horizon: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Optional[dict]:
    """
    High-level DynaMix forecast entry point.

    Returns:
      {
        "forecast_df": pd.DataFrame,
        "html_path": Optional[Path],
        "csv_path": Optional[Path],
      }
    """
    if ts_df is None or ts_df.empty:
        return None
    if target_col not in ts_df.columns:
        return None

    forecast_df = _dynamix_forecast_core(
        ts_df=ts_df,
        forecast_horizon=int(forecast_horizon),
        progress_callback=progress_callback,
    )
    if forecast_df is None or forecast_df.empty:
        return None

    html_path = None
    csv_path = None

    # Export only if plotting exists and EXPORT_ENABLED is True
    if HAS_PLOTTING and Plotting is not None and bool(getattr(C, "EXPORT_ENABLED", False)):
        try:
            dims = int(ts_df.shape[1])
            model_label = f"DynaMix-{_select_model_name_for_dims(dims)}"
            html_path, csv_path = Plotting.export_forecast_plot_and_csv(  # type: ignore[attr-defined]
                history_df=ts_df,
                forecast_df=forecast_df,
                target_col=target_col,
                model_label=model_label,
            )
        except Exception as exc:  # pragma: no cover
            log.exception("Error exporting DynaMix outputs: %r", exc)

    return {"forecast_df": forecast_df, "html_path": html_path, "csv_path": csv_path}


def _load_default_data() -> pd.DataFrame:
    """
    Loads the default dataset using the canonical loader after refactor.
    """
    if DU is None:
        # Fallback to flat import if someone runs without package context
        try:
            import data_utils as _DU  # type: ignore
            _ts_array, _date_index, ts_df = _DU.load_lottery_data()
            return ts_df
        except Exception as exc:
            log.exception("Failed to load DATA.csv via flat data_utils import: %r", exc)
            raise

    _ts_array, _date_index, ts_df = DU.load_lottery_data()
    return ts_df


# ----------------------------------------------------------------------
# 4. CLI entry point (self-test)
# ----------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        ts_df = _load_default_data()
    except Exception:
        return

    target_col = str(getattr(C, "PCE_TARGET_COL", "TS_1"))
    if target_col not in ts_df.columns:
        target_col = str(ts_df.columns[0])

    fh = int(getattr(C, "FH", 1) or 1)

    result = run_dynamix_forecast(ts_df, target_col, fh)
    if result and isinstance(result.get("forecast_df"), pd.DataFrame):
        print(result["forecast_df"].head())


if __name__ == "__main__":
    main()
