# -----------------------
# run_tests.py
# -----------------------
"""
Layered unittest runner for the DynaMix project.

Supports repo layout:
  repo_root/
    run_tests.py
    src/
      dynamix/...
    tests/
      core_unit/
      contract/
      optimization/
      state_integrity/
      integration/
      optional/

Key behaviors:
- Adds repo_root and repo_root/src to sys.path so tests can import:
    - entrypoints in repo root (if any)
    - package modules under src/dynamix
- Layer selection:
    --layer all (default) runs DEFAULT_LAYERS, optional only if --include-optional
    --layer <one layer> runs that layer; if --include-optional and not optional, also runs optional
- Pattern selection:
    --pattern test*.py (default)
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from typing import Iterable, List


# ----------------------------------------------------------------------
# Layer configuration
# ----------------------------------------------------------------------
LAYER_DIRS = {
    "core-unit": "tests/core_unit",
    "contract": "tests/contract",
    "optimization-core": "tests/optimization",
    "state-integrity": "tests/state_integrity",
    "integration": "tests/integration",
    "optional": "tests/optional",
}

DEFAULT_LAYERS = ["core-unit", "contract", "optimization-core", "state-integrity", "integration"]


# ----------------------------------------------------------------------
# Discovery helpers
# ----------------------------------------------------------------------
def _discover(start_dir: str, pattern: str, *, top_level_dir: str) -> unittest.TestSuite:
    """
    Use unittest discovery with an explicit top-level directory.
    This makes imports stable when tests are a package (tests/__init__.py present)
    and when code lives under src/.
    """
    loader = unittest.TestLoader()
    return loader.discover(start_dir=start_dir, pattern=pattern, top_level_dir=top_level_dir)


def _suite_for_layers(layers: Iterable[str], pattern: str, *, repo_root: Path) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for layer in layers:
        rel = LAYER_DIRS.get(layer)
        if not rel:
            continue
        start_dir = repo_root / rel
        if not start_dir.exists():
            continue
        suite.addTests(_discover(str(start_dir), pattern, top_level_dir=str(repo_root)))
    return suite


def _resolve_layers(requested_layer: str, include_optional: bool) -> List[str]:
    if requested_layer == "all":
        layers = list(DEFAULT_LAYERS)
        if include_optional:
            layers.append("optional")
        return layers

    # Single layer
    layers = [requested_layer]
    if requested_layer != "optional" and include_optional:
        layers.append("optional")
    return layers


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Layered unittest runner (DynaMix QA).")
    parser.add_argument(
        "--layer",
        default="all",
        choices=["all", *LAYER_DIRS.keys()],
        help="QA layer to run. 'all' runs default layers; optional included only with --include-optional.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Include optional-dependency tests (tests/optional).",
    )
    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="Discovery pattern (default: test*.py).",
    )
    parser.add_argument(
        "--failfast",
        action="store_true",
        help="Stop on first failure.",
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        default=2,
        help="unittest verbosity (default: 2).",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"

    # Ensure repo imports (root entrypoints) and package imports (src/dynamix) both work.
    sys.path.insert(0, str(repo_root))
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))

    layers = _resolve_layers(args.layer, args.include_optional)

    suite = _suite_for_layers(layers, args.pattern, repo_root=repo_root)
    runner = unittest.TextTestRunner(verbosity=args.verbosity, failfast=args.failfast)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
