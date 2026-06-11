# -----------------------
# opt/__init__.py
# -----------------------
"""
Optimization package.

Important:
- Do NOT import submodules here. Import them explicitly from callers (e.g. Orchestrator.py).
- This avoids circular-import issues during package initialization.
"""

# Pylance/Pyright: we intentionally keep __all__ without importing submodules here.
# This suppresses "reportUnsupportedDunderAll" warnings for this file.
# pyright: reportUnsupportedDunderAll=false

__all__ = [
    "opt_config",
    "opt_data",
    "opt_state",
    "opt_features",
    "opt_engine",
    "opt_strategies",
    "opt_calibration",
    "opt_diagnostics",
]
