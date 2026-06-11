# -----------------------
# tests/_util.py
# -----------------------
from __future__ import annotations

import contextlib
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional


def seed_everything(seed: int = 12345) -> None:
    random.seed(seed)
    try:
        import numpy as np  # type: ignore

        np.random.seed(seed)
    except Exception:
        pass


@dataclass
class TempOutputRoot:
    """
    Creates a temp root and sets DYNAMIX_OUTPUT_ROOT for any code that honors it.
    Provides Output/Reports inside the temp root for conventional layouts.
    """
    prefix: str = "dynamix_test_"

    def __post_init__(self) -> None:
        self._td: Optional[tempfile.TemporaryDirectory] = None
        self.path: Optional[Path] = None

    def __enter__(self) -> Path:
        self._td = tempfile.TemporaryDirectory(prefix=self.prefix)
        self.path = Path(self._td.name).resolve()
        (self.path / "Output" / "Reports").mkdir(parents=True, exist_ok=True)
        os.environ["DYNAMIX_OUTPUT_ROOT"] = str(self.path)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._td is not None:
            self._td.cleanup()
            self._td = None
            self.path = None


@contextlib.contextmanager
def chdir(path: Path) -> Iterator[None]:
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)
