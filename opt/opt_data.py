# -----------------------
# opt/opt_data.py
# -----------------------
from __future__ import annotations

import bisect
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from .opt_config import OptConfig

# Columns required by the optimizer pipeline
REQUIRED_COLS: Set[str] = {
    "dataset_index",
    "ts",
    "model",
    "rounding_id",
    "rounded",
    "true",
    "hit",
    "pred",
    "abs_err",
}


def list_run_ids(cfg: OptConfig) -> List[str]:
    """
    Returns run-id directory names under cfg.exports_dir (Output/Reports/Exports/StatGrid/<run_id>/).
    """
    root = Path(cfg.exports_dir)
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def load_statgrid_run(cfg: OptConfig, run_id: str) -> pd.DataFrame:
    """
    Loads a StatGrid run folder:
        Output/Reports/Exports/StatGrid/<run_id>/grid_part_*.csv.gz

    Returns:
        DataFrame containing concatenated parts.

    Notes:
        - Performs required-column validation.
        - Applies numeric type coercions for critical columns.
    """
    run_dir = Path(cfg.exports_dir) / str(run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"StatGrid run dir not found: {run_dir}")

    parts = sorted(run_dir.glob("grid_part_*.csv.gz"))
    if not parts:
        # Optional: allow uncompressed single-file fallback
        parts_csv = sorted(run_dir.glob("grid_part_*.csv"))
        if parts_csv:
            parts = parts_csv  # type: ignore[assignment]
        else:
            raise FileNotFoundError(f"No grid_part_*.csv.gz (or .csv) under: {run_dir}")

    dfs: List[pd.DataFrame] = []
    for p in parts:
        if p.suffixes[-2:] == [".csv", ".gz"]:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                dfs.append(pd.read_csv(f))
        else:
            dfs.append(pd.read_csv(p))

    grid = pd.concat(dfs, axis=0, ignore_index=True)
    if grid.empty:
        raise ValueError(f"Loaded grid is empty for run_id={run_id} under {run_dir}")

    missing = sorted(list(REQUIRED_COLS - set(grid.columns)))
    if missing:
        raise ValueError(f"Grid missing required columns: {missing}")

    # --- Type coercions (robust; tolerate presence/absence) ---
    int_cols = ["dataset_index", "rounding_id", "rounded", "true", "hit", "step_num", "window_rounds"]
    for c in int_cols:
        if c in grid.columns:
            grid[c] = pd.to_numeric(grid[c], errors="coerce").fillna(0).astype(int)

    float_cols = ["pred", "abs_err"]
    for c in float_cols:
        if c in grid.columns:
            grid[c] = pd.to_numeric(grid[c], errors="coerce").astype(float)

    str_cols = ["ts", "model", "step_label", "step_date", "run_id", "index_mode", "export_mode"]
    for c in str_cols:
        if c in grid.columns:
            grid[c] = grid[c].astype(str)

    # --- Minimal sanity checks ---
    if cfg.ts_list:
        bad_ts = sorted(set(grid["ts"].unique().tolist()) - set(cfg.ts_list))
        if bad_ts:
            print(f"[opt_data] WARNING: grid contains TS values not in cfg.ts_list: {bad_ts}", flush=True)

    if int(grid["dataset_index"].max()) == 0 and int(grid["dataset_index"].min()) == 0:
        print("[opt_data] WARNING: dataset_index appears to be all zeros after type coercion.", flush=True)

    return grid


