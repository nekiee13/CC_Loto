# ------------------------
# src/dynamix/candidate_grid.py
# ------------------------
"""
Forecast collection + candidate-grid row construction (extracted from ``dynamix.stat``).

This module owns the stage-2 -> stage-3 bridge: it runs the per-series model forecasts for a
rolling step (``collect_model_forecasts_for_step`` / ``_forecast_single_series``) and turns the
per-(TS, model) predictions into candidate-grid rows across all rounding modes
(``build_candidate_grid_rows`` + the rounding primitives).

It was split out of the ~1600-line ``dynamix.stat`` god-module (E4) so the candidate-grid logic
is importable and unit-testable in isolation, and so the optimizer/orchestrator can depend on it
directly rather than reaching into the backtest entrypoint. ``dynamix.stat`` re-exports every
public name here for backward compatibility.

Model dependencies stay fail-soft: a missing optional runtime (DynaMix/PCE/Darts) disables that
family with a warning rather than erroring.
"""
from __future__ import annotations

import logging
import math
import traceback
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal, ROUND_HALF_DOWN, ROUND_HALF_UP
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from dynamix import constants as C  # type: ignore
from dynamix import dynamix_core as DCore  # type: ignore
from dynamix import pce_narx  # type: ignore

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Darts Core import (with explicit diagnostics)
# - Prefer src/dynamix/darts_core.py if present.
# - If absent/unavailable, disable darts models.
# ----------------------------------------------------------------------
from typing import Any as _Any

DartCore: _Any
try:
    from dynamix import darts_core as _DartCore  # type: ignore

    DartCore = _DartCore
    HAS_DARTS_CORE: bool = True
except Exception as e:  # noqa: BLE001
    DartCore = None  # type: ignore[assignment]
    HAS_DARTS_CORE = False
    log.warning(
        "darts_core could not be imported. Darts models disabled. Error: %r", e
    )


# ----------------------------------------------------------------------
# Series / model configuration (config-derived, no model runtime needed)
# ----------------------------------------------------------------------
TS_LIST: List[str] = list(getattr(C, "TS_COLUMNS", []))

MODEL_NAMES: List[str] = [
    "DynaMix",
    "PCE",
    "GRU",
    "LSTM",
    "TCN",
    "NBEATS",
    "Transformer",
    "TFT",
]
DARTS_MODEL_TYPES: List[str] = ["GRU", "LSTM", "TCN", "NBEATS", "Transformer", "TFT"]

WorkerError = Dict[str, Any]
ExportRow = Dict[str, Any]


# ----------------------------------------------------------------------
# Step labelling helpers
# ----------------------------------------------------------------------
def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


def _format_step_label(dataset_index: int, step_date: Any) -> str:
    if _is_event_mode():
        label = f"EventIndex={int(dataset_index)}"
        try:
            if hasattr(step_date, "date"):
                label += f" (Date={step_date.date()})"
            elif step_date not in (None, "N/A"):
                label += f" (Date={str(step_date)})"
        except Exception:
            pass
        return label

    try:
        if hasattr(step_date, "strftime"):
            return f"Date={step_date.strftime(getattr(C, 'DATE_FORMAT', '%d/%m/%Y'))}"
    except Exception:
        pass
    return f"Date={step_date.isoformat()}" if hasattr(step_date, "isoformat") else f"Date={str(step_date)}"


# ----------------------------------------------------------------------
# Rounding modes
# ----------------------------------------------------------------------
class RoundingMode(Enum):
    TRUNCATE = auto()
    HALF_UP = auto()
    FLOOR = auto()
    CEIL = auto()
    HALF_TO_EVEN = auto()
    HALF_DOWN = auto()
    HALF_AWAY_FROM_ZERO = auto()


ROUNDING_MODE_LABELS: Dict[RoundingMode, str] = {
    RoundingMode.TRUNCATE: "1 - Truncate (towards zero)",
    RoundingMode.HALF_UP: "2 - Round half up",
    RoundingMode.FLOOR: "3 - Floor",
    RoundingMode.CEIL: "4 - Ceiling",
    RoundingMode.HALF_TO_EVEN: "5 - Round half to even",
    RoundingMode.HALF_DOWN: "6 - Round half down",
    RoundingMode.HALF_AWAY_FROM_ZERO: "7 - Round half away from zero",
}


def rounding_mode_id(mode: RoundingMode) -> int:
    return int(mode.value)


