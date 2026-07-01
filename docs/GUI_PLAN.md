# GUI Implementation Plan — Streamlit (v1: Core Loop)

A step-by-step, GitHub-issue-style plan to add a **beginner-first Streamlit GUI** that mirrors the
[User manual](User_manual.md) workflow (*update data → train rarely → forecast often*). The GUI
**wraps the existing CLIs** (`dynamix-stat`/`dynamix-opt`/`dynamix-report`/`dynamix-cli`) as
subprocesses and streams their logs. It reimplements **no** pipeline logic, so leakage-safety and
determinism (SRS NFR-9) are guaranteed by construction. The CLI stays fully usable; the existing
Tkinter GUI is left untouched (coexists for now).

**Status: v1 COMPLETE ✅ (all 7 epics G1–G7).** The full core loop is click-driven and equivalent
to the CLI; the suite is 150 tests, OK. Remaining work is the v2 backlog (bottom of this doc).

## How to use this plan

- Work one task at a time, in dependency order (see graph at the end).
- Each task follows **Red → Green (→ Refactor)** where it has testable logic. All non-UI logic
  lives in **pure helpers** unit-tested with the existing layered runner (`python run_tests.py`).
  The Streamlit view layer is thin and validated by the **manual acceptance checks** in each task.
- Tags: `type:` (feature|chore|test) · `layer:` (core_unit|contract|ui|packaging) · `effort:` S|M|L.
- **Status legend:** ⬜ Todo · 🟡 In progress · 🔵 In review · ✅ Done · ⏸️ Blocked · ❌ Dropped

## Scope (v1 = Core Loop)

**In:** Home/Status, Data (view + add draw), Train (full + incremental), Forecast (tickets),
live logs + Stop, guardrails. **Deferred to v2:** Optimize & Score page, Reports page, quick
single-series, charts/exports (listed at the end as a backlog).

## Conventions

- New optional package `src/dynamix/webapp/` with pure helpers + `app.py` (Streamlit).
- The runner invokes CLIs as `"<python> -u -m <module> <flags>"` with `cwd=REPO_ROOT` so output
  streams live and paths resolve. Modules: `dynamix.stat`, `dynamix.entrypoints.orchestrator`,
  `dynamix.entrypoints.stat_report`, `dynamix.entrypoints.run_cli`.
- Helper tests live under `tests/webapp/`, registered as the `webapp` layer in `run_tests.py` and
  included in the default layers; they must not import `streamlit` (keep logic import-light so the
  suite runs without the `[gui]` extra).
- No changes to `opt/`, `dynamix.stat`, or the entrypoints' behavior.

---

# EPIC G1 — Scaffolding & packaging  ✅
`priority:P0` · `type:chore`

**What.** Create the `webapp` package, the `[gui]` dependency extra, a `dynamix-gui` launcher, and a
minimal app shell that loads without error. **Why.** Everything else builds on a runnable skeleton
that installs cleanly and does not disturb core installs.

**Definition of done.** `pip install -e .[gui]` installs Streamlit; `dynamix-gui` opens the app; the
core suite still passes without the extra.

### Task G1.1 — Package + dependency + launcher ✅
`type:chore` · `layer:packaging` · `effort:S`
**What.** Add `src/dynamix/webapp/__init__.py`; add `streamlit>=1.36` to the `[gui]` extra in
`pyproject.toml`; add console script `dynamix-gui = "dynamix.webapp.launch:main"` where `launch.py`
shells `streamlit run <app.py>`; add a repo-root `app.py` shim (`streamlit run app.py` also works).
**Why.** One obvious way to start the GUI, consistent with the other `dynamix-*` scripts.
- **Red** — `tests/integration/test_gui_packaging.py::test_webapp_imports_without_streamlit`:
  importing `dynamix.webapp` and the pure helper modules must succeed even if `streamlit` is absent.
- **Green** — create the package; keep `streamlit` imports out of helper modules (only `app.py`/
  `launch.py` import it).
**Acceptance criteria**
- [ ] `pip install -e .[gui]` succeeds; `pip install -e .` (core) still works with no Streamlit.
- [ ] `dynamix-gui` and `streamlit run app.py` both launch the app.
- [ ] Helper modules import with `streamlit` uninstalled (test green).

