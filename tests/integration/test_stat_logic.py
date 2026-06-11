# ------------------------
# tests/integration/test_stat_logic.py
# ------------------------
"""
Tests for project Stat logic (rounding, aggregation, overlay).

Key requirements:
- DO NOT accidentally import Python stdlib module `stat`.
- Import project "stat logic" module robustly across layouts/renames:
    - legacy root modules (Stat.py / stat.py)
    - src/ layouts (package/module moved)
    - renamed module files (stat_logic.py, stat_core.py, etc.)

Assumes upgraded signature:
  update_stats_for_step(..., dataset_index=<int>, step_date=<pd.Timestamp>)
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar, cast

try:
    from typing import TypeGuard  # Python 3.10+
except ImportError:  # pragma: no cover
    from typing_extensions import TypeGuard  # type: ignore

import pandas as pd


# ----------------------------------------------------------------------
# Import bootstrapping (layout-agnostic)
# ----------------------------------------------------------------------
def _bootstrap_import_paths() -> Path:
    """
    Ensure imports work for both:
      - legacy root-module layout: repo_root/Stat.py or repo_root/stat.py
      - src layout: repo_root/src/<pkg>/...
    File location:
      repo_root/tests/integration/test_stat_logic.py
    """
    repo_root = Path(__file__).resolve().parents[2]
    src_dir = repo_root / "src"

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    return repo_root


REPO_ROOT = _bootstrap_import_paths()


# ----------------------------------------------------------------------
# Robust module resolution
# ----------------------------------------------------------------------
def _looks_like_project_stat(mod: ModuleType, repo_root: Path) -> bool:
    """
    Accept only modules that:
      - define required attributes, and
      - are sourced from inside this repo (not stdlib/site-packages).
    """
    required = ("RoundingMode", "apply_round")
    if not all(hasattr(mod, r) for r in required):
        return False

    origin = getattr(mod, "__file__", "") or ""
    # Many stdlib modules have no __file__ or are outside repo_root
    try:
        origin_path = Path(origin).resolve()
    except Exception:
        return False

    try:
        repo_root_res = repo_root.resolve()
        # origin must be within repo root
        origin_path.relative_to(repo_root_res)
        return True
    except Exception:
        return False


def _import_by_name_candidates(names: Sequence[str], repo_root: Path) -> Optional[ModuleType]:
    """
    Try importing by module name. Reject wrong modules (stdlib stat, etc.).
    """
    last_err: Optional[BaseException] = None
    for name in names:
        try:
            mod = importlib.import_module(name)
            if isinstance(mod, ModuleType) and _looks_like_project_stat(mod, repo_root):
                return mod
        except Exception as e:  # pragma: no cover
            last_err = e

    return None


def _import_by_filesystem_search(repo_root: Path) -> Optional[ModuleType]:
    """
    Last-resort: search repo for likely stat module files and load them directly.
    We then "accept" the first loaded module that has required attributes.
    """
    # Search order: most likely names first
    patterns = [
        "Stat.py",
        "stat.py",
        "stat_logic.py",
        "stat_core.py",
        "*Stat*.py",
        "*stat*.py",
    ]

    # Gather candidate files with deterministic order
    seen: set[Path] = set()
    candidates: List[Path] = []
    for pat in patterns:
        for p in repo_root.rglob(pat):
            if p.is_file() and p.suffix == ".py":
                rp = p.resolve()
                if rp not in seen:
                    seen.add(rp)
                    candidates.append(rp)

    # Prefer shallower paths first (often root-level or src/<pkg>/...)
    candidates.sort(key=lambda p: (len(p.parts), str(p).lower()))

    for idx, py_path in enumerate(candidates):
        # Create unique module name so we don't collide in sys.modules
        mod_name = f"_stat_candidate_{idx}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, py_path)
            if spec is None or spec.loader is None:
                continue

            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            if isinstance(mod, ModuleType) and _looks_like_project_stat(mod, repo_root):
                return mod
        except Exception:
            # Ignore and keep searching; some files may have heavy imports.
            continue

    return None


def _resolve_project_stat_module(repo_root: Path) -> ModuleType:
    """
    Resolve the project stat module robustly:
      1) by import name candidates
      2) by filesystem search and direct load
    """
    # Include "stat" but we will reject stdlib via _looks_like_project_stat.
    name_candidates = (
        "Stat",                 # legacy root: Stat.py
        "stat",                 # might exist as project module (reject stdlib)
        "dynamix.stat",         # older guess (may or may not exist)
        "dynamix.stat_core",
        "dynamix.stat_logic",
        "core.stat",            # common refactor target
        "core.stat_logic",
        "src.stat",             # occasional layout
    )

    mod = _import_by_name_candidates(name_candidates, repo_root)
    if mod is not None:
        return mod

    mod = _import_by_filesystem_search(repo_root)
    if mod is not None:
        return mod

    raise ImportError(
        "Could not resolve project Stat module. "
        "Tried name imports and filesystem scan for Stat/stat/stat_logic files, "
        "but none exposed required symbols (RoundingMode, apply_round)."
    )


Stat: ModuleType = _resolve_project_stat_module(REPO_ROOT)


# ----------------------------------------------------------------------
# Typed extraction + narrowing for Pylance
# ----------------------------------------------------------------------
T = TypeVar("T")
ApplyRoundFn = Callable[[float, Any], int]


def _is_list_str(x: object) -> TypeGuard[List[str]]:
    return isinstance(x, list) and all(isinstance(v, str) for v in x)


def _is_dict(x: object) -> TypeGuard[Dict[Any, Any]]:
    return isinstance(x, dict)


def _is_callable(x: object) -> TypeGuard[Callable[..., Any]]:
    return callable(x)


def _require_attr(mod: ModuleType, name: str) -> Any:
    if not hasattr(mod, name):
        raise RuntimeError(
            f"Resolved Stat module is missing required attribute: {name!r}. "
            f"Resolved module file: {getattr(mod, '__file__', None)!r}"
        )
    return getattr(mod, name)


_RoundingMode_obj = _require_attr(Stat, "RoundingMode")
_apply_round_obj = _require_attr(Stat, "apply_round")

# Optional symbols (validated per-test)
_MODEL_NAMES_obj = getattr(Stat, "MODEL_NAMES", None)
_TS_LIST_obj = getattr(Stat, "TS_LIST", None)

_init_stats_obj = getattr(Stat, "init_stats", None)
_init_multi_obj = getattr(Stat, "init_multi_hit_counts", None)
_init_hit_dist_obj = getattr(Stat, "init_hit_distribution", None)
_init_overlay_obj = getattr(Stat, "init_overlay_distribution", None)
_update_step_obj = getattr(Stat, "update_stats_for_step", None)

_ROUNDING_MODE_LABELS_obj = getattr(Stat, "ROUNDING_MODE_LABELS", None)

# Narrow required ones into typed names for Pylance.
RoundingMode = cast(Any, _RoundingMode_obj)
apply_round: ApplyRoundFn = cast(ApplyRoundFn, _apply_round_obj)


class TestStatLogic(unittest.TestCase):
    """Test suite for statistics logic."""

    def test_rounding_truncate(self) -> None:
        self.assertEqual(apply_round(3.9, RoundingMode.TRUNCATE), 3)
        self.assertEqual(apply_round(-3.9, RoundingMode.TRUNCATE), -3)
        self.assertEqual(apply_round(0.5, RoundingMode.TRUNCATE), 0)

    def test_rounding_half_up(self) -> None:
        self.assertEqual(apply_round(3.5, RoundingMode.HALF_UP), 4)
        self.assertEqual(apply_round(3.4, RoundingMode.HALF_UP), 3)
        self.assertEqual(apply_round(2.5, RoundingMode.HALF_UP), 3)

    def test_rounding_floor(self) -> None:
        self.assertEqual(apply_round(3.9, RoundingMode.FLOOR), 3)
        self.assertEqual(apply_round(-3.1, RoundingMode.FLOOR), -4)
        self.assertEqual(apply_round(0.0, RoundingMode.FLOOR), 0)

    def test_rounding_ceil(self) -> None:
        self.assertEqual(apply_round(3.1, RoundingMode.CEIL), 4)
        self.assertEqual(apply_round(-3.9, RoundingMode.CEIL), -3)
        self.assertEqual(apply_round(4.0, RoundingMode.CEIL), 4)

    def test_rounding_half_to_even(self) -> None:
        self.assertEqual(apply_round(3.5, RoundingMode.HALF_TO_EVEN), 4)
        self.assertEqual(apply_round(2.5, RoundingMode.HALF_TO_EVEN), 2)
        self.assertEqual(apply_round(4.5, RoundingMode.HALF_TO_EVEN), 4)

    def test_rounding_half_down(self) -> None:
        self.assertEqual(apply_round(3.5, RoundingMode.HALF_DOWN), 3)
        self.assertEqual(apply_round(3.6, RoundingMode.HALF_DOWN), 4)
        self.assertEqual(apply_round(3.4, RoundingMode.HALF_DOWN), 3)

    def test_rounding_half_away_from_zero(self) -> None:
        self.assertEqual(apply_round(3.5, RoundingMode.HALF_AWAY_FROM_ZERO), 4)
        self.assertEqual(apply_round(-3.5, RoundingMode.HALF_AWAY_FROM_ZERO), -4)
        self.assertEqual(apply_round(2.5, RoundingMode.HALF_AWAY_FROM_ZERO), 3)

    def test_rounding_special_values(self) -> None:
        self.assertEqual(apply_round(float("nan"), RoundingMode.TRUNCATE), 0)
        self.assertEqual(apply_round(float("inf"), RoundingMode.TRUNCATE), 0)
        self.assertEqual(apply_round(float("-inf"), RoundingMode.TRUNCATE), 0)

    def test_stat_initialization(self) -> None:
        if not _is_callable(_init_stats_obj):
            self.skipTest("Stat.init_stats not found")

        init_stats = cast(Callable[[], Dict[Any, Any]], _init_stats_obj)
        stats = init_stats()

        self.assertIsInstance(stats, dict)
        self.assertEqual(len(stats), len(list(RoundingMode)))

        for mode in RoundingMode:
            self.assertIn(mode, stats)

        self.assertIn("DynaMix", stats[RoundingMode.FLOOR])
        self.assertIn("PCE", stats[RoundingMode.FLOOR])

        self.assertIn("TS_1", stats[RoundingMode.FLOOR]["DynaMix"])
        self.assertEqual(stats[RoundingMode.FLOOR]["DynaMix"]["TS_1"], 0)

    def test_multi_hit_counts_initialization(self) -> None:
        if not _is_callable(_init_multi_obj) or not isinstance(_MODEL_NAMES_obj, list):
            self.skipTest("Stat.init_multi_hit_counts or Stat.MODEL_NAMES missing")

        init_multi = cast(Callable[[], Dict[str, int]], _init_multi_obj)
        model_names = cast(List[str], _MODEL_NAMES_obj)

        multi = init_multi()
        self.assertIsInstance(multi, dict)

        for model in model_names:
            self.assertIn(model, multi)
            self.assertEqual(multi[model], 0)

    def test_hit_distribution_initialization(self) -> None:
        if (
            not _is_callable(_init_hit_dist_obj)
            or not isinstance(_MODEL_NAMES_obj, list)
            or not _is_list_str(_TS_LIST_obj)
        ):
            self.skipTest("Stat.init_hit_distribution or MODEL_NAMES/TS_LIST missing")

        init_hit_dist = cast(Callable[[], Dict[Any, Any]], _init_hit_dist_obj)
        model_names = cast(List[str], _MODEL_NAMES_obj)
        ts_list = cast(List[str], _TS_LIST_obj)

        hit_dist = init_hit_dist()
        self.assertIsInstance(hit_dist, dict)

        for mode in RoundingMode:
            self.assertIn(mode, hit_dist)

            for model in model_names:
                self.assertIn(model, hit_dist[mode])

                for hits in range(0, len(ts_list) + 1):
                    self.assertIn(hits, hit_dist[mode][model])
                    self.assertEqual(hit_dist[mode][model][hits], 0)

    def test_overlay_distribution_initialization(self) -> None:
        if not _is_callable(_init_overlay_obj) or not _is_list_str(_TS_LIST_obj):
            self.skipTest("Stat.init_overlay_distribution or TS_LIST missing")

        init_overlay = cast(Callable[[], Dict[int, int]], _init_overlay_obj)
        ts_list = cast(List[str], _TS_LIST_obj)

        overlay = init_overlay()
        self.assertIsInstance(overlay, dict)

        for hits in range(0, len(ts_list) + 1):
            self.assertIn(hits, overlay)
            self.assertEqual(overlay[hits], 0)

    def test_stats_update_logic(self) -> None:
        if not all(
            _is_callable(x)
            for x in (_init_stats_obj, _init_multi_obj, _init_hit_dist_obj, _init_overlay_obj, _update_step_obj)
        ):
            self.skipTest("Stat init/update functions missing")

        if not _is_list_str(_TS_LIST_obj):
            self.skipTest("Stat.TS_LIST missing or unexpected type")

        init_stats = cast(Callable[[], Dict[Any, Any]], _init_stats_obj)
        init_multi = cast(Callable[[], Dict[str, int]], _init_multi_obj)
        init_hit_dist = cast(Callable[[], Dict[Any, Any]], _init_hit_dist_obj)
        init_overlay = cast(Callable[[], Dict[int, int]], _init_overlay_obj)

        update_fn = cast(Callable[..., None], _update_step_obj)

        stats = init_stats()
        multi = init_multi()
        hit_dist = init_hit_dist()
        overlay = init_overlay()

        true_data = {f"TS_{i}": i * 10 for i in range(1, 8)}
        true_row = pd.Series(true_data)

        model_forecasts = {
            "DynaMix": {
                "TS_1": 10.0,
                "TS_2": 20.0,
                "TS_3": 99.0,
                "TS_4": 99.0,
                "TS_5": 99.0,
                "TS_6": 99.0,
                "TS_7": 99.0,
            }
        }

        update_fn(
            stats,
            multi,
            hit_dist,
            overlay,
            true_row,
            model_forecasts,
            dataset_index=123,
            step_date=pd.Timestamp("2099-01-01"),
        )

        self.assertEqual(stats[RoundingMode.TRUNCATE]["DynaMix"]["TS_1"], 1)
        self.assertEqual(stats[RoundingMode.TRUNCATE]["DynaMix"]["TS_2"], 1)
        self.assertEqual(stats[RoundingMode.TRUNCATE]["DynaMix"]["TS_3"], 0)

        for mode in RoundingMode:
            self.assertEqual(stats[mode]["DynaMix"]["TS_1"], 1)
            self.assertEqual(stats[mode]["DynaMix"]["TS_2"], 1)

        self.assertEqual(sum(overlay.values()), 1)
        self.assertEqual(overlay[2], 1, f"Overlay distribution: {dict(overlay)}")

        for mode in RoundingMode:
            self.assertEqual(hit_dist[mode]["DynaMix"][2], 1)

    def test_rounding_mode_labels(self) -> None:
        if not _is_dict(_ROUNDING_MODE_LABELS_obj):
            self.skipTest("Stat.ROUNDING_MODE_LABELS missing")

        labels = cast(Dict[Any, str], _ROUNDING_MODE_LABELS_obj)

        for mode in RoundingMode:
            self.assertIn(mode, labels)
            label = labels[mode]
            self.assertIsInstance(label, str)
            self.assertGreater(len(label), 0)

    def test_model_names_list(self) -> None:
        if not isinstance(_MODEL_NAMES_obj, list):
            self.skipTest("Stat.MODEL_NAMES missing")

        model_names = cast(List[str], _MODEL_NAMES_obj)

        self.assertGreater(len(model_names), 0)
        for model in ["DynaMix", "PCE", "GRU", "LSTM", "NBEATS"]:
            self.assertIn(model, model_names)

    def test_ts_list_configuration(self) -> None:
        if not _is_list_str(_TS_LIST_obj):
            self.skipTest("Stat.TS_LIST missing")

        ts_list = cast(List[str], _TS_LIST_obj)
        self.assertEqual(len(ts_list), 7)

        for i, ts in enumerate(ts_list, start=1):
            self.assertEqual(ts, f"TS_{i}")


if __name__ == "__main__":
    unittest.main()
