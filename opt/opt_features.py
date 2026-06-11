# -----------------------
# opt/opt_features.py
# -----------------------
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import numpy as np
import pandas as pd


@dataclass
class TruthHistoryTables:
    # Truth frequency tables computed over TRAIN (no leakage relative to EVAL)
    n_steps: int
    steps_ordered: List[int]

    # counts (over full TRAIN)
    global_value_counts: Dict[int, int]
    ts_value_counts: Dict[Tuple[str, int], int]

    # last seen positions (0-based positions in steps_ordered, over full TRAIN)
    last_seen_global: Dict[int, int]                 # value -> last step position
    last_seen_ts: Dict[Tuple[str, int], int]         # (ts,value) -> last step position

    # pair / triple cooccurrence on truths over TRAIN
    pair_counts: Dict[Tuple[str, int, str, int], int]  # (tsA,valA,tsB,valB) canonical ordered by ts name
    triple_counts: Dict[Tuple[str, int, str, int, str, int], int]


def _canonical_pair(ts_a: str, v_a: int, ts_b: str, v_b: int) -> Tuple[str, int, str, int]:
    if ts_a < ts_b:
        return (ts_a, int(v_a), ts_b, int(v_b))
    return (ts_b, int(v_b), ts_a, int(v_a))


def _canonical_triple(a: Tuple[str, int], b: Tuple[str, int], c: Tuple[str, int]) -> Tuple[str, int, str, int, str, int]:
    items = sorted([(a[0], int(a[1])), (b[0], int(b[1])), (c[0], int(c[1]))], key=lambda x: x[0])
    return (items[0][0], items[0][1], items[1][0], items[1][1], items[2][0], items[2][1])


def build_truth_history_tables(grid: pd.DataFrame, ts_list: List[str], steps_ordered: List[int]) -> TruthHistoryTables:
    global_counts: Dict[int, int] = defaultdict(int)
    ts_counts: Dict[Tuple[str, int], int] = defaultdict(int)

    last_g: Dict[int, int] = {}
    last_ts: Dict[Tuple[str, int], int] = {}

    pair_counts: Dict[Tuple[str, int, str, int], int] = defaultdict(int)
    triple_counts: Dict[Tuple[str, int, str, int, str, int], int] = defaultdict(int)

    for pos, idx in enumerate(steps_ordered):
        sdf = grid[grid["dataset_index"] == int(idx)]
        if sdf.empty:
            continue

        truth_ticket: List[Tuple[str, int]] = []
        for ts in ts_list:
            sub = sdf[sdf["ts"] == ts]
            if sub.empty:
                continue
            v = int(sub["true"].iloc[0])
            truth_ticket.append((ts, v))

            global_counts[v] += 1
            ts_counts[(ts, v)] += 1

            last_g[v] = pos
            last_ts[(ts, v)] = pos

        for i in range(len(truth_ticket)):
            for j in range(i + 1, len(truth_ticket)):
                a = truth_ticket[i]
                b = truth_ticket[j]
                pair_counts[_canonical_pair(a[0], a[1], b[0], b[1])] += 1

        for i in range(len(truth_ticket)):
            for j in range(i + 1, len(truth_ticket)):
                for k in range(j + 1, len(truth_ticket)):
                    a = truth_ticket[i]
                    b = truth_ticket[j]
                    c = truth_ticket[k]
                    triple_counts[_canonical_triple(a, b, c)] += 1

    return TruthHistoryTables(
        n_steps=int(len(steps_ordered)),
        steps_ordered=[int(x) for x in steps_ordered],
        global_value_counts=dict(global_counts),
        ts_value_counts=dict(ts_counts),
        last_seen_global=dict(last_g),
        last_seen_ts=dict(last_ts),
        pair_counts=dict(pair_counts),
        triple_counts=dict(triple_counts),
    )


def bin_uniform(x: float, *, lo: float, hi: float, bins: int) -> int:
    if bins <= 1:
        return 0
    if not np.isfinite(x):
        return 0
    lo = float(lo)
    hi = float(hi)
    if hi <= lo:
        return 0
    x2 = float(np.clip(x, lo, hi))
    frac = (x2 - lo) / max(1e-12, (hi - lo))
    b = int(np.floor(frac * bins))
    if b == bins:
        b = bins - 1
    return int(max(0, min(bins - 1, b)))


def parity(v: int) -> int:
    return int(abs(int(v)) % 2)


def low_high(v: int, threshold: int = 25) -> int:
    return int(1 if int(v) > int(threshold) else 0)


def sum_bucket(values: List[int]) -> int:
    s = int(sum(int(x) for x in values))
    if s < 70:
        return 0
    if s < 100:
        return 1
    if s < 130:
        return 2
    return 3


def _ensure_col(df: pd.DataFrame, col: str, default) -> None:
    """
    Ensure df[col] exists as a Series, so downstream .fillna/.astype is always valid.
    """
    if col not in df.columns:
        df[col] = default


