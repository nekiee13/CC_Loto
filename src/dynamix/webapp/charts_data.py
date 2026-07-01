# ------------------------
# src/dynamix/webapp/charts_data.py
# ------------------------
"""
Chart-data readers for the GUI (V4.1).

Pure, Streamlit-free readers that turn the optimizer's written calibration file
(``Output/Reports/Optimization/Diagnostics/calibration_current.csv``; columns: ``optimizer,
hit_threshold, bin_lo, bin_hi, n, empirical, avg_p``) into tidy frames for a reliability curve.
Missing files degrade to empty frames rather than raising.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

CALIB_COLS = ["optimizer", "hit_threshold", "bin_lo", "bin_hi", "n", "empirical", "avg_p"]
_NUMERIC = ["hit_threshold", "bin_lo", "bin_hi", "n", "empirical", "avg_p"]


def _default_diag_dir() -> Path:
    from dynamix import constants as C

    return Path(C.OUTPUT_REPORTS_DIR) / "Optimization" / "Diagnostics"


def latest_calibration(diag_dir: Optional[Path] = None) -> Optional[Path]:
    """Path to ``calibration_current.csv`` under ``diag_dir``, or ``None`` if absent."""
    diag_dir = Path(diag_dir) if diag_dir is not None else _default_diag_dir()
    p = diag_dir / "calibration_current.csv"
    return p if p.exists() else None


def load_calibration(path: Optional[Path]) -> pd.DataFrame:
    """Read the calibration CSV into a DataFrame (numeric coerced). Missing → empty frame."""
    if path is None or not Path(path).exists():
        return pd.DataFrame(columns=CALIB_COLS)
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=CALIB_COLS)
    for c in _NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def reliability_curve(
    df: pd.DataFrame, *, optimizer: Optional[str] = None, hit_threshold: Optional[int] = None
) -> pd.DataFrame:
    """Tidy ``(avg_p, empirical)`` curve for one optimizer/H (or all), sorted by ``avg_p``."""
    out = df
    if optimizer is not None and "optimizer" in out.columns:
        out = out[out["optimizer"].astype(str) == str(optimizer)]
    if hit_threshold is not None and "hit_threshold" in out.columns:
        out = out[pd.to_numeric(out["hit_threshold"], errors="coerce") == int(hit_threshold)]
    cols = [c for c in ["avg_p", "empirical"] if c in out.columns]
    if len(cols) < 2:
        return pd.DataFrame(columns=["avg_p", "empirical"])
    return out[cols].dropna().sort_values("avg_p").reset_index(drop=True)
