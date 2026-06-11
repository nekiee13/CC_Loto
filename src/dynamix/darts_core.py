# ------------------------
# src/dynamix/darts_core.py
# ------------------------
"""
Darts forecasting pipeline for the DynaMix Lottery Forecasting System.

Post-refactor layout assumptions
--------------------------------
- This module is importable as:
    - src/dynamix/darts_core.py   (recommended)
  and the entrypoints at repo root insert REPO_ROOT into sys.path.

This module provides a stable API expected by:
- GUI / CLI entrypoints (run_cli.py)
- stat.py

Public API
----------
run_darts_forecast(
    ts_df: pd.DataFrame,
    target_col: str,
    forecast_horizon: int,
    model_type: str,
    **kwargs: Any,               # forwards/backwards compat (e.g., legacy use_cache)
) -> Dict[str, Any]

Compatibility notes
-------------------
- Accepts and ignores unknown kwargs (e.g., `use_cache=False`) to prevent test breakage.
- Event-mode: strict row semantics; no calendar expansion.
- TFT fix: `add_relative_index=True` to satisfy future covariates requirement.
"""

from __future__ import annotations

import argparse
import logging
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Preferred imports after your refactor (lowercase, src-based).
# If your entrypoints insert repo root into sys.path, these will work when:
#   src/dynamix is a package (has __init__.py).
try:
    from dynamix import constants as C
    from dynamix import data_utils as DU
except Exception:  # pragma: no cover
    # Fallback for transitional states where modules are still at repo root
    import constants as C  # type: ignore
    import data_utils as DU  # type: ignore

log = logging.getLogger(__name__)

# Optional Plotting integration (same pattern as GUI/CLI)
try:
    from dynamix import plotting as plotting  # type: ignore
    HAS_PLOTTING = True
except Exception:
    plotting = None  # type: ignore
    HAS_PLOTTING = False

# Darts imports (optional dependency)
try:
    from darts import TimeSeries
    from darts.dataprocessing.transformers import Scaler
    from darts.models import RNNModel, TCNModel, NBEATSModel, TransformerModel, TFTModel

    HAS_DARTS = True
except Exception as e:  # noqa: BLE001
    HAS_DARTS = False
    _DARTS_IMPORT_ERROR = repr(e)
else:
    _DARTS_IMPORT_ERROR = ""


# ----------------------------------------------------------------------
# Mode helpers
# ----------------------------------------------------------------------
def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


def _ts_columns() -> List[str]:
    cols = list(getattr(C, "TS_COLUMNS", []) or [])
    if cols:
        return cols
    return [f"TS_{i}" for i in range(1, 8)]


