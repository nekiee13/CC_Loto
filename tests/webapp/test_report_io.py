# -----------------------
# tests/webapp/test_report_io.py
# -----------------------
"""
V2.1 — report locator (`dynamix.webapp.report_io`).

`stat_report` writes a human-readable report to `Output/Reports/report_<checkpoint>_<ts>.txt`.
These pure, Streamlit-free helpers find the newest such report and read its text so the GUI can
show it. Missing dir / no report degrade to None rather than raising.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from dynamix.webapp import report_io


class TestReportIO(unittest.TestCase):
    def _tmp(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_latest_report_by_mtime(self) -> None:
        d = self._tmp()
        a = d / "report_ckpt558_20260101_000000.txt"
        b = d / "report_ckpt559_20260102_000000.txt"
        a.write_text("older report", encoding="utf-8")
        b.write_text("newer report", encoding="utf-8")
        os.utime(a, (1000, 1000))
        os.utime(b, (2000, 2000))
        found = report_io.latest_report(reports_dir=d)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, b.name)

    def test_latest_report_none_when_absent(self) -> None:
        self.assertIsNone(report_io.latest_report(reports_dir=self._tmp()))
        self.assertIsNone(report_io.latest_report(reports_dir=self._tmp() / "missing"))

    def test_latest_report_ignores_non_report_files(self) -> None:
        d = self._tmp()
        (d / "notes.txt").write_text("nope", encoding="utf-8")
        (d / "summary_current.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(report_io.latest_report(reports_dir=d))

    def test_read_report(self) -> None:
        d = self._tmp()
        p = d / "report_x_1.txt"
        p.write_text("hello report", encoding="utf-8")
        self.assertEqual(report_io.read_report(p), "hello report")
        self.assertIsNone(report_io.read_report(d / "nope.txt"))


if __name__ == "__main__":
    unittest.main()
