# GUI Implementation Plan — Streamlit (v2: Beyond the Core Loop)

Follow-on to [GUI_PLAN.md](GUI_PLAN.md) (v1, complete). v2 adds the remaining, non-core-loop pages
and polish. Same principles: the GUI **wraps the existing CLIs** as subprocesses (via the v1
`dynamix.webapp.runner`, which already builds `optimize` / `report` / `single_series` commands) and
reimplements no pipeline logic. All non-UI logic lives in pure, Streamlit-free helpers unit-tested
by the `webapp` layer; Streamlit views are thin and validated by per-task `AppTest` checks.

**Status: v2 COMPLETE ✅ (all 5 epics V1–V5).** V1–V4 built; V5 resolved as "keep both". The GUI now
covers the full CLI surface, click-driven. Suite: 163 tests, OK.

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

# EPIC V1 — Optimize & Score page  ✅
`priority:P1` · `type:feature`

**What.** A page that runs `--action optimize` and shows the honest verdict: per-optimizer
realized `>=H` rate vs the random-baseline base rate, `net_eur` vs baseline (`edge_eur`), and
`q_any` calibration (ECE/Brier) — the E1 scoreboard, click-driven.

**Why.** The core loop makes tickets; this page tells the user whether the strategy actually beats
a fair random control. It surfaces the project's central honesty feature in the GUI.

**Definition of done.** From a StatGrid, the user runs optimize and sees the scoreboard table +
a one-line verdict; gated with "train first" when no StatGrid exists.

### Task V1.1 — Scoreboard/summary parser (pure) ✅
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

### Task V1.2 — Optimize & Score page UI ✅
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

# EPIC V2 — Reports page  ✅
`priority:P2` · `type:feature`

**What.** Wrap `stat_report` so the user can render a human-readable report from a training
checkpoint without the terminal.

**Why.** The backtest report (hit distribution, overlay witnesses) is useful and currently
CLI-only.

**Definition of done.** The user picks a checkpoint (default latest), runs the report, and reads
it in the page.

### Task V2.1 — Report locator (pure) ✅
`type:feature` · `layer:webapp` · `effort:S`
**What.** Helper to find the newest report file `stat_report` writes (under
`Output/Reports/...`), returning its path + text. Degrades safely when absent.
- **Red** — `tests/webapp/test_report_io.py`: over temp dirs, find the newest report; missing → None.
- **Green** — implement (confirm the report path/naming from `stat_report` when implementing).
**Acceptance criteria**
- [ ] Newest report resolved by mtime; missing dir → clean "no report yet".

### Task V2.2 — Reports page UI ✅
`type:feature` · `layer:ui` · `effort:S`
**What.** Checkpoint text input (default `latest`); Advanced (`--show-multihit`, `--max-per-hit`);
**Generate report** button via `render_job_panel`; on success render the report text (from V2.1)
in a scrollable code block + a download button.
**Acceptance criteria** *(manual + AppTest)*
- [ ] Report generates and its text renders; options change the argv exactly as the CLI would.

---

# EPIC V3 — Quick single-series  ✅
`priority:P2` · `type:feature`

**What.** Wrap `run_cli` for a fast per-series peek (no StatGrid needed).

**Why.** A lightweight "what does one series look like next?" view, matching the manual's extra tool.

**Definition of done.** The user picks a series + horizon and sees the model outputs.

### Task V3.1 — Single-series page UI ✅
`type:feature` · `layer:ui` · `effort:S`
**What.** Target select (`All` or `TS_1..TS_7`), horizon number, window / no-window; **Run** button
via `render_job_panel` (`single_series` action); show the run's output (the log/table) live. Banner
when models are missing (output will be `N/A`).
**Acceptance criteria** *(manual + AppTest)*
- [ ] Run streams output; target/horizon/window flags map to the exact argv.
- [ ] Models-missing banner shown when applicable.

---

# EPIC V4 — Charts & exports  ✅
`priority:P3` · `type:feature`

**What.** Add simple charts (calibration reliability, ROI/edge per optimizer) and richer downloads.

**Why.** A picture makes the honesty verdict easier to read for non-technical users.

**Definition of done.** The Optimize page (and Home) show at least one chart derived from the
written diagnostics, with a download.

### Task V4.1 — Diagnostics/calibration readers (pure) ✅
`type:feature` · `layer:webapp` · `effort:M`
**What.** Pure readers turning the written diagnostics/calibration files into tidy DataFrames
(reliability bins; per-optimizer edge history).
- **Red** — `tests/webapp/test_charts_data.py`: parse sample files → expected frames; missing → empty.
**Acceptance criteria**
- [ ] Sample diagnostics parse to the expected frames; missing files degrade to empty.

### Task V4.2 — Charts on the Optimize/Home pages ✅
`type:feature` · `layer:ui` · `effort:M`
**What.** Render a reliability curve and an edge-per-optimizer bar chart (Streamlit/Plotly) from
V4.1; add CSV/PNG downloads.
**Acceptance criteria** *(manual)*
- [ ] Charts render from real diagnostics; downloads work; no errors when data is absent.

---

# EPIC V5 — Retire Tkinter *(decision-gated)*  ✅ (Resolved: keep both)
`priority:P3` · `type:chore`

**What.** Once Streamlit covers the workflow, either (a) redirect `gui.py` / the launcher to the
Streamlit app, or (b) remove the Tkinter GUI. **Requires an explicit user go/no-go** — it removes a
working feature.

**Why.** One GUI to maintain; less confusion.

**Definition of done.** A single, documented GUI path; the manual/README reflect the decision.