def _get_calendar_freq() -> Optional[str]:
    for attr in ("FREQ", "PCE_FREQ", "DARTS_FREQ"):
        v = getattr(C, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# ----------------------------------------------------------------------
# Index normalization
# ----------------------------------------------------------------------
def _coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        try:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        except Exception:
            pass
    return out


def _normalize_input_df(ts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure:
    - stable ordering
    - calendar mode: DatetimeIndex preferred (or parsed from DATE_COL if present)
    - event mode: preserve row semantics; do NOT require datetime freq
    """
    if ts_df is None or ts_df.empty:
        return ts_df

    df = ts_df.copy()

    # Sort if possible
    try:
        df = df.sort_index()
    except Exception:
        pass

    if _is_event_mode():
        # Event mode: do NOT coerce to datetime; do not expand/fill dates.
        return _coerce_numeric_columns(df).dropna(axis=0, how="all")

    # Calendar mode: parse DATE_COL into DatetimeIndex when needed
    date_col = str(getattr(C, "DATE_COL", "Date"))
    date_format = str(getattr(C, "DATE_FORMAT", "%d/%m/%Y"))

    if not isinstance(df.index, pd.DatetimeIndex):
        if date_col in df.columns:
            try:
                dt = pd.to_datetime(df[date_col], format=date_format, errors="coerce")
            except Exception:
                dt = pd.to_datetime(df[date_col], errors="coerce")

            mask = dt.notna()
            if mask.any():
                df = df.loc[mask].copy()
                df.index = dt.loc[mask]
                df.drop(columns=[date_col], inplace=True, errors="ignore")

    df = _coerce_numeric_columns(df)
    df = df.dropna(axis=0, how="all")

    try:
        df = df.sort_index()
    except Exception:
        pass

    return df


def _make_event_forecast_index(fh: int) -> pd.RangeIndex:
    return pd.RangeIndex(start=1, stop=int(fh) + 1, step=1, name=str(getattr(C, "FORECAST_STEP_INDEX_NAME", "ForecastStep")))


# ----------------------------------------------------------------------
# Darts model factory
# ----------------------------------------------------------------------
def _get_common_darts_hparams(forecast_horizon: int) -> Dict[str, Any]:
    in_len = int(getattr(C, "DARTS_INPUT_CHUNK_LENGTH", 12))
    out_len = int(getattr(C, "DARTS_OUTPUT_CHUNK_LENGTH", max(1, int(forecast_horizon))))
    n_epochs = int(getattr(C, "DARTS_EPOCHS", getattr(C, "DARTS_N_EPOCHS", 100)))
    batch_size = int(getattr(C, "DARTS_BATCH_SIZE", 32))
    random_state = int(getattr(C, "DARTS_RANDOM_STATE", 42))

    pl_trainer_kwargs = getattr(C, "DARTS_PL_TRAINER_KWARGS", None)
    if not isinstance(pl_trainer_kwargs, dict):
        pl_trainer_kwargs = {}

    if bool(getattr(C, "DARTS_FORCE_GPU", False)):
        pl_trainer_kwargs.setdefault("accelerator", "gpu")
        pl_trainer_kwargs.setdefault("devices", 1)

    if bool(getattr(C, "DARTS_DISABLE_PROGRESS_BAR", True)):
        pl_trainer_kwargs.setdefault("enable_progress_bar", False)

    return {
        "input_chunk_length": in_len,
        "output_chunk_length": out_len,
        "n_epochs": n_epochs,
        "batch_size": batch_size,
        "random_state": random_state,
        "pl_trainer_kwargs": pl_trainer_kwargs,
    }


def _build_model(model_type: str, forecast_horizon: int) -> Any:
    mt = str(model_type or "").strip().upper()
    hp = _get_common_darts_hparams(forecast_horizon)

    in_len = int(hp["input_chunk_length"])
    out_len = int(hp["output_chunk_length"])
    n_epochs = int(hp["n_epochs"])
    batch_size = int(hp["batch_size"])
    random_state = int(hp["random_state"])
    pl_trainer_kwargs = dict(hp["pl_trainer_kwargs"])

    lr = float(getattr(C, "DARTS_LR", 1e-3))

    if mt in ("GRU", "LSTM"):
        hidden_dim = int(getattr(C, "DARTS_RNN_HIDDEN_DIM", 64))
        n_rnn_layers = int(getattr(C, "DARTS_RNN_LAYERS", 2))
        dropout = float(getattr(C, "DARTS_RNN_DROPOUT", 0.0))

        return RNNModel(
            model=mt,
            input_chunk_length=in_len,
            output_chunk_length=out_len,
            hidden_dim=hidden_dim,
            n_rnn_layers=n_rnn_layers,
            dropout=dropout,
            batch_size=batch_size,
            n_epochs=n_epochs,
            optimizer_kwargs={"lr": lr},
            random_state=random_state,
            pl_trainer_kwargs=pl_trainer_kwargs,
        )

    if mt == "TCN":
        num_filters = int(getattr(C, "DARTS_TCN_NUM_FILTERS", 8))
        kernel_size = int(getattr(C, "DARTS_TCN_KERNEL_SIZE", 3))
        dilation_base = int(getattr(C, "DARTS_TCN_DILATION_BASE", 2))
        dropout = float(getattr(C, "DARTS_TCN_DILATION_BASE", 0.0)) if False else float(getattr(C, "DARTS_TCN_DROPOUT", 0.0))

        return TCNModel(
            input_chunk_length=in_len,
            output_chunk_length=out_len,
            num_filters=num_filters,
            kernel_size=kernel_size,
            dilation_base=dilation_base,
            dropout=dropout,
            batch_size=batch_size,
            n_epochs=n_epochs,
            optimizer_kwargs={"lr": lr},
            random_state=random_state,
            pl_trainer_kwargs=pl_trainer_kwargs,
        )

    if mt == "NBEATS":
        return NBEATSModel(
            input_chunk_length=in_len,
            output_chunk_length=out_len,
            batch_size=batch_size,
            n_epochs=n_epochs,
            random_state=random_state,
            pl_trainer_kwargs=pl_trainer_kwargs,
            optimizer_kwargs={"lr": lr},
        )

    if mt == "TRANSFORMER":
        d_model = int(getattr(C, "DARTS_TRANSFORMER_D_MODEL", 64))
        nhead = int(getattr(C, "DARTS_TRANSFORMER_NHEAD", 4))
        num_encoder_layers = int(getattr(C, "DARTS_TRANSFORMER_ENCODER_LAYERS", 3))
        num_decoder_layers = int(getattr(C, "DARTS_TRANSFORMER_DECODER_LAYERS", 3))
        dropout = float(getattr(C, "DARTS_TRANSFORMER_DROPOUT", 0.0))

        return TransformerModel(
            input_chunk_length=in_len,
            output_chunk_length=out_len,
            d_model=d_model,
            nhead=nhead,
            num_encoder_layers=num_encoder_layers,
            num_decoder_layers=num_decoder_layers,
            dropout=dropout,
            batch_size=batch_size,
            n_epochs=n_epochs,
            optimizer_kwargs={"lr": lr},
            random_state=random_state,
            pl_trainer_kwargs=pl_trainer_kwargs,
        )

    if mt == "TFT":
        hidden_size = int(getattr(C, "DARTS_TFT_HIDDEN_SIZE", 16))
        lstm_layers = int(getattr(C, "DARTS_TFT_LSTM_LAYERS", 1))
        dropout = float(getattr(C, "DARTS_TFT_DROPOUT", 0.0))

        # FIX: enable add_relative_index to satisfy TFT future covariates requirement
        return TFTModel(
            input_chunk_length=in_len,
            output_chunk_length=out_len,
            hidden_size=hidden_size,
            lstm_layers=lstm_layers,
            dropout=dropout,
            batch_size=batch_size,
            n_epochs=n_epochs,
            optimizer_kwargs={"lr": lr},
            random_state=random_state,
            pl_trainer_kwargs=pl_trainer_kwargs,
            add_relative_index=True,
        )

    raise ValueError(
        f"Unsupported Darts model_type='{model_type}'. Expected one of: GRU, LSTM, TCN, NBEATS, Transformer, TFT."
    )


# ----------------------------------------------------------------------
# TimeSeries creation + conversion + standardized output
# ----------------------------------------------------------------------
def _build_darts_series_from_target_df(tmp: pd.DataFrame, target_col: str) -> "TimeSeries":
    """
    Critical fix for frequency issues:
    - In event mode: force RangeIndex.
    - In calendar mode: allow missing dates and supply freq if configured.
    """
    if _is_event_mode():
        tmp2 = tmp.copy()
        tmp2 = tmp2.reset_index(drop=True)
        tmp2.index = pd.RangeIndex(start=0, stop=len(tmp2), step=1, name="Round")
        return TimeSeries.from_dataframe(tmp2, value_cols=[target_col])

    freq = _get_calendar_freq()
    return TimeSeries.from_dataframe(
        tmp,
        value_cols=[target_col],
        fill_missing_dates=True,
        freq=freq,
    )


def _timeseries_to_dataframe(pred: Any) -> pd.DataFrame:
    if hasattr(pred, "to_dataframe"):
        return pred.to_dataframe(copy=True, time_as_index=True)  # type: ignore[no-any-return]
    raise AttributeError("Prediction object does not expose to_dataframe(); unexpected Darts API.")


def _standardize_forecast_df(pred_df: pd.DataFrame, target_col: str, fh: int) -> pd.DataFrame:
    """
    - Enforce event-mode ForecastStep index
    - Standardize output columns to TS_1..TS_7 (or Constants.TS_COLUMNS)
    """
    out = pred_df.copy().iloc[: int(fh)].copy()

    if out.shape[1] == 1 and out.columns[0] != target_col:
        out = out.rename(columns={out.columns[0]: target_col})

    if _is_event_mode():
        out.index = _make_event_forecast_index(int(fh))

    ts_cols = _ts_columns()
    std = pd.DataFrame(index=out.index, columns=ts_cols, dtype="object")

    if target_col in out.columns:
        std[target_col] = out[target_col].to_list()
    else:
        if out.shape[1] == 1:
            std[target_col] = out.iloc[:, 0].to_list()
        else:
            std[target_col] = [pd.NA] * len(std)

    return std


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def run_darts_forecast(
    ts_df: pd.DataFrame,
    target_col: str,
    forecast_horizon: int = 1,
    model_type: str = "NBEATS",
    **_ignored_kwargs: Any,  # important: keeps compatibility with older callers (e.g., use_cache)
) -> Dict[str, Any]:
    """
    Returns:
      {
        "forecast_df": pd.DataFrame | None,
        "html_path": Path | None,
        "csv_path": Path | None,
        "model_type": str,
        "error": str | None
      }
    """
    if not HAS_DARTS:
        msg = f"Darts is not available. Import error: {_DARTS_IMPORT_ERROR}"
        log.error(msg)
        return {"forecast_df": None, "html_path": None, "csv_path": None, "model_type": str(model_type), "error": msg}

    if ts_df is None or ts_df.empty:
        msg = "run_darts_forecast: ts_df is empty."
        log.error(msg)
        return {"forecast_df": None, "html_path": None, "csv_path": None, "model_type": str(model_type), "error": msg}

    if target_col not in ts_df.columns:
        msg = f"run_darts_forecast: target_col '{target_col}' not in ts_df columns."
        log.error(msg)
        return {"forecast_df": None, "html_path": None, "csv_path": None, "model_type": str(model_type), "error": msg}

    try:
        fh = max(1, int(forecast_horizon))
    except Exception:
        fh = 1

    # Optional: Torch matmul precision knob
    try:
        if bool(getattr(C, "DARTS_SET_TORCH_MATMUL_PRECISION", False)):
            import torch  # type: ignore

            prec = str(getattr(C, "DARTS_TORCH_MATMUL_PRECISION", "high")).lower().strip()
            if prec not in ("medium", "high"):
                prec = "high"
            torch.set_float32_matmul_precision(prec)
    except Exception:
        pass

    # Normalize input
    df = _normalize_input_df(ts_df)

    # Target training series (numeric, drop NaNs)
    y = pd.to_numeric(df[target_col], errors="coerce")
    tmp = pd.DataFrame({target_col: y}, index=df.index).dropna(how="any")
    if tmp.empty or tmp.shape[0] < 10:
        msg = f"run_darts_forecast: insufficient non-NaN history for '{target_col}'. rows={tmp.shape[0]}"
        log.error(msg)
        return {"forecast_df": None, "html_path": None, "csv_path": None, "model_type": str(model_type), "error": msg}

    try:
        series = _build_darts_series_from_target_df(tmp, target_col)

        scaler = Scaler()
        series_scaled = scaler.fit_transform(series)

        model = _build_model(model_type=model_type, forecast_horizon=fh)
        model.fit(series_scaled, verbose=bool(getattr(C, "DARTS_VERBOSE", False)))

        pred_scaled = model.predict(n=fh)
        pred = scaler.inverse_transform(pred_scaled)

        pred_df_raw = _timeseries_to_dataframe(pred)
        forecast_df = _standardize_forecast_df(pred_df_raw, target_col=target_col, fh=fh)

    except Exception as e:  # noqa: BLE001
        err = f"Darts-{model_type} forecast failed: {e!r}"
        log.error("%s\n%s", err, traceback.format_exc())
        return {"forecast_df": None, "html_path": None, "csv_path": None, "model_type": str(model_type), "error": err}

    # Optional export
    html_path: Optional[Path] = None
    csv_path: Optional[Path] = None
    try:
        if HAS_PLOTTING and plotting is not None and bool(getattr(C, "EXPORT_ENABLED", True)):
            html_path, csv_path = plotting.export_forecast_plot_and_csv(  # type: ignore[attr-defined]
                history_df=df.copy(),
                forecast_df=forecast_df,
                target_col=target_col,
                model_label=f"Darts-{model_type}",
            )
    except Exception:
        log.error("Darts export failed:\n%s", traceback.format_exc())

    return {
        "forecast_df": forecast_df,
        "html_path": html_path,
        "csv_path": csv_path,
        "model_type": str(model_type),
        "error": None,
    }


# ----------------------------------------------------------------------
# Self-test helpers
# ----------------------------------------------------------------------
def _format_markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    str_rows = [[str(x) for x in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in str_rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: List[str]) -> str:
        padded = [cells[i].ljust(widths[i]) for i in range(len(headers))]
        return "| " + " | ".join(padded) + " |"

    header_line = fmt_row(headers)
    sep_line = "| " + " | ".join("-" * w for w in widths) + " |"
    data_lines = [fmt_row(r) for r in str_rows]
    return "\n".join([header_line, sep_line] + data_lines) + "\n"


def _safe_cell(v: Any) -> str:
    if v is None or v is pd.NA:
        return "-"
    try:
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return "-"
    except Exception:
        pass
    return str(v)


def _first_step_label(forecast_df: pd.DataFrame) -> str:
    if forecast_df is None or forecast_df.empty:
        return "N/A"
    idx0 = forecast_df.index[0]
    if _is_event_mode():
        return f"Step={idx0}"
    try:
        return idx0.strftime(getattr(C, "DATE_FORMAT", "%d/%m/%Y"))
    except Exception:
        return str(idx0)


def _apply_training_window(df: pd.DataFrame, window_rounds: int) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    w = int(window_rounds)
    if w <= 0:
        return df
    if len(df) <= w:
        return df
    return df.tail(w).copy()


def _resolve_effective_training_window(cli_window: Optional[int], no_window: bool) -> int:
    if no_window:
        return 0
    if cli_window is not None:
        try:
            return max(0, int(cli_window))
        except Exception:
            return 0
    try:
        return max(0, int(getattr(C, "TRAINING_WINDOW_ROUNDS", 0) or 0))
    except Exception:
        return 0


def _selftest(target: str, horizon: int, model_type: str, window: Optional[int], no_window: bool) -> int:
    print("[darts_core] Self-test starting...")
    print(f"[darts_core] HAS_DARTS={HAS_DARTS}")
    if not HAS_DARTS:
        print(f"[darts_core] Import error: {_DARTS_IMPORT_ERROR}")
        return 2

    try:
        # Prefer Constants.DATA_FILE if present, else DU default.
        data_file = Path(getattr(C, "DATA_FILE", "DATA.csv"))
        if data_file.exists():
            _ts_array, _date_index, ts_df = DU.load_lottery_data(data_file)
        else:
            _ts_array, _date_index, ts_df = DU.load_lottery_data()
    except Exception as e:  # noqa: BLE001
        print(f"[darts_core] Failed to load data via data_utils: {e!r}")
        return 2

    if ts_df is None or ts_df.empty:
        print("[darts_core] Loaded dataset is empty.")
        return 2

    if target not in ts_df.columns:
        print(f"[darts_core] Target '{target}' not found in dataset columns.")
        return 2

    effective_window = _resolve_effective_training_window(window, no_window)

    ts_df_full = ts_df
    ts_df = _apply_training_window(ts_df_full, effective_window)

    if effective_window > 0:
        print(f"[darts_core] Training window: last {effective_window} rows. full={len(ts_df_full)} windowed={len(ts_df)}")
    else:
        print("[darts_core] Training window: DISABLED (full history).")

    res = run_darts_forecast(
        ts_df=ts_df,
        target_col=target,
        forecast_horizon=int(horizon),
        model_type=str(model_type),
    )

    fdf = res.get("forecast_df", None)
    if not isinstance(fdf, pd.DataFrame) or fdf.empty:
        print("[darts_core] Forecast failed or returned empty forecast_df.")
        err = res.get("error", None)
        if err:
            print(f"[darts_core] error: {err}")
        return 1

    ts_cols = _ts_columns()
    headers = ["Model", ("Event/Step" if _is_event_mode() else "Date")] + ts_cols

    row = [f"Darts-{model_type}", _first_step_label(fdf)]
    for c in ts_cols:
        try:
            row.append(_safe_cell(fdf.iloc[0][c] if c in fdf.columns else pd.NA))
        except Exception:
            row.append("-")

    print("\n[darts_core] Self-test first-step forecast table:\n")
    print(_format_markdown_table(headers, [row]))

    if res.get("html_path") or res.get("csv_path"):
        print("[darts_core] Exports:")
        if res.get("html_path"):
            print(f"  HTML: {res['html_path']}")
        if res.get("csv_path"):
            print(f"  CSV : {res['csv_path']}")

    print("[darts_core] Self-test completed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="darts_core (DynaMix Lottery Forecasting System)")
    parser.add_argument("--selftest", action="store_true", help="Run end-to-end self-test and print first-step table.")
    parser.add_argument(
        "--target",
        type=str,
        default=str(getattr(C, "DARTS_SELFTEST_TARGET", getattr(C, "DARTS_MODEL_TARGET", "TS_1"))),
        help="Target series for selftest (default: TS_1 or constants overrides).",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=int(getattr(C, "DARTS_SELFTEST_HORIZON", 1)),
        help="Forecast horizon for selftest (default: 1 or constants override).",
    )
    parser.add_argument(
        "--model-type",
        type=str,
        default=str(getattr(C, "DARTS_MODEL_TYPE", "NBEATS")),
        help="Darts model type for selftest (default: constants.DARTS_MODEL_TYPE or NBEATS).",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        help="Row-based training window (rounds). If provided: use last N rows. N=0 disables the window.",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Force full-history training (disables any configured window).",
    )
    args = parser.parse_args()

    if args.selftest:
        raise SystemExit(
            _selftest(
                target=str(args.target),
                horizon=int(args.horizon),
                model_type=str(args.model_type),
                window=args.window,
                no_window=bool(args.no_window),
            )
        )

    print("darts_core.py is intended to be imported by GUI/CLI/stat.")
    print("Run `python -m dynamix.darts_core --selftest` (or `python darts_core.py --selftest`) to validate Darts end-to-end.")


if __name__ == "__main__":
    main()
