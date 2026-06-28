# ------------------------
# run_cli.py
# ------------------------
"""
CLI entry point for the DynaMix Lottery Forecasting System.

Assumed repo layout (recommended):
  repo_root/
    run_cli.py              (this file; entrypoint)
    src/
      dynamix/
        __init__.py
        constants.py
        data_utils.py
        dynamix_core.py
        pce_narx.py
        darts_core.py        (optional dependency boundary)
        plotting.py
    tools/
    tests/

This entrypoint adds repo_root/src to sys.path so imports work without installing the package.
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ----------------------------------------------------------------------
# Project imports (package entrypoint: dynamix.entrypoints.run_cli)
# ----------------------------------------------------------------------
from dynamix import constants as C  # type: ignore
from dynamix import data_utils as DU  # type: ignore
from dynamix import dynamix_core as DCore  # type: ignore
from dynamix import pce_narx as PCE  # type: ignore

# Optional: Darts core
try:
    from dynamix import darts_core as DartCore  # type: ignore
except Exception:
    DartCore = None  # type: ignore[assignment]


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("pytorch_lightning").setLevel(logging.WARNING)
logging.getLogger("darts").setLevel(logging.WARNING)
warnings.filterwarnings("ignore")
log = logging.getLogger("CLI")


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
ALL_DARTS_MODELS = ["GRU", "LSTM", "TCN", "NBEATS", "Transformer", "TFT"]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


def _format_forecast_index_label(idx0: Any, *, index_name: Optional[str] = None) -> str:
    """Format the forecast step label (Date or Event/Step)."""
    if _is_event_mode():
        name = (index_name or "").strip().lower()
        val_str = str(idx0)

        if "forecast" in name and "step" in name:
            return f"Step={val_str}"
        if val_str.isdigit():
            return f"EventID={val_str}"
        return val_str

    try:
        return idx0.strftime(getattr(C, "DATE_FORMAT", "%d/%m/%Y"))
    except Exception:
        return str(idx0)


def format_val(val: Any) -> str:
    """Format value to 2 decimal places."""
    if val is None:
        return "N/A"
    try:
        if pd.isna(val):
            return "N/A"
    except Exception:
        pass
    try:
        return f"{float(val):.2f}"
    except Exception:
        return str(val)


def get_first_forecast_step(
    forecast_df: Optional[pd.DataFrame],
    col_name: str,
) -> Tuple[str, Any]:
    """Extracts (label_str, raw_value) for the first step."""
    if forecast_df is None or forecast_df.empty:
        return ("N/A", None)

    idx0 = forecast_df.index[0]
    idx_name = getattr(forecast_df.index, "name", None)
    label_str = _format_forecast_index_label(idx0, index_name=str(idx_name) if idx_name is not None else None)

    # Prefer requested column
    if col_name in forecast_df.columns:
        return (label_str, forecast_df[col_name].iloc[0])

    # PCE fallback
    if "PCE_Pred" in forecast_df.columns:
        return (label_str, forecast_df["PCE_Pred"].iloc[0])

    # First column fallback
    try:
        return (label_str, forecast_df.iloc[0, 0])
    except Exception:
        return (label_str, None)


def _apply_training_window(df: pd.DataFrame, window_rounds: int) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    w = int(window_rounds)
    if w <= 0 or len(df) <= w:
        return df
    return df.tail(w).copy()


def resolve_effective_training_window(cli_window: Optional[int], no_window: bool) -> int:
    if no_window:
        return 0
    if cli_window is not None:
        return max(0, int(cli_window))
    try:
        return max(0, int(getattr(C, "TRAINING_WINDOW_ROUNDS", 0) or 0))
    except Exception:
        return 0


def _announce_window(w: int) -> None:
    if w <= 0:
        print("[CLI] Training window: DISABLED (full history).")
    else:
        print(f"[CLI] Training window: last {w} rounds (rows).")


def _set_runtime_window(effective_window: int) -> None:
    """Best-effort: keep runtime config consistent across modules."""
    try:
        setattr(C, "TRAINING_WINDOW_ROUNDS", int(effective_window))
    except Exception:
        pass


# ----------------------------------------------------------------------
# Single Mode (Univariate Focus)
# ----------------------------------------------------------------------
def run_single_mode(ts_df: pd.DataFrame, target_col: str, fh: int, effective_window: int) -> None:
    """Runs DynaMix, PCE, and ALL Darts models for a single series."""
    print(f"\n--- Single Mode: Forecasting {target_col} (Horizon={fh}) ---\n")
    _announce_window(effective_window)
    _set_runtime_window(effective_window)

    ts_win = _apply_training_window(ts_df[[target_col]], effective_window)

    rows: List[List[str]] = []

    # 1) DynaMix
    log.info("Running DynaMix...")
    try:
        dm_res = DCore.run_dynamix_forecast(ts_df=ts_win, target_col=target_col, forecast_horizon=fh)
        dm_df = dm_res.get("forecast_df") if isinstance(dm_res, dict) else None
        d_str, val = get_first_forecast_step(dm_df, target_col)
        rows.append(["DynaMix", d_str, format_val(val)])
    except Exception as e:
        log.error(f"DynaMix failed: {e}")
        rows.append(["DynaMix", "N/A", "N/A"])

    # 2) PCE-NARX
    log.info("Running PCE-NARX...")
    try:
        pce_df = PCE.predict_pce_narx(data=ts_win, target_col=target_col, forecast_horizon=fh)
        d_str, val = get_first_forecast_step(pce_df, "PCE_Pred")
        rows.append(["PCE", d_str, format_val(val)])
    except Exception as e:
        log.error(f"PCE-NARX failed: {e}")
        rows.append(["PCE", "N/A", "N/A"])

    # 3) Darts (All Architectures)
    if DartCore is not None and bool(getattr(C, "DARTS_ENABLED", True)):
        for model in ALL_DARTS_MODELS:
            log.info(f"Running Darts-{model}...")
            try:
                res = DartCore.run_darts_forecast(
                    ts_df=ts_win,
                    target_col=target_col,
                    forecast_horizon=fh,
                    model_type=model,
                )
                f_df = res.get("forecast_df") if isinstance(res, dict) else None
                d_str, val = get_first_forecast_step(f_df, target_col)
                rows.append([model, d_str, format_val(val)])
            except Exception as e:
                log.error(f"Darts-{model} failed: {e}")
                rows.append([model, "N/A", "N/A"])
    else:
        rows.append(["Darts (All)", "Skipped", "Module Missing/Disabled"])

    headers = ["Model", "Event/Step" if _is_event_mode() else "Date", target_col]
    print("\n[Final Forecast Result]")
    DU.print_markdown_table(headers, rows)


# ----------------------------------------------------------------------
# Batch Mode (All Series, All Models)
# ----------------------------------------------------------------------
def run_batch_mode(ts_df: pd.DataFrame, fh: int, effective_window: int) -> None:
    """Runs forecasts for ALL series using ALL models (DynaMix, PCE, All Darts)."""
    print(f"\n--- Batch Mode: Forecasting All Series (Horizon={fh}) ---\n")
    _announce_window(effective_window)
    _set_runtime_window(effective_window)

    ts_cols = list(getattr(C, "TS_COLUMNS", []))
    if not ts_cols:
        log.error("C.TS_COLUMNS is empty.")
        return

    ts_win = _apply_training_window(ts_df, effective_window)

    rows: List[List[str]] = []

    # 1) DynaMix (Multivariate baseline — but your wrapper signature is univariate target_col;
    # we call it with one target and then read all cols from forecast_df if available)
    log.info("Running DynaMix (Multivariate baseline call)...")
    dm_row: List[str] = ["DynaMix"]
    try:
        dm_res = DCore.run_dynamix_forecast(ts_df=ts_win, target_col=ts_cols[0], forecast_horizon=fh)
        dm_df = dm_res.get("forecast_df") if isinstance(dm_res, dict) else None

        d_str, _ = get_first_forecast_step(dm_df, ts_cols[0])
        dm_row.append(d_str)

        if dm_df is not None and not dm_df.empty:
            for col in ts_cols:
                dm_row.append(format_val(dm_df[col].iloc[0] if col in dm_df.columns else None))
        else:
            dm_row.extend(["N/A"] * len(ts_cols))
    except Exception as e:
        log.error(f"DynaMix failed: {e}")
        dm_row.append("N/A")
        dm_row.extend(["N/A"] * len(ts_cols))
    rows.append(dm_row)

    # 2) PCE-NARX (univariate per series)
    log.info("Running PCE-NARX...")
    pce_row: List[str] = ["PCE"]
    pce_date = "N/A"
    pce_vals: List[str] = []

    for col in ts_cols:
        try:
            sub = ts_win[[col]]
            pce_df = PCE.predict_pce_narx(data=sub, target_col=col, forecast_horizon=fh)
            d_s, val = get_first_forecast_step(pce_df, "PCE_Pred")
            if pce_date == "N/A":
                pce_date = d_s
            pce_vals.append(format_val(val))
        except Exception as e:
            log.error(f"PCE failed for {col}: {e}")
            pce_vals.append("N/A")

    pce_row.append(pce_date)
    pce_row.extend(pce_vals)
    rows.append(pce_row)

    # 3) Darts (all models per series)
    if DartCore is not None and bool(getattr(C, "DARTS_ENABLED", True)):
        for model in ALL_DARTS_MODELS:
            log.info(f"Running Darts-{model}...")
            m_row: List[str] = [model]
            m_date = "N/A"
            m_vals: List[str] = []

            for col in ts_cols:
                try:
                    res = DartCore.run_darts_forecast(
                        ts_df=ts_win[[col]],
                        target_col=col,
                        forecast_horizon=fh,
                        model_type=model,
                    )
                    f_df = res.get("forecast_df") if isinstance(res, dict) else None
                    d_s, val = get_first_forecast_step(f_df, col)
                    if m_date == "N/A":
                        m_date = d_s
                    m_vals.append(format_val(val))
                except Exception as e:
                    log.error(f"Darts-{model} failed on {col}: {e}")
                    m_vals.append("N/A")

            m_row.append(m_date)
            m_row.extend(m_vals)
            rows.append(m_row)
    else:
        rows.append(["Darts", "Skipped"] + ["Disabled/Missing"] * len(ts_cols))

    headers = ["Model", "Event/Step" if _is_event_mode() else "Date"] + ts_cols
    print("\n[Batch Forecast Matrix]")
    DU.print_markdown_table(headers, rows)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="DynaMix Lottery Forecast CLI")
    parser.add_argument("--target", type=str, help="Target series (e.g. TS_1). If omitted, runs batch.")
    parser.add_argument("--horizon", type=int, default=int(getattr(C, "FH", 1)))
    parser.add_argument("--window", type=int, default=None, help="Row-based training window.")
    parser.add_argument("--no-window", action="store_true", help="Force full history.")

    args = parser.parse_args()
    eff_win = resolve_effective_training_window(args.window, args.no_window)

    if args.horizon <= 0:
        log.error("Horizon must be >= 1")
        return

    try:
        _arr, _idx, ts_df = DU.load_lottery_data()
    except Exception as e:
        log.error(f"Data load error: {e}")
        return

    if args.target:
        if args.target not in ts_df.columns:
            log.error(f"Target {args.target} not in data.")
            return
        run_single_mode(ts_df, args.target, args.horizon, eff_win)
    else:
        run_batch_mode(ts_df, args.horizon, eff_win)


if __name__ == "__main__":
    main()
