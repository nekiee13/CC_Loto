# -----------------------
# tests/webapp/test_runner.py
# -----------------------
"""
G4.1 — the job runner (`dynamix.webapp.runner`): build CLI commands, run them, stream logs, stop.

All process logic lives here (Streamlit-free) so it is unit-testable and the UI stays thin. These
tests pin the exact argv the GUI will run (so GUI == CLI), the progress parser, the log tail, and a
real start/stream/stop cycle using a trivial `python -c` job (no ML deps).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from dynamix.webapp import runner


class TestBuildCommand(unittest.TestCase):
    def _py(self) -> str:
        return sys.executable

    def test_train_full(self) -> None:
        cmd = runner.build_command("train_full", {}, python=self._py())
        self.assertEqual(cmd, [self._py(), "-u", "-m", "dynamix.stat", "--statgrid-export", "full"])

    def test_train_full_with_dedupe(self) -> None:
        cmd = runner.build_command("train_full", {"dedupe": True}, python=self._py())
        self.assertEqual(
            cmd,
            [self._py(), "-u", "-m", "dynamix.stat", "--statgrid-export", "full", "--statgrid-dedupe"],
        )

    def test_train_incremental(self) -> None:
        cmd = runner.build_command("train_incremental", {}, python=self._py())
        self.assertEqual(
            cmd,
            [self._py(), "-u", "-m", "dynamix.stat", "--resume", "latest", "--statgrid-export", "incremental"],
        )

    def test_forecast_defaults(self) -> None:
        cmd = runner.build_command("forecast", {}, python=self._py())
        self.assertEqual(
            cmd,
            [self._py(), "-u", "-m", "dynamix.entrypoints.orchestrator", "--action", "forecast", "--run-id", "latest"],
        )

    def test_forecast_with_options(self) -> None:
        cmd = runner.build_command("forecast", {"run_id": "r1", "max_tickets": 5, "seed": 123}, python=self._py())
        self.assertEqual(
            cmd,
            [self._py(), "-u", "-m", "dynamix.entrypoints.orchestrator",
             "--action", "forecast", "--run-id", "r1", "--max-tickets", "5", "--seed", "123"],
        )

    def test_unknown_action_raises(self) -> None:
        with self.assertRaises(ValueError):
            runner.build_command("nope", {}, python=self._py())


class TestProgressAndTail(unittest.TestCase):
    def test_parse_progress_prefers_progress_lines(self) -> None:
        text = (
            "[STAT] Dataset observations: 562\n"
            "[STAT] Full export rebuild progress: 120/512 (23.4%)\n"
            "some other line\n"
        )
        self.assertEqual(runner.parse_progress(text), (120, 512))

    def test_parse_progress_none_when_absent(self) -> None:
        self.assertIsNone(runner.parse_progress("no numbers here\njust text\n"))

    def test_parse_progress_tracks_a_growing_log(self) -> None:
        # As the CLI logs more "Step X/Y" lines, the parsed fraction increases (bar advances).
        early = "[STAT] Step 1/512 elapsed=1s\n"
        later = early + "[STAT] Step 128/512 elapsed=30s\n[STAT] Step 256/512 elapsed=60s\n"
        e = runner.parse_progress(early)
        l = runner.parse_progress(later)
        self.assertEqual(e, (1, 512))
        self.assertEqual(l, (256, 512))
        self.assertLess(e[0] / e[1], l[0] / l[1])

    def test_parse_progress_reads_optimize_and_step_formats(self) -> None:
        self.assertEqual(runner.parse_progress("[OPT][greedy] progress: 40/120 (33.3%) | eta=0:12"), (40, 120))
        self.assertEqual(runner.parse_progress("[STAT] Step 7/512 | 1.4%"), (7, 512))

    def test_parse_eta(self) -> None:
        self.assertEqual(runner.parse_eta("progress: 40/120 | elapsed=0:30 | eta=0:12"), "0:12")
        self.assertEqual(
            runner.parse_eta("eta=1:02:03\nlater eta=0:00:45"), "0:00:45"
        )  # last one wins
        self.assertIsNone(runner.parse_eta("no eta here"))

    def test_tail_returns_last_n_lines(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "log.txt"
            p.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
            self.assertEqual(runner.tail(p, 2), ["d", "e"])
            self.assertEqual(runner.tail(p, 99), ["a", "b", "c", "d", "e"])
            self.assertEqual(runner.tail(Path(td) / "missing.txt", 3), [])


class TestJobView(unittest.TestCase):
    def _finished_job(self, code: int, out: str) -> "runner.Job":
        td = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(td, ignore_errors=True))
        log = Path(td) / "job.log"
        job = runner.start_job(
            [sys.executable, "-c", f"import sys; print({out!r}); sys.exit({code})"], log
        )
        job.proc.wait(timeout=30)
        return job

    def test_view_done(self) -> None:
        v = runner.job_view(self._finished_job(0, "[STAT] progress: 2/2 (100%)"))
        self.assertEqual(v["state"], "done")
        self.assertEqual(v["progress"], (2, 2))
        self.assertIn("progress: 2/2", v["text"])

    def test_view_failed(self) -> None:
        v = runner.job_view(self._finished_job(1, "boom"))
        self.assertEqual(v["state"], "failed")
        self.assertEqual(v["returncode"], 1)

    def test_view_stopped_flag(self) -> None:
        v = runner.job_view(self._finished_job(0, "x"), stopped=True)
        self.assertEqual(v["state"], "stopped")


class TestProcessLifecycle(unittest.TestCase):
    def test_start_streams_to_log_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "job.log"
            job = runner.start_job([sys.executable, "-c", "print('hello-from-job')"], log)
            job.proc.wait(timeout=30)
            self.assertFalse(runner.is_running(job))
            self.assertEqual(runner.returncode(job), 0)
            self.assertIn("hello-from-job", log.read_text(encoding="utf-8"))

    def test_stop_terminates_running_job(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "job.log"
            job = runner.start_job([sys.executable, "-c", "import time; time.sleep(30)"], log)
            self.assertTrue(runner.is_running(job))
            runner.stop_job(job)
            job.proc.wait(timeout=10)
            self.assertFalse(runner.is_running(job))


if __name__ == "__main__":
    unittest.main()
