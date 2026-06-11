# -----------------------
# tools/qa/verify_optconfig_casts.py
# -----------------------
from __future__ import annotations

import re
from pathlib import Path

PAT = re.compile(r"cast\(\s*OptConfig\s*,", re.MULTILINE)

# Central adapter is allowed to contain the cast.
ALLOWLIST_REL = {
    Path("tests/_typing.py"),
}


def main() -> int:
    root = Path(__file__).resolve().parents[2]  # repo_root/tools/qa/verify...
    tests_dir = root / "tests"
    if not tests_dir.exists():
        print(f"[verify] ERROR: tests/ not found under: {root}")
        return 2

    hits = []
    for p in tests_dir.rglob("*.py"):
        rel = p.relative_to(root)

        # Allow the canonical adapter to contain the cast.
        if rel in ALLOWLIST_REL:
            continue

        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            txt = p.read_text(encoding="utf-8", errors="replace")
        if PAT.search(txt):
            hits.append(rel)

    if hits:
        print("[verify] Found remaining cast(OptConfig, ...) occurrences:")
        for rel in hits:
            print(f"  - {rel}")
        print("[verify] Fix by switching to: from tests._typing import as_opt_config; cfg = as_opt_config(cfg0)")
        return 1

    print("[verify] OK: No cast(OptConfig, ...) occurrences found in tests/ (excluding allowlist).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
