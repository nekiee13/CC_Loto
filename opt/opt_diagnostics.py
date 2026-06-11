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
from .opt_calibration import brier_score, expected_calibration_error, calibration_table, reliability_plot_html

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
) -> None:
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
