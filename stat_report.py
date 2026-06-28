# -----------------------
# stat_report.py — thin entrypoint shim
# -----------------------
"""
Backward-compatible launcher for the checkpoint report tool.

Implementation lives at ``dynamix.entrypoints.stat_report``. Run via:
    python stat_report.py --checkpoint latest
    python -m dynamix.entrypoints.stat_report
    dynamix-report          (console script, after `pip install -e .`)

Requires the package to be importable (`pip install -e .`).
"""
from dynamix.entrypoints.stat_report import main

if __name__ == "__main__":
    main()
