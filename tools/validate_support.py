"""Deterministic CC_Loto support validation aggregate.

Run support checks in the support-operator environment and compose them with
the existing layered unittest runner. The runner is read-only; ``--no-record``
explicitly guarantees that no validation history is written.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

STATES = {"passed", "failed", "skipped", "not-run", "unknown",
          "not-configured", "unavailable"}
FAILURE_STATES = {"failed", "unknown", "unavailable"}


@dataclass(frozen=True)
class CheckResult:
    name: str
    state: str
    detail: str

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"invalid check state: {self.state}")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(command, cwd=root, env=env, text=True,
                          capture_output=True, check=False)


def _command_result(name: str, command: list[str], root: Path,
                    runner: Callable = _run) -> CheckResult:
    try:
        result = runner(command, root)
    except FileNotFoundError as exc:
        return CheckResult(name, "unavailable", str(exc))
    state = "passed" if result.returncode == 0 else "failed"
    detail = f"exit={result.returncode}; command={' '.join(command)}"
    return CheckResult(name, state, detail)


def check_coordination(root: Path) -> CheckResult:
    try:
        support_tools = root / "tools" / "support"
        sys.path.insert(0, str(support_tools))
        module = _load("cc_loto_agent_coord", support_tools / "agent_coord.py")
        result = module.validate(root)
    except (OSError, ImportError, ModuleNotFoundError) as exc:
        return CheckResult("coordination", "unavailable", str(exc))
    return CheckResult("coordination", "passed" if result.ok else "failed",
                       f"errors={len(result.errors)}; warnings={len(result.warnings)}")


def check_handoff(root: Path) -> CheckResult:
    pointer = root / "HANDOFF.md"
    if not pointer.is_file():
        return CheckResult("handoff", "not-configured", "HANDOFF.md is absent")
    text = pointer.read_text(encoding="utf-8")
    if "Record: none published (bootstrap state)" in text:
        return CheckResult("handoff", "not-configured", "bootstrap pointer; no record published")
    match = re.search(r"support/handoffs/[0-9A-Za-z_.-]+\.md", text)
    if not match:
        return CheckResult("handoff", "failed", "pointer does not name an immutable record")
    record_path = root / match.group(0)
    if not record_path.is_file():
        return CheckResult("handoff", "failed", f"missing record: {match.group(0)}")
    try:
        support_tools = root / "tools" / "support"
        sys.path.insert(0, str(support_tools))
        module = _load("cc_loto_make_handoff", support_tools / "make_handoff.py")
        errors = module.validate_record(module.parse_record(record_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ImportError, ModuleNotFoundError) as exc:
        return CheckResult("handoff", "failed", str(exc))
    return CheckResult("handoff", "failed" if errors else "passed",
                       f"validation_errors={len(errors)}")


def check_support_schemas(root: Path) -> CheckResult:
    schemas = sorted((root / "support" / "schemas").glob("*.json"))
    if not schemas:
        return CheckResult("support-schemas", "not-configured", "no support schemas")
    try:
        for path in schemas:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"{path.name} is not a JSON object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return CheckResult("support-schemas", "failed", str(exc))
    return CheckResult("support-schemas", "passed", f"parsed={len(schemas)}")


def run_checks(root: Path, *, native_python: str | None = None,
               runner: Callable | None = None) -> list[CheckResult]:
    runner = _run if runner is None else runner
    python = native_python or sys.executable
    results = [check_coordination(root), check_handoff(root), check_support_schemas(root)]
    results.append(_command_result(
        "native-contract-support",
        [python, "run_tests.py", "--layer", "contract", "--pattern",
         "test_support_*.py", "--verbosity", "1"], root, runner,
    ))
    results.append(CheckResult(
        "native-optional", "not-run", "optional layer is not requested by the fast support aggregate"
    ))
    results.append(CheckResult(
        "hosted-ci", "not-run", "hosted workflow is not executed by a local aggregate"
    ))
    return results


def exit_code(results: list[CheckResult]) -> int:
    return 1 if any(item.state in FAILURE_STATES for item in results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--native-python",
                        help="interpreter used only to invoke the existing target-native runner")
    parser.add_argument("--no-record", action="store_true",
                        help="write no validation-run record (the current runner is read-only)")
    args = parser.parse_args(argv)
    results = run_checks(args.root.resolve(), native_python=args.native_python)
    for item in results:
        print(f"{item.name}: {item.state} ({item.detail})")
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
