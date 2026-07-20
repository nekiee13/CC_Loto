"""Focused unittest coverage for handoff truth and read-only mode."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]


def load_aggregate():
    path = ROOT / "tools" / "validate_support.py"
    spec = importlib.util.spec_from_file_location("loto_support_test_handoff_aggregate", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


aggregate = load_aggregate()


def tracked_digest(root: Path) -> str:
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root,
                            text=True, capture_output=True, check=False)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise unittest.SkipTest("tracked-file invariant requires an exact Git worktree")
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root,
                         text=True, capture_output=True, check=True)
    if Path(top.stdout.strip()).resolve() != root.resolve():
        raise AssertionError("Git top-level does not equal the candidate repository root")
    names = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True,
                           capture_output=True).stdout.split(b"\0")
    digest = hashlib.sha256()
    for raw in sorted(item for item in names if item):
        relative = raw.decode("utf-8")
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update((root / relative).read_bytes())
    return digest.hexdigest()


class SupportHandoffTests(unittest.TestCase):
    def test_bootstrap_handoff_is_truthfully_not_configured(self):
        result = aggregate.check_handoff(ROOT)
        self.assertEqual(result.state, "not-configured")

    def test_no_record_mode_changes_no_tracked_file(self):
        passed = [aggregate.CheckResult("probe", "passed", "injected")]
        before = tracked_digest(ROOT)
        with mock.patch.object(aggregate, "run_checks", return_value=passed):
            self.assertEqual(aggregate.main(["--root", str(ROOT), "--no-record"]), 0)
        self.assertEqual(tracked_digest(ROOT), before)


if __name__ == "__main__":
    unittest.main()
