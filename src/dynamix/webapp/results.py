# ------------------------
# src/dynamix/webapp/results.py
# ------------------------
"""
forecast.json parser for the GUI (G6.1).

Turns the raw report the orchestrator writes (``--action forecast``) into a tidy, friendly view:
up-to-5 tickets (TS_1..TS_7 per ticket) with per-ticket ``q``, plus metadata (run id, timestamp,
``q_any``). Pure and Streamlit-free; missing / malformed / partial files degrade to an "empty"
view instead of raising.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ts_columns() -> List[str]:
    try:
        from dynamix import constants as C

        cols = list(getattr(C, "TS_COLUMNS", []) or [])
        if cols:
            return cols
    except Exception:
        pass
    return [f"TS_{i}" for i in range(1, 8)]


@dataclass
class ForecastView:
    ok: bool
    error: Optional[str] = None
    tickets: List[List[int]] = field(default_factory=list)
    q_per_ticket: List[float] = field(default_factory=list)
    q_any: Optional[float] = None
    generated_at: Optional[str] = None
    grid_run_id: Optional[str] = None
    opt_run_id: Optional[str] = None
    tickets_count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    def ticket_rows(self, ts_columns: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """One dict per ticket: ``{Ticket, TS_1..TS_7, q}`` — ready for a table."""
        cols = ts_columns or _ts_columns()
        rows: List[Dict[str, Any]] = []
        for i, tk in enumerate(self.tickets, start=1):
            row: Dict[str, Any] = {"Ticket": i}
            for j, name in enumerate(cols):
                row[name] = int(tk[j]) if j < len(tk) else None
            if i - 1 < len(self.q_per_ticket):
                row["q"] = round(float(self.q_per_ticket[i - 1]), 6)
            rows.append(row)
        return rows


def load_forecast(path: Path) -> ForecastView:
    """Load and parse a ``forecast.json``. Never raises; see :class:`ForecastView`."""
    path = Path(path)
    if not path.exists():
        return ForecastView(ok=False, error=f"{path.name} not found. Make a forecast first.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return ForecastView(ok=False, error=f"Could not read forecast: {e!r}")
    if not isinstance(data, dict):
        return ForecastView(ok=False, error="Forecast file is not in the expected format.")

    raw_tickets = data.get("tickets") or []
    tickets: List[List[int]] = []
    for t in raw_tickets:
        try:
            tickets.append([int(x) for x in t])
        except (TypeError, ValueError):
            continue

    q_per = data.get("q_per_ticket") or []
    try:
        q_per = [float(x) for x in q_per]
    except (TypeError, ValueError):
        q_per = []

    q_any = data.get("q_any")
    try:
        q_any = float(q_any) if q_any is not None else None
    except (TypeError, ValueError):
        q_any = None

    return ForecastView(
        ok=True,
        error=None,
        tickets=tickets,
        q_per_ticket=q_per,
        q_any=q_any,
        generated_at=data.get("generated_at"),
        grid_run_id=data.get("grid_run_id"),
        opt_run_id=data.get("opt_run_id"),
        tickets_count=int(data.get("tickets_count", len(tickets)) or 0),
        raw=data,
    )
