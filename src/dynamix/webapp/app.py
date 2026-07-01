# ------------------------
# src/dynamix/webapp/app.py
# ------------------------
"""
DynaMix Streamlit GUI — app shell (G1.2).

This is the only webapp module that imports Streamlit; it is meant to be run via
``streamlit run`` (through ``dynamix-gui`` or the repo-root ``app.py`` shim), not imported.
Later epics fill in the page bodies (Home/Data/Train/Forecast). For now it provides the frame:
title, sidebar navigation, and a placeholder Project Status panel.
"""
from __future__ import annotations

import streamlit as st

APP_TITLE = "DynaMix Lottery Forecasting"


# ----------------------------------------------------------------------
# Pages (bodies filled in by later epics; G1 provides the frame only)
# ----------------------------------------------------------------------
def page_home() -> None:
    st.header("Home")
    st.write(
        "Welcome. This app helps you train on past draws and forecast the next one. "
        "Use the steps in the sidebar, top to bottom."
    )
    st.info("Project status and your next step will appear here (coming in G2).")


def page_data() -> None:
    st.header("1. Data")
    st.write("View your draws and add a new one. (Coming in G3.)")


def page_train() -> None:
    st.header("2. Train")
    st.write("Run a full training, or add a new draw to the notes. (Coming in G5.)")


def page_forecast() -> None:
    st.header("3. Forecast")
    st.write("Make your tickets for the next draw. (Coming in G6.)")


PAGES = {
    "Home": page_home,
    "1. Data": page_data,
    "2. Train": page_train,
    "3. Forecast": page_forecast,
}


def _render_status_placeholder() -> None:
    """Placeholder for the live Project Status panel (implemented in G2)."""
    st.sidebar.subheader("Project status")
    st.sidebar.caption("Status checks appear here (coming in G2).")


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="wide")
    st.title(APP_TITLE)

    st.sidebar.title("Steps")
    choice = st.sidebar.radio("Go to", list(PAGES.keys()), label_visibility="collapsed")
    st.sidebar.divider()
    _render_status_placeholder()

    PAGES[choice]()

    st.divider()
    st.caption(
        "Same workflow as the User manual — just click instead of typing. "
        "The command-line steps still work exactly as before."
    )


if __name__ == "__main__":
    main()