### Task G1.2 — App shell (nav + layout) ✅
`type:feature` · `layer:ui` · `effort:S`
**What.** `app.py` with a sidebar page selector (Home, Data, Train, Forecast), app title, and a
placeholder Project-Status panel. Wire empty page functions. **Why.** A navigable frame to fill in.
- **Green** — implement the shell; no logic yet.
**Acceptance criteria** *(manual)*
- [ ] App loads with no exceptions; all four pages are reachable from the sidebar.
- [ ] Layout is readable on a laptop screen; matches the manual's step order.

---

# EPIC G2 — Project status & guardrails  ✅
`priority:P0` · `type:feature`

**What.** A read-only "where am I" reader plus a Home page that tells the user the next step in plain
words. **Why.** The manual's whole value is a clear path; the GUI must show state and prevent the
exact errors listed in the manual's Troubleshooting section.

**Definition of done.** The Home page always shows draw count, last draw date, latest training run +
date, latest forecast, and install status — and names the next action.

### Task G2.1 — `state.py` project-status reader (pure) ✅
`type:feature` · `layer:webapp` · `effort:M`
**What.** Pure functions returning a `ProjectStatus` dataclass: DATA.csv exists + row count + last
date; latest StatGrid run id + folder mtime; latest `forecast.json` path + mtime; booleans for
`models_installed` (torch/darts/chaospy importable) and `milp_installed` (pulp). Reads paths from
`dynamix.constants` / `OptConfig` defaults. **Why.** One trustworthy source for the UI and guardrails.
- **Red** — `tests/webapp/test_state.py`: over a temp `Output/` + `DATA.csv`, assert row count, last
  date, "no StatGrid" vs "latest run" resolution, and `forecast.json` discovery. Uses the existing
  `tests/_util.TempOutputRoot` pattern; no Streamlit import.
- **Green** — implement readers with safe fallbacks (missing files → clearly "not done yet").
**Acceptance criteria**
- [ ] Correct counts/dates on a seeded fixture; empty/missing paths never raise.
- [ ] `latest_statgrid_run()` matches `orchestrator._resolve_latest_grid_run_id` semantics.

### Task G2.2 — Home page + status panel + guardrails ✅
`type:feature` · `layer:ui` · `effort:M`
**What.** Render the status as traffic lights in the sidebar; a Home page with a plain-language
"Next step" (e.g., *no StatGrid → "Do a full training (Train page)"*). Guardrail banners: models
missing → "forecasts will be N/A + how to install"; DATA.csv invalid → link to Data page.
**Why.** Turns state into guidance; prevents dead-ends.
- **Green** — bind the panel/home to `state.py`.
**Acceptance criteria** *(manual)*
- [ ] With no training, Home says "train first" and Forecast is gated (see G6).
- [ ] With models absent, a clear banner explains the N/A outcome.

---

# EPIC G3 — Data page  ✅
`priority:P0` · `type:feature`

**What.** View DATA.csv and add a new draw safely. **Why.** Steps 1 & 4 of the manual; bad data is the
top cause of "Data load error".

**Definition of done.** A user can view all draws and append a valid new draw from a form; invalid
input is rejected with a clear message.

### Task G3.1 — DATA.csv validation + append (pure) ✅
`type:feature` · `layer:webapp` · `effort:M`
**What.** Pure helpers: `validate_row(date, values)` (7 integers, `dd/mm/yyyy` date, ranges from
`constants` if defined) and `append_draw(path, date, values)` (atomic append, header preserved,
trailing-newline safe). A `read_data(path)` returning a DataFrame + basic file health. **Why.**
Enforce the manual's format rules before they reach `stat.py`.
- **Red** — `tests/webapp/test_data_io.py`: reject bad date form, wrong column count, non-integers;
  accept a valid row and confirm it lands as the last line with the header intact.
- **Green** — implement; write to a temp copy then replace (safe append).
**Acceptance criteria**
- [ ] Valid row appends as the last line; header unchanged; file stays parseable by `data_utils`.
- [ ] Every invalid case is rejected with a specific reason string.

### Task G3.2 — Data page UI ✅
`type:feature` · `layer:ui` · `effort:S`
**What.** Show the draws table (last rows first), an "Add new draw" form (date picker + 7 number
inputs) calling the G3.1 helpers, and a success/refresh on append. **Why.** Steps 1 & 4, click-only.
- **Green** — wire the form to the helpers; show validation errors inline.
**Acceptance criteria** *(manual)*
- [ ] Adding a valid draw updates the table and the Home draw-count immediately.
- [ ] A bad entry shows the reason and does not modify the file.

