# ------------------------
# src/dynamix/data_utils.py
# ------------------------
"""
Data utilities for the DynaMix Lottery Forecasting System.

Responsibilities:
1. Load and validate DATA.csv using configured separator/encoding.
2. Parse dates using dd/mm/yyyy (or configured format).
3. Detect and validate TS_1..TS_7 numeric columns.
4. Align to daily frequency with forward-fill (ONLY when INDEX_MODE == "calendar").
5. In event-based mode (INDEX_MODE == "event"), keep one row per event
   (e.g., lottery draw) without calendar expansion. Duplicate dates are allowed.
   Missing values result in row drops, not imputation.
6. Confirm minimum data length.
7. Return a clean multivariate time-series array and its DatetimeIndex.
8. Provide CLI formatting utilities for Markdown tables.

Primary public API:
    load_lottery_data(...) -> Tuple[np.ndarray, pd.DatetimeIndex, pd.DataFrame]
    print_markdown_table(headers, rows) -> None
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Robust import for configuration constants after repo refactor
# - Preferred: package import (src/dynamix/constants.py)
# - Fallback: flat import (if repo root is on sys.path)
# ----------------------------------------------------------------------
try:
    from . import constants as C  # type: ignore
except Exception:  # pragma: no cover
    import constants as C  # type: ignore

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Event identity configuration (non-breaking, opt-in)
# ----------------------------------------------------------------------
# In INDEX_MODE="event", the DatetimeIndex may contain duplicates and therefore
# must not be treated as a unique identifier for a row/event. For interpretability,
# callers may request a stable row identifier column.
EVENT_ID_COL_DEFAULT: str = "EventIndex"


def _repo_root() -> Path:
    """
    Compute repository root robustly from this file location:
      <repo>/src/dynamix/data_utils.py -> parents[2] == <repo>
    """
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()


def _is_event_mode() -> bool:
    try:
        return str(getattr(C, "INDEX_MODE", "calendar")).lower().strip() == "event"
    except Exception:
        return False


def _event_id_col_name() -> str:
    try:
        name = str(getattr(C, "EVENT_ID_COL", EVENT_ID_COL_DEFAULT)).strip()
        return name if name else EVENT_ID_COL_DEFAULT
    except Exception:
        return EVENT_ID_COL_DEFAULT


# ----------------------------------------------------------------------
# 1. Helper: ensure output directories exist
# ----------------------------------------------------------------------
def ensure_output_dirs() -> None:
    """
    Ensures that standard output directories exist.
    Safe to call multiple times.

    Supports both:
    - New constants layout (recommended fields exist)
    - Partial constants (falls back to repo-relative defaults)
    """
    try:
        root = getattr(C, "PROJECT_ROOT", _repo_root())
        root = Path(root)

        output_dir = Path(getattr(C, "OUTPUT_DIR", root / "Output"))
        output_graphs_dir = Path(getattr(C, "OUTPUT_GRAPHS_DIR", output_dir / "Graphs"))
        output_logs_dir = Path(getattr(C, "OUTPUT_LOGS_DIR", output_dir / "Logs"))

        output_dir.mkdir(parents=True, exist_ok=True)
        output_graphs_dir.mkdir(parents=True, exist_ok=True)
        output_logs_dir.mkdir(parents=True, exist_ok=True)

        if bool(getattr(C, "MODEL_CACHE_ENABLED", True)):
            model_cache_dir = Path(getattr(C, "MODEL_CACHE_DIR", root / "model_cache"))
            model_cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log.exception("Failed to create output/model cache directories.")


# ----------------------------------------------------------------------
# 2. Internal helpers for data loading and validation
# ----------------------------------------------------------------------
def _resolve_data_path(csv_path: Optional[Union[str, Path]]) -> Path:
    """
    Resolve the dataset path after refactor.

    Priority:
      1) explicit csv_path
      2) C.DATA_FILE (if exists)
      3) <repo_root>/DATA.csv
      4) <cwd>/DATA.csv (last resort)
    """
    if csv_path is not None:
        path = Path(csv_path)
        if path.is_file():
            return path
        raise FileNotFoundError(f"Lottery data file not found: {path}")

    # Try constants
    c_path = getattr(C, "DATA_FILE", None)
    if c_path is not None:
        try:
            p = Path(c_path)
            if p.is_file():
                return p
        except Exception:
            pass

    # Repo root fallback (this is the typical desired location)
    p2 = _repo_root() / "DATA.csv"
    if p2.is_file():
        return p2

    # CWD fallback
    p3 = Path("DATA.csv")
    if p3.is_file():
        return p3

    raise FileNotFoundError(
        "Lottery data file not found. Tried: explicit csv_path, C.DATA_FILE, <repo_root>/DATA.csv, ./DATA.csv"
    )


def _parse_and_set_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parses DATE_COL and sets it as a DatetimeIndex.

    Behavior depends on INDEX_MODE:
    - "calendar": deduplicate dates (keep='last') to force 1 row/day.
    - "event": preserve duplicates (multiple draws per day allowed).
    """
    date_col = str(getattr(C, "DATE_COL", "Date"))
    date_fmt = str(getattr(C, "DATE_FORMAT", "%d/%m/%Y"))

    if isinstance(df.index, pd.DatetimeIndex):
        try:
            return df.sort_index()
        except Exception:
            return df

    if date_col not in df.columns:
        raise ValueError(f"Expected date column '{date_col}' not found in dataset.")

    try:
        dt_idx = pd.to_datetime(df[date_col], format=date_fmt, errors="coerce")
    except Exception:
        dt_idx = pd.to_datetime(df[date_col], errors="coerce")

    mask_valid = dt_idx.notna()
    if not mask_valid.any():
        raise ValueError(
            f"Failed to parse any valid dates from column '{date_col}'. "
            f"Check DATE_FORMAT={date_fmt} and the CSV content."
        )

    out = df.loc[mask_valid].copy()
    out.index = dt_idx.loc[mask_valid]
    out.drop(columns=[date_col], inplace=True, errors="ignore")

    try:
        out.sort_index(inplace=True)
    except Exception:
        pass

    index_mode = str(getattr(C, "INDEX_MODE", "calendar")).lower().strip()

    if out.index.has_duplicates:
        if index_mode == "calendar":
            log.warning(
                "Duplicate timestamps detected (calendar mode). "
                "Keeping last occurrence per date to enforce daily frequency."
            )
            out = out[~out.index.duplicated(keep="last")]
        else:
            log.info(
                "Duplicate timestamps detected (event mode). "
                "Preserving duplicates to maintain one-row-per-event semantics."
            )

    if not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError("Internal error: index is not DatetimeIndex after parsing.")

    return out


