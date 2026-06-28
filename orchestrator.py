# -----------------------
# orchestrator.py — thin entrypoint shim
# -----------------------
"""
Backward-compatible launcher for the optimizer / forecast orchestrator.

Implementation lives at ``dynamix.entrypoints.orchestrator``. Run via:
    python orchestrator.py --action {optimize|forecast} [...]
    python -m dynamix.entrypoints.orchestrator
    dynamix-opt             (console script, after `pip install -e .`)

Requires the package to be importable (`pip install -e .`).
"""
from dynamix.entrypoints.orchestrator import main

if __name__ == "__main__":
    main()
