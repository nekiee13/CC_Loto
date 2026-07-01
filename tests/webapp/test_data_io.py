# -----------------------
# tests/webapp/test_data_io.py
# -----------------------
"""
G3.1 — DATA.csv validation + safe append (`dynamix.webapp.data_io`).

Pure, Streamlit-free helpers so the GUI can add a draw without corrupting the file or letting bad
rows reach `stat.py`. Rules mirror the data contract: header `Date,TS_1..TS_7`, date format
`%d/%m/%Y`, exactly 7 whole numbers per row. Append is atomic and preserves the header; the file
must stay parseable the way `data_utils` parses it.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dynamix.webapp import data_io


class TestDataIO(unittest.TestCase):
    def _tmp(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def _seed(self, root: Path) -> Path:
        p = root / "DATA.csv"
        p.write_text(
            "Date,TS_1,TS_2,TS_3,TS_4,TS_5,TS_6,TS_7\n"
            "01/01/2020,1,2,3,4,5,6,7\n",
            encoding="utf-8",
        )
        return p

    # --- validation ---
    def test_validate_row_accepts_valid(self) -> None:
        res = data_io.validate_row("15/03/2021", [1, 2, 3, 4, 5, 6, 7])
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.values, (1, 2, 3, 4, 5, 6, 7))

    def test_validate_row_rejects_bad_date(self) -> None:
        self.assertFalse(data_io.validate_row("2021-03-15", [1, 2, 3, 4, 5, 6, 7]).ok)
        self.assertFalse(data_io.validate_row("", [1, 2, 3, 4, 5, 6, 7]).ok)

    def test_validate_row_rejects_wrong_count(self) -> None:
        self.assertFalse(data_io.validate_row("15/03/2021", [1, 2, 3]).ok)

    def test_validate_row_rejects_non_integer(self) -> None:
        self.assertFalse(data_io.validate_row("15/03/2021", [1, 2, 3, 4, 5, 6, "x"]).ok)
        self.assertFalse(data_io.validate_row("15/03/2021", [1, 2, 3, 4, 5, 6, 7.5]).ok)

    # --- append ---
    def test_append_valid_row_lands_last_and_parses(self) -> None:
        root = self._tmp()
        p = self._seed(root)
        res = data_io.append_draw(p, "02/01/2020", [7, 6, 5, 4, 3, 2, 1])
        self.assertTrue(res.ok, res.error)

        lines = p.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "Date,TS_1,TS_2,TS_3,TS_4,TS_5,TS_6,TS_7", "header preserved")
        self.assertEqual(lines[-1], "02/01/2020,7,6,5,4,3,2,1", "new row is last")

        # Stays parseable the way data_utils parses it (date format + numeric TS columns).
        df = pd.read_csv(p)
        self.assertEqual(list(df.columns), ["Date"] + [f"TS_{i}" for i in range(1, 8)])
        dt = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
        self.assertFalse(dt.isna().any(), "all dates parse under %d/%m/%Y")
        self.assertEqual(int(df.iloc[-1]["TS_1"]), 7)

    def test_append_creates_file_with_header_when_missing(self) -> None:
        root = self._tmp()
        p = root / "DATA.csv"
        res = data_io.append_draw(p, "01/01/2020", [1, 2, 3, 4, 5, 6, 7])
        self.assertTrue(res.ok, res.error)
        lines = p.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "Date,TS_1,TS_2,TS_3,TS_4,TS_5,TS_6,TS_7")
        self.assertEqual(lines[-1], "01/01/2020,1,2,3,4,5,6,7")

    def test_append_rejects_invalid_and_leaves_file_untouched(self) -> None:
        root = self._tmp()
        p = self._seed(root)
        before = p.read_text(encoding="utf-8")
        res = data_io.append_draw(p, "bad-date", [1, 2, 3, 4, 5, 6, 7])
        self.assertFalse(res.ok)
        self.assertEqual(p.read_text(encoding="utf-8"), before, "file must be unchanged on rejection")

    # --- read ---
    def test_read_data_returns_header_and_rows(self) -> None:
        root = self._tmp()
        p = self._seed(root)
        header, rows, err = data_io.read_data(p)
        self.assertIsNone(err)
        self.assertEqual(header[0], "Date")
        self.assertEqual(len(rows), 1)

    def test_read_data_missing_file(self) -> None:
        root = self._tmp()
        header, rows, err = data_io.read_data(root / "nope.csv")
        self.assertEqual(rows, [])
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()
