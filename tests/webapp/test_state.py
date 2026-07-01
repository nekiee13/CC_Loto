# -----------------------
# tests/webapp/test_state.py
# -----------------------
"""
G2.1 — the project-status reader (`dynamix.webapp.state`).

Pure, Streamlit-free helpers that answer "where am I in the workflow?": how many draws exist,
whether a training run (StatGrid) exists, whether a forecast has been made, and whether the
optional model/MILP deps are importable. The GUI uses this for the status panel and guardrails.
Tested over temp dirs so results are deterministic and need no torch/darts/streamlit.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from dynamix.webapp import state


class TestState(unittest.TestCase):
    def _tmp(self) -> Path:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_data_status_counts_rows_and_last_date(self) -> None:
        root = self._tmp()
        dcsv = root / "DATA.csv"
        dcsv.write_text(
            "Date,TS_1,TS_2,TS_3,TS_4,TS_5,TS_6,TS_7\n"
            "01/01/2020,1,2,3,4,5,6,7\n"
            "02/01/2020,7,6,5,4,3,2,1\n",
            encoding="utf-8",
        )
        exists, rows, last = state.data_status(dcsv)
        self.assertTrue(exists)
        self.assertEqual(rows, 2)
        self.assertEqual(last, "02/01/2020")

    def test_data_status_missing_file(self) -> None:
        root = self._tmp()
        self.assertEqual(state.data_status(root / "nope.csv"), (False, 0, None))

    def test_latest_statgrid_run_by_name(self) -> None:
        root = self._tmp()
        exp = root / "StatGrid"
        (exp / "statgrid_A").mkdir(parents=True)
        (exp / "statgrid_B").mkdir()
        run, mtime = state.latest_statgrid_run(exp)
        self.assertEqual(run, "statgrid_B", "latest = last by sorted name (matches orchestrator)")
        self.assertIsInstance(mtime, float)
        self.assertEqual(state.latest_statgrid_run(root / "none"), (None, None))

    def test_latest_forecast_by_mtime(self) -> None:
        root = self._tmp()
        sd = root / "State"
        a = sd / "opt_A"; a.mkdir(parents=True); (a / "forecast.json").write_text("{}")
        b = sd / "opt_B"; b.mkdir(); (b / "forecast.json").write_text("{}")
        os.utime(a / "forecast.json", (1000, 1000))
        os.utime(b / "forecast.json", (2000, 2000))
        path, mtime = state.latest_forecast(sd)
        self.assertIsNotNone(path)
        self.assertEqual(path.parent.name, "opt_B")
        self.assertEqual(mtime, 2000)
        self.assertEqual(state.latest_forecast(root / "none"), (None, None))

    def test_deps_installed_returns_bools(self) -> None:
        models, milp = state.deps_installed()
        self.assertIsInstance(models, bool)
        self.assertIsInstance(milp, bool)

    def test_read_project_status_and_next_step(self) -> None:
        root = self._tmp()
        dcsv = root / "DATA.csv"
        dcsv.write_text("Date,TS_1\n01/01/2020,1\n", encoding="utf-8")
        exp = root / "Exports" / "StatGrid"; exp.mkdir(parents=True)
        sd = root / "Optimization" / "State"; sd.mkdir(parents=True)

        st = state.read_project_status(data_file=dcsv, exports_dir=exp, state_dir=sd)
        self.assertTrue(st.data_exists)
        self.assertEqual(st.data_rows, 1)
        self.assertFalse(st.has_training)
        self.assertFalse(st.has_forecast)
        # With data but no training, the next step is a full training.
        self.assertIn("training", st.next_step().lower())

        # state.py must be Streamlit-free (logic stays importable without the [gui] extra).
        # Scan the source rather than sys.modules, which other tests may have polluted.
        src = Path(state.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import streamlit", src)


if __name__ == "__main__":
    unittest.main()