def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def compute_grid_fingerprint(grid: pd.DataFrame, ts_list: List[str], sample_steps: int = 25) -> Dict[str, Any]:
    """
    Computes a deterministic fingerprint to support resume-safety:
      - steps_hash: hash of ordered unique dataset_index values
      - schema_hash: hash of column names + dtypes
      - sample_true_hash: hash of a deterministic sample of (dataset_index, ts, true)

    Args:
        grid: full grid dataframe
        ts_list: expected TS order
        sample_steps: number of steps from head and tail used in sample_true_hash

    Returns:
        dict with fingerprint fields
    """
    steps = sorted(pd.unique(grid["dataset_index"]).tolist())
    steps_hash = _sha256_bytes(("|".join(str(int(x)) for x in steps)).encode("utf-8"))

    cols = sorted(list(grid.columns))
    dtypes = {c: str(grid[c].dtype) for c in cols}
    schema_hash = _sha256_bytes(json.dumps({"cols": cols, "dtypes": dtypes}, sort_keys=True).encode("utf-8"))

    k = max(1, int(sample_steps))
    sample_indices: List[int] = []
    sample_indices.extend([int(x) for x in steps[: min(k, len(steps))]])
    if len(steps) > k:
        sample_indices.extend([int(x) for x in steps[-min(k, len(steps)) :]])
    sample_indices = sorted(set(sample_indices))

    g = grid[grid["dataset_index"].isin(sample_indices)][["dataset_index", "ts", "true"]].copy()
    g["dataset_index"] = pd.to_numeric(g["dataset_index"], errors="coerce").fillna(0).astype(int)
    g["ts"] = g["ts"].astype(str)
    g["true"] = pd.to_numeric(g["true"], errors="coerce").fillna(0).astype(int)

    # Detect inconsistent truths within a (dataset_index, ts)
    truth_nunique = g.groupby(["dataset_index", "ts"], dropna=False)["true"].nunique()
    inconsistent_keys = truth_nunique[truth_nunique > 1]
    inconsistent_set: Set[Tuple[int, str]] = set((int(di), str(ts)) for (di, ts) in inconsistent_keys.index.tolist())

    truth_first = g.groupby(["dataset_index", "ts"], dropna=False)["true"].first()

    # Deterministic sample rows in ts_list order
    sample_rows: List[str] = []
    for idx in sample_indices:
        for ts in ts_list:
            key = (int(idx), str(ts))
            if key in inconsistent_set:
                sample_rows.append(f"{idx}:{ts}=INCONSISTENT")
                continue
            if key in truth_first.index:
                sample_rows.append(f"{idx}:{ts}={int(truth_first.loc[key])}")
            else:
                sample_rows.append(f"{idx}:{ts}=NA")

    sample_true_hash = _sha256_bytes(("|".join(sample_rows)).encode("utf-8"))

    return {
        "n_rows": int(len(grid)),
        "n_steps": int(len(steps)),
        "min_dataset_index": int(min(steps)) if steps else None,
        "max_dataset_index": int(max(steps)) if steps else None,
        "steps_hash": steps_hash,
        "schema_hash": schema_hash,
        "sample_true_hash": sample_true_hash,
    }