---

# EPIC G4 — Job runner & live logs  ✅
`priority:P0` · `type:feature`

**What.** The subprocess engine: build a CLI command from an action + flags, run it, stream logs live,
show progress, and allow Stop. **Why.** This is the heart of "GUI = the CLI, click-driven"; every
Train/Forecast action goes through it.

**Definition of done.** Any wrapped CLI runs from the GUI with live log output, a parsed progress
line, and a working Stop button; failures surface clearly.

### Task G4.1 — `runner.py` command builder + process control (pure-ish) ✅
`type:feature` · `layer:webapp` · `effort:L`
**What.** `build_command(action, options) -> list[str]` mapping GUI actions to
`[python, "-u", "-m", <module>, <flags...>]` (Train-full, Train-incremental, Forecast, Optimize,
Report, Single-series). `start_job(cmd, log_path)` → `Popen` teeing stdout to `Output/Logs/gui_*.log`;
`is_running`, `stop_job` (terminate process group), `tail(log_path, n)`, and `parse_progress(text)`
(extract `step X/Y` and stage from the `[STAT]`/`[OPT]` logging). **Why.** Isolate all process logic
so it is unit-testable and the UI stays thin.
- **Red** — `tests/webapp/test_runner.py`: `build_command` produces exact argv for each action +
  flag set (e.g., full training → `... -m dynamix.stat --statgrid-export full`); `parse_progress`
  extracts `120/512` from a sample log line; `tail` returns the last N lines. Process start/stop is
  smoke-tested with a trivial `python -c` command (no ML deps).
- **Green** — implement with `cwd=REPO_ROOT`, unbuffered, line-streamed; store handle in session.
- **Refactor** — a single command-spec table drives both `build_command` and the Advanced-options UI.
**Acceptance criteria**
- [ ] `build_command` argv is asserted for full-train, incremental, and forecast (exact match).
- [ ] `parse_progress` and `tail` pass on sample logs; a dummy job starts, streams, and stops.

### Task G4.2 — Live log panel + Stop + progress ✅
`type:feature` · `layer:ui` · `effort:M`
**What.** A reusable component: spinner + progress bar (from `parse_progress`) + scrolling last-N log
lines + a Stop button, auto-refreshing (~1–2s) while a job runs; on exit, a success/fail banner.
**Why.** Long jobs (full training, optimize) need honest, non-blocking feedback.
- **Green** — poll the log file each rerun via `st.session_state` job flag + autorefresh.
**Acceptance criteria** *(manual)*
- [ ] A running job shows live lines and a moving progress bar; Stop ends it and reports "stopped".
- [ ] The UI never freezes while a job runs.

---

# EPIC G5 — Train page  ✅
`priority:P0` · `type:feature`

**What.** Buttons for full training and incremental update, wired through the runner. **Why.** Step 2
and Step 5a of the manual, click-only.

**Definition of done.** A user can run a full training and an incremental update from the GUI and
watch progress to completion.

### Task G5.1 — Train page UI ✅
`type:feature` · `layer:ui` · `effort:M`
**What.** **Full training (slow)** button behind a confirm dialog (explains it takes a while), and
**Add new draw to notes (fast)** button (`--resume latest --statgrid-export incremental`). Advanced
expander exposes `--statgrid-export`, `--statgrid-dedupe`, `--resume` with CLI-identical defaults.
Uses the G4.2 log panel. **Why.** The manual's training steps without the terminal.
- **Green** — map buttons to `runner.build_command`; confirm-gate the slow one.
**Acceptance criteria** *(manual)*
- [ ] Full training starts, streams progress, and finishes with a new StatGrid run visible on Home.
- [ ] Incremental update runs and Home's "last training" updates.
- [ ] Advanced flags change the argv exactly as the CLI would.

---

# EPIC G6 — Forecast page  ✅
`priority:P0` · `type:feature`

**What.** One-click forecast that shows tickets nicely, gated on having a StatGrid. **Why.** Steps 3 &
5b — the payoff.

**Definition of done.** A user clicks "Make tickets" and sees the parsed tickets from `forecast.json`,
or a clear "train first" gate if no StatGrid exists.

