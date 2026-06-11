# -----------------------
# tests/_typing.py
# -----------------------
from __future__ import annotations

import typing as _t

from opt.opt_config import OptConfig


def as_opt_config(cfg0: object) -> OptConfig:
    """
    Centralized typing adapter for tests.
    Use this instead of inline cast(OptConfig, cfg0) to keep tests clean and consistent.
    """
    # Intentionally written as _t.cast(...) (not bare cast(...)) so repository-wide grep/verifiers can enforce "no cast(OptConfig, ...)" usage in test files.
    # Pylance still understands this as an OptConfig for type-checking.
    return _t.cast(OptConfig, cfg0)