def compute_candidate_features_for_step(
    step_df: pd.DataFrame,
    *,
    ts_list: List[str],
    tables: TruthHistoryTables,
    abs_err_bins: int,
    rank_bins: int,
    freq_bins: int,
    gap_bins: int,
    # Leakage-safe reference point.
    ref_pos: Optional[int] = None,
    ref_steps: Optional[int] = None,
) -> pd.DataFrame:
    df = step_df.copy()

    # Ensure needed cols exist as SERIES (fixes Pylance float.fillna warnings)
    _ensure_col(df, "abs_err", 0.0)
    _ensure_col(df, "pred", 0.0)
    _ensure_col(df, "rounded", 0)
    _ensure_col(df, "hit", 0)
    _ensure_col(df, "ts", "")

    # Basic numeric hygiene (operate on Series only)
    df["abs_err"] = pd.to_numeric(df["abs_err"], errors="coerce").fillna(0.0).astype(float)
    df["pred"] = pd.to_numeric(df["pred"], errors="coerce").fillna(0.0).astype(float)
    df["rounded"] = pd.to_numeric(df["rounded"], errors="coerce").fillna(0).astype(int)
    df["hit"] = pd.to_numeric(df["hit"], errors="coerce").fillna(0).astype(int)
    df["ts"] = df["ts"].astype(str)

    # consensus count within step for same (ts, rounded)
    df["consensus_count"] = df.groupby(["ts", "rounded"])["rounded"].transform("count").astype(int)

    # abs_err bin using empirical bounds per step (robust)
    ae = df["abs_err"].to_numpy(dtype=float, copy=False)
    if ae.size == 0:
        hi = 1.0
    else:
        hi = float(np.nanpercentile(ae, 95))
        if not np.isfinite(hi) or hi <= 0.0:
            mx = float(np.nanmax(ae)) if np.isfinite(np.nanmax(ae)) else 1.0
            hi = max(1e-9, mx)
        hi = max(1e-9, hi)

    df["abs_err_bin"] = [
        bin_uniform(float(x), lo=0.0, hi=hi, bins=int(abs_err_bins)) for x in df["abs_err"].tolist()
    ]

    # rank within ts by abs_err (lower abs_err = better rank)
    df["_rank"] = df.groupby("ts")["abs_err"].rank(method="first", ascending=True)
    df["_rank_max"] = df.groupby("ts")["_rank"].transform("max").replace(0, 1.0)
    df["_rank_norm"] = (df["_rank"] - 1.0) / (df["_rank_max"] - 1.0 + 1e-9)  # 0 best
    df["rank_bin"] = [
        bin_uniform(float(x), lo=0.0, hi=1.0, bins=int(rank_bins)) for x in df["_rank_norm"].tolist()
    ]
    df.drop(columns=["_rank", "_rank_max", "_rank_norm"], inplace=True, errors="ignore")

    # Reference history length and position (prefix-safe)
    n_total = max(1, int(tables.n_steps))
    ref_pos_eff = (n_total - 1) if ref_pos is None else int(ref_pos)
    ref_steps_eff = n_total if ref_steps is None else max(1, int(ref_steps))

    def freq_to_bin(c: int) -> int:
        return bin_uniform(float(c) / float(ref_steps_eff), lo=0.0, hi=1.0, bins=int(freq_bins))

    df["freq_global_bin"] = [
        freq_to_bin(int(tables.global_value_counts.get(int(v), 0))) for v in df["rounded"].tolist()
    ]
    df["freq_ts_bin"] = [
        freq_to_bin(int(tables.ts_value_counts.get((str(ts), int(v)), 0)))
        for ts, v in zip(df["ts"].tolist(), df["rounded"].tolist())
    ]

    denom_gap = float(max(1, ref_steps_eff - 1))

    def gap_bin(last_pos_val: Optional[int]) -> int:
        if last_pos_val is None:
            gap = ref_steps_eff  # never seen in history
        else:
            gap = max(0, int(ref_pos_eff) - int(last_pos_val))
        return bin_uniform(float(gap) / denom_gap, lo=0.0, hi=1.0, bins=int(gap_bins))

    df["gap_global_bin"] = [gap_bin(tables.last_seen_global.get(int(v), None)) for v in df["rounded"].tolist()]
    df["gap_ts_bin"] = [
        gap_bin(tables.last_seen_ts.get((str(ts), int(v)), None))
        for ts, v in zip(df["ts"].tolist(), df["rounded"].tolist())
    ]

    # parity, low/high, pred deltas
    df["parity"] = [parity(int(v)) for v in df["rounded"].tolist()]
    df["low_high"] = [low_high(int(v), threshold=25) for v in df["rounded"].tolist()]
    df["pred_minus_rounded"] = (df["pred"] - df["rounded"].astype(float)).astype(float)
    df["pred_minus_rounded_abs"] = df["pred_minus_rounded"].abs().astype(float)

    return df
