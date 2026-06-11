# ------------------------
# stat.py  (UPGRADED: candidate-grid export for optimization + export modes)
# ------------------------
"""
Statistical backtest for the DynaMix Lottery Forecasting System.

Candidate-Grid Export (for Optimization)
----------------------------------------
This version can export, for every rolling step, a "candidate grid" covering:
  - per TS (position), per model, per rounding:
        pred, rounded, true, hit, abs_err

Export is written as append-only compressed CSV shards under:
  Output/Reports/Exports/StatGrid/<run_id>/

Export modes (CLI)
------------------
--statgrid-export none|incremental|full

- none:
    No StatGrid export.

- incremental:
    Export only steps computed in the current run session.
    (If you resume, it exports only the new steps beyond the checkpoint.)

- full:
    Rebuild and export ALL steps already covered by the checkpoint at start,
    and then continue exporting new steps as the run progresses.
    This is implemented as a safe "recompute export" pass, because checkpoints
    do not store per-step model predictions.

Notes:
- This does NOT delete or rotate checkpoints (Output/Stats/*.pkl are preserved).
- Tickets/plots are not produced here; those are produced by the optimization subsystem.
- Existing features preserved:
    rolling-origin backtest, strict independence, parallel workers, overlay witnesses,
    checkpoints, logging, etc.

Layout assumptions (post-refactor)
----------------------------------
- This file lives at repo root: stat.py
- Core library modules live under: src/dynamix/
  (constants.py, data_utils.py, dynamix_core.py, pce_narx.py, etc.)
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import math
import os
import pickle
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from decimal import Decimal, ROUND_HALF_DOWN, ROUND_HALF_UP
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------
# sys.path bootstrapping for new layout
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ----------------------------------------------------------------------
# Project imports (lowercase, src-based)
# ----------------------------------------------------------------------
from dynamix import constants as C  # type: ignore  # noqa: E402
from dynamix import data_utils as DU  # type: ignore  # noqa: E402
from dynamix import dynamix_core as DCore  # type: ignore  # noqa: E402
from dynamix import pce_narx  # type: ignore  # noqa: E402


# ----------------------------------------------------------------------
# Darts Core import (with explicit diagnostics)
# - Prefer src/dynamix/darts_core.py if present.
# - If absent/unavailable, disable darts models.
# ----------------------------------------------------------------------
from typing import Any as _Any  # noqa: E402

DartCore: _Any
try:
    from dynamix import darts_core as _DartCore  # type: ignore  # noqa: E402

    DartCore = _DartCore
    HAS_DARTS_CORE: bool = True
except Exception as e:  # noqa: BLE001
    DartCore = None  # type: ignore[assignment]
    HAS_DARTS_CORE = False
    print(
        "[STAT] WARNING: darts_core could not be imported. "
        f"Darts models disabled. Error: {e!r}"
    )


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
TS_LIST: List[str] = list(getattr(C, "TS_COLUMNS", []))
MIN_STAT_HISTORY: int = int(getattr(C, "STATS_MIN_HISTORY", 50))

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

STATS_PROGRESS_EVERY_STEPS: int = int(getattr(C, "STATS_PROGRESS_EVERY_STEPS", 1))
DEFAULT_STATS_DIR: Path = Path(getattr(C, "OUTPUT_DIR", Path("Output"))) / "Stats"
CHECKPOINT_PREFIX = "stats_checkpoint_step_"
CHECKPOINT_SUFFIX = ".pkl"
CHECKPOINT_EVERY_STEPS: int = int(getattr(C, "STATS_CHECKPOINT_EVERY_STEPS", 10))

# Max workers for ProcessPool (defaults to CPU count - 1, min 1)
try:
    _DEFAULT_MAX_WORKERS = max(1, (os.cpu_count() or 2) - 1)
except Exception:  # pragma: no cover
    _DEFAULT_MAX_WORKERS = 1
STATS_MAX_WORKERS: int = int(getattr(C, "STATS_MAX_WORKERS", _DEFAULT_MAX_WORKERS))

# Training window configuration (from constants.py)
TRAINING_WINDOW_ROUNDS: int = int(getattr(C, "TRAINING_WINDOW_ROUNDS", 0) or 0)
TRAINING_WINDOW_ENFORCE_MIN: bool = bool(getattr(C, "TRAINING_WINDOW_ENFORCE_MIN", True))
TRAINING_WINDOW_MAX_ROUNDS: int = int(getattr(C, "TRAINING_WINDOW_MAX_ROUNDS", 0) or 0)

# Overlay witness recording switches
STATS_RECORD_OVERLAY_WITNESSES: bool = bool(getattr(C, "STATS_RECORD_OVERLAY_WITNESSES", True))
STATS_OVERLAY_MIN_HITS_TO_RECORD: int = int(getattr(C, "STATS_OVERLAY_MIN_HITS_TO_RECORD", 3))

STATS_OVERLAY_STORE_ALL_HITS: bool = bool(getattr(C, "STATS_OVERLAY_STORE_ALL_HITS", True))
_ST_MAXH = getattr(C, "STATS_OVERLAY_MAX_CANDIDATES_PER_TS", 0)
STATS_OVERLAY_MAX_CANDIDATES_PER_TS: int = int(_ST_MAXH) if _ST_MAXH is not None else 0

# Error capture (stored in checkpoints as capped recent list)
STATS_STORE_RECENT_ERRORS: bool = bool(getattr(C, "STATS_STORE_RECENT_ERRORS", True))
STATS_RECENT_ERRORS_CAP: int = int(getattr(C, "STATS_RECENT_ERRORS_CAP", 200))

# Candidate-grid export settings (some can be overridden by CLI)
STATS_EXPORT_GRID_DEFAULT: bool = bool(getattr(C, "STATS_EXPORT_GRID", True))
OUTPUT_REPORTS_DIR: Path = Path(getattr(C, "OUTPUT_REPORTS_DIR", Path("Output") / "Reports"))
EXPORT_ROOT_DIR: Path = OUTPUT_REPORTS_DIR / "Exports" / "StatGrid"
STATS_EXPORT_FLUSH_EVERY_STEPS: int = int(getattr(C, "STATS_EXPORT_FLUSH_EVERY_STEPS", CHECKPOINT_EVERY_STEPS))

# Optional explicit run id; otherwise auto
_EXPLICIT_RUN_ID = getattr(C, "STATS_EXPORT_RUN_ID", None)


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
def _setup_stat_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"stat_{ts}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    root.addHandler(fh)
    root.addHandler(sh)

    logging.getLogger("stat").info("Stat logging started. log_path=%s", log_path)
    return log_path


log = logging.getLogger("stat")


# ----------------------------------------------------------------------
# Mode helpers (INDEX_MODE semantics)
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
# Types
# ----------------------------------------------------------------------
Stats = Dict[RoundingMode, Dict[str, Dict[str, int]]]
MultiHitCounts = Dict[str, int]
HitDistribution = Dict[RoundingMode, Dict[str, Dict[int, int]]]
OverlayDistribution = Dict[int, int]

OverlayWitness = Dict[str, Any]
WorkerError = Dict[str, Any]
ExportRow = Dict[str, Any]


# ----------------------------------------------------------------------
# Export modes (CLI)
# ----------------------------------------------------------------------
EXPORT_MODE_VALUES = ("none", "incremental", "full")


def _export_mode_normalize(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in EXPORT_MODE_VALUES else "incremental"


def _make_export_run_id(export_mode: str) -> str:
    # If constants provides explicit run-id, respect it.
    if isinstance(_EXPLICIT_RUN_ID, str) and _EXPLICIT_RUN_ID.strip():
        base = _EXPLICIT_RUN_ID.strip()
        if export_mode == "full" and not base.endswith("_full"):
            return base + "_full"
        if export_mode == "incremental" and not base.endswith("_inc") and not base.endswith("_full"):
            return base
        return base

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "full" if export_mode == "full" else "inc"
    return f"statgrid_{ts}_{suffix}"


def init_stats() -> Stats:
    stats: Stats = {}
    for mode in RoundingMode:
        stats[mode] = {}
        for model in MODEL_NAMES:
            stats[mode][model] = {ts: 0 for ts in TS_LIST}
    return stats


def init_multi_hit_counts() -> MultiHitCounts:
    return {model: 0 for model in MODEL_NAMES}


def init_hit_distribution() -> HitDistribution:
    max_hits = len(TS_LIST)
    dist: HitDistribution = {}
    for mode in RoundingMode:
        dist[mode] = {}
        for model in MODEL_NAMES:
            dist[mode][model] = {h: 0 for h in range(0, max_hits + 1)}
    return dist


def init_overlay_distribution() -> OverlayDistribution:
    return {h: 0 for h in range(len(TS_LIST) + 1)}


def init_error_counts() -> Dict[str, int]:
    return {"total": 0}


# ----------------------------------------------------------------------
# Training window helpers
# ----------------------------------------------------------------------
def _min_required_history_for_enabled_models() -> int:
    reqs: List[int] = [1]

    if bool(getattr(C, "STATS_ENABLE_DYNAMIX", True)):
        pce_lags = int(getattr(C, "PCE_LAGS", 5))
        dm_min = max(10, pce_lags + 5)
        reqs.append(dm_min)

    if bool(getattr(C, "STATS_ENABLE_PCE", True)) and bool(getattr(C, "PCE_ENABLED", True)):
        pce_min_samples = int(getattr(C, "PCE_MIN_SAMPLES", 50))
        pce_lags = int(getattr(C, "PCE_LAGS", 5))
        reqs.append(pce_min_samples + pce_lags)

    if bool(getattr(C, "STATS_ENABLE_DARTS", True)) and bool(getattr(C, "DARTS_ENABLED", True)) and HAS_DARTS_CORE:
        in_len = int(getattr(C, "DARTS_INPUT_CHUNK_LENGTH", 12))
        out_len = int(getattr(C, "DARTS_OUTPUT_CHUNK_LENGTH", int(getattr(C, "FH", 1))))
        reqs.append(in_len + out_len + 1)

    reqs.append(int(MIN_STAT_HISTORY))
    return int(max(reqs))


def _resolve_effective_training_window() -> Tuple[int, List[str]]:
    notes: List[str] = []

    w = int(TRAINING_WINDOW_ROUNDS)
    if w < 0:
        w = 0

    if w <= 0:
        notes.append("Training window disabled (full history, legacy behavior).")
        return 0, notes

    min_req = _min_required_history_for_enabled_models()
    if TRAINING_WINDOW_ENFORCE_MIN and w < min_req:
        notes.append(
            f"Training window requested={w} is below conservative minimum={min_req}; "
            f"auto-expanding effective window to {min_req}."
        )
        w = min_req

    if TRAINING_WINDOW_MAX_ROUNDS and TRAINING_WINDOW_MAX_ROUNDS > 0 and w > TRAINING_WINDOW_MAX_ROUNDS:
        notes.append(
            f"Effective window {w} exceeds TRAINING_WINDOW_MAX_ROUNDS={TRAINING_WINDOW_MAX_ROUNDS}; "
            f"capping to {TRAINING_WINDOW_MAX_ROUNDS}. (Models may skip if insufficient.)"
        )
        w = int(TRAINING_WINDOW_MAX_ROUNDS)

    if w < 0:
        w = 0

    notes.append(f"Effective training window: last {w} rounds.")
    return w, notes


def _slice_history(ts_df: pd.DataFrame, end_idx: int, window_rounds: int) -> pd.DataFrame:
    if window_rounds <= 0:
        return ts_df.iloc[:end_idx]
    start = max(0, int(end_idx) - int(window_rounds))
    return ts_df.iloc[start:end_idx]


# ----------------------------------------------------------------------
# Candidate-grid exporter (append-only shards, compressed CSV)
# ----------------------------------------------------------------------
class CandidateGridExporter:
    """
    Append-only exporter that buffers per-step grid rows and flushes them
    into gzipped CSV shards.

    Layout:
      Output/Reports/Exports/StatGrid/<run_id>/
        manifest.jsonl
        schema.json
        grid_part_000001.csv.gz
        grid_part_000002.csv.gz
        ...

    Flush strategy:
    - Flush interval controls shard sizes.
    """

    SCHEMA_VERSION = "1.1"

    def __init__(self, root_dir: Path, run_id: str, flush_every_steps: int) -> None:
        self.run_id = str(run_id)
        self.flush_every_steps = max(1, int(flush_every_steps))
        self.base_dir = Path(root_dir) / self.run_id
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.base_dir / "manifest.jsonl"
        self.schema_path = self.base_dir / "schema.json"

        self._buffer: List[ExportRow] = []
        self._part_idx: int = 0
        self._steps_since_flush: int = 0

        self._write_schema_once()

    @property
    def export_dir(self) -> Path:
        return self.base_dir

    def _write_schema_once(self) -> None:
        if self.schema_path.exists():
            return

        schema = {
            "schema_version": self.SCHEMA_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "columns": [
                "run_id",
                "dataset_index",
                "step_num",
                "step_label",
                "step_date",
                "ts",
                "model",
                "rounding_id",
                "pred",
                "rounded",
                "true",
                "hit",
                "abs_err",
                "window_rounds",
                "index_mode",
                "export_mode",
            ],
            "notes": "Candidate grid for optimization; one row per (step, ts, model, rounding).",
        }
        self.schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    def add_rows(self, rows: Iterable[ExportRow]) -> None:
        self._buffer.extend(list(rows))

    def step_completed(self) -> None:
        self._steps_since_flush += 1
        if self._steps_since_flush >= self.flush_every_steps:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            self._steps_since_flush = 0
            return

        self._part_idx += 1
        part_name = f"grid_part_{self._part_idx:06d}.csv.gz"
        part_path = self.base_dir / part_name

        cols = [
            "run_id",
            "dataset_index",
            "step_num",
            "step_label",
            "step_date",
            "ts",
            "model",
            "rounding_id",
            "pred",
            "rounded",
            "true",
            "hit",
            "abs_err",
            "window_rounds",
            "index_mode",
            "export_mode",
        ]

        with gzip.open(part_path, "wt", encoding="utf-8", newline="") as gz:
            writer = csv.DictWriter(gz, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            for r in self._buffer:
                writer.writerow(r)

        manifest_rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "part": part_name,
            "rows": len(self._buffer),
        }
        with self.manifest_path.open("a", encoding="utf-8") as mf:
            mf.write(json.dumps(manifest_rec) + "\n")

        log.info("[STAT-EXPORT] Wrote %d rows to %s", len(self._buffer), part_path)
        self._buffer.clear()
        self._steps_since_flush = 0


# ----------------------------------------------------------------------
# Worker: univariate forecasts for a single TS (executed in subprocesses)
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
# Overlay Witness Construction
# ----------------------------------------------------------------------
def _model_rank(model_name: str) -> int:
    try:
        return MODEL_NAMES.index(model_name)
    except ValueError:
        return 10_000


def _finalize_candidates(
    candidates: List[Dict[str, Any]],
    max_keep: int,
) -> List[Dict[str, Any]]:
    candidates.sort(
        key=lambda c: (
            float(c.get("abs_err", 1e18)),
            _model_rank(str(c.get("model", ""))),
            int(c.get("rounding", 999)),
        )
    )
    if max_keep and max_keep > 0:
        return candidates[:max_keep]
    return candidates


def build_overlay_witness_for_step(
    true_row: pd.Series,
    model_forecasts: Dict[str, Dict[str, float]],
) -> Tuple[int, Dict[str, Any]]:
    per_ts_candidates: Dict[str, List[Dict[str, Any]]] = {ts: [] for ts in TS_LIST}

    for model_name, forecast_map in model_forecasts.items():
        if model_name not in MODEL_NAMES or not forecast_map:
            continue

        for ts_name in TS_LIST:
            if ts_name not in true_row.index or ts_name not in forecast_map:
                continue

            try:
                true_val = int(true_row[ts_name])
                pred_val = float(forecast_map[ts_name])
            except Exception:  # noqa: BLE001
                continue

            for mode in RoundingMode:
                rounded = apply_round(pred_val, mode)
                if rounded == true_val:
                    abs_err = float(abs(pred_val - float(true_val)))
                    per_ts_candidates[ts_name].append(
                        {
                            "model": model_name,
                            "rounding": rounding_mode_id(mode),
                            "pred": float(pred_val),
                            "rounded": int(rounded),
                            "true": int(true_val),
                            "abs_err": abs_err,
                        }
                    )

    overlay_hits = sum(1 for ts in TS_LIST if per_ts_candidates.get(ts))

    witness_per_ts: Dict[str, Any] = {}
    for ts_name in TS_LIST:
        cand = per_ts_candidates.get(ts_name, [])
        if cand:
            cand_sorted = _finalize_candidates(
                cand,
                max_keep=(STATS_OVERLAY_MAX_CANDIDATES_PER_TS if STATS_OVERLAY_STORE_ALL_HITS else 1),
            )
            best = cand_sorted[0] if cand_sorted else None
            witness_per_ts[ts_name] = {
                "best": best,
                "all_hits": cand_sorted if STATS_OVERLAY_STORE_ALL_HITS else ([best] if best else []),
            }
        else:
            witness_per_ts[ts_name] = {"best": None, "all_hits": []}

    return overlay_hits, witness_per_ts


# ----------------------------------------------------------------------
# Statistics Update (includes overlay witness recording)
# ----------------------------------------------------------------------
def update_stats_for_step(
    stats: Stats,
    multi_hit_counts: MultiHitCounts,
    hit_distribution: HitDistribution,
    overlay_distribution: OverlayDistribution,
    true_row: pd.Series,
    model_forecasts: Dict[str, Dict[str, float]],
    *,
    dataset_index: int,
    step_date: Any,
    overlay_witnesses: Optional[List[OverlayWitness]] = None,
    multi_hit_threshold: int = 3,
) -> None:
    union_correct_hits: Set[str] = set()

    for model_name, forecast_map in model_forecasts.items():
        if model_name not in MODEL_NAMES or not forecast_map:
            continue

        matches_for_rounding: Dict[RoundingMode, int] = {m: 0 for m in RoundingMode}

        for ts_name in TS_LIST:
            if ts_name not in true_row.index or ts_name not in forecast_map:
                continue

            try:
                true_val = int(true_row[ts_name])
                pred_val = float(forecast_map[ts_name])
            except Exception:  # noqa: BLE001
                continue

            for mode in RoundingMode:
                rounded = apply_round(pred_val, mode)
                if rounded == true_val:
                    stats[mode][model_name][ts_name] += 1
                    matches_for_rounding[mode] += 1
                    union_correct_hits.add(ts_name)

        for mode, hits in matches_for_rounding.items():
            if 0 <= hits <= len(TS_LIST):
                hit_distribution[mode][model_name][hits] += 1

        if max(matches_for_rounding.values()) >= int(multi_hit_threshold):
            multi_hit_counts[model_name] += 1

    overlay_hits = len(union_correct_hits)
    if 0 <= overlay_hits <= len(TS_LIST):
        overlay_distribution[overlay_hits] += 1

    if (
        STATS_RECORD_OVERLAY_WITNESSES
        and overlay_witnesses is not None
        and overlay_hits >= STATS_OVERLAY_MIN_HITS_TO_RECORD
    ):
        oh, per_ts = build_overlay_witness_for_step(true_row, model_forecasts)

        if oh != overlay_hits:
            log.warning(
                "Overlay witness hit count mismatch at index=%d: union=%d witness=%d",
                dataset_index,
                overlay_hits,
                oh,
            )
            overlay_hits = oh

        step_label = _format_step_label(int(dataset_index), step_date)
        try:
            date_str = step_date.isoformat() if hasattr(step_date, "isoformat") else str(step_date)
        except Exception:
            date_str = str(step_date)

        overlay_witnesses.append(
            {
                "dataset_index": int(dataset_index),
                "step_label": str(step_label),
                "date": date_str,
                "overlay_hits": int(overlay_hits),
                "per_ts": per_ts,
            }
        )


# ----------------------------------------------------------------------
# Build candidate grid rows for export (one step)
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


# ----------------------------------------------------------------------
# Checkpointing
# ----------------------------------------------------------------------
def checkpoint_path(stats_dir: Path, step: int) -> Path:
    return Path(stats_dir) / f"{CHECKPOINT_PREFIX}{step}{CHECKPOINT_SUFFIX}"


def save_checkpoint(stats_dir: Path, step: int, payload: dict) -> None:
    try:
        Path(stats_dir).mkdir(parents=True, exist_ok=True)
        cp = checkpoint_path(Path(stats_dir), step)
        with open(cp, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        log.info("Checkpoint saved: %s (last_step=%d)", cp, step)
    except Exception:  # noqa: BLE001
        log.exception("Checkpoint save failed.")


class _StatUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if name == "RoundingMode" and module in ("__main__", __name__):
            return RoundingMode
        return super().find_class(module, name)


def load_checkpoint(cp_path: Path) -> dict:
    with open(cp_path, "rb") as f:
        return _StatUnpickler(f).load()


def find_latest_checkpoint(stats_dir: Path) -> Optional[Path]:
    stats_dir = Path(stats_dir)
    if not stats_dir.is_dir():
        return None

    candidates: List[Tuple[int, Path]] = []
    for p in stats_dir.iterdir():
        if p.name.startswith(CHECKPOINT_PREFIX) and p.name.endswith(CHECKPOINT_SUFFIX):
            try:
                idx = int(p.name[len(CHECKPOINT_PREFIX) : -len(CHECKPOINT_SUFFIX)])
                candidates.append((idx, p))
            except ValueError:
                continue

    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x[0])[-1][1]


# ----------------------------------------------------------------------
# Reporting (Optimization reads exports; stat_report.py reads checkpoints)
# ----------------------------------------------------------------------
def print_results(
    stats: Stats,
    hit_dist: HitDistribution,
    multi_hit: MultiHitCounts,
    overlay_dist: OverlayDistribution,
    duration: float,
) -> None:
    print("\n" + "=" * 80)
    print(f"STATISTICS REPORT (Total Time: {duration:.2f} s)\n")

    for mode in RoundingMode:
        label = ROUNDING_MODE_LABELS[mode]
        print(f"--- Per-TS statistics: {label} ---")
        headers = ["Model"] + TS_LIST
        rows2: List[List[Any]] = []
        for m in MODEL_NAMES:
            row = [m] + [stats[mode][m].get(ts, 0) for ts in TS_LIST]
            rows2.append(row)
        DU.print_markdown_table(headers, rows2)
        print()

    for mode in RoundingMode:
        label = ROUNDING_MODE_LABELS[mode]
        print(f"--- Hit distribution: {label} ---")
        headers = ["Model", "3 hits", "4 hits", "5 hits", "6 hits", "7 hits"]
        rows3 = []
        for m in MODEL_NAMES:
            d = hit_dist[mode][m]
            rows3.append([m, d.get(3, 0), d.get(4, 0), d.get(5, 0), d.get(6, 0), d.get(7, 0)])
        DU.print_markdown_table(headers, rows3)
        print()

    print("=" * 80)
    print("OVERLAY SUMMARY (Best Combination)")
    print(
        "Counts of steps where the union of ALL models and ALL rounding options "
        "produced X unique correct hits.\n"
    )

    headers = ["Type", "3 hits", "4 hits", "5 hits", "6 hits", "7 hits"]
    row = [
        "All models & roundings",
        overlay_dist.get(3, 0),
        overlay_dist.get(4, 0),
        overlay_dist.get(5, 0),
        overlay_dist.get(6, 0),
        overlay_dist.get(7, 0),
    ]
    DU.print_markdown_table(headers, [row])
    print("\n" + "=" * 80)


def _print_rounding_legend() -> None:
    print("Rounding legend:")
    for mode in RoundingMode:
        print(ROUNDING_MODE_LABELS[mode])
    print("")


def print_overlay_witness_report(
    overlay_witnesses: List[OverlayWitness],
    *,
    max_per_hit: Optional[int] = None,
    show_multihit: bool = False,
    max_multihit_candidates_per_ts: int = 20,
) -> None:
    if not overlay_witnesses:
        print("----\n(No overlay witness records stored in this checkpoint.)\n")
        return

    print("----\n")
    _print_rounding_legend()

    by_hits: Dict[int, List[OverlayWitness]] = {h: [] for h in range(0, len(TS_LIST) + 1)}
    for w in overlay_witnesses:
        try:
            h = int(w.get("overlay_hits", 0))
        except Exception:
            h = 0
        by_hits.setdefault(h, []).append(w)

    for h in (7, 6, 5, 4, 3):
        group = by_hits.get(h, [])
        if not group:
            continue

        print(f"**{h} hits**\n")
        count_printed = 0

        for idx_in_group, w in enumerate(group, start=1):
            if max_per_hit is not None and count_printed >= max_per_hit:
                break

            dataset_index = w.get("dataset_index", "N/A")
            step_label = w.get("step_label", None)
            if not step_label:
                date_str = w.get("date", "N/A")
                step_label = f"Date={date_str}"

            print(f"#{idx_in_group}  (dataset index={dataset_index}, {step_label})")

            per_ts = w.get("per_ts", {}) or {}

            model_row: List[str] = []
            rounding_row: List[str] = []

            for ts in TS_LIST:
                ts_rec = per_ts.get(ts, {}) if isinstance(per_ts, dict) else {}
                best = ts_rec.get("best") if isinstance(ts_rec, dict) else None
                if isinstance(best, dict) and best:
                    model_row.append(str(best.get("model", "-")))
                    rounding_row.append(str(best.get("rounding", "-")))
                else:
                    model_row.append("-")
                    rounding_row.append("-")

            headers = ["Serie"] + TS_LIST
            rowsx = [
                ["Model"] + model_row,
                ["Rounding"] + rounding_row,
            ]
            DU.print_markdown_table(headers, rowsx)

            if show_multihit:
                multi_lines: List[str] = []
                for ts in TS_LIST:
                    ts_rec = per_ts.get(ts, {}) if isinstance(per_ts, dict) else {}
                    all_hits = ts_rec.get("all_hits", []) if isinstance(ts_rec, dict) else []
                    if isinstance(all_hits, list) and len(all_hits) > 1:
                        shown = all_hits[: max_multihit_candidates_per_ts]
                        parts = []
                        for c in shown:
                            if not isinstance(c, dict):
                                continue
                            if isinstance(c.get("pred"), (int, float)):
                                parts.append(f"{c.get('model')}[r{c.get('rounding')},pred={c.get('pred'):.4f}]")
                            else:
                                parts.append(f"{c.get('model')}[r{c.get('rounding')}]")
                        suffix = ""
                        if len(all_hits) > len(shown):
                            suffix = f" (+{len(all_hits)-len(shown)} more)"
                        multi_lines.append(f"- {ts}: {len(all_hits)} hits -> " + ", ".join(parts) + suffix)

                if multi_lines:
                    print("Multi-hit details (all correct candidates):")
                    for line in multi_lines:
                        print(line)
                    print("")

            print("----\n")
            count_printed += 1


# ----------------------------------------------------------------------
# Error accounting
# ----------------------------------------------------------------------
def _log_worker_errors(
    errors: List[WorkerError],
    *,
    state: Dict[str, Any],
    dataset_index: int,
    step_num: int,
) -> None:
    if not errors:
        return

    for e in errors:
        model = str(e.get("model", "UNKNOWN"))
        ts = str(e.get("ts", "UNKNOWN"))
        msg = str(e.get("error", ""))
        hist = e.get("history_len", "?")
        log.error(
            "Worker error at step=%d index=%d ts=%s model=%s history_len=%s error=%s",
            step_num,
            dataset_index,
            ts,
            model,
            hist,
            msg,
        )
        tb = e.get("traceback")
        if tb:
            log.error("Traceback (trimmed):\n%s", tb)

        ec = state.setdefault("error_counts", init_error_counts())
        ec["total"] = int(ec.get("total", 0)) + 1
        ec[model] = int(ec.get(model, 0)) + 1

        if STATS_STORE_RECENT_ERRORS:
            recent = state.setdefault("recent_errors", [])
            if isinstance(recent, list):
                recent.append(
                    {
                        "step": int(step_num),
                        "dataset_index": int(dataset_index),
                        "ts": ts,
                        "model": model,
                        "error": msg,
                    }
                )
                cap = max(0, STATS_RECENT_ERRORS_CAP)
                if cap > 0 and len(recent) > cap:
                    del recent[:-cap]


# ----------------------------------------------------------------------
# FULL export rebuild pass (safe recompute)
# ----------------------------------------------------------------------
def rebuild_full_export_from_checkpoint_coverage(
    *,
    ts_df: pd.DataFrame,
    executor: ProcessPoolExecutor,
    exporter: CandidateGridExporter,
    export_run_id: str,
    export_mode: str,
    effective_window: int,
    export_end_index_inclusive: int,
) -> None:
    """
    Recompute forecasts and export candidate grid for indices:
        i in [MIN_STAT_HISTORY, export_end_index_inclusive]

    This is required because checkpoints do not store per-step model predictions.
    """
    if export_end_index_inclusive < MIN_STAT_HISTORY:
        log.info("[STAT-EXPORT] Full rebuild skipped: export_end_index_inclusive < MIN_STAT_HISTORY.")
        return

    total = (export_end_index_inclusive - MIN_STAT_HISTORY) + 1
    log.info(
        "[STAT-EXPORT] FULL rebuild export starting: indices [%d..%d] (%d steps). export_dir=%s",
        MIN_STAT_HISTORY,
        export_end_index_inclusive,
        total,
        exporter.export_dir,
    )
    print(
        f"[STAT] StatGrid FULL export rebuild: {total} steps "
        f"(indices {MIN_STAT_HISTORY}..{export_end_index_inclusive})."
    )

    fh = int(getattr(C, "FH", 1))
    t0 = time.time()

    for n, i in enumerate(range(MIN_STAT_HISTORY, export_end_index_inclusive + 1), start=1):
        history_df = _slice_history(ts_df, end_idx=i, window_rounds=effective_window)
        true_row = ts_df.iloc[i]
        try:
            step_date = ts_df.index[i]
        except Exception:
            step_date = "N/A"

        forecasts, worker_errors = collect_model_forecasts_for_step(
            history_df=history_df,
            executor=executor,
            forecast_horizon=fh,
        )
        if worker_errors:
            _dummy_state: Dict[str, Any] = {"error_counts": init_error_counts(), "recent_errors": []}
            _log_worker_errors(worker_errors, state=_dummy_state, dataset_index=i, step_num=n)

        rows = build_candidate_grid_rows(
            run_id=export_run_id,
            export_mode=export_mode,
            model_forecasts=forecasts,
            true_row=true_row,
            dataset_index=i,
            step_num=(i - MIN_STAT_HISTORY + 1),
            step_date=step_date,
            effective_window=effective_window,
        )
        exporter.add_rows(rows)
        exporter.step_completed()

        if n == 1 or n % max(1, STATS_PROGRESS_EVERY_STEPS) == 0:
            elapsed = time.time() - t0
            pct = (n / total) * 100.0
            print(f"[STAT] Full export rebuild progress: {n}/{total} ({pct:5.1f}%) | Elapsed: {elapsed:7.1f}s")

    exporter.flush()
    log.info("[STAT-EXPORT] FULL rebuild export completed. export_dir=%s", exporter.export_dir)
    print("[STAT] StatGrid FULL export rebuild: DONE.")


# ----------------------------------------------------------------------
# Main backtest
# ----------------------------------------------------------------------
def run_statistics(resume_arg: Optional[str], export_mode: str) -> None:
    DU.ensure_output_dirs()
    logs_dir: Path = Path(getattr(C, "OUTPUT_LOGS_DIR", Path("Output") / "Logs"))
    log_path = _setup_stat_logging(logs_dir)

    stats_dir = DEFAULT_STATS_DIR
    stats_dir.mkdir(parents=True, exist_ok=True)

    effective_window, window_notes = _resolve_effective_training_window()

    # Ensure Reports/Exports dirs exist (no deletions)
    OUTPUT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_ROOT_DIR.mkdir(parents=True, exist_ok=True)

    export_mode = _export_mode_normalize(export_mode)

    # Decide whether export is enabled.
    export_enabled = STATS_EXPORT_GRID_DEFAULT and (export_mode != "none")
    export_run_id = _make_export_run_id(export_mode)

    exporter: Optional[CandidateGridExporter] = None
    if export_enabled:
        try:
            exporter = CandidateGridExporter(EXPORT_ROOT_DIR, export_run_id, STATS_EXPORT_FLUSH_EVERY_STEPS)
            log.info(
                "[STAT-EXPORT] Enabled. mode=%s run_id=%s export_dir=%s",
                export_mode,
                export_run_id,
                exporter.export_dir,
            )
        except Exception as e:  # noqa: BLE001
            exporter = None
            export_enabled = False
            log.exception("[STAT-EXPORT] Failed to initialize exporter. Export disabled. err=%r", e)

    log.info("Darts support: HAS_DARTS_CORE=%s, DARTS_ENABLED=%s", HAS_DARTS_CORE, getattr(C, "DARTS_ENABLED", True))
    log.info(
        "Model enables: STATS_ENABLE_DYNAMIX=%s STATS_ENABLE_PCE=%s STATS_ENABLE_DARTS=%s",
        getattr(C, "STATS_ENABLE_DYNAMIX", True),
        getattr(C, "STATS_ENABLE_PCE", True),
        getattr(C, "STATS_ENABLE_DARTS", True),
    )
    log.info(
        "Training window requested=%d, effective=%d, enforce_min=%s, max_rounds=%d",
        TRAINING_WINDOW_ROUNDS,
        effective_window,
        TRAINING_WINDOW_ENFORCE_MIN,
        TRAINING_WINDOW_MAX_ROUNDS,
    )
    for n in window_notes:
        log.info("Training window note: %s", n)

    log.info(
        "Overlay witnesses: enabled=%s, min_hits=%d, store_all_hits=%s, cap_per_ts=%s",
        STATS_RECORD_OVERLAY_WITNESSES,
        STATS_OVERLAY_MIN_HITS_TO_RECORD,
        STATS_OVERLAY_STORE_ALL_HITS,
        ("unlimited" if STATS_OVERLAY_MAX_CANDIDATES_PER_TS <= 0 else STATS_OVERLAY_MAX_CANDIDATES_PER_TS),
    )
    log.info(
        "Error capture: store_recent=%s, recent_cap=%d (checkpointed)",
        STATS_STORE_RECENT_ERRORS,
        STATS_RECENT_ERRORS_CAP,
    )
    log.info(
        "Stat settings: workers=%d, checkpoint_every=%d, progress_every=%d",
        STATS_MAX_WORKERS,
        CHECKPOINT_EVERY_STEPS,
        STATS_PROGRESS_EVERY_STEPS,
    )
    log.info("Log file: %s", log_path)
    log.info("[STAT-EXPORT] mode=%s enabled=%s run_id=%s", export_mode, export_enabled, export_run_id)

    try:
        _ts_array, _date_index, ts_df = DU.load_lottery_data()
    except Exception as e:  # noqa: BLE001
        log.exception("Data load failed: %r", e)
        return

    try:
        ts_df = ts_df.sort_index()
    except Exception:
        pass

    n_obs = ts_df.shape[0]
    if n_obs <= MIN_STAT_HISTORY:
        log.error("Insufficient data for statistics: n_obs=%d min_history=%d", n_obs, MIN_STAT_HISTORY)
        return

    total_steps = n_obs - MIN_STAT_HISTORY
    print(
        f"[STAT] Dataset observations: {n_obs} (min history={MIN_STAT_HISTORY}). "
        f"Total forecast steps (tests) possible: {total_steps}."
    )

    if effective_window <= 0:
        print("[STAT] Training window: DISABLED (full history).")
    else:
        print(f"[STAT] Training window: last {effective_window} rounds.")

    if exporter is not None:
        print(f"[STAT] Export grid: ENABLED (mode={export_mode}) -> {exporter.export_dir}")
    else:
        print(f"[STAT] Export grid: DISABLED (mode={export_mode})")

    state: Dict[str, Any] = {
        "last_step": MIN_STAT_HISTORY - 1,
        "stats": init_stats(),
        "multi_hit": init_multi_hit_counts(),
        "hit_dist": init_hit_distribution(),
        "overlay_dist": init_overlay_distribution(),
        "start_time_offset": 0.0,
        "overlay_witnesses": [],
        "error_counts": init_error_counts(),
        "recent_errors": [],
        "training_window_rounds": int(effective_window),
        # export provenance
        "export_mode": str(export_mode),
        "export_run_id": str(export_run_id),
        "export_dir": str((EXPORT_ROOT_DIR / export_run_id)) if exporter is not None else "",
    }

    if resume_arg:
        cp_path: Optional[Path] = None
        if resume_arg == "latest":
            cp_path = find_latest_checkpoint(stats_dir)
        elif Path(resume_arg).exists():
            cp_path = Path(resume_arg)
        elif resume_arg.isdigit():
            cp_path = checkpoint_path(stats_dir, int(resume_arg))

        if cp_path is not None:
            log.info("Resuming from checkpoint: %s", cp_path)
            saved = load_checkpoint(cp_path)
            if isinstance(saved, dict):
                state.update(saved)

            state.setdefault("overlay_witnesses", [])
            state.setdefault("error_counts", init_error_counts())
            state.setdefault("recent_errors", [])
            cp_window = int(state.get("training_window_rounds", 0) or 0)

            if "training_window_rounds" not in (saved or {}):
                log.warning(
                    "Legacy checkpoint detected (no training_window_rounds stored). "
                    "Assuming checkpoint window=0 (full history) for provenance."
                )

            if cp_window != int(effective_window):
                log.warning(
                    "Training window differs between checkpoint and current run: "
                    "checkpoint=%d, current_effective=%d. "
                    "Resume is allowed, but results will be a mixed-regime run.",
                    cp_window,
                    int(effective_window),
                )

            # Always store current run's effective window for provenance going forward.
            state["training_window_rounds"] = int(effective_window)

    start_idx = int(state["last_step"]) + 1
    if start_idx >= n_obs:
        log.info("All steps already completed. Printing existing results.")
        print_results(
            state["stats"],
            state["hit_dist"],
            state["multi_hit"],
            state["overlay_dist"],
            float(state.get("elapsed_total", 0.0)),
        )
        ow = state.get("overlay_witnesses", [])
        if isinstance(ow, list) and ow:
            print_overlay_witness_report(ow, max_per_hit=None, show_multihit=False)
        return

    print(
        f"[STAT] Starting/Resuming backtest from dataset index {start_idx}. "
        "Independent Variable Mode: ACTIVE. Parallel per-series execution enabled."
    )
    log.info("Starting from dataset index=%d (last_step=%d)", start_idx, int(state.get("last_step", -1)))

    t0 = time.time()
    multi_hit_threshold = int(getattr(C, "STATS_MULTI_HIT_THRESHOLD", 3) or 3)

    try:
        with ProcessPoolExecutor(max_workers=STATS_MAX_WORKERS) as executor:
            # If export_mode == "full", rebuild export for the checkpoint-covered portion first.
            if export_mode == "full" and exporter is not None:
                export_end = max(MIN_STAT_HISTORY - 1, start_idx - 1)
                if export_end >= MIN_STAT_HISTORY:
                    log.info(
                        "[STAT-EXPORT] FULL mode: rebuilding export for checkpoint coverage. "
                        "export_end_index_inclusive=%d (start_idx=%d).",
                        export_end,
                        start_idx,
                    )
                    rebuild_full_export_from_checkpoint_coverage(
                        ts_df=ts_df,
                        executor=executor,
                        exporter=exporter,
                        export_run_id=export_run_id,
                        export_mode="full",
                        effective_window=effective_window,
                        export_end_index_inclusive=export_end,
                    )
                else:
                    log.info("[STAT-EXPORT] FULL mode: no checkpoint coverage to rebuild (start is at MIN_STAT_HISTORY).")

            # Main Stat loop: only new steps beyond last_step.
            for i in range(start_idx, n_obs):
                step_wall_t0 = time.perf_counter()

                step_num = i - MIN_STAT_HISTORY + 1
                elapsed_session = time.time() - t0
                elapsed_total = float(state.get("start_time_offset", 0.0)) + elapsed_session
                pct = (step_num / total_steps) * 100.0

                if step_num == 1 or step_num % STATS_PROGRESS_EVERY_STEPS == 0:
                    avg_time = elapsed_total / max(step_num, 1)
                    etr = avg_time * (total_steps - step_num)
                    print(
                        f"[STAT] Step {step_num}/{total_steps} "
                        f"(dataset index={i}, {pct:5.1f}%) | "
                        f"Elapsed: {elapsed_total:7.1f}s | ETR: {etr:7.1f}s"
                    )

                history_df = _slice_history(ts_df, end_idx=i, window_rounds=effective_window)
                true_row = ts_df.iloc[i]
                try:
                    step_date = ts_df.index[i]
                except Exception:
                    step_date = "N/A"

                forecasts, worker_errors = collect_model_forecasts_for_step(
                    history_df=history_df,
                    executor=executor,
                    forecast_horizon=int(getattr(C, "FH", 1)),
                )

                _log_worker_errors(worker_errors, state=state, dataset_index=i, step_num=step_num)

                # Export (incremental export of new steps; full mode also exports new steps)
                if exporter is not None:
                    try:
                        rows = build_candidate_grid_rows(
                            run_id=export_run_id,
                            export_mode=export_mode,
                            model_forecasts=forecasts,
                            true_row=true_row,
                            dataset_index=i,
                            step_num=step_num,
                            step_date=step_date,
                            effective_window=effective_window,
                        )
                        exporter.add_rows(rows)
                        exporter.step_completed()
                    except Exception as e:  # noqa: BLE001
                        log.exception("[STAT-EXPORT] Failed to add/flush step=%d idx=%d err=%r", step_num, i, e)

                update_stats_for_step(
                    stats=state["stats"],
                    multi_hit_counts=state["multi_hit"],
                    hit_distribution=state["hit_dist"],
                    overlay_distribution=state["overlay_dist"],
                    true_row=true_row,
                    model_forecasts=forecasts,
                    dataset_index=i,
                    step_date=step_date,
                    overlay_witnesses=state.get("overlay_witnesses", None),
                    multi_hit_threshold=multi_hit_threshold,
                )

                state["last_step"] = i

                step_dt = time.perf_counter() - step_wall_t0
                ok_models = sum(
                    1
                    for m in MODEL_NAMES
                    if isinstance(forecasts.get(m, {}), dict) and len(forecasts[m]) > 0
                )
                log.info(
                    "Step done: step=%d/%d index=%d dt=%.3fs ok_models=%d worker_errors=%d overlay_sum=%d history_len=%d",
                    step_num,
                    total_steps,
                    i,
                    step_dt,
                    ok_models,
                    len(worker_errors),
                    int(sum(state["overlay_dist"].values())),
                    int(len(history_df)),
                )

                if step_num % CHECKPOINT_EVERY_STEPS == 0:
                    payload = dict(state)
                    payload["elapsed_total"] = elapsed_total
                    payload["start_time_offset"] = elapsed_total
                    payload["training_window_rounds"] = int(effective_window)

                    payload["export_mode"] = str(export_mode)
                    payload["export_run_id"] = str(export_run_id)
                    payload["export_dir"] = str((EXPORT_ROOT_DIR / export_run_id)) if exporter is not None else ""

                    if not STATS_STORE_RECENT_ERRORS:
                        payload["recent_errors"] = []

                    save_checkpoint(stats_dir, i, payload)

    except KeyboardInterrupt:
        print("\n[STAT] KeyboardInterrupt detected. Saving checkpoint and exiting...")
        elapsed_total = float(state.get("start_time_offset", 0.0)) + (time.time() - t0)
        state["elapsed_total"] = elapsed_total
        state["start_time_offset"] = elapsed_total
        state["training_window_rounds"] = int(effective_window)
        state["export_mode"] = str(export_mode)
        state["export_run_id"] = str(export_run_id)
        state["export_dir"] = str((EXPORT_ROOT_DIR / export_run_id)) if exporter is not None else ""
        last_step = int(state.get("last_step", MIN_STAT_HISTORY - 1))
        save_checkpoint(stats_dir, last_step, state)
        if exporter is not None:
            try:
                exporter.flush()
            except Exception:
                pass
        return
    except Exception as e:  # noqa: BLE001
        log.exception("Fatal error in Stat loop: %r", e)
        elapsed_total = float(state.get("start_time_offset", 0.0)) + (time.time() - t0)
        state["elapsed_total"] = elapsed_total
        state["start_time_offset"] = elapsed_total
        state["training_window_rounds"] = int(effective_window)
        state["export_mode"] = str(export_mode)
        state["export_run_id"] = str(export_run_id)
        state["export_dir"] = str((EXPORT_ROOT_DIR / export_run_id)) if exporter is not None else ""
        last_step = int(state.get("last_step", MIN_STAT_HISTORY - 1))
        save_checkpoint(stats_dir, last_step, state)
        if exporter is not None:
            try:
                exporter.flush()
            except Exception:
                pass
        raise
    finally:
        if exporter is not None:
            try:
                exporter.flush()
            except Exception:
                pass

    final_time = float(state.get("start_time_offset", 0.0)) + (time.time() - t0)
    state["elapsed_total"] = final_time
    state["training_window_rounds"] = int(effective_window)
    state["export_mode"] = str(export_mode)
    state["export_run_id"] = str(export_run_id)
    state["export_dir"] = str((EXPORT_ROOT_DIR / export_run_id)) if exporter is not None else ""

    print_results(
        state["stats"],
        state["hit_dist"],
        state["multi_hit"],
        state["overlay_dist"],
        final_time,
    )

    ow = state.get("overlay_witnesses", [])
    if isinstance(ow, list) and ow:
        print_overlay_witness_report(ow, max_per_hit=None, show_multihit=False)

    try:
        payload = dict(state)
        payload["start_time_offset"] = float(state.get("elapsed_total", final_time))
        payload["training_window_rounds"] = int(effective_window)
        save_checkpoint(stats_dir, int(state.get("last_step", n_obs - 1)), payload)
    except Exception:  # noqa: BLE001
        log.exception("Final checkpoint save failed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        help="Resume from checkpoint (optional: 'latest' or path or step index).",
    )
    parser.add_argument(
        "--statgrid-export",
        default="incremental",
        choices=list(EXPORT_MODE_VALUES),
        help="StatGrid export mode: none|incremental|full",
    )
    args = parser.parse_args()
    run_statistics(args.resume, args.statgrid_export)


if __name__ == "__main__":
    main()
