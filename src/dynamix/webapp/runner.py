# ------------------------
# src/dynamix/webapp/runner.py
# ------------------------
"""
Job runner for the GUI (G4.1): build a CLI command, run it, stream its logs, and stop it.

The GUI never reimplements pipeline logic — it runs the exact same entrypoints the User manual
documents, as subprocesses (``python -u -m <module> <flags>``, unbuffered so logs stream live).
Stdout+stderr are teed straight to a run-scoped log file; the UI tails that file. This module is
Streamlit-free and fully unit-testable.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# action -> module invoked as `python -u -m <module>`
_MODULES: Dict[str, str] = {
    "train_full": "dynamix.stat",
    "train_incremental": "dynamix.stat",
    "forecast": "dynamix.entrypoints.orchestrator",
    "optimize": "dynamix.entrypoints.orchestrator",
    "report": "dynamix.entrypoints.stat_report",
    "single_series": "dynamix.entrypoints.run_cli",
}


def _repo_root() -> Path:
    # src/dynamix/webapp/runner.py -> parents[3] == repo root
    return Path(__file__).resolve().parents[3]


def _flags_for(action: str, o: Dict[str, object]) -> List[str]:
    """Map an action + options dict to the CLI flags (one spec per action)."""
    if action == "train_full":
        flags = ["--statgrid-export", "full"]
        if o.get("dedupe"):
            flags.append("--statgrid-dedupe")
        if o.get("resume"):
            flags += ["--resume", str(o["resume"])]
        return flags

    if action == "train_incremental":
        flags = ["--resume", str(o.get("resume", "latest")), "--statgrid-export", "incremental"]
        if o.get("dedupe"):
            flags.append("--statgrid-dedupe")
        return flags

    if action == "forecast":
        flags = ["--action", "forecast", "--run-id", str(o.get("run_id", "latest"))]
        if o.get("max_tickets") is not None:
            flags += ["--max-tickets", str(int(o["max_tickets"]))]
        if o.get("seed") is not None:
            flags += ["--seed", str(int(o["seed"]))]
        return flags

    if action == "optimize":
        flags = [
            "--action", "optimize",
            "--run-id", str(o.get("run_id", "latest")),
            "--optimizer", str(o.get("optimizer", "all")),
        ]
        if o.get("seed") is not None:
            flags += ["--seed", str(int(o["seed"]))]
        return flags

    if action == "report":
        flags = ["--checkpoint", str(o.get("checkpoint", "latest"))]
        if o.get("show_multihit"):
            flags.append("--show-multihit")
        if o.get("max_per_hit") is not None:
            flags += ["--max-per-hit", str(int(o["max_per_hit"]))]
        return flags

    if action == "single_series":
        flags: List[str] = []
        if o.get("target"):
            flags += ["--target", str(o["target"])]
        if o.get("horizon") is not None:
            flags += ["--horizon", str(int(o["horizon"]))]
        if o.get("no_window"):
            flags.append("--no-window")
        elif o.get("window") is not None:
            flags += ["--window", str(int(o["window"]))]
        return flags

    raise ValueError(f"unknown action: {action!r}")


def build_command(action: str, options: Optional[Dict[str, object]] = None, *, python: Optional[str] = None) -> List[str]:
    """Build the exact argv the GUI will run for ``action``. Raises ``ValueError`` if unknown."""
    module = _MODULES.get(action)
    if module is None:
        raise ValueError(f"unknown action: {action!r}")
    py = python or sys.executable
    return [py, "-u", "-m", module, *_flags_for(action, options or {})]


@dataclass
class Job:
    proc: subprocess.Popen
    log_path: Path
    cmd: List[str]
    _logfile: object = field(default=None, repr=False)


def start_job(cmd: List[str], log_path: Path, *, cwd: Optional[Path] = None) -> Job:
    """Start ``cmd``, teeing stdout+stderr to ``log_path`` (line-buffered). Runs in its own session
    so the whole process group can be stopped."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "w", encoding="utf-8", buffering=1)
    kwargs: Dict[str, object] = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True  # new process group for clean stop
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd or _repo_root()),
        stdout=logf,
        stderr=subprocess.STDOUT,
        text=True,
        **kwargs,
    )
    return Job(proc=proc, log_path=log_path, cmd=list(cmd), _logfile=logf)


def is_running(job: Job) -> bool:
    return job.proc.poll() is None


def returncode(job: Job) -> Optional[int]:
    return job.proc.poll()


def stop_job(job: Job) -> None:
    """Terminate the job (its whole process group on POSIX), then close the log file."""
    if is_running(job):
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(job.proc.pid), signal.SIGTERM)
            else:
                job.proc.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                job.proc.terminate()
            except Exception:
                pass
    try:
        if job._logfile is not None:
            job._logfile.close()
    except Exception:
        pass


_NUM_PAIR = re.compile(r"(\d+)\s*/\s*(\d+)")


def parse_progress(text: str) -> Optional[Tuple[int, int]]:
    """Extract ``(current, total)`` progress from CLI log text.

    Prefers the last line that mentions "progress"; otherwise the last ``X/Y`` seen. Returns
    ``None`` if no numeric pair is present.
    """
    if not text:
        return None
    progress_hit: Optional[Tuple[int, int]] = None
    any_hit: Optional[Tuple[int, int]] = None
    for line in text.splitlines():
        m = None
        for m in _NUM_PAIR.finditer(line):
            pass  # keep last match on the line
        if m is None:
            continue
        pair = (int(m.group(1)), int(m.group(2)))
        any_hit = pair
        if "progress" in line.lower():
            progress_hit = pair
    return progress_hit or any_hit


def job_view(job: Job, *, stopped: bool = False, n_lines: int = 200) -> Dict[str, object]:
    """Pure view-model for the live panel: the job's state + progress + tail text.

    ``state`` is one of ``running`` | ``stopped`` | ``done`` | ``failed``. Keeping this
    Streamlit-free means the UI panel is a trivial, testable mapping over it.
    """
    running = is_running(job)
    text = "\n".join(tail(job.log_path, n_lines))
    prog = parse_progress(text)
    if running:
        state = "running"
    elif stopped:
        state = "stopped"
    else:
        state = "done" if returncode(job) == 0 else "failed"
    return {"state": state, "progress": prog, "returncode": returncode(job), "text": text}


def tail(log_path: Path, n: int) -> List[str]:
    """Return the last ``n`` lines of ``log_path`` (empty list if missing/unreadable)."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    return lines[-int(n):] if n > 0 else []
