# ------------------------
# src/dynamix/webapp/app.py
# ------------------------
"""
DynaMix Streamlit GUI — app shell + Home/Status (G1.2, G2.2).

This is the only webapp module that imports Streamlit; run it via ``streamlit run`` (through
``dynamix-gui`` or the repo-root ``app.py`` shim), not by importing it. All logic lives in the
Streamlit-free helper modules (``state.py`` now; ``runner.py``/``results.py`` in later epics);
the pages here are thin views. Later epics fill in the Data/Train/Forecast bodies.
"""
from __future__ import annotations

import streamlit as st

from dynamix.webapp import state as project_state

APP_TITLE = "DynaMix Lottery Forecasting"


# ----------------------------------------------------------------------
# Sidebar status panel (G2.2)
# ----------------------------------------------------------------------
def _render_status(status: "project_state.ProjectStatus") -> None:
    st.sidebar.subheader("Project status")

    def light(ok: bool, label: str) -> None:
        st.sidebar.write(f"{'🟢' if ok else '🔴'} {label}")

    light(status.data_exists and status.data_rows > 0, f"Draws: {status.data_rows}")
    light(status.has_training, "Training done" if status.has_training else "No training yet")
    light(status.has_forecast, "Forecast ready" if status.has_forecast else "No forecast yet")
    light(status.models_installed, "Models installed" if status.models_installed else "Models missing")
    st.sidebar.caption(f"Next: {status.next_step()}")


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------
def page_home(status: "project_state.ProjectStatus") -> None:
    st.header("Home")
    st.write(
        "Welcome. This app learns from past draws and forecasts the next one. "
        "Follow the steps in the sidebar, top to bottom."
    )

    if not status.data_exists or status.data_rows == 0:
        st.info("No draws found yet. Open the **Data** page to add your draws (Step 1).")
    if not status.models_installed:
        st.warning(
            "The forecasting models are not installed, so forecasts will show **N/A**. "
            "Install them with `pip install -e .[models]`, or see Troubleshooting in the manual."
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Draws", status.data_rows)
    c2.metric("Last draw", status.data_last_date or "—")
    c3.metric("Latest training", status.statgrid_run or "none")

    st.subheader("Your next step")
    st.success(status.next_step())


def page_data(status: "project_state.ProjectStatus") -> None:
    st.header("1. Data")
    st.write("View your draws and add a new one. (Coming in G3.)")


def page_train(status: "project_state.ProjectStatus") -> None:
    st.header("2. Train")
    st.write("Run a full training, or add a new draw to the notes. (Coming in G5.)")


def page_forecast(status: "project_state.ProjectStatus") -> None:
    st.header("3. Forecast")
    st.write("Make your tickets for the next draw. (Coming in G6.)")


PAGES = {
    "Home": page_home,
    "1. Data": page_data,
    "2. Train": page_train,
    "3. Forecast": page_forecast,
}


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="wide")
    st.title(APP_TITLE)

    status = project_state.read_project_status()

    st.sidebar.title("Steps")
    choice = st.sidebar.radio("Go to", list(PAGES.keys()), label_visibility="collapsed")
    st.sidebar.divider()
    _render_status(status)

    PAGES[choice](status)

    st.divider()
    st.caption(
        "Same workflow as the User manual — just click instead of typing. "
        "The command-line steps still work exactly as before."
    )


if __name__ == "__main__":
    main()
