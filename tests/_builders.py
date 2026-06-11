# -----------------------
# tests/_builders.py
# -----------------------
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd


@dataclass(frozen=True)
class SyntheticGridSpec:
    n_steps: int = 12
    ts_list: Sequence[str] = ("TS_1", "TS_2", "TS_3", "TS_4", "TS_5", "TS_6", "TS_7")
    models: Sequence[str] = ("DynaMix", "PCE")
    rounding_ids: Sequence[int] = (1, 2)
    index_mode: str = "event"


def _truth_value(step: int, ts: str) -> int:
    ts_num = int(ts.split("_")[1])
    return (step * 3 + ts_num * 2) % 10


def _pred_value(step: int, ts: str, model: str, rounding_id: int) -> float:
    base = float(_truth_value(step, ts))
    model_bias = 0.15 if model == "DynaMix" else -0.10
    rounding_bias = 0.05 * float(rounding_id)
    return base + model_bias + rounding_bias


def _round(pred: float, rounding_id: int) -> int:
    import math
    if rounding_id == 1:
        return int(pred)  # truncate toward 0 (pred positive in generator)
    if rounding_id == 2:
        return int(math.floor(pred + 0.5))  # half-up for positives
    return int(round(pred))


def make_synthetic_statgrid(spec: SyntheticGridSpec) -> pd.DataFrame:
    rows = []
    for dataset_index in range(1, spec.n_steps + 1):
        for ts in spec.ts_list:
            true = _truth_value(dataset_index, ts)
            for model in spec.models:
                for rid in spec.rounding_ids:
                    pred = _pred_value(dataset_index, ts, model, rid)
                    rounded = _round(pred, rid)
                    hit = 1 if rounded == true else 0
                    abs_err = abs(float(rounded) - float(true))
                    rows.append(
                        {
                            "dataset_index": int(dataset_index),
                            "step_num": int(dataset_index),
                            "ts": str(ts),
                            "model": str(model),
                            "rounding_id": int(rid),
                            "pred": float(pred),
                            "rounded": int(rounded),
                            "true": int(true),
                            "hit": int(hit),
                            "abs_err": float(abs_err),
                            "window_rounds": 50,
                            "index_mode": spec.index_mode,
                        }
                    )
    return pd.DataFrame(rows)


def write_statgrid_run_shards(df: pd.DataFrame, run_dir: Path, parts: int = 2) -> None:
    """
    Writes shards matching opt_data loader glob:
      grid_part_*.csv.gz
    """
    run_dir.mkdir(parents=True, exist_ok=True)

    n = len(df)
    parts = max(1, int(parts))
    part_size = max(1, n // parts)

    for i in range(parts):
        start = i * part_size
        end = n if i == parts - 1 else (i + 1) * part_size
        part_df = df.iloc[start:end].copy()

        fname = f"grid_part_{i:04d}.csv.gz"
        fpath = run_dir / fname
        part_df.to_csv(fpath, index=False, compression="gzip")
