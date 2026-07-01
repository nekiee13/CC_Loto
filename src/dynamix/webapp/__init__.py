# ------------------------
# src/dynamix/webapp/__init__.py
# ------------------------
"""
Streamlit GUI for the DynaMix Lottery Forecasting System (see docs/GUI_PLAN.md).

The GUI is a thin, beginner-first front end that mirrors the User manual workflow. It **wraps the
existing CLIs** as subprocesses and streams their logs; it reimplements no pipeline logic, so
leakage-safety and determinism are untouched.

Import hygiene: every module here except ``app.py`` must be importable **without** Streamlit
installed (Streamlit is the optional ``[gui]`` extra). Only ``app.py`` — the file run via
``streamlit run`` — may import ``streamlit``. Keep all GUI *logic* in Streamlit-free helper modules
so it stays unit-testable by the core suite.
"""

__all__: list[str] = []
