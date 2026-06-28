# -----------------------
# gui.py — thin entrypoint shim
# -----------------------
"""
Backward-compatible launcher for the Tkinter GUI.

Implementation lives at ``dynamix.entrypoints.gui``. Run via:
    python gui.py
    python -m dynamix.entrypoints.gui

Requires the package to be importable (`pip install -e .`) and tkinter.
"""
from dynamix.entrypoints.gui import main

if __name__ == "__main__":
    main()
