# ------------------------
# src/dynamix/webapp/report_io.py
# ------------------------
"""
Report locator for the GUI (V2.1).

``stat_report`` writes a human-readable report to
``Output/Reports/report_<checkpoint>_<timestamp>.txt``. These pure, Streamlit-free helpers find
the newest such report and read its text so the GUI can render it. Missing dir / no report degrade
to ``None`` rather than raising.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def _default_reports_dir() -> Path:
    from dynamix import constants as C

    return Path(C.OUTPUT_REPORTS_DIR)


def latest_report(reports_dir: Optional[Path] = None) -> Optional[Path]:
    """Path to the newest ``report_*.txt`` under ``reports_dir`` (by mtime), or ``None``."""
    reports_dir = Path(reports_dir) if reports_dir is not None else _default_reports_dir()
    if not reports_dir.exists():
        return None
    reports = list(reports_dir.glob("report_*.txt"))
    if not reports:
        return None
    return max(reports, key=lambda p: p.stat().st_mtime)


def read_report(path: Optional[Path]) -> Optional[str]:
    """Read a report file's text, or ``None`` if missing/unreadable."""
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
