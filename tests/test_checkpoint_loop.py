# -----------------------
# tests/state_integrity/test_checkpoint_loop.py
# -----------------------
"""
tests/test_checkpoint_loop.py

Detects suspicious checkpoint sequences where Stat.py appears to "fast-forward"
and save many checkpoints without actually processing new steps.

It validates:
- checkpoint schema keys
- filename step matches checkpoint['last_step']
- overlay_dist sum is consistent with last_step and start_time_offset
- overlay_dist sum strictly increases across checkpoints
- total hit counts never decrease across checkpoints

Run:
    python run_tests.py --module checkpoint --verbose
or:
    python -m unittest -v tests.test_checkpoint_loop
"""

from __future__ import annotations

import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# Project-root import pattern used by your suite
PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    import Stat  # type: ignore
except Exception as e:  # pragma: no cover
    Stat = None  # type: ignore
    _STAT_IMPORT_ERROR = e
else:
    _STAT_IMPORT_ERROR = None


_STEP_RE = re.compile(r"stats_checkpoint_step_(\d+)\.pkl$")


@dataclass(frozen=True)
class CheckpointInfo:
    step_in_name: int
    path: Path


def _discover_checkpoints(stats_dir: Path) -> List[CheckpointInfo]:
    items: List[CheckpointInfo] = []
    for p in stats_dir.glob("stats_checkpoint_step_*.pkl"):
        m = _STEP_RE.search(p.name)
        if not m:
            continue
        items.append(CheckpointInfo(step_in_name=int(m.group(1)), path=p))
    items.sort(key=lambda x: x.step_in_name)
    return items


def _total_hits(state: Dict[str, Any]) -> int:
    """
    Sum all hits across all rounding modes, models, and TS keys.

    Expected structure (as you showed):
        state['stats'][rounding][model][ts] -> int hit counter
    """
    st = state.get("stats", {})
    total = 0
    for rounding_key in st:
        for model_key in st[rounding_key]:
            for ts_key in st[rounding_key][model_key]:
                v = st[rounding_key][model_key][ts_key]
                if isinstance(v, int):
                    total += v
    return total


def _overlay_sum(state: Dict[str, Any]) -> int:
    overlay = state.get("overlay_dist", {})
    if not isinstance(overlay, dict):
        return 0
    s = 0
    for k, v in overlay.items():
        if isinstance(v, int):
            s += v
    return s


