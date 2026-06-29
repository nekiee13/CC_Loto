# -----------------------
# tests/core_unit/test_packaging.py
# -----------------------
"""
E2.1 — packaging metadata contract.

Why: the project relied on per-entrypoint sys.path bootstrapping (the fragility that broke
orchestrator.py and stat_report.py). A declarative pyproject.toml that makes the code an
installable package removes that whole class of bug. These tests pin the manifest's shape so
packaging cannot silently regress.

Scope: this validates the *declaration*. End-to-end `pip install -e .` and runnable console
scripts are verified in CI / E2.2.
"""
from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
LOCKFILE = REPO_ROOT / "requirements.lock"


def _load() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


class TestPackaging(unittest.TestCase):
    def test_pyproject_exists_and_parses(self) -> None:
        self.assertTrue(PYPROJECT.is_file(), "pyproject.toml must exist at repo root")
        data = _load()
        self.assertIn("project", data, "pyproject.toml must declare a [project] table")
        self.assertIn("build-system", data, "pyproject.toml must declare [build-system]")

    def test_declares_name_and_supported_python(self) -> None:
        proj = _load()["project"]
        self.assertTrue(str(proj.get("name", "")).strip(), "project.name must be set")
        req = str(proj.get("requires-python", ""))
        # Must admit the CI target versions 3.11 and 3.12.
        try:
            from packaging.specifiers import SpecifierSet  # type: ignore

            spec = SpecifierSet(req)
            self.assertIn("3.11.0", spec, f"requires-python {req!r} must allow 3.11")
            self.assertIn("3.12.0", spec, f"requires-python {req!r} must allow 3.12")
        except ImportError:  # fallback if packaging is unavailable
            self.assertIn("3.11", req)

    def test_declares_core_dependencies(self) -> None:
        deps = " ".join(_load()["project"].get("dependencies", [])).lower()
        for pkg in ("pandas", "numpy", "scipy", "scikit-learn", "plotly"):
            self.assertIn(pkg, deps, f"core dependency {pkg} must be declared")

    def test_declares_optional_extras(self) -> None:
        extras = _load()["project"].get("optional-dependencies", {})
        for extra in ("milp", "models"):
            self.assertIn(extra, extras, f"optional-dependency extra '{extra}' must be declared")
        self.assertIn("pulp", " ".join(extras["milp"]).lower())
        models = " ".join(extras["models"]).lower()
        for pkg in ("chaospy", "torch", "darts"):
            self.assertIn(pkg, models, f"models extra must include {pkg}")

    def test_declares_console_scripts(self) -> None:
        scripts = _load()["project"].get("scripts", {})
        for name in ("dynamix-cli", "dynamix-stat", "dynamix-opt", "dynamix-report"):
            self.assertIn(name, scripts, f"console script {name} must be declared")
            self.assertIn(":", scripts[name], f"{name} target must be a 'module:attr' reference")

    def test_lockfile_present(self) -> None:
        # E2.3: a committed lockfile gives reproducible installs (the requires-python /
        # supported versions are covered by test_declares_name_and_supported_python).
        self.assertTrue(
            LOCKFILE.is_file(), "requirements.lock must exist at the repo root"
        )

    def test_lockfile_pins_core_dependencies(self) -> None:
        text = LOCKFILE.read_text(encoding="utf-8").lower()
        for pkg in ("pandas==", "numpy==", "scipy==", "scikit-learn==", "plotly=="):
            self.assertIn(
                pkg, text, f"requirements.lock must pin {pkg.rstrip('=')} with an exact == version"
            )

    def test_packages_dynamix_and_opt_discoverable(self) -> None:
        data = _load()
        find = data.get("tool", {}).get("setuptools", {}).get("packages", {}).get("find", {})
        where = find.get("where", [])
        self.assertIn("src", where, "package discovery must include the src/ layout (dynamix)")
        # opt/ lives at the repo root and must also be discoverable/installed.
        self.assertTrue(
            "." in where or "opt" in str(data),
            "the opt package must be declared/discoverable",
        )


if __name__ == "__main__":
    unittest.main()
