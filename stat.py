# -----------------------
# stat.py — thin entrypoint shim
# -----------------------
"""
Backward-compatible launcher for the rolling-origin backtest / StatGrid exporter.

The implementation now lives in the package at ``dynamix.stat`` (importable as a normal
module, avoiding the stdlib ``stat`` collision). Run via any of:
    python stat.py [--resume ...] [--statgrid-export ...]
    python -m dynamix.stat
    dynamix-stat            (console script, after `pip install -e .`)

Requires the package to be importable (`pip install -e .`).
"""
from dynamix.stat import main

if __name__ == "__main__":
    main()
