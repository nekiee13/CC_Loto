# -----------------------
# opt/opt_calibration.py
# -----------------------
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go


@dataclass(frozen=True)
class CalibrationMetrics:
    brier: float
    ece: float


def brier_score(y_true: np.ndarray, p: np.ndarray) -> float:
    y = y_true.astype(float)
    p2 = np.clip(p.astype(float), 0.0, 1.0)
    if y.size == 0:
        return 0.0
    return float(np.mean((p2 - y) ** 2))


def expected_calibration_error(y_true: np.ndarray, p: np.ndarray, n_bins: int) -> float:
    nb = int(n_bins)
    if nb <= 0:
        raise ValueError("n_bins must be >= 1")

    y = y_true.astype(float)
    p2 = np.clip(p.astype(float), 0.0, 1.0)
    if y.size == 0:
        return 0.0

    bins = np.linspace(0.0, 1.0, nb + 1)
    ece = 0.0
    N = int(len(y))

    for i in range(len(bins) - 1):
        lo, hi = float(bins[i]), float(bins[i + 1])
        # include right edge on last bin
        if i == len(bins) - 2:
            mask = (p2 >= lo) & (p2 <= hi)
        else:
            mask = (p2 >= lo) & (p2 < hi)

        n = int(np.sum(mask))
        if n == 0:
            continue

        acc = float(np.mean(y[mask]))
        conf = float(np.mean(p2[mask]))
        ece += (n / max(1, N)) * abs(acc - conf)

    return float(ece)


def calibration_table(
    df: pd.DataFrame,
    *,
    p_col: str,
    y_col: str,
    n_bins: int,
    by_cols: Sequence[str] = (),
) -> pd.DataFrame:
    """
    Returns a calibration table with columns:
      - [by_cols...]
      - bin_lo, bin_hi
      - n
      - empirical (mean y)
      - avg_p (mean predicted p)
    """
    if df.empty:
        return pd.DataFrame(columns=[*list(by_cols), "bin_lo", "bin_hi", "n", "empirical", "avg_p"])

    nb = int(n_bins)
    if nb <= 0:
        raise ValueError("n_bins must be >= 1")

    out_rows: List[Dict[str, Any]] = []
    bins = np.linspace(0.0, 1.0, nb + 1)

    gcols = list(by_cols) if by_cols else []
    if not gcols:
        group_iter = [((), df)]
    else:
        group_iter = df.groupby(gcols, dropna=False)

    for key, g in group_iter:
        p = pd.to_numeric(g[p_col], errors="coerce").fillna(0.0).clip(0.0, 1.0).to_numpy(dtype=float)
        y = pd.to_numeric(g[y_col], errors="coerce").fillna(0).to_numpy(dtype=int)

        # Normalize key to tuple form for uniform downstream handling
        key_t: Tuple[Any, ...]
        if not gcols:
            key_t = ()
        else:
            key_t = key if isinstance(key, tuple) else (key,)

        for i in range(len(bins) - 1):
            lo, hi = float(bins[i]), float(bins[i + 1])
            if i == len(bins) - 2:
                mask = (p >= lo) & (p <= hi)
            else:
                mask = (p >= lo) & (p < hi)

            n = int(np.sum(mask))
            if n == 0:
                continue

            row: Dict[str, Any] = {}
            for kname, kval in zip(gcols, key_t):
                row[kname] = kval

            row.update(
                {
                    "bin_lo": lo,
                    "bin_hi": hi,
                    "n": n,
                    "empirical": float(np.mean(y[mask])) if n > 0 else 0.0,
                    "avg_p": float(np.mean(p[mask])) if n > 0 else 0.0,
                }
            )
            out_rows.append(row)

    out = pd.DataFrame(out_rows)
    if out.empty:
        return pd.DataFrame(columns=[*gcols, "bin_lo", "bin_hi", "n", "empirical", "avg_p"])

    # Stable ordering for plots and readability
    sort_cols = [*gcols, "bin_lo"]
    out = out.sort_values(by=sort_cols).reset_index(drop=True)
    return out


def reliability_plot_html(
    cal_df: pd.DataFrame,
    *,
    title: str,
    out_path: Path,
    series_name: str = "",
) -> None:
    fig = go.Figure()

    if cal_df.empty:
        fig.update_layout(title=title, template="plotly_white", width=1100, height=600)
        out_path.write_text(fig.to_html(full_html=True, include_plotlyjs="cdn"), encoding="utf-8")
        return

    # Avoid zig-zag lines if cal_df is not already sorted by avg_p
    cal_df2 = cal_df.copy()
    cal_df2["avg_p"] = pd.to_numeric(cal_df2["avg_p"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    cal_df2["empirical"] = pd.to_numeric(cal_df2["empirical"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    cal_df2["n"] = pd.to_numeric(cal_df2["n"], errors="coerce").fillna(0).astype(int)
    cal_df2 = cal_df2.sort_values(by=["avg_p", "bin_lo"]).reset_index(drop=True)

    x = cal_df2["avg_p"].astype(float).tolist()
    y = cal_df2["empirical"].astype(float).tolist()
    n = cal_df2["n"].astype(int).tolist()

    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name=series_name or "empirical",
            text=[f"n={nn}" for nn in n],
        )
    )

    # Diagonal ideal calibration
    fig.add_trace(
        go.Scatter(
            x=[0.0, 1.0],
            y=[0.0, 1.0],
            mode="lines",
            name="ideal",
            line=dict(dash="dash"),
            showlegend=True,
        )
    )

    fig.update_layout(
        title=title,
        xaxis_title="Mean predicted probability (bin)",
        yaxis_title="Empirical success rate (bin)",
        template="plotly_white",
        width=1100,
        height=600,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(fig.to_html(full_html=True, include_plotlyjs="cdn"), encoding="utf-8")


def compute_calibration_metrics_from_df(
    df: pd.DataFrame,
    *,
    p_col: str,
    y_col: str,
    n_bins: int,
) -> CalibrationMetrics:
    """
    Convenience helper: compute Brier + ECE directly from a dataframe.
    """
    if df.empty:
        return CalibrationMetrics(brier=0.0, ece=0.0)

    p = pd.to_numeric(df[p_col], errors="coerce").fillna(0.0).clip(0.0, 1.0).to_numpy(dtype=float)
    y = pd.to_numeric(df[y_col], errors="coerce").fillna(0).to_numpy(dtype=int)

    return CalibrationMetrics(
        brier=brier_score(y, p),
        ece=expected_calibration_error(y, p, int(n_bins)),
    )
