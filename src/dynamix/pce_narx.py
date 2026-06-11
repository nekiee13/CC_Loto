# ------------------------
# src/dynamix/pce_narx.py
# ------------------------
"""
Sparse PCE-NARX forecaster for DynaMix Lottery Forecasting System.

This module implements a probabilistic N-step-ahead forecast for a selected
lottery series (TS_1..TS_7) using a Polynomial Chaos Expansion (PCE) of a
NARX model:

    y_t ~= f(y_{t-1}, ..., y_{t-P}, exog_t)

Default configuration for your lottery use case is a pure NAR model:

    y_t ~= f(y_{t-1}, ..., y_{t-P})

Optionally, other TS_k (k ≠ n) can be used as regressors if:
    constants.PCE_USE_OTHER_TS_AS_EXOG = True

Important: Training-window compliance
-------------------------------------
Stat.py slices the history per step, possibly applying TRAINING_WINDOW_ROUNDS.
To preserve the meaning of "N rounds", this module supports a strict row-based mode:

    constants.PCE_STRICT_ROW_INDEX = True

When enabled:
- No asfreq() calendar expansion is applied (even if INDEX_MODE == "calendar").
- The data is treated exactly as passed in: one row = one round.

When disabled (legacy behavior):
- If INDEX_MODE == "calendar", we align to a regular frequency using asfreq()+ffill.

Public API:
    predict_pce_narx(data: pd.DataFrame, target_col: str, forecast_horizon: int) -> Optional[pd.DataFrame]
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

# ----------------------------------------------------------------------
# Robust imports after refactor
# ----------------------------------------------------------------------
try:
    from . import constants as C  # type: ignore
except Exception:  # pragma: no cover
    import constants as C  # type: ignore

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Mode helpers
# ----------------------------------------------------------------------
def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


def _make_future_index(y_index: pd.Index, fh: int, freq_str: str) -> pd.Index:
    """
    Construct a forecast index consistent with INDEX_MODE semantics.

    Event mode:
      - Default: ForecastStep = 1..fh (do not hallucinate calendar dates).
      - Optional: if constants.EVENT_FORECAST_ANCHOR_TO_LAST_EVENT_ID=True and
        y_index is integer-like, continue it (last_id+1..last_id+fh) using EVENT_INDEX_NAME.

    Calendar mode:
      - If y_index is DatetimeIndex: return date_range(last + freq, periods=fh).
      - Else: integer-like continuation where possible.
    """
    fh = max(1, int(fh))

    if _is_event_mode():
        anchor = bool(getattr(C, "EVENT_FORECAST_ANCHOR_TO_LAST_EVENT_ID", False))
        idx_name = str(getattr(C, "EVENT_INDEX_NAME", "EventID") or "EventID")
        step_name = str(getattr(C, "FORECAST_STEP_INDEX_NAME", "ForecastStep") or "ForecastStep")

        if anchor:
            try:
                last_int = int(y_index[-1])  # type: ignore[arg-type]
                return pd.RangeIndex(start=last_int + 1, stop=last_int + 1 + fh, step=1, name=idx_name)
            except Exception:
                pass

        return pd.RangeIndex(start=1, stop=fh + 1, step=1, name=step_name)

    # Calendar mode
    last_idx = y_index[-1]
    if isinstance(y_index, pd.DatetimeIndex):
        try:
            return pd.date_range(
                start=pd.Timestamp(last_idx) + to_offset(freq_str),
                periods=fh,
                freq=freq_str,
            )
        except Exception:
            return pd.date_range(
                start=pd.Timestamp(last_idx) + to_offset("D"),
                periods=fh,
                freq="D",
            )

    # Non-datetime: attempt integer continuation
    try:
        last_int = int(last_idx)
        return pd.RangeIndex(start=last_int + 1, stop=last_int + 1 + fh, step=1, name="Round")
    except Exception:
        return pd.RangeIndex(start=0, stop=fh, step=1, name="Round")


# ----------------------------------------------------------------------
# 1. Lazy imports of optional dependencies
# ----------------------------------------------------------------------
def _import_dependencies() -> Tuple[Any, Any, Any]:
    """
    Imports chaospy and LassoCV lazily.

    Returns
    -------
    (cp, cp_expansion, LassoCV)
        cp : chaospy module or None
        cp_expansion : chaospy.expansion submodule or None
        LassoCV : sklearn.linear_model.LassoCV class or None
    """
    try:
        import chaospy as cp  # type: ignore
    except ImportError:
        log.warning("PCE-NARX: Optional dependency 'chaospy' is not installed. Skipping PCE model.")
        return None, None, None

    try:
        from sklearn.linear_model import LassoCV  # type: ignore
    except ImportError:
        log.warning("PCE-NARX: scikit-learn is not installed. Skipping PCE model.")
        return None, None, None

    try:
        from chaospy import expansion as cp_expansion  # type: ignore
    except Exception:
        cp_expansion = None

    return cp, cp_expansion, LassoCV


# ----------------------------------------------------------------------
# 2. Dataset construction (NARX design matrix)
# ----------------------------------------------------------------------
def _build_narx_dataset_from_df(
    y_series: pd.Series,
    exog_df: Optional[pd.DataFrame],
    max_lag: int,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Constructs a NARX-style regression dataset.

    Model structure:
        y_t ~ f(y_{t-1}, ..., y_{t-max_lag}, exog_t)

    Returns (None, None) if insufficient data.
    """
    if exog_df is not None:
        common_idx = y_series.index.intersection(exog_df.index)
        y_subset = y_series.loc[common_idx]
        exog_subset = exog_df.loc[common_idx]
    else:
        y_subset = y_series
        exog_subset = None

    if len(y_subset) <= max_lag:
        return None, None

    X_list: List[List[float]] = []
    y_list: List[float] = []

    values_y = y_subset.values
    values_exog = exog_subset.values if exog_subset is not None else None

    for i in range(max_lag, len(y_subset)):
        row_features: List[float] = []

        # Autoregressive lags: y_{t-1}, ..., y_{t-max_lag}
        for lag in range(1, max_lag + 1):
            row_features.append(float(values_y[i - lag]))

        # Exogenous inputs at time t
        if values_exog is not None:
            row_features.extend(values_exog[i].astype(float))

        X_list.append(row_features)
        y_list.append(float(values_y[i]))

    X = np.asarray(X_list, dtype=float)
    y = np.asarray(y_list, dtype=float)
    return X, y