def apply_round(value: float, mode: RoundingMode) -> int:
    if math.isnan(value) or math.isinf(value):
        return 0

    if mode == RoundingMode.TRUNCATE:
        return int(value)
    if mode == RoundingMode.FLOOR:
        return math.floor(value)
    if mode == RoundingMode.CEIL:
        return math.ceil(value)

    d = Decimal(str(value))

    if mode == RoundingMode.HALF_TO_EVEN:
        return int(d.to_integral_value(rounding="ROUND_HALF_EVEN"))
    if mode == RoundingMode.HALF_UP:
        return int(d.to_integral_value(rounding=ROUND_HALF_UP))
    if mode == RoundingMode.HALF_DOWN:
        return int(d.to_integral_value(rounding=ROUND_HALF_DOWN))
    if mode == RoundingMode.HALF_AWAY_FROM_ZERO:
        if value >= 0:
            return int(d.to_integral_value(rounding=ROUND_HALF_UP))
        mag = -d
        mag_rounded = mag.to_integral_value(rounding=ROUND_HALF_UP)
        return int(-mag_rounded)

    return int(round(value))


# ----------------------------------------------------------------------
# Per-series forecasting (strictly independent worker)
# ----------------------------------------------------------------------
def _forecast_single_series(args: Tuple[str, pd.DataFrame, int]) -> Tuple[str, Dict[str, float], List[WorkerError]]:
    ts_name, ts_univariate_df, forecast_horizon = args
    forecasts_for_ts: Dict[str, float] = {}
    errors: List[WorkerError] = []

    def _err(model: str, exc: BaseException) -> None:
        errors.append(
            {
                "ts": ts_name,
                "model": model,
                "error": repr(exc),
                "traceback": traceback.format_exc(limit=15),
                "history_len": int(ts_univariate_df.shape[0]),
            }
        )

    if bool(getattr(C, "STATS_ENABLE_DYNAMIX", True)):
        try:
            if ts_univariate_df.shape[0] > 0:
                dm_res = DCore.run_dynamix_forecast(
                    ts_df=ts_univariate_df,
                    target_col=ts_name,
                    forecast_horizon=forecast_horizon,
                )
                if isinstance(dm_res, dict):
                    dm_df = dm_res.get("forecast_df")
                    if isinstance(dm_df, pd.DataFrame) and not dm_df.empty and ts_name in dm_df.columns:
                        forecasts_for_ts["DynaMix"] = float(dm_df[ts_name].iloc[0])
        except Exception as e:  # noqa: BLE001
            _err("DynaMix", e)

    if bool(getattr(C, "STATS_ENABLE_PCE", True)) and bool(getattr(C, "PCE_ENABLED", True)):
        try:
            pce_df = pce_narx.predict_pce_narx(
                data=ts_univariate_df,
                target_col=ts_name,
                forecast_horizon=forecast_horizon,
            )
            if isinstance(pce_df, pd.DataFrame) and not pce_df.empty and "PCE_Pred" in pce_df.columns:
                forecasts_for_ts["PCE"] = float(pce_df["PCE_Pred"].iloc[0])
        except Exception as e:  # noqa: BLE001
            _err("PCE", e)

    if (
        bool(getattr(C, "STATS_ENABLE_DARTS", True))
        and HAS_DARTS_CORE
        and bool(getattr(C, "DARTS_ENABLED", True))
        and DartCore is not None
    ):
        for model_type in DARTS_MODEL_TYPES:
            try:
                darts_res = DartCore.run_darts_forecast(
                    ts_df=ts_univariate_df,
                    target_col=ts_name,
                    forecast_horizon=forecast_horizon,
                    model_type=model_type,
                )
                if isinstance(darts_res, dict):
                    d_df = darts_res.get("forecast_df")
                    if isinstance(d_df, pd.DataFrame) and not d_df.empty and ts_name in d_df.columns:
                        forecasts_for_ts[model_type] = float(d_df[ts_name].iloc[0])
            except Exception as e:  # noqa: BLE001
                _err(f"Darts:{model_type}", e)

    return ts_name, forecasts_for_ts, errors


# ----------------------------------------------------------------------
# Forecast Collection (Strictly Independent + Parallel)
# ----------------------------------------------------------------------
def collect_model_forecasts_for_step(
    history_df: pd.DataFrame,
    executor: Optional[ProcessPoolExecutor],
    forecast_horizon: int = 1,
) -> Tuple[Dict[str, Dict[str, float]], List[WorkerError]]:
    forecasts: Dict[str, Dict[str, float]] = {m: {} for m in MODEL_NAMES}
    all_errors: List[WorkerError] = []

    if not TS_LIST:
        return forecasts, all_errors

    args_list: List[Tuple[str, pd.DataFrame, int]] = []
    for ts in TS_LIST:
        ts_univariate_df = history_df[[ts]].copy()
        args_list.append((ts, ts_univariate_df, forecast_horizon))

    results_iter = executor.map(_forecast_single_series, args_list) if executor is not None else map(_forecast_single_series, args_list)

    for ts_name, ts_forecasts, errs in results_iter:
        if isinstance(errs, list) and errs:
            all_errors.extend(errs)

        for model_name, value in ts_forecasts.items():
            if model_name in forecasts:
                forecasts[model_name][ts_name] = value

    return forecasts, all_errors


