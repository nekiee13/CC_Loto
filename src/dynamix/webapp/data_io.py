# ------------------------
# src/dynamix/webapp/data_io.py
# ------------------------
"""
DATA.csv read / validate / safe-append helpers for the GUI (G3.1).

Pure and Streamlit-free. These enforce the data contract before a row can reach ``stat.py`` — the
top cause of "Data load error" — and append atomically so the file is never left half-written.

Contract (from ``dynamix.constants``): header ``Date,TS_1..TS_7``; date format ``%d/%m/%Y``;
exactly 7 whole numbers per row. No per-position value bounds are defined, so values are only
required to be integers.
"""
from __future__ import annotations

import csv
import io
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


def _ts_columns() -> List[str]:
    from dynamix import constants as C

    return list(getattr(C, "TS_COLUMNS", [f"TS_{i}" for i in range(1, 8)]))


def _date_col() -> str:
    from dynamix import constants as C

    return str(getattr(C, "DATE_COL", "Date"))


def _date_format() -> str:
    from dynamix import constants as C

    return str(getattr(C, "DATE_FORMAT", "%d/%m/%Y"))


def expected_header() -> List[str]:
    """The canonical DATA.csv header: ``[Date, TS_1..TS_7]``."""
    return [_date_col(), *_ts_columns()]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: Optional[str] = None
    date: Optional[str] = None
    values: Optional[Tuple[int, ...]] = None


def validate_row(date: str, values: Sequence[object]) -> ValidationResult:
    """Validate a single draw. Returns a :class:`ValidationResult` with a clear ``error`` if bad."""
    ncols = len(_ts_columns())
    fmt = _date_format()

    d = (date or "").strip()
    if not d:
        return ValidationResult(False, "Date is required.")
    try:
        datetime.strptime(d, fmt)
    except ValueError:
        example = datetime(2021, 3, 15).strftime(fmt)
        return ValidationResult(False, f"Date must look like {example} (format {fmt}).")

    vals = list(values)
    if len(vals) != ncols:
        return ValidationResult(False, f"Need exactly {ncols} numbers (got {len(vals)}).")

    ints: List[int] = []
    for i, v in enumerate(vals, start=1):
        s = str(v).strip()
        try:
            iv = int(s)
        except (ValueError, TypeError):
            return ValidationResult(False, f"Value {i} ('{v}') is not a whole number.")
        ints.append(iv)

    return ValidationResult(True, None, d, tuple(ints))


def read_data(path: Path) -> Tuple[List[str], List[List[str]], Optional[str]]:
    """Return ``(header, rows, error)`` for a DATA.csv file (rows exclude the header).

    A missing file yields ``([], [], "<msg>")``. A present file returns its header + non-empty rows,
    with ``error`` set to a health note if the header does not match the expected contract.
    """
    path = Path(path)
    if not path.exists():
        return ([], [], f"{path.name} not found.")
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            all_rows = [r for r in csv.reader(f) if any((c or "").strip() for c in r)]
    except Exception as e:  # noqa: BLE001
        return ([], [], f"Could not read {path.name}: {e!r}")
    if not all_rows:
        return ([], [], f"{path.name} is empty.")

    header, rows = all_rows[0], all_rows[1:]
    err: Optional[str] = None
    if header != expected_header():
        err = f"Unexpected header. Expected {expected_header()}."
    return (header, rows, err)


def append_draw(path: Path, date: str, values: Sequence[object]) -> ValidationResult:
    """Validate then atomically append a draw. Creates the file (with header) if missing.

    On invalid input the file is left untouched and the returned result carries the reason.
    """
    res = validate_row(date, values)
    if not res.ok:
        return res

    path = Path(path)
    assert res.date is not None and res.values is not None

    # Build the new row with csv quoting rules.
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow([res.date, *[str(v) for v in res.values]])
    new_line = buf.getvalue()  # already ends with "\n"

    if not path.exists():
        header_line = ",".join(expected_header()) + "\n"
        content = header_line + new_line
    else:
        existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"  # never concatenate onto the last row
        content = existing + new_line

    # Atomic replace: write to a temp file in the same dir, then os.replace.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".data_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as tf:
            tf.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    return res
