# -----------------------
# opt/opt_diagnostics.py
# -----------------------
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .opt_config import OptConfig
from .opt_calibration import (
    brier_score,
    expected_calibration_error,
    calibration_table,
    reliability_plot_html,
    qany_calibration,
)


def build_strategy_scoreboard(
    diag_df: pd.DataFrame,
    *,
    baseline: Dict[str, Any] | None = None,
    n_bins: int = 10,
) -> Dict[str, Dict[str, float]]:
    """E1.4 — per-strategy honest verdict: did it beat random, and does it make money?

    For each optimizer in ``diag_df`` returns:
      - ``realized_ge_H_rate`` — fraction of EVAL draws reaching the hit threshold,
      - ``base_rate_ge_H``     — same rate for the random-ticket control (E1.2),
      - ``qany_ece`` / ``qany_brier`` — calibration of the predicted q_any (E1.3),
      - ``net_eur``            — realized net EUR (sum of per-draw profit),
      - ``baseline_net_eur``   — the control's net EUR,
      - ``edge_eur``           — ``net_eur - baseline_net_eur`` (the headline number).

    ``baseline`` is the dict from ``random_ticket_baseline`` (its ``net_eur`` and, for the base
    rate, ``best_hits_per_draw``); when absent the control terms are zero.
    """
    board: Dict[str, Dict[str, float]] = {}
    if diag_df is None or diag_df.empty:
        return board

    df = diag_df.copy()
    df["q_any"] = pd.to_numeric(df["q_any"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    df["success_ge_H"] = pd.to_numeric(df["success_ge_H"], errors="coerce").fillna(0).astype(int)
    df["profit"] = pd.to_numeric(df["profit"], errors="coerce").fillna(0.0)
    df["hit_threshold"] = pd.to_numeric(df["hit_threshold"], errors="coerce").fillna(0).astype(int)

    base = baseline or {}
    base_net = float(base.get("net_eur", 0.0))
    base_hits = [int(h) for h in base.get("best_hits_per_draw", [])]

    for opt, g in df.groupby("optimizer", dropna=False):
        H = int(g["hit_threshold"].max()) if len(g) else 0
        realized_rate = float(g["success_ge_H"].mean())
        calib = qany_calibration(
            g["q_any"].tolist(), g["success_ge_H"].tolist(), n_bins=int(n_bins)
        )
        net = float(g["profit"].sum())
        base_rate = (
            float(sum(1 for h in base_hits if h >= H) / len(base_hits)) if base_hits else 0.0
        )
        board[str(opt)] = {
            "realized_ge_H_rate": float(realized_rate),
            "base_rate_ge_H": float(base_rate),
            "qany_ece": float(calib["qany_ece"]),
            "qany_brier": float(calib["qany_brier"]),
            "net_eur": float(net),
            "baseline_net_eur": float(base_net),
            "edge_eur": float(net - base_net),
        }
    return board

def ensure_dirs(cfg: OptConfig) -> None:
    for d in [cfg.opt_dir, cfg.state_dir, cfg.diag_dir, cfg.diag_history_dir, cfg.graphs_dir]:
        d.mkdir(parents=True, exist_ok=True)

def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def write_diagnostics_current_and_history(cfg: OptConfig, opt_run_id: str, grid_run_id: str, diag_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    run_stamp = _now_stamp()

    df = pd.DataFrame(diag_rows)
    if df.empty:
        df = pd.DataFrame(columns=[
            "optimizer","dataset_index","tickets_count","tickets","q_per_ticket","q_any",
            "hit_threshold","realized_max_hits","success_ge_H","profit","arm"
        ])

    current = cfg.diag_dir / "diagnostics_current.csv"
    current.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(current, index=False, encoding="utf-8")

    hist = cfg.diag_history_dir / f"diagnostics_{opt_run_id}_{grid_run_id}_{run_stamp}.csv"
    df.to_csv(hist, index=False, encoding="utf-8")

    return df

def write_calibration_current_and_history(cfg: OptConfig, opt_run_id: str, grid_run_id: str, diag_df: pd.DataFrame) -> pd.DataFrame:
    run_stamp = _now_stamp()

    if diag_df.empty:
        cal = pd.DataFrame()
    else:
        # Portfolio-level calibration: q_any -> success_ge_H
        cal = calibration_table(
            diag_df,
            p_col="q_any",
            y_col="success_ge_H",
            n_bins=int(cfg.calibration_bins),
            by_cols=["optimizer","hit_threshold"],
        )

    current = cfg.diag_dir / "calibration_current.csv"
    cal.to_csv(current, index=False, encoding="utf-8")

    hist = cfg.diag_history_dir / f"calibration_{opt_run_id}_{grid_run_id}_{run_stamp}.csv"
    cal.to_csv(hist, index=False, encoding="utf-8")

    # Write reliability plots per optimizer/H
    if not cal.empty:
        for (opt, H), g in cal.groupby(["optimizer","hit_threshold"], dropna=False):
            out = cfg.graphs_dir / f"reliability_{str(opt)}_H{int(H)}_current.html"
            reliability_plot_html(
                g.sort_values("bin_lo").reset_index(drop=True),
                title=f"{cfg.reliability_plot_title} | optimizer={opt} | H={int(H)}",
                out_path=out,
                series_name=str(opt),
            )

    return cal

def write_final_summary(
    cfg: OptConfig,
    opt_run_id: str,
    grid_run_id: str,
    grid_fp: Dict[str, Any],
    slice_info: Dict[str, Any],
    results: Dict[str, Any],
    diag_df: pd.DataFrame,
    calib_df: pd.DataFrame,
    baseline: Dict[str, Any] | None = None,
) -> None:
    # Honest EV/ROI + calibration scoreboard (E1.4): per-strategy verdict vs. random control.
    scoreboard = build_strategy_scoreboard(
        diag_df, baseline=baseline, n_bins=int(cfg.calibration_bins)
    )

    # Calibration metrics (overall, by optimizer/H)
    metrics = {}
    if not diag_df.empty:
        diag_df2 = diag_df.copy()
        diag_df2["q_any"] = pd.to_numeric(diag_df2["q_any"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
        diag_df2["success_ge_H"] = pd.to_numeric(diag_df2["success_ge_H"], errors="coerce").fillna(0).astype(int)

        overall_brier = brier_score(diag_df2["success_ge_H"].to_numpy(), diag_df2["q_any"].to_numpy())
        overall_ece = expected_calibration_error(diag_df2["success_ge_H"].to_numpy(), diag_df2["q_any"].to_numpy(), n_bins=int(cfg.calibration_bins))
        metrics["overall"] = {"brier": float(overall_brier), "ece": float(overall_ece)}

        by = {}
        for (opt, H), g in diag_df2.groupby(["optimizer","hit_threshold"], dropna=False):
            b = brier_score(g["success_ge_H"].to_numpy(), g["q_any"].to_numpy())
            e = expected_calibration_error(g["success_ge_H"].to_numpy(), g["q_any"].to_numpy(), n_bins=int(cfg.calibration_bins))
            by[f"{opt}|H{int(H)}"] = {"brier": float(b), "ece": float(e), "n": int(len(g))}
        metrics["by_optimizer_H"] = by

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "opt_run_id": opt_run_id,
        "grid_run_id": grid_run_id,
        "code_version": cfg.code_version,
        "config_identity": cfg.config_identity(),
        "grid_fingerprint": grid_fp,
        "slice": slice_info,
        "results": results,
        "scoreboard": scoreboard,
        "baseline": baseline or {},
        "diagnostics": {
            "diagnostics_csv": str(cfg.diag_dir / "diagnostics_current.csv"),
            "calibration_csv": str(cfg.diag_dir / "calibration_current.csv"),
            "graphs_dir": str(cfg.graphs_dir),
            "n_diag_rows": int(len(diag_df)) if diag_df is not None else 0,
            "n_calibration_rows": int(len(calib_df)) if calib_df is not None else 0,
            "calibration_metrics": metrics,
        },
    }

    out = cfg.opt_dir / "summary_current.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    hist = cfg.opt_dir / f"summary_{opt_run_id}_{grid_run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    hist.write_text(json.dumps(summary, indent=2), encoding="utf-8")