# ----------------------------------------------------------------------
# Candidate-grid row construction
# ----------------------------------------------------------------------
def build_candidate_grid_rows(
    *,
    run_id: str,
    export_mode: str,
    model_forecasts: Dict[str, Dict[str, float]],
    true_row: pd.Series,
    dataset_index: int,
    step_num: int,
    step_date: Any,
    effective_window: int,
) -> List[ExportRow]:
    rows: List[ExportRow] = []

    step_label = _format_step_label(int(dataset_index), step_date)
    try:
        step_date_str = step_date.isoformat() if hasattr(step_date, "isoformat") else str(step_date)
    except Exception:
        step_date_str = str(step_date)

    index_mode = "event" if _is_event_mode() else "calendar"

    for ts in TS_LIST:
        try:
            true_val = int(true_row[ts])
        except Exception:
            true_val = 0

        for model_name in MODEL_NAMES:
            forecast_map = model_forecasts.get(model_name, {})
            if not isinstance(forecast_map, dict):
                continue
            if ts not in forecast_map:
                continue

            try:
                pred = float(forecast_map[ts])
            except Exception:
                continue

            for mode in RoundingMode:
                rid = rounding_mode_id(mode)
                rounded = apply_round(pred, mode)
                hit = 1 if int(rounded) == int(true_val) else 0
                abs_err = float(abs(pred - float(true_val)))

                rows.append(
                    {
                        "run_id": str(run_id),
                        "dataset_index": int(dataset_index),
                        "step_num": int(step_num),
                        "step_label": str(step_label),
                        "step_date": str(step_date_str),
                        "ts": str(ts),
                        "model": str(model_name),
                        "rounding_id": int(rid),
                        "pred": float(pred),
                        "rounded": int(rounded),
                        "true": int(true_val),
                        "hit": int(hit),
                        "abs_err": float(abs_err),
                        "window_rounds": int(effective_window),
                        "index_mode": str(index_mode),
                        "export_mode": str(export_mode),
                    }
                )

    return rows


def dedupe_candidate_grid_rows(rows: List[ExportRow]) -> List[ExportRow]:
    """
    Collapse legacy per-rounding-mode rows to one row per distinct candidate value.

    The 7 rounding modes mostly agree (they differ only at .5 boundaries), so a cell
    ``(dataset_index, ts, model)`` typically yields far fewer than 7 distinct ``rounded``
    integers. We keep one representative row per ``(dataset_index, ts, model, rounded)``
    group and carry the full set of rounding ids that produced it in a new ``rounding_ids``
    column (sorted, comma-joined, e.g. ``"1,3,5,6"``). The representative ``rounding_id`` is
    the minimum id in the group, preserving deterministic ordering.

    Every other field (``pred``, ``rounded``, ``true``, ``hit``, ``abs_err``, ...) is constant
    within a group, so this is lossless: :func:`opt.opt_data.expand_deduped_grid` reconstructs
    the legacy rows byte-for-byte. Output order follows first appearance, which matches the
    legacy emission order (cells in TS_LIST x MODEL_NAMES order; values in ascending rid order).
    """
    groups: Dict[tuple, Dict[str, Any]] = {}
    order: List[tuple] = []
    for r in rows:
        key = (int(r["dataset_index"]), str(r["ts"]), str(r["model"]), int(r["rounded"]))
        g = groups.get(key)
        if g is None:
            g = {"template": dict(r), "rids": []}
            groups[key] = g
            order.append(key)
        g["rids"].append(int(r["rounding_id"]))

    out: List[ExportRow] = []
    for key in order:
        g = groups[key]
        rids = sorted(g["rids"])
        row = dict(g["template"])
        row["rounding_id"] = int(rids[0])
        row["rounding_ids"] = ",".join(str(x) for x in rids)
        out.append(row)  # type: ignore[arg-type]
    return out


def build_candidate_grid_rows_deduped(**kwargs: Any) -> List[ExportRow]:
    """Distinct-value encoding of :func:`build_candidate_grid_rows` (E7.1).

    Identical signature; returns the deduped rows (one per distinct candidate value, with a
    ``rounding_ids`` column). Guarded behind the ``--statgrid-dedupe`` exporter flag.
    """
    return dedupe_candidate_grid_rows(build_candidate_grid_rows(**kwargs))