def resolve_slices(
    steps_ordered: List[int],
    *,
    train_frac: Optional[float],
    train_end_step: Optional[int],
    eval_start_step: Optional[int],
    eval_end_step: Optional[int],
    slice_mode: str = "pos",
) -> Dict[str, Any]:
    """
    Resolve TRAIN/EVAL slices from an ordered list of dataset_index steps.

    slice_mode:
      - "pos"   : train_end_step / eval_* interpreted as 1-based POSITIONS in steps_ordered (legacy behavior)
      - "index" : train_end_step / eval_* interpreted as literal dataset_index VALUES (inclusive bounds)

    Returns:
      A dict with:
        - slice_mode
        - N_steps_total
        - train_frac (effective)
        - train_end_step_pos / eval_start_step_pos / eval_end_step_pos  (positions; best-effort for "index")
        - train_steps_dataset_index
        - eval_steps_dataset_index
    """
    mode = str(slice_mode).strip().lower()
    if mode not in {"pos", "index"}:
        raise ValueError("--slice-mode must be one of: pos, index")

    N = len(steps_ordered)
    if N <= 0:
        raise ValueError("No steps in grid.")

    steps = [int(x) for x in steps_ordered]

    def clamp_pos_1based(p: int) -> int:
        return max(1, min(N, int(p)))

    def pos_from_index_value_rightmost_le(v: int) -> int:
        """
        Return 0..N position COUNT such that steps[:pos] are <= v.
        Equivalent to bisect_right.
        """
        return int(bisect.bisect_right(steps, int(v)))

    def pos_from_index_value_leftmost_ge(v: int) -> int:
        """
        Return 1..N+1 as a 1-based START position for first step >= v.
        If all steps < v, returns N+1.
        """
        i0 = int(bisect.bisect_left(steps, int(v)))  # 0..N
        return int(i0 + 1)  # 1..N+1

    # ---- TRAIN end (position count) ----
    train_frac_used: Optional[float] = None

    if train_end_step is not None:
        if mode == "pos":
            train_end_pos = clamp_pos_1based(int(train_end_step))  # 1..N
        else:
            # "index" mode: dataset_index upper bound (inclusive); may yield 0..N
            train_end_pos = pos_from_index_value_rightmost_le(int(train_end_step))
        train_frac_used = None
    elif train_frac is not None:
        tf = float(train_frac)
        if not (0.0 < tf <= 1.0):
            raise ValueError("--train-frac must be in (0,1].")
        if tf >= 1.0:
            train_end_pos = N
        else:
            train_end_pos = int(math.floor(tf * N))
            if train_end_pos < 1:
                train_end_pos = 1
        train_frac_used = tf
    else:
        train_end_pos = N
        train_frac_used = None

    # train_end_pos semantics:
    # - "pos"   : 1..N (1-based inclusive end position)
    # - "index" : 0..N (count of steps <= bound)
    train_steps = steps[: int(train_end_pos)]

    # ---- EVAL slice ----
    if mode == "pos":
        if eval_start_step is None:
            eval_start_pos = int(train_end_pos) + 1
        else:
            eval_start_pos = int(eval_start_step)

        eval_end_pos = N if eval_end_step is None else int(eval_end_step)

        if eval_start_pos > N:
            eval_steps: List[int] = []
            eval_start_pos_clamped = N + 1
            eval_end_pos_clamped = N
        else:
            eval_start_pos_clamped = clamp_pos_1based(eval_start_pos)
            eval_end_pos_clamped = clamp_pos_1based(eval_end_pos)
            if eval_end_pos_clamped < eval_start_pos_clamped:
                eval_steps = []
            else:
                eval_steps = steps[eval_start_pos_clamped - 1 : eval_end_pos_clamped]

        return {
            "slice_mode": mode,
            "N_steps_total": int(N),
            "train_frac": train_frac_used,
            "train_end_step_pos": int(train_end_pos),
            "eval_start_step_pos": int(eval_start_pos_clamped),
            "eval_end_step_pos": int(eval_end_pos_clamped),
            "train_steps_dataset_index": [int(x) for x in train_steps],
            "eval_steps_dataset_index": [int(x) for x in eval_steps],
        }

    # ---- index mode defaults ----
    # Defaults:
    # - if eval_start_step omitted:
    #     - if train_end_step given: start at first step > train_end_step
    #     - else: start at first step after training prefix (position train_end_pos + 1)
    # - if eval_end_step omitted: use max dataset_index
    if eval_end_step is None:
        eval_end_value = steps[-1]
    else:
        eval_end_value = int(eval_end_step)

    if eval_start_step is None:
        if train_end_step is not None:
            start_pos_1based = pos_from_index_value_leftmost_ge(int(train_end_step) + 1)
        else:
            start_pos_1based = int(train_end_pos) + 1
    else:
        start_pos_1based = pos_from_index_value_leftmost_ge(int(eval_start_step))

    end_pos_count = pos_from_index_value_rightmost_le(eval_end_value)  # 0..N
    eval_end_pos_1based = int(end_pos_count)  # 0..N (inclusive end position as a 1-based number)

    # Clamp start to 1..N+1 (N+1 => empty)
    start_pos_1based = max(1, min(N + 1, int(start_pos_1based)))
    # Clamp end to 0..N (0 => empty)
    eval_end_pos_1based = max(0, min(N, int(eval_end_pos_1based)))

    if start_pos_1based > N or eval_end_pos_1based < start_pos_1based:
        eval_steps = []
    else:
        eval_steps = steps[start_pos_1based - 1 : eval_end_pos_1based]

    return {
        "slice_mode": mode,
        "N_steps_total": int(N),
        "train_frac": train_frac_used,
        "train_end_step_pos": int(train_end_pos),
        "eval_start_step_pos": int(start_pos_1based),
        "eval_end_step_pos": int(eval_end_pos_1based),
        "train_steps_dataset_index": [int(x) for x in train_steps],
        "eval_steps_dataset_index": [int(x) for x in eval_steps],
    }
