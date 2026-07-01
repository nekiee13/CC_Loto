# ------------------------
# src/dynamix/webapp/optimize_results.py
# ------------------------
"""
Optimizer summary / scoreboard parser for the GUI (V1.1).

Turns the optimizer's ``summary_current.json`` (written by
``opt_diagnostics.write_final_summary`` under ``Output/Reports/Optimization/``) into tidy
per-optimizer rows with an EDGE / no-edge verdict — the E1 honest scoreboard, made click-friendly.

Pure and Streamlit-free. Missing / malformed files degrade to an empty view instead of raising.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SummaryView:
    ok: bool
    error: Optional[str] = None
    generated_at: Optional[str] = None
    opt_run_id: Optional[str] = None
    grid_run_id: Optional[str] = None
    scoreboard: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    baseline: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def scoreboard_rows(self) -> List[Dict[str, Any]]:
        """One tidy dict per optimizer, sorted by name, with a verdict."""
        rows: List[Dict[str, Any]] = []
        for opt, m in sorted(self.scoreboard.items()):
            if not isinstance(m, dict):
                continue
            edge = _f(m.get("edge_eur"))
            rows.append({
                "Optimizer": str(opt),
                ">=H rate": round(_f(m.get("realized_ge_H_rate")), 4),
                "base rate": round(_f(m.get("base_rate_ge_H")), 4),
                "net_eur": round(_f(m.get("net_eur")), 2),
                "baseline_eur": round(_f(m.get("baseline_net_eur")), 2),
                "edge_eur": round(edge, 2),
                "q_any ECE": round(_f(m.get("qany_ece")), 4),
                "verdict": "EDGE" if edge > 0 else "no edge",
            })
        return rows

    def any_edge(self) -> bool:
        return any(_f(m.get("edge_eur")) > 0 for m in self.scoreboard.values() if isinstance(m, dict))


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_summary(path: Path) -> SummaryView:
    """Load and parse an optimizer ``summary_current.json``. Never raises."""
    path = Path(path)
    if not path.exists():
        return SummaryView(ok=False, error=f"{path.name} not found. Run an optimize first.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return SummaryView(ok=False, error=f"Could not read summary: {e!r}")
    if not isinstance(data, dict):
        return SummaryView(ok=False, error="Summary file is not in the expected format.")

    scoreboard = data.get("scoreboard")
    if not isinstance(scoreboard, dict):
        scoreboard = {}
    baseline = data.get("baseline")
    if not isinstance(baseline, dict):
        baseline = {}

    return SummaryView(
        ok=True,
        error=None,
        generated_at=data.get("generated_at"),
        opt_run_id=data.get("opt_run_id"),
        grid_run_id=data.get("grid_run_id"),
        scoreboard=scoreboard,
        baseline=baseline,
        raw=data,
    )


def _default_opt_dir() -> Path:
    from dynamix import constants as C

    return Path(C.OUTPUT_REPORTS_DIR) / "Optimization"


def latest_summary(opt_dir: Optional[Path] = None) -> Optional[Path]:
    """Path to the newest optimizer summary, or ``None``.

    Prefers ``summary_current.json`` (always the latest); otherwise the newest ``summary_*.json``
    history file by mtime.
    """
    opt_dir = Path(opt_dir) if opt_dir is not None else _default_opt_dir()
    if not opt_dir.exists():
        return None
    current = opt_dir / "summary_current.json"
    if current.exists():
        return current
    history = list(opt_dir.glob("summary_*.json"))
    if not history:
        return None
    return max(history, key=lambda p: p.stat().st_mtime)