def _expected_last_step_from_overlay(state: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    """
    In most implementations:
        overlay_sum == number of processed steps
        last_step == start_time_offset + overlay_sum - 1

    But some code uses slightly different conventions (off-by-one),
    so we return both plausible expected values:
        expected_a = start_offset + overlay_sum - 1
        expected_b = start_offset + overlay_sum
    """
    start_offset = state.get("start_time_offset", 0)
    if not isinstance(start_offset, int):
        return (None, None)

    osum = _overlay_sum(state)
    expected_a = start_offset + osum - 1
    expected_b = start_offset + osum
    return (expected_a, expected_b)


class TestCheckpointLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if Stat is None:
            raise unittest.SkipTest(f"Stat import failed: {_STAT_IMPORT_ERROR}")

        # Prefer Constants if available, otherwise use default Output/Stats under project root
        stats_dir = PROJECT_ROOT / "Output" / "Stats"
        try:
            import Constants as C  # type: ignore
            if hasattr(C, "OUTPUT_DIR"):
                # If OUTPUT_DIR exists, attempt OUTPUT_DIR/Stats
                cand = Path(getattr(C, "OUTPUT_DIR")) / "Stats"
                if cand.exists():
                    stats_dir = cand
            if hasattr(C, "OUTPUT_STATS_DIR"):
                cand2 = Path(getattr(C, "OUTPUT_STATS_DIR"))
                if cand2.exists():
                    stats_dir = cand2
        except Exception:
            pass

        cls.stats_dir = stats_dir
        cls.checkpoints = _discover_checkpoints(stats_dir)

        if len(cls.checkpoints) == 0:
            raise unittest.SkipTest(f"No checkpoints found in: {stats_dir}")

    def test_checkpoint_schema_has_expected_keys(self) -> None:
        # Only sample a few to keep test fast
        sample = self.checkpoints[:3] + self.checkpoints[-3:] if len(self.checkpoints) > 6 else self.checkpoints

        for cp in sample:
            with self.subTest(file=str(cp.path)):
                state = Stat.load_checkpoint(cp.path)  # type: ignore[attr-defined]
                self.assertIsInstance(state, dict)

                for k in ["stats", "hit_dist", "overlay_dist", "last_step"]:
                    self.assertIn(k, state, f"Missing key '{k}' in {cp.path.name}")

                self.assertIsInstance(state["stats"], dict)
                self.assertIsInstance(state["hit_dist"], dict)
                self.assertIsInstance(state["overlay_dist"], dict)
                self.assertIsInstance(state["last_step"], int)

    def test_filename_step_matches_last_step(self) -> None:
        for cp in self.checkpoints:
            with self.subTest(file=str(cp.path)):
                state = Stat.load_checkpoint(cp.path)  # type: ignore[attr-defined]
                last_step = state.get("last_step")
                self.assertEqual(
                    cp.step_in_name,
                    last_step,
                    f"Filename step {cp.step_in_name} != checkpoint last_step {last_step} for {cp.path.name}",
                )

    def test_overlay_sum_consistent_with_last_step(self) -> None:
        """
        If last_step rises but overlay_sum does not track it, it indicates the loop
        saved checkpoints without actually processing steps.
        """
        for cp in self.checkpoints:
            with self.subTest(file=str(cp.path)):
                state = Stat.load_checkpoint(cp.path)  # type: ignore[attr-defined]
                last_step = state.get("last_step")
                osum = _overlay_sum(state)

                self.assertGreaterEqual(osum, 0, "overlay_sum should be >= 0")

                expected_a, expected_b = _expected_last_step_from_overlay(state)
                # If expected values are not computed, skip the strict check
                if expected_a is None or expected_b is None:
                    continue

                # Accept either convention
                self.assertIn(
                    last_step,
                    {expected_a, expected_b},
                    (
                        f"Inconsistent overlay_sum vs last_step in {cp.path.name}. "
                        f"start_time_offset={state.get('start_time_offset')} overlay_sum={osum} "
                        f"last_step={last_step} expected_one_of={expected_a, expected_b}"
                    ),
                )

    def test_overlay_sum_strictly_increases_across_checkpoints(self) -> None:
        """
        The sum of overlay_dist counts equals the number of evaluated steps.
        It must strictly increase as last_step increases.
        """
        prev_last: Optional[int] = None
        prev_osum: Optional[int] = None

        for cp in self.checkpoints:
            state = Stat.load_checkpoint(cp.path)  # type: ignore[attr-defined]
            last_step = int(state.get("last_step", -1))
            osum = _overlay_sum(state)

            if prev_last is not None:
                self.assertGreater(last_step, prev_last, "Checkpoints are not sorted by last_step")
                self.assertGreater(
                    osum,
                    prev_osum if prev_osum is not None else -1,
                    (
                        "overlay_sum did not strictly increase. This strongly suggests Stat.py "
                        "saved checkpoints without processing new steps.\n"
                        f"prev: last_step={prev_last}, overlay_sum={prev_osum}\n"
                        f"curr: last_step={last_step}, overlay_sum={osum}\n"
                        f"file: {cp.path.name}"
                    ),
                )

            prev_last = last_step
            prev_osum = osum

    def test_total_hits_never_decrease_across_checkpoints(self) -> None:
        prev_hits: Optional[int] = None
        prev_step: Optional[int] = None

        for cp in self.checkpoints:
            state = Stat.load_checkpoint(cp.path)  # type: ignore[attr-defined]
            hits = _total_hits(state)

            if prev_hits is not None:
                self.assertGreater(cp.step_in_name, prev_step if prev_step is not None else -1)
                self.assertGreaterEqual(
                    hits,
                    prev_hits,
                    (
                        "Total hits decreased across checkpoints, which should not happen.\n"
                        f"prev: step={prev_step}, hits={prev_hits}\n"
                        f"curr: step={cp.step_in_name}, hits={hits}\n"
                        f"file: {cp.path.name}"
                    ),
                )

            prev_hits = hits
            prev_step = cp.step_in_name


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