def _select_and_validate_ts_columns(
    df: pd.DataFrame,
    expected_ts_cols: Optional[Sequence[str]],
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Returns:
      - ts_df (TS-only columns)
      - resolved_ts_cols (list[str])
    """
    if expected_ts_cols is None:
        expected_ts_cols = list(getattr(C, "TS_COLUMNS", []) or [f"TS_{i}" for i in range(1, 8)])

    resolved = [str(c) for c in expected_ts_cols]
    missing = [c for c in resolved if c not in df.columns]
    if missing:
        raise ValueError(
            f"The following TS columns are missing from the dataset: {missing}. "
            f"Expected at least: {resolved}"
        )

    ts_df = df.loc[:, resolved].copy()
    return ts_df, resolved


def _convert_to_numeric_and_align_frequency(ts_df: pd.DataFrame, freq: Optional[str]) -> pd.DataFrame:
    """
    Convert TS columns to numeric and align frequency based on INDEX_MODE.

    - calendar:
        * asfreq(freq)
        * forward-fill
    - event:
        * no expansion
        * drop rows with any NaNs (integrity)
    """
    out = ts_df.apply(pd.to_numeric, errors="coerce")
    out = out.dropna(how="all")
    if out.empty:
        raise ValueError("All TS values are NaN after numeric conversion.")

    index_mode = str(getattr(C, "INDEX_MODE", "calendar")).lower().strip()

    if index_mode == "calendar" and freq:
        out = out.asfreq(freq)
        out = out.ffill()
        out = out.dropna(how="all")
    else:
        initial_len = len(out)
        out = out.dropna(how="any")
        dropped = initial_len - len(out)
        if dropped > 0:
            log.warning(
                "Event mode: dropped %d rows containing NaNs/invalid TS values. "
                "Forward-fill is disabled to preserve lottery integrity.",
                dropped,
            )

    if out.empty:
        raise ValueError("No valid TS data remain after processing.")

    return out.astype("float32")


def _check_min_history_length(ts_df: pd.DataFrame, min_history: Optional[int]) -> None:
    if min_history is None:
        min_history = int(getattr(C, "MIN_HISTORY_LENGTH", 0) or 0)

    n_obs = len(ts_df)
    if min_history > 0 and n_obs < int(min_history):
        raise ValueError(
            f"Insufficient history length for forecasting. Got {n_obs} observations; require at least {min_history}."
        )


# ----------------------------------------------------------------------
# 3. Public API
# ----------------------------------------------------------------------
def load_lottery_data(
    csv_path: Optional[Union[str, Path]] = None,
    expected_ts_cols: Optional[Sequence[str]] = None,
    min_history: Optional[int] = None,
    *,
    include_event_index: bool = False,
) -> Tuple[np.ndarray, pd.DatetimeIndex, pd.DataFrame]:
    """
    Loads, validates, and preprocesses the lottery multivariate dataset.

    Parameters
    ----------
    csv_path : str or Path, optional
        Explicit CSV path. If None, resolves via constants + repo-root fallback.
    expected_ts_cols : sequence of str, optional
        Expected TS column names. Defaults to constants.TS_COLUMNS.
    min_history : int, optional
        Minimum required length of post-processed series. If None uses constants.MIN_HISTORY_LENGTH.
    include_event_index : bool, optional (default False)
        If True and INDEX_MODE="event", adds an explicit integer identifier column
        (constants.EVENT_ID_COL, else "EventIndex") to the returned DataFrame.

    Returns
    -------
    ts_array : np.ndarray (float32), shape (n_obs, n_series)
    date_index : pd.DatetimeIndex
    ts_df : pd.DataFrame
        Cleaned multivariate time-series DataFrame (TS columns, plus optional event id column if requested).
    """
    ensure_output_dirs()

    path = _resolve_data_path(csv_path)

    sep = str(getattr(C, "CSV_SEPARATOR", ","))
    enc = str(getattr(C, "CSV_ENCODING", "utf-8-sig"))

    log.info("Loading lottery dataset from: %s", path)
    try:
        df_raw = pd.read_csv(path, sep=sep, encoding=enc, engine="python")
    except Exception as e:
        raise IOError(f"Failed to read CSV file {path}. Check format/encoding. Error: {e}") from e

    df_dt = _parse_and_set_datetime_index(df_raw)
    ts_df, ts_cols = _select_and_validate_ts_columns(df_dt, expected_ts_cols)

    freq = None
    try:
        freq = str(getattr(C, "FREQ", "D")) if getattr(C, "FREQ", None) is not None else None
    except Exception:
        freq = None

    ts_df = _convert_to_numeric_and_align_frequency(ts_df, freq)
    _check_min_history_length(ts_df, min_history)

    # Optional: stable event identifier for interpretability (opt-in)
    if include_event_index and _is_event_mode():
        eid_col = _event_id_col_name()
        if eid_col in ts_df.columns:
            log.warning(
                "include_event_index=True requested, but column '%s' already exists; leaving unchanged.",
                eid_col,
            )
        else:
            ts_df = ts_df.copy()
            ts_df.insert(
                0,
                eid_col,
                pd.RangeIndex(start=0, stop=len(ts_df), step=1, name=eid_col).astype("int64"),
            )
            log.info("Event mode: added explicit event identifier column '%s' (0..%d).", eid_col, len(ts_df) - 1)

    # Summary (safe for duplicate timestamps)
    try:
        d0 = ts_df.index[0].date()
        d1 = ts_df.index[-1].date()
    except Exception:
        d0 = str(ts_df.index[0]) if len(ts_df.index) else "N/A"
        d1 = str(ts_df.index[-1]) if len(ts_df.index) else "N/A"

    log.info(
        "Lottery dataset summary: %d observations, %d series, from %s to %s. index_mode=%s duplicates=%s",
        len(ts_df),
        len(ts_cols),
        d0,
        d1,
        "event" if _is_event_mode() else "calendar",
        bool(ts_df.index.has_duplicates) if isinstance(ts_df.index, pd.DatetimeIndex) else False,
    )

    # Ensure model inputs remain TS-only regardless of include_event_index
    ts_array = ts_df.loc[:, ts_cols].values.astype("float32")
    date_index = pd.DatetimeIndex(ts_df.index)

    return ts_array, date_index, ts_df


# ----------------------------------------------------------------------
# 4. Reporting Utilities (Markdown Tables)
# ----------------------------------------------------------------------
def print_markdown_table(headers: List[str], rows: List[List[Any]]) -> None:
    """
    Prints a formatted Markdown table to stdout.

    | Header1 | Header2 |
    |---------|---------|
    | Val1    | Val2    |
    """
    if not headers:
        return

    str_headers = [str(h) for h in headers]
    str_rows = [[str(c) for c in r] for r in rows]

    col_widths = [len(h) for h in str_headers]
    for row in str_rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(val))

    def _format_row(items: List[str]) -> str:
        padded = []
        for i, item in enumerate(items):
            if i < len(col_widths):
                padded.append(item.center(col_widths[i]))
        return "| " + " | ".join(padded) + " |"

    print(_format_row(str_headers))
    print(_format_row(["-" * w for w in col_widths]))
    for row in str_rows:
        # If a row is shorter than headers, pad it to avoid IndexErrors
        if len(row) < len(str_headers):
            row = row + [""] * (len(str_headers) - len(row))
        print(_format_row(row[: len(str_headers)]))
    print("")
