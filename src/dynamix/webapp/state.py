# ------------------------
# src/dynamix/webapp/state.py
# ------------------------
"""
Project-status reader for the GUI (G2.1).

Pure, Streamlit-free helpers that answer "where am I in the workflow?": how many draws exist and
the last draw date; whether a training run (StatGrid) exists; whether a forecast has been made;
and whether the optional model / MILP dependencies are importable. The GUI uses this for the
sidebar status panel, the Home "next step", and the guardrails that prevent the manual's common
errors.

All functions take explicit paths (so they are testable over temp dirs); ``read_project_status``
fills in the real defaults from :mod:`dynamix.constants`, anchored to the repo root — the same
place the CLIs read/write when launched from the repo root.
"""
from __future__ import annotations

import csv
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


def _module_available(name: str) -> bool:
    """True if an import spec exists for ``name`` (does not import the module)."""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def data_status(data_file: Path) -> Tuple[bool, int, Optional[str]]:
    """Return ``(exists, n_draws, last_date)`` for a DATA.csv file.

    ``n_draws`` excludes the header; ``last_date`` is the first cell of the last non-empty row.
    A missing file returns ``(False, 0, None)``; an unreadable/empty file returns ``(True, 0, None)``.
    """
    data_file = Path(data_file)
    if not data_file.exists():
        return (False, 0, None)
    try:
        with data_file.open("r", encoding="utf-8", newline="") as f:
            rows = [r for r in csv.reader(f) if any((c or "").strip() for c in r)]
    except Exception:
        return (True, 0, None)
    if len(rows) <= 1:
        return (True, 0, None)
    data_rows = rows[1:]
    last = data_rows[-1]
    last_date = last[0] if last else None
    return (True, len(data_rows), last_date)


def latest_statgrid_run(exports_dir: Path) -> Tuple[Optional[str], Optional[float]]:
    """Return ``(run_id, mtime)`` of the newest StatGrid run, or ``(None, None)``.

    "Newest" is the last run folder by sorted name — matching
    ``orchestrator._resolve_latest_grid_run_id`` / ``opt_data.list_run_ids`` semantics.
    """
    exports_dir = Path(exports_dir)
    if not exports_dir.exists():
        return (None, None)
    runs = sorted(p for p in exports_dir.iterdir() if p.is_dir())
    if not runs:
        return (None, None)
    latest = runs[-1]
    return (latest.name, latest.stat().st_mtime)


def latest_forecast(state_dir: Path) -> Tuple[Optional[Path], Optional[float]]:
    """Return ``(path, mtime)`` of the most recent ``forecast.json`` under ``state_dir/*/``."""
    state_dir = Path(state_dir)
    if not state_dir.exists():
        return (None, None)
    candidates = list(state_dir.glob("*/forecast.json"))
    if not candidates:
        return (None, None)
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return (latest, latest.stat().st_mtime)


def deps_installed() -> Tuple[bool, bool]:
    """Return ``(models_installed, milp_installed)``.

    ``models_installed`` is True if *any* forecasting-model dependency (torch / darts / chaospy)
    is importable — i.e. at least one model family can produce forecasts. ``milp_installed`` is
    True if ``pulp`` is importable.
    """
    models = any(_module_available(m) for m in ("torch", "darts", "chaospy"))
    milp = _module_available("pulp")
    return (models, milp)


@dataclass(frozen=True)
class ProjectStatus:
    data_exists: bool
    data_rows: int
    data_last_date: Optional[str]
    statgrid_run: Optional[str]
    statgrid_mtime: Optional[float]
    forecast_path: Optional[Path]
    forecast_mtime: Optional[float]
    models_installed: bool
    milp_installed: bool
    device_label: str = "CPU"

    @property
    def has_training(self) -> bool:
        return self.statgrid_run is not None

    @property
    def has_forecast(self) -> bool:
        return self.forecast_path is not None

    def next_step(self) -> str:
        """One plain-language sentence: what the user should do next."""
        if not self.data_exists or self.data_rows == 0:
            return "Add your draws on the Data page (Step 1)."
        if not self.has_training:
            return "Do a full training on the Train page (Step 2)."
        if not self.has_forecast:
            return "Make your first forecast on the Forecast page (Step 3)."
        return "You're set. Add each new draw, then forecast again (Steps 4-5)."


def _defaults() -> Tuple[Path, Path, Path]:
    from dynamix import constants as C  # local import keeps module load light

    reports = Path(C.OUTPUT_REPORTS_DIR)
    return (
        Path(C.DATA_FILE),
        reports / "Exports" / "StatGrid",
        reports / "Optimization" / "State",
    )


def read_project_status(
    *,
    data_file: Optional[Path] = None,
    exports_dir: Optional[Path] = None,
    state_dir: Optional[Path] = None,
) -> ProjectStatus:
    """Assemble the full :class:`ProjectStatus`. Paths default to the real repo-anchored locations."""
    d_def, e_def, s_def = _defaults()
    data_file = Path(data_file) if data_file is not None else d_def
    exports_dir = Path(exports_dir) if exports_dir is not None else e_def
    state_dir = Path(state_dir) if state_dir is not None else s_def

    exists, rows, last = data_status(data_file)
    run, run_mtime = latest_statgrid_run(exports_dir)
    fpath, fmtime = latest_forecast(state_dir)
    models, milp = deps_installed()
    try:
        from dynamix import device as _device

        device_label = _device.describe_device()
    except Exception:
        device_label = "CPU"
    return ProjectStatus(
        data_exists=exists,
        data_rows=rows,
        data_last_date=last,
        statgrid_run=run,
        statgrid_mtime=run_mtime,
        forecast_path=fpath,
        forecast_mtime=fmtime,
        models_installed=models,
        milp_installed=milp,
        device_label=device_label,
    )
