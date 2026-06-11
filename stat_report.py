# ------------------------
# stat_report.py
# ------------------------
"""
Utility script to print a statistics report from an existing STAT checkpoint.
Captures full output to a .txt file to prevent console truncation.

Compatible with the upgraded Stat module (src/dynamix layout).

Usage examples:
    python stat_report.py --checkpoint latest
    python stat_report.py --checkpoint Output/Stats/stats_checkpoint_step_558.pkl --show-multihit
    python stat_report.py --checkpoint 558 --max-per-hit 50
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union


# ----------------------------------------------------------------------
# sys.path bootstrapping for new layout
#   repo_root/
#     stat_report.py
#     stat.py                  (legacy)
#     src/dynamix/stat.py       (new)
# ----------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _import_project_stat_module():
    """
    Import the project's Stat module without colliding with stdlib `stat`.

    Preference:
      1) src.dynamix.stat   (new layout)
      2) stat               (legacy file at repo root), ONLY if it is our file.
    """
    # 1) New layout
    try:
        return importlib.import_module("src.dynamix.stat")
    except Exception:
        pass

    # 2) Legacy: `stat.py` in repo root (but avoid stdlib `stat`)
    try:
        mod = importlib.import_module("stat")
        mod_file = getattr(mod, "__file__", "") or ""
        try:
            mod_path = Path(mod_file).resolve()
            if mod_path.name.lower() != "stat.py":
                raise ImportError("Imported non-project 'stat' module.")
            if REPO_ROOT.resolve() not in mod_path.parents and mod_path != (REPO_ROOT / "stat.py").resolve():
                raise ImportError(f"Imported stdlib/foreign 'stat' from {mod_path}")
        except Exception as e:
            raise ImportError(f"Rejected 'stat' import ({mod_file}): {e}")
        return mod
    except Exception as e:
        raise ImportError(
            "Failed to import project Stat module. Expected 'src.dynamix.stat' "
            "or legacy 'stat.py' at repo root. Last error: "
            f"{e!r}"
        )


Stat = _import_project_stat_module()


class DualWriter:
    """Duplicate writes to both stdout and a file."""

    def __init__(self, filepath: Path) -> None:
        self.file = open(filepath, "w", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, text: str) -> None:
        self.stdout.write(text)
        self.file.write(text)

    def flush(self) -> None:
        self.stdout.flush()
        self.file.flush()

    def close(self) -> None:
        self.file.close()


# ----------------------------------------------------------------------
# Pylance-friendly path coercion
# ----------------------------------------------------------------------
_PathLikeStr = Union[str, os.PathLike[str], Path]


def _as_path(v: Any, *, default: Path) -> Path:
    """
    Convert unknown objects to Path in a type-narrowed way that satisfies Pylance.

    Accepts:
      - str
      - Path
      - os.PathLike[str]
    Otherwise returns `default`.
    """
    if isinstance(v, Path):
        return v
    if isinstance(v, str):
        return Path(v)
    # os.PathLike is not directly runtime-checkable with generics; check base protocol.
    if isinstance(v, os.PathLike):
        try:
            return Path(os.fspath(v))
        except Exception:
            return default
    return default


def _default_stats_dir() -> Path:
    """
    Resolve default stats directory from Stat module or fall back.
    """
    fallback = Path("Output") / "Stats"
    v = getattr(Stat, "DEFAULT_STATS_DIR", None)
    return _as_path(v, default=fallback)


def _find_latest_checkpoint(stats_dir: Path) -> Optional[Path]:
    """
    Support either:
      - Stat.find_latest_checkpoint(stats_dir)
    Or fallback by scanning for stats_checkpoint_step_*.pkl.
    """
    fn = getattr(Stat, "find_latest_checkpoint", None)
    if callable(fn):
        cp = fn(stats_dir)  # type: ignore[misc]
        if cp is None:
            return None
        return _as_path(cp, default=stats_dir)  # default unused if cp valid

    if not stats_dir.is_dir():
        return None
    cands = sorted(stats_dir.glob("stats_checkpoint_step_*.pkl"))
    return cands[-1] if cands else None


def _checkpoint_path(stats_dir: Path, step: int) -> Path:
    """
    Support either:
      - Stat.checkpoint_path(stats_dir, step)
    Or fallback to naming convention.
    """
    fn = getattr(Stat, "checkpoint_path", None)
    if callable(fn):
        cp = fn(stats_dir, step)  # type: ignore[misc]
        # If Stat returns something odd, fall back to convention
        fallback = stats_dir / f"stats_checkpoint_step_{int(step)}.pkl"
        return _as_path(cp, default=fallback)

    return stats_dir / f"stats_checkpoint_step_{int(step)}.pkl"


def _resolve_checkpoint_path(arg: str) -> Path:
    """
    Accepts:
      - 'latest'
      - file path to a checkpoint .pkl
      - integer index (e.g., '558') meaning stats_checkpoint_step_558.pkl in DEFAULT_STATS_DIR
    """
    stats_dir = _default_stats_dir()

    if arg == "latest":
        cp = _find_latest_checkpoint(stats_dir)
        if cp is None:
            raise FileNotFoundError(f"No checkpoints found in stats directory: {stats_dir}")
        return cp

    candidate = Path(arg)
    if candidate.is_file():
        return candidate

    if arg.isdigit():
        idx = int(arg)
        cp = _checkpoint_path(stats_dir, idx)
        if cp.is_file():
            return cp
        raise FileNotFoundError(f"Checkpoint for index {idx} not found at: {cp}")

    raise FileNotFoundError(
        f"Checkpoint argument '{arg}' is neither 'latest', an existing file, nor an integer index."
    )


def _resolve_reports_dir() -> Path:
    """
    Target directory for saved reports.

    Priority:
      1) constants.OUTPUT_REPORTS_DIR if present (via Stat.C)
      2) Output/Reports under constants.OUTPUT_DIR if present
      3) Output/Reports relative to repo root
    """
    fallback = REPO_ROOT / "Output" / "Reports"

    C = getattr(Stat, "C", None)
    if C is None:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    out_dir = _as_path(getattr(C, "OUTPUT_DIR", None), default=REPO_ROOT / "Output")
    reports_dir = _as_path(getattr(C, "OUTPUT_REPORTS_DIR", None), default=Path(out_dir) / "Reports")

    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def _make_report_path(reports_dir: Path, checkpoint_path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return reports_dir / f"report_{checkpoint_path.stem}_{ts}.txt"


def _print_report_header(*, cp_path: Path, output_txt: Path, state: Dict[str, Any]) -> None:
    print("=" * 80)
    print("[STAT-REPORT] STAT checkpoint report")
    print(f"[STAT-REPORT] Checkpoint: {cp_path}")
    print(f"[STAT-REPORT] Saved report: {output_txt}")
    print(f"[STAT-REPORT] Generated at: {datetime.now().isoformat(timespec='seconds')}")
    print("")

    tw = state.get("training_window_rounds", None)
    last_step = state.get("last_step", None)
    export_mode = state.get("export_mode", None)
    export_run_id = state.get("export_run_id", None)
    export_dir = state.get("export_dir", None)

    if any(v is not None for v in [tw, last_step, export_mode, export_run_id, export_dir]):
        print("[STAT-REPORT] Run provenance (from checkpoint, if available):")
        if last_step is not None:
            print(f"  - last_step: {last_step}")
        if tw is not None:
            print(f"  - training_window_rounds: {tw}")
        if export_mode is not None:
            print(f"  - export_mode: {export_mode}")
        if export_run_id is not None:
            print(f"  - export_run_id: {export_run_id}")
        if export_dir is not None:
            print(f"  - export_dir: {export_dir}")
        print("")

    print("=" * 80)
    print("")


def _safe_get_state_field(state: Dict[str, Any], key: str) -> Any:
    if key not in state:
        raise KeyError(f"Checkpoint payload is missing required key: {key!r}")
    return state[key]


def _load_checkpoint(cp_path: Path) -> Dict[str, Any]:
    fn = getattr(Stat, "load_checkpoint", None)
    if not callable(fn):
        raise AttributeError(
            "Stat module does not expose load_checkpoint(). "
            "Ensure src/dynamix/stat.py defines load_checkpoint(path: Path) -> dict."
        )
    state = fn(cp_path)  # type: ignore[misc]
    if not isinstance(state, dict):
        raise TypeError(f"Checkpoint load returned non-dict payload: {type(state)}")
    return state


def _print_results(stats: Any, hit_dist: Any, multi_hit: Any, overlay_dist: Any, duration: float) -> None:
    fn = getattr(Stat, "print_results", None)
    if not callable(fn):
        raise AttributeError(
            "Stat module does not expose print_results(). "
            "Ensure src/dynamix/stat.py defines print_results(stats, hit_dist, multi_hit, overlay_dist, duration)."
        )
    fn(stats, hit_dist, multi_hit, overlay_dist, duration)  # type: ignore[misc]


def _print_overlay_witness_report(
    overlay_witnesses: Any,
    *,
    max_per_hit: Optional[int],
    show_multihit: bool,
    max_multihit_candidates_per_ts: int,
) -> None:
    fn = getattr(Stat, "print_overlay_witness_report", None)
    if callable(fn):
        fn(  # type: ignore[misc]
            overlay_witnesses,
            max_per_hit=max_per_hit,
            show_multihit=show_multihit,
            max_multihit_candidates_per_ts=max_multihit_candidates_per_ts,
        )
        return

    print("[STAT-REPORT] WARNING: Stat.print_overlay_witness_report() not found. Printing raw overlay_witnesses.")
    try:
        if isinstance(overlay_witnesses, list):
            print(f"[STAT-REPORT] overlay_witnesses count: {len(overlay_witnesses)}")
            limit = int(max_per_hit) if (max_per_hit is not None and max_per_hit > 0) else 50
            for i, w in enumerate(overlay_witnesses[:limit]):
                print(f"  - {i}: {w}")
        else:
            print(f"[STAT-REPORT] overlay_witnesses: {overlay_witnesses!r}")
    except Exception as exc:
        print(f"[STAT-REPORT] Failed to print overlay_witnesses: {exc!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Print STAT report from an existing checkpoint.")
    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="Checkpoint spec: 'latest', a file path, or a numeric index.",
    )
    parser.add_argument(
        "--show-multihit",
        action="store_true",
        help="Show multi-hit details (all correct candidates per TS for each witness step).",
    )
    parser.add_argument(
        "--max-per-hit",
        type=int,
        default=0,
        help="If > 0, limit witness steps printed per hit level (3/4/5/6/7).",
    )
    parser.add_argument(
        "--max-multihit-candidates",
        type=int,
        default=20,
        help="Max candidates to print per TS when --show-multihit is enabled.",
    )
    args = parser.parse_args()

    # 1) Resolve checkpoint path
    try:
        cp_path = _resolve_checkpoint_path(args.checkpoint)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # 2) Resolve report destination
    reports_dir = _resolve_reports_dir()
    output_txt = _make_report_path(reports_dir, cp_path)

    # 3) Setup output capture
    original_stdout = sys.stdout
    dual_writer = DualWriter(output_txt)
    sys.stdout = dual_writer

    try:
        state = _load_checkpoint(cp_path)

        _print_report_header(cp_path=cp_path, output_txt=output_txt, state=state)

        stats = _safe_get_state_field(state, "stats")
        hit_dist = _safe_get_state_field(state, "hit_dist")
        multi_hit = _safe_get_state_field(state, "multi_hit")
        overlay_dist = _safe_get_state_field(state, "overlay_dist")
        duration = float(state.get("elapsed_total", 0.0))

        _print_results(stats, hit_dist, multi_hit, overlay_dist, duration)

        overlay_witnesses = state.get("overlay_witnesses", [])
        if not isinstance(overlay_witnesses, list):
            overlay_witnesses = []

        max_per_hit: Optional[int] = int(args.max_per_hit) if int(args.max_per_hit) > 0 else None

        _print_overlay_witness_report(
            overlay_witnesses,
            max_per_hit=max_per_hit,
            show_multihit=bool(args.show_multihit),
            max_multihit_candidates_per_ts=int(args.max_multihit_candidates),
        )

    except Exception as e:
        print(f"\n[STAT-REPORT] Error occurred: {e!r}")
        raise
    finally:
        sys.stdout = original_stdout
        dual_writer.close()
        print(f"[STAT-REPORT] Full report saved to: {output_txt}")


if __name__ == "__main__":
    main()
