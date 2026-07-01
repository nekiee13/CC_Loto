# GUI Implementation Plan — Streamlit (v2: Beyond the Core Loop)

Follow-on to [GUI_PLAN.md](GUI_PLAN.md) (v1, complete). v2 adds the remaining, non-core-loop pages
and polish. Same principles: the GUI **wraps the existing CLIs** as subprocesses (via the v1
`dynamix.webapp.runner`, which already builds `optimize` / `report` / `single_series` commands) and
reimplements no pipeline logic. All non-UI logic lives in pure, Streamlit-free helpers unit-tested
by the `webapp` layer; Streamlit views are thin and validated by per-task `AppTest` checks.

## How to use this plan

- One task at a time, Red → Green (→ Refactor) where there is testable logic.
- Tags: `type:` (feature|chore|test) · `layer:` (webapp|ui|contract|packaging) · `effort:` S|M|L.
- **Status legend:** ⬜ Todo · 🟡 In progress · 🔵 In review · ✅ Done · ⏸️ Blocked · ❌ Dropped

## Scope (v2)

| Epic | What | Priority |
|------|------|----------|
| V1 — Optimize & Score page | Run `--action optimize`; show the honest EV/ROI + calibration scoreboard | P1 |
| V2 — Reports page | Wrap `stat_report`; render the report | P2 |
| V3 — Quick single-series | Wrap `run_cli --target/--horizon` | P2 |
| V4 — Charts & exports | Calibration/ROI charts + richer downloads | P3 |
| V5 — Retire Tkinter | Redirect/remove the legacy Tkinter GUI once Streamlit covers everything | P3 (decision-gated) |

**Suggested order:** V1 → V3 → V2 → V4 → V5 (V1 is infra-ready and highest value; V3 is small; V4
builds on V1's data; V5 is last and needs an explicit go/no-go).

---

# EPIC V1 — Optimize & Score page
`priority:P1` · `type:feature`

**What.** A page that runs `--action optimize` and shows the honest verdict: per-optimizer
realized `>=H` rate vs the random-baseline base rate, `net_eur` vs baseline (`edge_eur`), and
`q_any` calibration (ECE/Brier) — the E1 scoreboard, click-driven.

**Why.** The core loop makes tickets; this page tells the user whether the strategy actually beats
a fair random control. It surfaces the project's central honesty feature in the GUI.

**Definition of done.** From a StatGrid, the user runs optimize and sees the scoreboard table +
a one-line verdict; gated with "train first" when no StatGrid exists.

### Task V1.1 — Scoreboard/summary parser (pure)
`type:feature` · `layer:webapp` · `effort:M`
**What.** `dynamix.webapp.optimize_results` (or extend `results.py`): `load_summary(path) ->
SummaryView` parsing the optimizer's `summary_current.json` (the E1.4 `scoreboard` + `baseline`
keys) into tidy per-optimizer rows (`optimizer, realized_ge_H_rate, base_rate_ge_H, net_eur,
baseline_net_eur, edge_eur, qany_ece, qany_brier`) plus a `latest_summary()` locator. Degrades to
an empty view on missing/partial files.
- **Red** — `tests/webapp/test_optimize_results.py`: parse a sample summary into the expected rows;
  missing/malformed → empty view (no raise). *(Confirm the real `summary_current.json` shape +
  location from `opt_diagnostics.write_final_summary` when implementing.)*
- **Green** — implement the parser + locator.
**Acceptance criteria**
- [ ] Sample summary parses to the correct scoreboard rows + verdict fields; bad input is safe.
- [ ] `latest_summary()` finds the newest written summary under the optimization dir.

### Task V1.2 — Optimize & Score page UI
`type:feature` · `layer:ui` · `effort:M`
**What.** Gated on `has_training`. A **Run optimize** button (`--action optimize --run-id latest
--optimizer all`) via `render_job_panel`; Advanced expander (`--optimizer`, `--seed`, slice flags);
on success, render the scoreboard as a table with an "EDGE / no edge" verdict per optimizer and a
plain-language summary. CSV download.
- **Green** — wire to `runner` + `V1.1` parser; reuse the live-log panel.
**Acceptance criteria** *(manual + AppTest)*
- [ ] No StatGrid → "train first" gate, no run button.
- [ ] With a StatGrid, running optimize streams progress and then shows the scoreboard table.
- [ ] Advanced `--optimizer evo` produces the exact argv (opt-in; heads-up shown).

---

# EPIC V2 — Reports page
`priority:P2` · `type:feature`

**What.** Wrap `stat_report` so the user can render a human-readable report from a training
checkpoint without the terminal.

**Why.** The backtest report (hit distribution, overlay witnesses) is useful and currently
CLI-only.

