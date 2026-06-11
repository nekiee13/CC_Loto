# ------------------------
# tools/statgrid/StatGrid_Merge.py
# ------------------------
"""
Merge multiple StatGrid export runs (statgrid_*) into a single StatGrid_DB.

Goal
----
Create a durable, appendable “StatGrid database” directory:

  Output/Reports/Exports/StatGrid_DB/
    schema.json
    provenance.json
    manifest.jsonl
    grid_part_000001.csv.gz
    grid_part_000002.csv.gz
    ...

Safety & strictness
-------------------
This tool is intentionally strict to protect DB integrity.

1) Schema checks
   - All input shards must contain the required columns.
   - Extra columns are preserved only if present in ALL inputs; otherwise dropped (and logged).

2) Truth consistency checks on overlaps
   - For any overlap on key (dataset_index, ts), `true` must be identical.

3) Duplicate row checks on overlaps
   - Uniqueness key:
        (dataset_index, ts, model, rounding_id, rounded)
     For duplicates across runs:
        - `true` must match (enforced by #2)
        - `hit` must match
        - `pred` and `abs_err` must match within tolerance
     Otherwise merge fails.

4) Atomic commit
   - Writes into StatGrid_DB.__tmp__ then atomically swaps into place.
   - Lock file prevents concurrent merges.

Modes
-----
A) Build/Replace (default):
   --mode replace
   Builds a new StatGrid_DB from the specified runs only.

B) Append:
   --mode append
   Loads existing StatGrid_DB shards first as the baseline, then merges additional runs.
   All strict checks apply.

Usage examples
--------------
# Replace DB from selected runs:
python StatGrid_Merge.py --runs statgrid_20251226_123559 statgrid_20251228_115618 --mode replace

# Append runs into DB:
python StatGrid_Merge.py --runs statgrid_20251229_013541 statgrid_20251229_110045 --mode append

# Append latest N runs (by folder name sort):
python StatGrid_Merge.py --latest 3 --mode append

Notes
-----
- Expects Stat.py exported schema including:
  dataset_index, ts, model, rounding_id, rounded, true, hit, pred, abs_err
- Deterministic and conservative: fails fast on any inconsistency.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


# ------------------------
# Defaults / Paths
# ------------------------
OUTPUT_DIR = Path("Output")
REPORTS_DIR = OUTPUT_DIR / "Reports"
EXPORTS_DIR = REPORTS_DIR / "Exports"
STATGRID_ROOT = EXPORTS_DIR / "StatGrid"

DB_DIR = EXPORTS_DIR / "StatGrid_DB"
DB_LOCK = EXPORTS_DIR / "StatGrid_DB.lock"

DEFAULT_ROWS_PER_PART = 200_000

REQUIRED_COLS = [
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
]

# Tolerance for float comparisons on duplicate row keys
PRED_TOL = 1e-9
ABSERR_TOL = 1e-9


# ------------------------
# Merge keys
# ------------------------
TruthKey = Tuple[int, str]  # (dataset_index, ts)
RowKey = Tuple[int, str, str, int, int]  # (dataset_index, ts, model, rounding_id, rounded)


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


# ------------------------
# Locking
# ------------------------
class FileLock:
    def __init__(self, path: Path, stale_seconds: int = 6 * 3600) -> None:
        self.path = path
        self.stale_seconds = int(stale_seconds)

    def acquire(self) -> None:
        now = time.time()
        if self.path.exists():
            try:
                age = now - self.path.stat().st_mtime
                if age > float(self.stale_seconds):
                    eprint(f"[MERGE] WARNING: Lock file is stale (age={age:.0f}s). Removing: {self.path}")
                    self.path.unlink(missing_ok=True)
                else:
                    raise RuntimeError(f"Lock file exists: {self.path}. Another merge may be running.")
            except FileNotFoundError:
                pass

        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def release(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass


# ------------------------
# Input discovery
# ------------------------
def list_statgrid_runs(root: Path) -> List[str]:
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir() and p.name.startswith("statgrid_")])


def resolve_runs(root: Path, runs: Optional[List[str]], latest_n: Optional[int]) -> List[str]:
    existing = list_statgrid_runs(root)

    if latest_n is not None:
        n = int(latest_n)
        if n <= 0:
            raise ValueError("--latest must be > 0")
        if not existing:
            raise FileNotFoundError(f"No statgrid_* runs found under: {root}")
        return existing[-n:]

    if not runs:
        raise ValueError("Provide --runs ... or --latest N")

    missing = [r for r in runs if not (root / r).is_dir()]
    if missing:
        raise FileNotFoundError(f"These run folders do not exist under {root}: {missing}")

    return runs


def iter_run_parts(run_dir: Path) -> List[Path]:
    parts = sorted(run_dir.glob("grid_part_*.csv.gz"))
    if not parts:
        raise FileNotFoundError(f"No grid_part_*.csv.gz found in: {run_dir}")
    return parts


# ------------------------
# Schema handling
# ------------------------
def read_schema_from_run(run_dir: Path) -> Optional[dict]:
    schema_path = run_dir / "schema.json"
    if schema_path.exists():
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = ["dataset_index", "step_num", "rounding_id", "rounded", "true", "hit", "window_rounds"]
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    float_cols = ["pred", "abs_err"]
    for c in float_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)

    str_cols = ["run_id", "step_label", "step_date", "ts", "model", "index_mode"]
    for c in str_cols:
        if c in df.columns:
            df[c] = df[c].astype(str)

    return df


def validate_required_columns(cols: Iterable[str], context: str) -> None:
    colset = set(cols)
    missing = [c for c in REQUIRED_COLS if c not in colset]
    if missing:
        raise ValueError(f"[MERGE] Missing required columns in {context}: {missing}")


def compute_common_schema_columns(datasets_cols: List[Set[str]]) -> List[str]:
    """
    DB schema is:
      - all REQUIRED_COLS (must exist everywhere)
      - plus only extra columns present in *all* inputs
    """
    common = set.intersection(*datasets_cols) if datasets_cols else set()
    # REQUIRED_COLS are enforced separately; ensure ordering is stable.
    for c in REQUIRED_COLS:
        common.add(c)

    extras = sorted([c for c in common if c not in REQUIRED_COLS])
    return REQUIRED_COLS + extras


# ------------------------
# Output writer (CSV.GZ parts + manifest)
# ------------------------
@dataclass
class PartWriter:
    out_dir: Path
    rows_per_part: int
    columns: List[str]

    part_idx: int = 0
    buffered: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def manifest_path(self) -> Path:
        return self.out_dir / "manifest.jsonl"

    @property
    def schema_path(self) -> Path:
        return self.out_dir / "schema.json"

    def __post_init__(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def write_schema(self, schema_obj: dict) -> None:
        self.schema_path.write_text(json.dumps(schema_obj, indent=2), encoding="utf-8")

    def add_rows(self, rows: Iterable[Dict[str, Any]]) -> None:
        for r in rows:
            self.buffered.append(r)
            if len(self.buffered) >= int(self.rows_per_part):
                self.flush()

    def flush(self) -> None:
        if not self.buffered:
            return

        self.part_idx += 1
        part_name = f"grid_part_{self.part_idx:06d}.csv.gz"
        part_path = self.out_dir / part_name

        with gzip.open(part_path, "wt", encoding="utf-8", newline="") as gz:
            writer = csv.DictWriter(gz, fieldnames=self.columns, extrasaction="ignore")
            writer.writeheader()
            for r in self.buffered:
                writer.writerow(r)

        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "part": part_name,
            "rows": len(self.buffered),
        }
        with self.manifest_path.open("a", encoding="utf-8") as mf:
            mf.write(json.dumps(rec) + "\n")

        print(f"[MERGE] Wrote {len(self.buffered)} rows -> {part_path}")
        self.buffered.clear()


# ------------------------
# Core merge logic
# ------------------------
def iter_rows_from_parts(parts: List[Path], keep_columns: List[str]) -> Iterable[pd.DataFrame]:
    for p in parts:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            df = pd.read_csv(f)
        validate_required_columns(df.columns, context=str(p))
        df = normalize_types(df)
        df = df[[c for c in keep_columns if c in df.columns]].copy()
        yield df


def build_columns_presence_for_runs(
    run_dirs: List[Path],
    *,
    include_db_existing: bool,
    db_dir: Path,
) -> Tuple[List[Set[str]], List[Tuple[str, Path]]]:
    """
    Returns:
      - list of column sets for each dataset source (db baseline (optional) + each run)
      - ordered list of sources for reading: (source_name, dir)
    """
    sources: List[Tuple[str, Path]] = []
    colsets: List[Set[str]] = []

    if include_db_existing and db_dir.exists() and db_dir.is_dir():
        sources.append(("__db__", db_dir))

        schema = None
        try:
            schema_path = db_dir / "schema.json"
            if schema_path.exists():
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception:
            schema = None

        if schema and isinstance(schema.get("columns"), list):
            cs = set(str(x) for x in schema["columns"])
        else:
            parts = sorted(db_dir.glob("grid_part_*.csv.gz"))
            if not parts:
                cs = set(REQUIRED_COLS)
            else:
                with gzip.open(parts[0], "rt", encoding="utf-8") as f:
                    df0 = pd.read_csv(f, nrows=5)
                cs = set(df0.columns)

        colsets.append(cs)

    for rd in run_dirs:
        sources.append((rd.name, rd))
        schema = read_schema_from_run(rd)
        if schema and isinstance(schema.get("columns"), list):
            cs = set(str(x) for x in schema["columns"])
        else:
            parts = iter_run_parts(rd)
            with gzip.open(parts[0], "rt", encoding="utf-8") as f:
                df0 = pd.read_csv(f, nrows=5)
            cs = set(df0.columns)
        colsets.append(cs)

    return colsets, sources


def merge_sources_to_db(
    sources: List[Tuple[str, Path]],
    *,
    out_dir_tmp: Path,
    keep_columns: List[str],
    rows_per_part: int,
) -> Dict[str, Any]:
    """
    Reads each source (db baseline optional + runs) and writes a new DB into out_dir_tmp.
    Enforces truth consistency and duplicate-row strict checks.
    """
    truth_map: Dict[TruthKey, int] = {}
    row_fingerprint: Dict[RowKey, Tuple[int, int, float, float]] = {}  # true, hit, pred, abs_err

    total_rows_in = 0
    total_rows_out = 0
    sources_used: List[Dict[str, Any]] = []

    writer = PartWriter(out_dir_tmp, rows_per_part=rows_per_part, columns=keep_columns)

    for source_name, src_dir in sources:
        if source_name == "__db__":
            parts = sorted(src_dir.glob("grid_part_*.csv.gz"))
            if not parts:
                print("[MERGE] DB baseline selected, but DB has no parts. Continuing.")
                continue
        else:
            parts = iter_run_parts(src_dir)

        print(f"[MERGE] Reading source={source_name} parts={len(parts)} dir={src_dir}")

        sources_used.append({"source": source_name, "dir": str(src_dir), "parts": len(parts)})

        for df in iter_rows_from_parts(parts, keep_columns):
            if df.empty:
                continue

            total_rows_in += int(len(df))

            out_rows: List[Dict[str, Any]] = []

            di = df["dataset_index"].astype(int)
            ts = df["ts"].astype(str)
            truev = df["true"].astype(int)
            model = df["model"].astype(str)
            rid = df["rounding_id"].astype(int)
            rounded = df["rounded"].astype(int)
            hitv = df["hit"].astype(int)
            predv = df["pred"].astype(float)
            absv = df["abs_err"].astype(float)

            for i in range(len(df)):
                tkey: TruthKey = (int(di.iat[i]), str(ts.iat[i]))
                tv = int(truev.iat[i])

                if tkey in truth_map:
                    if int(truth_map[tkey]) != tv:
                        raise ValueError(
                            "[MERGE] TRUTH CONFLICT on overlap: "
                            f"key={tkey} existing_true={truth_map[tkey]} incoming_true={tv} "
                            f"(source={source_name})"
                        )
                else:
                    truth_map[tkey] = tv

                rkey: RowKey = (int(di.iat[i]), str(ts.iat[i]), str(model.iat[i]), int(rid.iat[i]), int(rounded.iat[i]))
                hv = int(hitv.iat[i])
                pv = float(predv.iat[i])
                av = float(absv.iat[i])

                if rkey in row_fingerprint:
                    etrue, ehit, epred, eabs = row_fingerprint[rkey]
                    if etrue != tv:
                        raise ValueError(
                            "[MERGE] DUPLICATE ROW KEY with true mismatch: "
                            f"key={rkey} existing_true={etrue} incoming_true={tv} source={source_name}"
                        )
                    if ehit != hv:
                        raise ValueError(
                            "[MERGE] DUPLICATE ROW KEY with hit mismatch: "
                            f"key={rkey} existing_hit={ehit} incoming_hit={hv} source={source_name}"
                        )
                    if abs(epred - pv) > PRED_TOL:
                        raise ValueError(
                            "[MERGE] DUPLICATE ROW KEY with pred mismatch: "
                            f"key={rkey} existing_pred={epred} incoming_pred={pv} tol={PRED_TOL} source={source_name}"
                        )
                    if abs(eabs - av) > ABSERR_TOL:
                        raise ValueError(
                            "[MERGE] DUPLICATE ROW KEY with abs_err mismatch: "
                            f"key={rkey} existing_abs_err={eabs} incoming_abs_err={av} tol={ABSERR_TOL} source={source_name}"
                        )
                    # Exact duplicate row -> skip output (dedupe)
                    continue

                row_fingerprint[rkey] = (tv, hv, pv, av)
                out_rows.append(df.iloc[i].to_dict())

            if out_rows:
                writer.add_rows(out_rows)
                total_rows_out += int(len(out_rows))

    writer.flush()

    return {
        "rows_in": int(total_rows_in),
        "rows_out": int(total_rows_out),
        "unique_truth_keys": int(len(truth_map)),
        "unique_row_keys": int(len(row_fingerprint)),
        "sources_used": sources_used,
    }


def atomic_replace_dir(src_tmp: Path, dst: Path) -> None:
    """
    Atomically replace dst with src_tmp content using directory renames.
    """
    if dst.exists():
        backup = dst.with_name(dst.name + ".__bak__")
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        os.replace(str(dst), str(backup))
        os.replace(str(src_tmp), str(dst))
        shutil.rmtree(backup, ignore_errors=True)
    else:
        os.replace(str(src_tmp), str(dst))


# ------------------------
# Main
# ------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Merge StatGrid runs into StatGrid_DB with strict consistency checks.")
    parser.add_argument("--statgrid-root", type=str, default=str(STATGRID_ROOT), help="Root folder containing statgrid_* runs.")
    parser.add_argument("--db-dir", type=str, default=str(DB_DIR), help="Destination StatGrid_DB directory.")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["replace", "append"],
        default="replace",
        help="replace builds DB from specified runs; append merges into existing DB then adds runs.",
    )
    parser.add_argument("--runs", nargs="*", default=None, help="One or more statgrid_* run folder names to merge.")
    parser.add_argument("--latest", type=int, default=None, help="Merge the latest N runs (by folder name sort).")
    parser.add_argument("--rows-per-part", type=int, default=DEFAULT_ROWS_PER_PART, help="Max rows per output shard (csv.gz).")
    args = parser.parse_args()

    statgrid_root = Path(args.statgrid_root)
    db_dir = Path(args.db_dir)
    out_tmp = db_dir.with_name(db_dir.name + ".__tmp__")

    statgrid_root.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lock = FileLock(DB_LOCK)
    lock.acquire()
    try:
        run_names = resolve_runs(statgrid_root, runs=args.runs, latest_n=args.latest)
        run_dirs = [statgrid_root / r for r in run_names]

        include_db_existing = (args.mode == "append")

        # Compute schema columns as intersection across all inputs (plus required columns).
        colsets, sources = build_columns_presence_for_runs(
            run_dirs,
            include_db_existing=include_db_existing,
            db_dir=db_dir,
        )

        # Validate required columns exist in every source.
        for (src_name, src_dir), cs in zip(sources, colsets):
            validate_required_columns(cs, context=f"{src_name}:{src_dir}")

        keep_columns = compute_common_schema_columns(colsets)

        # Inform about dropped columns.
        all_union = set().union(*colsets) if colsets else set()
        dropped = sorted([c for c in all_union if c not in keep_columns])
        if dropped:
            print(f"[MERGE] NOTE: Dropping non-common columns to keep DB schema stable: {dropped}")

        # Prepare temp output.
        if out_tmp.exists():
            shutil.rmtree(out_tmp, ignore_errors=True)
        out_tmp.mkdir(parents=True, exist_ok=True)

        # Write schema/provenance.
        schema_obj = {
            "schema_version": "db-1.0",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "columns": keep_columns,
            "required_columns": REQUIRED_COLS,
            "notes": "Merged StatGrid DB. Columns are the intersection across all merged inputs (plus required columns).",
        }
        provenance_obj = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "mode": str(args.mode),
            "statgrid_root": str(statgrid_root),
            "db_dir": str(db_dir),
            "runs": run_names,
            "include_db_existing": bool(include_db_existing),
            "rows_per_part": int(args.rows_per_part),
            "float_tolerances": {"pred_tol": PRED_TOL, "abs_err_tol": ABSERR_TOL},
        }
        (out_tmp / "schema.json").write_text(json.dumps(schema_obj, indent=2), encoding="utf-8")
        (out_tmp / "provenance.json").write_text(json.dumps(provenance_obj, indent=2), encoding="utf-8")

        # Merge.
        merge_stats = merge_sources_to_db(
            sources=sources,
            out_dir_tmp=out_tmp,
            keep_columns=keep_columns,
            rows_per_part=int(args.rows_per_part),
        )

        # Append summary record to manifest.jsonl (after part records written by PartWriter).
        summary_rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": "merge_complete",
            "rows_in": merge_stats["rows_in"],
            "rows_out": merge_stats["rows_out"],
            "unique_truth_keys": merge_stats["unique_truth_keys"],
            "unique_row_keys": merge_stats["unique_row_keys"],
            "sources_used": merge_stats["sources_used"],
        }
        with (out_tmp / "manifest.jsonl").open("a", encoding="utf-8") as mf:
            mf.write(json.dumps(summary_rec) + "\n")

        # Atomic commit.
        atomic_replace_dir(out_tmp, db_dir)

        print("[MERGE] SUCCESS")
        print(json.dumps({"db_dir": str(db_dir), **merge_stats}, indent=2))

    finally:
        # If failure, ensure tmp is cleaned (best-effort).
        try:
            if out_tmp.exists():
                shutil.rmtree(out_tmp, ignore_errors=True)
        except Exception:
            pass
        lock.release()


if __name__ == "__main__":
    main()
