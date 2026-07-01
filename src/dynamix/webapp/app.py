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

from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd
import streamlit as st

from dynamix.webapp import data_io
from dynamix.webapp import results as forecast_results
from dynamix.webapp import runner
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


def _data_file() -> Path:
    from dynamix import constants as C

    return Path(C.DATA_FILE)


def page_data(status: "project_state.ProjectStatus") -> None:
    st.header("1. Data")
    data_file = _data_file()
    st.caption(f"File: `{data_file}`")

    flash = st.session_state.pop("data_flash", None)
    if flash:
        st.success(flash)

    header, rows, err = data_io.read_data(data_file)
    if err:
        st.warning(err)

    st.subheader("Your draws")
    if rows:
        cols = header or data_io.expected_header()
        df = pd.DataFrame(rows, columns=cols[: len(rows[0])])
        st.dataframe(df.iloc[::-1], width="stretch", hide_index=True)  # newest first
        st.caption(f"{len(rows)} draws. Newest at the top.")
    else:
        st.info("No draws yet. Add your first one below.")

    st.subheader("Add a new draw")
    st.caption("New draws come twice a week. Add each one as it happens.")
    ts_cols = (header or data_io.expected_header())[1:]
    with st.form("add_draw", clear_on_submit=True):
        date = st.text_input("Date (dd/mm/yyyy)", placeholder="31/12/2026", key="new_date")
        input_cols = st.columns(len(ts_cols))
        values = [
            input_cols[i].number_input(c, step=1, value=0, format="%d", key=f"new_{c}")
            for i, c in enumerate(ts_cols)
        ]
        submitted = st.form_submit_button("Add draw")

    if submitted:
        res = data_io.append_draw(data_file, date, [int(v) for v in values])
        if res.ok:
            st.session_state["data_flash"] = f"Added draw for {res.date}. It is now the newest row."
            st.rerun()
        else:
            st.error(res.error)


def _log_dir() -> Path:
    from dynamix import constants as C

    return Path(C.OUTPUT_LOGS_DIR)


def render_job_panel(
    *,
    key: str,
    start_label: str,
    action: str,
    options: Optional[Dict[str, object]] = None,
    on_success: Optional[Callable[[], None]] = None,
    confirm_text: Optional[str] = None,
) -> None:
    """Reusable live-job panel (G4.2): start a wrapped CLI, stream its log, show progress, Stop.

    Thin view over ``runner.job_view`` (the state machine lives there, unit-tested). Auto-refreshes
    via a Streamlit fragment while the job runs; shows a success/stopped/failed banner when it ends.
    """
    ss = st.session_state
    jkey = f"job_{key}"

    if jkey not in ss:
        proceed = True
        if confirm_text:
            proceed = st.checkbox(confirm_text, key=f"confirm_{key}")
        if st.button(start_label, key=f"start_{key}", type="primary", disabled=not proceed):
            log_path = _log_dir() / f"gui_{action}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
            ss[jkey] = runner.start_job(runner.build_command(action, options or {}), log_path)
            ss.pop(f"stopped_{key}", None)
            st.rerun()
        return

    job = ss[jkey]

    def _body(in_fragment: bool) -> None:
        view = runner.job_view(job, stopped=bool(ss.get(f"stopped_{key}")))
        state, prog, text = view["state"], view["progress"], view["text"]

        if state == "running":
            if prog and prog[1] > 0:
                st.progress(min(prog[0] / prog[1], 1.0), text=f"Working… step {prog[0]}/{prog[1]}")
            else:
                st.progress(0.0, text="Working…")
            if st.button("Stop", key=f"stop_{key}"):
                runner.stop_job(job)
                ss[f"stopped_{key}"] = True
                st.rerun()
        elif state == "stopped":
            st.warning("Stopped.")
        elif state == "done":
            st.success("Done.")
            if on_success:
                on_success()
        else:
            st.error(f"Failed (exit code {view['returncode']}). See the log below.")

        st.code(text or "(waiting for output…)", language="log")

        if state != "running" and st.button("Clear output", key=f"clear_{key}"):
            ss.pop(jkey, None)
            ss.pop(f"stopped_{key}", None)
            st.rerun()

        if in_fragment and state != "running":
            st.rerun()  # break out of the live fragment to a static render

    if runner.is_running(job):
        st.fragment(lambda: _body(True), run_every=1.5)()
    else:
        _body(False)


def page_train(status: "project_state.ProjectStatus") -> None:
    st.header("2. Train")
    st.write(
        "Train once in a while (Step 2). After each new draw, add it to the notes (Step 5a). "
        "A full training is slow; the incremental update is fast."
    )

    with st.expander("Advanced settings"):
        dedupe = st.checkbox(
            "Store notes in the smaller de-duped form (`--statgrid-dedupe`)", key="train_dedupe"
        )
        resume = st.text_input(
            "Resume from (blank = default) — `--resume`", key="train_resume",
            placeholder="latest, a step index, or a path",
        )
    options: Dict[str, object] = {"dedupe": bool(dedupe)}
    if resume.strip():
        options["resume"] = resume.strip()

    st.subheader("Full training (slow)")
    st.caption("Rebuilds the notes from every draw. Do this rarely — e.g. once every six months.")
    render_job_panel(
        key="train_full",
        start_label="Run full training",
        action="train_full",
        options=options,
        confirm_text="I understand this reads every draw and can take a long time.",
    )

    st.divider()
    st.subheader("Add new draw to notes (fast)")
    st.caption("Folds the newest draw into the training notes (Step 5a).")
    render_job_panel(
        key="train_inc",
        start_label="Add new draw to notes",
        action="train_incremental",
        options=options,
    )


def _render_latest_tickets() -> None:
    status = project_state.read_project_status()
    if not status.forecast_path:
        st.info("No forecast file found yet.")
        return
    view = forecast_results.load_forecast(status.forecast_path)
    if not view.ok:
        st.error(view.error)
        return
    if not view.tickets:
        st.info("The forecast produced no tickets — the models may not be installed (see Home).")
        return

    st.subheader("Your tickets")
    df = pd.DataFrame(view.ticket_rows())
    st.dataframe(df, width="stretch", hide_index=True)

    meta = f"From training run `{view.grid_run_id or '?'}`"
    if view.generated_at:
        meta += f" · generated {view.generated_at}"
    if view.q_any is not None:
        meta += f" · q_any = {view.q_any:.4f}"
    st.caption(meta)
    st.download_button(
        "Download tickets (CSV)", df.to_csv(index=False), file_name="tickets.csv", mime="text/csv"
    )


def page_forecast(status: "project_state.ProjectStatus") -> None:
    st.header("3. Forecast")
    st.write("Make up to 5 tickets for the next draw (Steps 3 and 5b).")

    if not status.has_training:
        st.warning(
            "No training yet. Do a **full training** on the Train page first (Step 2), "
            "then come back here."
        )
        return

    with st.expander("Advanced settings"):
        run_id = st.text_input("Which training run — `--run-id`", value="latest", key="fc_run_id")
        max_tickets = st.number_input(
            "How many tickets — `--max-tickets`", min_value=1, max_value=20, value=5, step=1, key="fc_max"
        )
        seed = st.number_input("Random seed — `--seed`", value=123, step=1, key="fc_seed")
    options: Dict[str, object] = {
        "run_id": (run_id or "").strip() or "latest",
        "max_tickets": int(max_tickets),
        "seed": int(seed),
    }

    render_job_panel(
        key="forecast",
        start_label="Make tickets",
        action="forecast",
        options=options,
        on_success=_render_latest_tickets,
    )


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
