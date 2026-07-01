# ------------------------
# src/dynamix/webapp/launch.py
# ------------------------
"""
Launcher for the Streamlit GUI (the ``dynamix-gui`` console script).

This module must import without Streamlit installed, so it does **not** import ``streamlit`` at
module load. It shells out to ``python -m streamlit run <app.py>`` at call time, forwarding any
extra CLI args. If the ``[gui]`` extra is not installed, the subprocess prints a clear hint.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_PATH = Path(__file__).resolve().with_name("app.py")


def main() -> int:
    """Run the Streamlit app. Returns the subprocess exit code."""
    try:
        import streamlit  # noqa: F401  (presence check only)
    except Exception:
        print(
            "Streamlit is not installed. Install the GUI extra first:\n"
            "    pip install -e .[gui]\n"
            "then run:  dynamix-gui",
            file=sys.stderr,
        )
        return 1

    cmd = [sys.executable, "-m", "streamlit", "run", str(APP_PATH), *sys.argv[1:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