### Task G6.1 — `results.py` forecast.json parser (pure) ✅
`type:feature` · `layer:webapp` · `effort:S`
**What.** `load_forecast(path) -> ForecastView`: the up-to-5 tickets as a tidy table (TS_1..TS_7 per
ticket), plus metadata (run id, timestamp, per-ticket q if present). Tolerates missing/partial files.
**Why.** Turn raw JSON into a friendly table; keep parsing testable.
- **Red** — `tests/webapp/test_results.py`: parse a sample `forecast.json` into the expected rows;
  a missing/empty file yields an "empty" view, not an exception.
- **Green** — implement against the real `forecast.json` shape written by the orchestrator.
**Acceptance criteria**
- [ ] Sample forecast parses to the correct ticket rows + metadata; malformed input degrades safely.

### Task G6.2 — Forecast page UI ✅
`type:feature` · `layer:ui` · `effort:M`
**What.** **Make tickets** button (`--action forecast --run-id latest`) via the runner; on success
render the G6.1 table + a CSV/JSON download; disabled with "Train first (Step 2)" when no StatGrid.
Advanced expander: `--max-tickets`, `--seed`, `--run-id`. **Why.** Steps 3 & 5b, click-only.
- **Green** — gate on `state.latest_statgrid_run()`; show results after the job exits.
**Acceptance criteria** *(manual)*
- [ ] With a StatGrid present, clicking makes tickets and shows the table + download.
- [ ] With no StatGrid, the button is gated and points the user to Train.

---

# EPIC G7 — Docs & manual integration  ✅
`priority:P1` · `type:chore`

**What.** Document the GUI path so users can pick CLI *or* GUI for the same workflow. **Why.** The
stated goal: two equivalent routes.

**Definition of done.** The manual and README explain how to launch and use the GUI; both GUIs'
coexistence is stated.

### Task G7.1 — Manual "Using the GUI" section + README/install note ✅
`type:chore` · `layer:contract` · `effort:S`
**What.** Add a GUI section to `User_manual.md` mirroring Steps 1–5 with screenshots/placeholders and
the `pip install -e .[gui]` + `dynamix-gui` launch. Note the Tkinter GUI still exists. Keep
Flesch-Kincaid < 10. **Why.** Beginners need the click-path written down too.
- **Green** — write the section; cross-link CLI ↔ GUI steps.
**Acceptance criteria**
- [ ] Manual documents install, launch, and each core-loop action via the GUI; readability < 10.
- [ ] README mentions the GUI and the `[gui]` extra.

### Task G7.2 — Import/smoke test in CI *(optional)* ✅
`type:test` · `layer:webapp` · `effort:S`
**What.** A headless smoke test that imports `dynamix.webapp` helpers and (if Streamlit is present)
builds the app object via `streamlit.testing.AppTest` for one render. **Why.** Catch breakage without
manual clicking. **Acceptance criteria**
- [ ] Helper import test runs in the default suite; the AppTest render is gated to the `[gui]` extra.

---

## Cross-epic Definition of Done (v1)

Using **only the GUI**, a user can: see project status and the next step; add a new draw; run a full
training and an incremental update with live progress; make a forecast and see the tickets — with a
working Stop button and guardrails that prevent the manual's common errors. The CLI is unchanged, the
Tkinter GUI still works, and the core test suite passes with and without the `[gui]` extra.

## Dependency graph

```
G1 (scaffold) ─▶ G2 (status) ─▶ G3 (data)
                         │
                         └▶ G4 (runner) ─▶ G5 (train)
                                        └▶ G6 (forecast, needs G6.1 parser)
G2 + G3 + G5 + G6 ─▶ G7 (docs)
```

Suggested order: **G1 → G2 → G4 → G3 → G5 → G6 → G7** (build the runner early; Data can land in
parallel once status exists).

## Deferred to v2 (backlog, not in this plan)

- **Optimize & Score page** — `--action optimize`; render the EV/ROI + calibration scoreboard.
- **Reports page** — wrap `stat_report`.
- **Quick single-series** — wrap `run_cli --target/--horizon`.
- **Charts/exports** — calibration/ROI plots, richer downloads.
- **Retire Tkinter** — once Streamlit covers the full workflow.

## Progress log