**Definition of done.** The user picks a checkpoint (default latest), runs the report, and reads
it in the page.

### Task V2.1 — Report locator (pure)
`type:feature` · `layer:webapp` · `effort:S`
**What.** Helper to find the newest report file `stat_report` writes (under
`Output/Reports/...`), returning its path + text. Degrades safely when absent.
- **Red** — `tests/webapp/test_report_io.py`: over temp dirs, find the newest report; missing → None.
- **Green** — implement (confirm the report path/naming from `stat_report` when implementing).
**Acceptance criteria**
- [ ] Newest report resolved by mtime; missing dir → clean "no report yet".

### Task V2.2 — Reports page UI
`type:feature` · `layer:ui` · `effort:S`
**What.** Checkpoint text input (default `latest`); Advanced (`--show-multihit`, `--max-per-hit`);
**Generate report** button via `render_job_panel`; on success render the report text (from V2.1)
in a scrollable code block + a download button.
**Acceptance criteria** *(manual + AppTest)*
- [ ] Report generates and its text renders; options change the argv exactly as the CLI would.

---

# EPIC V3 — Quick single-series
`priority:P2` · `type:feature`

**What.** Wrap `run_cli` for a fast per-series peek (no StatGrid needed).

**Why.** A lightweight "what does one series look like next?" view, matching the manual's extra tool.

**Definition of done.** The user picks a series + horizon and sees the model outputs.

### Task V3.1 — Single-series page UI
`type:feature` · `layer:ui` · `effort:S`
**What.** Target select (`All` or `TS_1..TS_7`), horizon number, window / no-window; **Run** button
via `render_job_panel` (`single_series` action); show the run's output (the log/table) live. Banner
when models are missing (output will be `N/A`).
**Acceptance criteria** *(manual + AppTest)*
- [ ] Run streams output; target/horizon/window flags map to the exact argv.
- [ ] Models-missing banner shown when applicable.

---

# EPIC V4 — Charts & exports
`priority:P3` · `type:feature`

**What.** Add simple charts (calibration reliability, ROI/edge per optimizer) and richer downloads.

**Why.** A picture makes the honesty verdict easier to read for non-technical users.

**Definition of done.** The Optimize page (and Home) show at least one chart derived from the
written diagnostics, with a download.

### Task V4.1 — Diagnostics/calibration readers (pure)
`type:feature` · `layer:webapp` · `effort:M`
**What.** Pure readers turning the written diagnostics/calibration files into tidy DataFrames
(reliability bins; per-optimizer edge history).
- **Red** — `tests/webapp/test_charts_data.py`: parse sample files → expected frames; missing → empty.
**Acceptance criteria**
- [ ] Sample diagnostics parse to the expected frames; missing files degrade to empty.

### Task V4.2 — Charts on the Optimize/Home pages
`type:feature` · `layer:ui` · `effort:M`
**What.** Render a reliability curve and an edge-per-optimizer bar chart (Streamlit/Plotly) from
V4.1; add CSV/PNG downloads.
**Acceptance criteria** *(manual)*
- [ ] Charts render from real diagnostics; downloads work; no errors when data is absent.

---

# EPIC V5 — Retire Tkinter *(decision-gated)*
`priority:P3` · `type:chore`

**What.** Once Streamlit covers the workflow, either (a) redirect `gui.py` / the launcher to the
Streamlit app, or (b) remove the Tkinter GUI. **Requires an explicit user go/no-go** — it removes a
working feature.

**Why.** One GUI to maintain; less confusion.

**Definition of done.** A single, documented GUI path; the manual/README reflect the decision.

### Task V5.1 — Decision + redirect/removal
`type:chore` · `layer:contract` · `effort:S`
**What.** On approval: repoint `python gui.py` (and/or the `gui` entry) to Streamlit, or delete the
Tkinter app; update `User_manual.md` §12 and README to name a single GUI.
**Acceptance criteria**
- [ ] Exactly one documented GUI path; no dangling references to the removed one.
- [ ] Explicit user approval recorded before removal.

---

## Cross-epic Definition of Done (v2)

Using **only the GUI**, a user can additionally: run an optimize and read the honest scoreboard;
generate and read a backtest report; do a quick single-series forecast; and see at least one chart —
all click-driven, equivalent to the CLI, with the core suite green with and without the `[gui]` extra.

## Dependency graph

```
v1 (done) ─▶ V1 (optimize+score) ─▶ V4 (charts)
          ├▶ V2 (reports)
          ├▶ V3 (single-series)
          └▶ V5 (retire Tkinter, gated, last)
```

## Open decision

- **V5 (retire Tkinter)** needs your call: keep both GUIs, redirect Tkinter → Streamlit, or remove
  Tkinter. Default until you decide: **keep both** (no change).
