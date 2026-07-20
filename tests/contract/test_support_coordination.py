"""Focused unittest coverage for the support aggregate contract."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


aggregate = load("loto_support_test_aggregate", ROOT / "tools" / "validate_support.py")


class SupportCoordinationTests(unittest.TestCase):
    def test_native_command_uses_existing_contract_layer(self):
        calls = []

        def passing_runner(command, root):
            calls.append((command, root))
            return subprocess.CompletedProcess(command, 0, "", "")

        results = aggregate.run_checks(ROOT, native_python="native-python", runner=passing_runner)
        native = next(item for item in results if item.name == "native-contract-support")
        self.assertEqual(native.state, "passed")
        self.assertEqual(calls, [([
            "native-python", "run_tests.py", "--layer", "contract", "--pattern",
            "test_support_*.py", "--verbosity", "1"], ROOT)])

    def test_aggregate_failure_composition(self):
        def failing_runner(command, root):
            return subprocess.CompletedProcess(command, 7, "", "injected")

        results = aggregate.run_checks(ROOT, runner=failing_runner)
        native = next(item for item in results if item.name == "native-contract-support")
        self.assertEqual(native.state, "failed")
        self.assertEqual(aggregate.exit_code(results), 1)

    def test_result_state_exit_semantics(self):
        non_failure = ["passed", "skipped", "not-run", "not-configured"]
        results = [aggregate.CheckResult(str(index), state, "probe")
                   for index, state in enumerate(non_failure)]
        self.assertEqual(aggregate.exit_code(results), 0)
        for state in ("failed", "unknown", "unavailable"):
            with self.subTest(state=state):
                self.assertEqual(
                    aggregate.exit_code([aggregate.CheckResult("probe", state, "applicable")]), 1
                )


if __name__ == "__main__":
    unittest.main()