- 2026-07-01 — **Enhancement: live progress bar tied to the calculations (refines G4.2).** The three
  long operations already log parseable progress — full training `[STAT] Step {n}/{total}`, the
  export rebuild `Full export rebuild progress: {n}/{total}`, and optimize
  `[OPT][stage] progress: {n}/{total} (…%) … eta=…`. Enriched the live panel so the bar shows
  **percentage · step n/total · eta** (added `runner.parse_eta`; the bar value is `n/total`). The
  fragment re-reads the log tail every 1.5s so the bar advances in real time. Added runner tests
  (growing-log tracking, optimize/step formats, eta parsing) and **verified via `AppTest`** that as a
  job's log grows the progress element climbs **10% → 80%**. Suite: **166 tests, OK (skipped=5)**.
- 2026-07-01 — **Epic G7 complete (G7.1 + G7.2 ✅) → v1 GUI plan DONE (all 7 epics).** Added a
  beginner-friendly **§12 "Prefer clicking? Use the GUI"** to `User_manual.md` (install
  `pip install -e .[gui]`, launch `dynamix-gui`, the status lights, and the Data/Train/Forecast
  steps — noting the legacy Tkinter GUI coexists), a pointer from the setup section, and a **GUI**
  subsection in the README. Readability held at **Flesch-Kincaid ~2.7**. Added
  `tests/webapp/test_gui_smoke.py`: helper modules import (always), and — when Streamlit is present
  — the app renders once via `AppTest` with no exception (skipped without the `[gui]` extra). Also
  hardened `test_state`'s "Streamlit-free" guard to scan the source instead of global `sys.modules`
  (which the smoke test now legitimately populates). Suite: **150 tests, OK (skipped=5)**.
  **v1 GUI is complete**: Home/Status → Data → Train → Forecast, with live logs, Stop, and
  guardrails, entirely click-driven and equivalent to the CLI. Remaining items are the **v2 backlog**
  (Optimize & Score, Reports, single-series, charts/exports, retire Tkinter).
- 2026-07-01 — **Epic G6 complete (G6.1 + G6.2 ✅) → v1 core loop functional.** Added
  `dynamix.webapp.results` — pure, Streamlit-free `load_forecast(path) -> ForecastView`: parses the
  orchestrator's `forecast.json` (top-level `tickets` = 7-int lists, parallel `q_per_ticket`, plus
  `q_any`/`generated_at`/`grid_run_id`/`opt_run_id`), with `ticket_rows()` → `{Ticket, TS_1..TS_7,
  q}`; missing/malformed/partial files degrade to an "empty" view (never raises). Red→Green
  `tests/webapp/test_results.py` (5 tests). Built the Forecast page: gated on `has_training` (shows
  "train first" when no StatGrid), a **Make tickets** button (`--action forecast --run-id latest`)
  via `render_job_panel`, an Advanced expander (`--run-id`/`--max-tickets`/`--seed`), and an
  on-success renderer that loads the latest `forecast.json` into a tickets table + CSV download.
  **Live-verified** via `AppTest` over temp `DYNAMIX_OUTPUT_DIR`: (A) no StatGrid → warning + no
  button; (B) StatGrid + `forecast.json` → Make-tickets button, and an injected finished job renders
  the tickets table with columns `Ticket, TS_1..TS_7, q`. Suite: **148 tests, OK (skipped=5)**. The
  v1 core loop (Home/Status → Data → Train → Forecast, with live logs + guardrails) is now usable
  end to end; only docs (G7) remain.
- 2026-07-01 — **Epic G5 complete (G5.1 ✅).** Finished the Train page (reusing `render_job_panel`):
  a **Full training (slow)** button gated behind a confirm checkbox, a fast **Add new draw to notes**
  (incremental) button, and an Advanced expander exposing `--statgrid-dedupe` and `--resume` with
  CLI-identical defaults. **Live-verified** via `AppTest`: both buttons render; the full-training
  start button is disabled until the confirm box is ticked (True→False on the `.disabled` flag); and
  ticking the advanced dedupe box makes the started job's argv exactly
  `… -m dynamix.stat --statgrid-export full --statgrid-dedupe` (checked with a capturing monkeypatch
  so no real training ran). UI-only; argv correctness is covered by the G4 runner tests. Suite:
  **143 tests, OK (skipped=5)**.
