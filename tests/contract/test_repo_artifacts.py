# -----------------------
# tests/contract/test_repo_artifacts.py
# -----------------------
"""
E8.3 — committed-artifact hygiene.

Two problems this pins:
  1. ``DynaMix-python/`` was committed as a *dangling gitlink* (git mode ``160000``, a submodule
     pointer) with **no** ``.gitmodules`` — cloning produced a confusing empty submodule whose
     commit can't resolve. The external DynaMix repo is placed there at runtime, so the path
     should be gitignored, not tracked. This test fails if the index contains *any* gitlink.
  2. Repo-hygiene decisions must be *documented*: the ``DynaMix-python/`` placeholder's purpose
     and the ``DATA.csv`` data policy (kept in git as the canonical reference input) are stated
     in the README so the intent is discoverable.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_ls_files_stage() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


class TestRepoArtifacts(unittest.TestCase):
    def test_no_committed_gitlinks(self) -> None:
        if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
            self.skipTest("git not available / not a git checkout")
        proc = _git_ls_files_stage()
        self.assertEqual(proc.returncode, 0, f"git ls-files failed: {proc.stderr}")
        gitlinks = [
            line.split("\t", 1)[-1]
            for line in proc.stdout.splitlines()
            if line.startswith("160000 ")
        ]
        self.assertEqual(
            gitlinks,
            [],
            "Committed gitlink(s) (submodule pointers) found with no .gitmodules; "
            f"untrack them (git rm --cached): {gitlinks}",
        )

    def test_dynamix_python_gitignored(self) -> None:
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(
            "DynaMix-python/",
            gitignore,
            ".gitignore must ignore the DynaMix-python/ runtime placeholder",
        )

    def test_artifacts_policy_documented(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Data policy", readme, "README must state the DATA.csv data policy")
        self.assertIn(
            "DynaMix-python/",
            readme,
            "README must document the DynaMix-python/ placeholder",
        )
        self.assertIn(
            "not tracked in git",
            readme,
            "README must state the DynaMix-python/ placeholder is not tracked in git",
        )


if __name__ == "__main__":
    unittest.main()