# ----------------------------------------------------------------------
# 3. Feature scaling
# ----------------------------------------------------------------------
def _scale_features(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Affine scales each feature in X into approximately [-1, 1].
    """
    feat_min = X.min(axis=0)
    feat_max = X.max(axis=0)
    feat_range = feat_max - feat_min
    feat_range[feat_range == 0.0] = 1.0
    X_scaled = 2.0 * (X - feat_min) / feat_range - 1.0
    return X_scaled, feat_min, feat_range


# ----------------------------------------------------------------------
# 4. Public API
# ----------------------------------------------------------------------
def predict_pce_narx(
    data: pd.DataFrame,
    target_col: Optional[str] = None,
    forecast_horizon: Optional[int] = None,
    progress_callback=None,
) -> Optional[pd.DataFrame]:
    """
    Trains a sparse PCE-NARX model for the selected series and produces
    an N-step-ahead forecast with a simple normal-approx interval.

    Window compliance:
    - Stat.py provides a history slice (potentially training-windowed).
    - If constants.PCE_STRICT_ROW_INDEX=True, do NOT expand/fill dates.

    Returns
    -------
    pd.DataFrame with columns:
        PCE_Pred, PCE_Lower, PCE_Upper
    indexed by a future index (datetime if possible; otherwise RangeIndex-like).
    """
    if not bool(getattr(C, "PCE_ENABLED", True)):
        log.info("PCE-NARX: Disabled via constants.PCE_ENABLED = False.")
        return None

    if data is None or data.empty:
        log.warning("PCE-NARX: Input DataFrame is empty.")
        return None

    cp, cp_expansion, LassoCV = _import_dependencies()
    if cp is None or LassoCV is None:
        return None

    if target_col is None:
        target_col = str(getattr(C, "PCE_TARGET_COL", "TS_1"))

    if target_col not in data.columns:
        log.warning("PCE-NARX: Target column '%s' not found in data.", target_col)
        return None

    # Configuration
    freq_str = str(getattr(C, "PCE_FREQ", getattr(C, "FREQ", "D")))
    date_col_name = str(getattr(C, "DATE_COL", "Date"))
    date_format = str(getattr(C, "DATE_FORMAT", "%d/%m/%Y"))

    index_mode = str(getattr(C, "INDEX_MODE", "calendar")).lower().strip()
    strict_row = bool(getattr(C, "PCE_STRICT_ROW_INDEX", True))

    # ------------------------------------------------------------------
    # 4.1 Index normalization
    # ------------------------------------------------------------------
    df = data.copy()

    # If there is a Date column, parse it; otherwise keep existing index.
    if not isinstance(df.index, pd.DatetimeIndex):
        if date_col_name in df.columns:
            try:
                dt_idx = pd.to_datetime(df[date_col_name], format=date_format, errors="coerce")
            except Exception:
                dt_idx = pd.to_datetime(df[date_col_name], errors="coerce")

            mask_valid = dt_idx.notna()
            if not mask_valid.any():
                log.warning("PCE-NARX: No valid dates after parsing. Using row index instead.")
                df = df.drop(columns=[date_col_name], errors="ignore")
                df.index = pd.RangeIndex(start=0, stop=len(df), step=1)
            else:
                df = df.loc[mask_valid].copy()
                df.index = dt_idx[mask_valid]
                df.drop(columns=[date_col_name], inplace=True, errors="ignore")
        else:
            # No datetime info at all => enforce row index
            df.index = pd.RangeIndex(start=0, stop=len(df), step=1)

    try:
        df.sort_index(inplace=True)
    except Exception:
        pass

    # Numeric conversion
    df_numeric = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    if df_numeric.empty:
        log.warning("PCE-NARX: All rows are NaN after numeric conversion.")
        return None

    # ------------------------------------------------------------------
    # 4.2 Frequency handling
    # ------------------------------------------------------------------
    # Legacy (calendar) behavior expands to regular dates, but that breaks
    # "N rounds" semantics under TRAINING_WINDOW_ROUNDS.
    if (not strict_row) and (index_mode == "calendar") and (not _is_event_mode()):
        # Legacy calendar behavior: expand to regular dates and ffill.
        try:
            df_numeric = df_numeric.asfreq(freq_str).ffill()
        except Exception:
            df_numeric = df_numeric.asfreq("D").ffill()
    else:
        # Strict row-based (calendar) or event mode: never expand index.
        if _is_event_mode():
            before = int(len(df_numeric))
            df_numeric = df_numeric.dropna(how="any")
            dropped = before - int(len(df_numeric))
            if dropped > 0:
                log.warning("PCE-NARX (event mode): Dropped %d rows containing NaNs to avoid imputation.", dropped)
        else:
            # Strict row-based calendar mode: keep rows, allow ffill only within existing rows
            df_numeric = df_numeric.ffill()

    if target_col not in df_numeric.columns:
        log.warning("PCE-NARX: Target column '%s' missing after preprocessing.", target_col)
        return None

    y_series = df_numeric[target_col].dropna()
    if y_series.empty:
        log.warning("PCE-NARX: Target series is empty after dropna.")
        return None

    # ------------------------------------------------------------------
    # 4.3 Exogenous configuration
    # ------------------------------------------------------------------
    use_other_ts_as_exog = bool(getattr(C, "PCE_USE_OTHER_TS_AS_EXOG", False))
    if use_other_ts_as_exog:
        exog_cols = [c for c in df_numeric.columns if c != target_col]
        exog_train_df = df_numeric[exog_cols].copy() if exog_cols else None
    else:
        exog_train_df = None

    # Align exog with target
    if exog_train_df is not None:
        exog_train_df = exog_train_df.apply(pd.to_numeric, errors="coerce").reindex(y_series.index)

        # Keep only rows where ALL exog are non-NaN (strict for regressors)
        valid_idx = exog_train_df.dropna(how="any").index
        exog_train_df = exog_train_df.loc[valid_idx]
        y_series = y_series.reindex(valid_idx).dropna()
        exog_train_df = exog_train_df.reindex(y_series.index)

        if y_series.empty:
            log.warning("PCE-NARX: Target became empty after exog alignment.")
            return None

    # ------------------------------------------------------------------
    # 4.4 Build dataset
    # ------------------------------------------------------------------
    max_lag = int(getattr(C, "PCE_LAGS", 5))
    min_samples = int(getattr(C, "PCE_MIN_SAMPLES", 50))

    X, y = _build_narx_dataset_from_df(y_series, exog_train_df, max_lag)
    if X is None or y is None:
        log.warning("PCE-NARX: Insufficient data: len(y_series)=%d max_lag=%d", len(y_series), max_lag)
        return None

    if len(X) < min_samples:
        log.warning(
            "PCE-NARX: Insufficient samples after lagging. samples=%d required>=%d (max_lag=%d).",
            len(X), min_samples, max_lag
        )
        return None

    n_samples, n_features = X.shape
    log.info("PCE-NARX: Training dataset shape X=%s y=%s.", X.shape, y.shape)

    # ------------------------------------------------------------------
    # 4.5 Scale features
    # ------------------------------------------------------------------
    X_scaled, feat_min, feat_range = _scale_features(X)

    # ------------------------------------------------------------------
    # 4.6 Polynomial chaos basis
    # ------------------------------------------------------------------
    poly_degree = int(getattr(C, "PCE_POLY_DEGREE", 2))
    dist = cp.Iid(cp.Uniform(-1.0, 1.0), n_features)

    if cp_expansion is not None and hasattr(cp_expansion, "stieltjes"):
        poly_expansion = cp_expansion.stieltjes(poly_degree, dist)
    else:
        poly_expansion = cp.orth_ttr(poly_degree, dist)

    # Evaluate basis on training data
    try:
        A_train = cp.call(poly_expansion, X_scaled.T).T
    except AttributeError:
        A_train = cp.eval_polynomial(poly_expansion, X_scaled.T).T

    # ------------------------------------------------------------------
    # 4.7 Sparse regression via LassoCV
    # ------------------------------------------------------------------
    alphas = getattr(C, "PCE_LASSO_ALPHAS", [1e-4, 1e-3, 1e-2])
    cv_folds = int(getattr(C, "PCE_LASSO_CV_FOLDS", 3))
    random_state = int(getattr(C, "PCE_RANDOM_STATE", 42))

    lasso = LassoCV(
        alphas=alphas,
        cv=cv_folds,
        n_jobs=1,
        random_state=random_state,
    )
    lasso.fit(A_train, y)

    y_hat = lasso.predict(A_train)
    residuals = y - y_hat
    sigma = float(np.std(residuals, ddof=1))
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.std(y) * 0.05) if np.std(y) > 0 else 1.0

    log.info("PCE-NARX: Fitted LassoCV; alpha=%.2e sigma=%.4f", float(lasso.alpha_), sigma)

    # ------------------------------------------------------------------
    # 4.8 Recursive forecasting
    # ------------------------------------------------------------------
    if forecast_horizon is not None:
        fh = int(forecast_horizon)
    else:
        fh = int(getattr(C, "PCE_FH", getattr(C, "FH", 1)))

    if fh <= 0:
        log.warning("PCE-NARX: Non-positive forecast horizon fh=%d.", fh)
        return None

    # Future exogenous (if used): naive persistence
    if exog_train_df is not None and not exog_train_df.empty:
        last_exog_row = np.array(exog_train_df.iloc[-1].values, dtype=float)
        exog_future_vals = np.tile(last_exog_row, (fh, 1))
    else:
        exog_future_vals = None

    y_hist: List[float] = list(y_series.values)

    preds: List[float] = []
    lowers: List[float] = []
    uppers: List[float] = []

    z_score = float(getattr(C, "PCE_Z_SCORE", 1.645))

    for step in range(fh):
        feats: List[float] = [float(y_hist[-lag]) for lag in range(1, max_lag + 1)]
        if exog_future_vals is not None:
            feats.extend(exog_future_vals[step].tolist())

        z_vec = np.asarray(feats, dtype=float)
        if int(z_vec.shape[0]) != int(n_features):
            log.error(
                "PCE-NARX: Feature length mismatch during forecast: got %d expected %d",
                int(z_vec.shape[0]), int(n_features)
            )
            return None

        # Scale
        z_scaled = 2.0 * (z_vec - feat_min) / feat_range - 1.0
        z_scaled_2d = z_scaled.reshape(n_features, 1)

        # Polynomial evaluation
        try:
            A_future = cp.call(poly_expansion, z_scaled_2d).T
        except AttributeError:
            A_future = cp.eval_polynomial(poly_expansion, z_scaled_2d).T

        y_pred = float(lasso.predict(A_future)[0])
        preds.append(y_pred)
        lowers.append(y_pred - z_score * sigma)
        uppers.append(y_pred + z_score * sigma)

        y_hist.append(y_pred)

        if progress_callback is not None:
            try:
                progress_callback(step + 1, fh)
            except Exception:
                log.exception("PCE-NARX: progress_callback raised an exception.")

    # ------------------------------------------------------------------
    # 4.9 Future index
    # ------------------------------------------------------------------
    future_index = _make_future_index(y_series.index, fh=int(fh), freq_str=str(freq_str))

    result_df = pd.DataFrame(
        {"PCE_Pred": preds, "PCE_Lower": lowers, "PCE_Upper": uppers},
        index=future_index,
    )

    # Name the index meaningfully
    if _is_event_mode():
        result_df.index.name = str(getattr(C, "FORECAST_STEP_INDEX_NAME", "ForecastStep") or "ForecastStep")
    else:
        if isinstance(result_df.index, pd.DatetimeIndex):
            result_df.index.name = y_series.index.name or "Date"
        else:
            result_df.index.name = y_series.index.name or "Round"

    return result_df