- 2026-07-01 — **Epic G4 complete (G4.1 + G4.2 ✅).** Added `dynamix.webapp.runner` — the pure,
  Streamlit-free subprocess engine: `build_command(action, options)` maps each GUI action to the
  exact `python -u -m <module> <flags>` argv (train_full / train_incremental / forecast / optimize /
  report / single_series), `start_job` tees stdout+stderr to a run-scoped log file (own session so
  the group can be stopped), `is_running`/`returncode`/`stop_job` (SIGTERM the process group),
  `tail`, `parse_progress` (last "X/Y", preferring "progress" lines), and `job_view` (pure state
  machine → running|stopped|done|failed + progress + tail). Red→Green `tests/webapp/test_runner.py`
  (14 tests incl. exact argv per action, a real start/stream/**stop** cycle, and job_view states).
  Added the reusable `render_job_panel` Streamlit component (thin mapping over `job_view`: start
  button, live progress bar + log via an `st.fragment(run_every=1.5)` auto-refresh, Stop, and a
  success/stopped/failed banner) and wired it into the Train page's incremental button. **Live-
  verified** via `AppTest`: start button renders; an injected finished job shows **Done** + its log;
  a failed job shows **Failed (exit code 1)**. Suite: **143 tests, OK (skipped=5)**.
- 2026-07-01 — **Epic G3 complete (G3.1 + G3.2 ✅).** Added `dynamix.webapp.data_io` — pure,
  Streamlit-free `validate_row` (date `%d/%m/%Y`, exactly 7 whole numbers; clear per-field errors),
  `append_draw` (validate → **atomic** temp-write + `os.replace`; creates the file with header when
  missing; header preserved; never concatenates onto the last row), and `read_data` (header + rows +
  a health note if the header is off). Red→Green `tests/webapp/test_data_io.py` (9 tests, incl. a
  pandas re-parse under the real date format to prove the file stays loadable). Wired the Data page:
  draws table (newest first) + an "Add a new draw" form that validates and appends, with a flash
  message that survives the post-submit rerun. **Live-verified** via `AppTest` against a *temp*
  DATA.csv (real file untouched): table renders; a valid draw appends as the newest row with a
  success flash; a bad date is rejected with a clear error and the file is unchanged. (Also switched
  `st.dataframe` to `width="stretch"` to drop a Streamlit deprecation warning.) Suite: **129 tests,
  OK (skipped=5)**.
- 2026-07-01 — **Epic G2 complete (G2.1 + G2.2 ✅).** Added `dynamix.webapp.state` — pure,
  Streamlit-free readers: `data_status` (draws + last date), `latest_statgrid_run` (newest by
  sorted name, matching the orchestrator), `latest_forecast` (newest `forecast.json` by mtime),
  `deps_installed` (models = any of torch/darts/chaospy importable; milp = pulp), and
  `read_project_status()` → a `ProjectStatus` dataclass with `has_training`/`has_forecast` and a
  plain-language `next_step()`. Registered a new **`webapp`** test layer in `run_tests.py` (in the
  default set); Red→Green `tests/webapp/test_state.py` (6 tests over temp dirs; asserts logic stays
  Streamlit-free). Wired the Home page + sidebar status panel (traffic lights) + guardrail banners
  (no-data info, models-missing warning) to the reader. **Live-verified** via `AppTest`: Home shows
  the real status (562 draws, last draw date, "no training", models-missing warning, correct next
  step) and all pages navigate. Suite: **120 tests, OK (skipped=5)**.
- 2026-07-01 — **Epic G1 complete (G1.1 + G1.2 ✅).** Added the `src/dynamix/webapp/` package
  (`__init__.py`, `launch.py`, `app.py`), a repo-root `app.py` shim, the `dynamix-gui` console
  script, and `streamlit>=1.36` in the `[gui]` extra. `launch.py` shells `python -m streamlit run
  app.py` and degrades gracefully with a clear hint when Streamlit is absent (verified: prints the
  hint, returns 1). `app.py` is the shell: title, sidebar step-nav (Home/Data/Train/Forecast),
  placeholder status panel, stub page bodies (guarded by `if __name__ == "__main__"` so it renders
  only under `streamlit run`). Red test `tests/integration/test_gui_packaging.py` (webapp + launcher
  import without Streamlit; pyproject declares the extra + script; root shim exists) — green.
  **Live-verified** after `pip install -e .[gui]` (Streamlit 1.58): `dynamix-gui` registered; a
  headless `streamlit.testing.v1.AppTest` render loads with no exception, shows the title, exposes
  the 4-step sidebar nav, and navigates all four pages cleanly. Suite: **114 tests, OK (skipped=5)**
  (the "imports without streamlit" guard still holds — our modules never import Streamlit outside
  `app.py`).