### Task V5.1 — Decision + redirect/removal ✅ (Decision: keep both — no removal)
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

## Progress log

- 2026-07-01 — **Epic V5 resolved → v2 GUI plan DONE (all 5 epics).** User decided **keep both** GUIs:
  no code removed; the legacy Tkinter GUI (`python gui.py`) and the Streamlit GUI (`dynamix-gui`)
  coexist (both already documented in the manual §12 + README). v2 is complete — the Streamlit GUI
  now covers the whole workflow plus Optimize & Score, Reports, Single-series, and charts, all
  click-driven and equivalent to the CLI.
- 2026-07-01 — **Epic V4 complete (V4.1 + V4.2 ✅).** Added `dynamix.webapp.charts_data` — pure,
  Streamlit-free `load_calibration(path)` (reads `calibration_current.csv`: `optimizer,
  hit_threshold, bin_lo, bin_hi, n, empirical, avg_p`; numeric-coerced; missing → empty frame with
  the expected columns), `reliability_curve(df, optimizer, hit_threshold)` (tidy `(avg_p, empirical)`
  sorted), and a `latest_calibration()` locator. Red→Green `tests/webapp/test_charts_data.py`
  (4 tests). Added charts to the Optimize page's scoreboard renderer: an **edge-per-optimizer bar
  chart** (from the scoreboard) and a **reliability curve** (observed vs a "perfect" diagonal, with
  an optimizer selector), plus a calibration CSV download. **Live-verified** via `AppTest` over temp
  `DYNAMIX_OUTPUT_DIR` (summary + calibration present): the page renders with no exception and both
  chart subheaders ("Edge per optimizer (EUR)", "Reliability (calibration)") appear. Suite:
  **163 tests, OK (skipped=5)**. Only V5 (retire Tkinter, decision-gated) remains.
- 2026-07-01 — **Epic V2 complete (V2.1 + V2.2 ✅).** Added `dynamix.webapp.report_io` — pure,
  Streamlit-free `latest_report(reports_dir)` (newest `report_*.txt` under `Output/Reports/` by
  mtime, ignoring non-report files) and `read_report(path)`; missing dir/file → `None`. Red→Green
  `tests/webapp/test_report_io.py` (4 tests). Added the gated **Reports** page: a checkpoint input
  (default `latest`), Advanced (`--show-multihit`, `--max-per-hit`), a **Generate report** button
  via `render_job_panel`, and an on-success renderer that shows the newest report text in a code
  block + `.txt` download. **Live-verified** via `AppTest` over temp `DYNAMIX_OUTPUT_DIR`: no
  StatGrid → gate + no button; with training + a `report_*.txt`, the Generate button appears, ticking
  show-multihit yields argv `… -m dynamix.entrypoints.stat_report --checkpoint latest --show-multihit`,
  and an injected finished job renders the report text. Suite: **159 tests, OK (skipped=5)**.
- 2026-07-01 — **Epic V3 complete (V3.1 ✅).** Added the **Single series** page (wraps `run_cli` via
  the existing `single_series` runner action): a series selector (`All series` or `TS_1..TS_7`), a
  horizon input, an Advanced expander (`--no-window` / `--window`), and a **Run** button through
  `render_job_panel` that streams the model output live; a models-missing banner when the forecast
  deps are absent (output would be `N/A`). No StatGrid needed. **Live-verified** via `AppTest`: page
  renders, models-missing banner shows, and selecting `TS_3` + horizon 7 + no-window produces the
  exact argv `… -m dynamix.entrypoints.run_cli --target TS_3 --horizon 7 --no-window` (capturing
  monkeypatch, no real run). UI-only; argv covered by the G4 runner tests. Suite: **155 tests, OK
  (skipped=5)**.
- 2026-07-01 — **Epic V1 complete (V1.1 + V1.2 ✅).** Added `dynamix.webapp.optimize_results` —
  pure, Streamlit-free `load_summary(path) -> SummaryView` parsing the optimizer's
  `summary_current.json` (`opt_diagnostics.write_final_summary`, under `Output/Reports/Optimization/`):
  its `scoreboard` (keyed by optimizer → `realized_ge_H_rate`/`base_rate_ge_H`/`qany_ece`/`net_eur`/
  `baseline_net_eur`/`edge_eur`) becomes tidy `scoreboard_rows()` with an **EDGE / no-edge** verdict,
  plus `any_edge()` and a `latest_summary()` locator (prefers `summary_current.json`, else newest
  `summary_*.json`). Red→Green `tests/webapp/test_optimize_results.py` (5 tests). Added the gated
  **4. Optimize & Score** page: a **Run optimize** button (`--action optimize --run-id latest
  --optimizer all`) via `render_job_panel`, Advanced (`--optimizer` incl. an evo opt-in heads-up,
  `--seed`), and an on-success renderer that loads the latest summary into a scoreboard table +
  edge banner + CSV download. **Live-verified** via `AppTest` over temp `DYNAMIX_OUTPUT_DIR`: no
  StatGrid → gate + no button; StatGrid + summary → Run button, and an injected finished job renders
  the scoreboard (`Optimizer … edge_eur, verdict` with EDGE/no-edge) and the "beat the random
  control" banner. Suite: **155 tests, OK (skipped=5)**.

## Resolved decision

- **V5 (retire Tkinter):** user chose **keep both** (2026-07-01). No code removed; the legacy Tkinter
  GUI (`python gui.py`) and the Streamlit GUI (`dynamix-gui`) coexist. The manual (§12) and README
  already document both. Can be revisited later.
