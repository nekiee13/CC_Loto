# -----------------------
# run_cli.py — thin entrypoint shim
# -----------------------
"""
Backward-compatible launcher for the forecasting CLI.

Implementation lives at ``dynamix.entrypoints.run_cli``. Run via:
    python run_cli.py [--target ...] [--horizon ...]
    python -m dynamix.entrypoints.run_cli
    dynamix-cli             (console script, after `pip install -e .`)

Requires the package to be importable (`pip install -e .`).
"""
from dynamix.entrypoints.run_cli import main

if __name__ == "__main__":
    main()
