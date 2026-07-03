# Objective Project Critique And Upgrade Plan

## Source Context

This plan is based on the supplied project documents, including the README, architecture notes, architectural analysis, SRS, AS-IS snapshot, user manual, GUI implementation plans, roadmap, TDD plan, and progress tracker.

## 1. Context Analysis

### 1.1 System Shape

The project is a three-stage lottery forecasting and ticket-selection system. Historical draw data is read from `DATA.csv`, forecasts are generated for seven positional series, backtests are exported as a candidate grid, and an optimizer selects up to five tickets per draw.

The architecture has strong operational separation:

1. **Stage 1 — Forecasting**  
   Forecasts are produced from DynaMix, PCE-NARX, and Darts model families. Optional dependencies are fail-soft, so missing model runtimes disable only the affected model families.

2. **Stage 2 — Backtest and StatGrid export**  
   Rolling-origin backtests produce rows per draw step, series, model, and rounding mode. These rows contain prediction, rounded value, true value, hit flag, error, and provenance.

3. **Stage 3 — Optimization**  
   The optimizer loads a StatGrid run, uses leakage-safe TRAIN/EVAL slicing, fits a calibrated hit-probability model, builds ticket pools, and selects portfolios using greedy, MILP, bandit, or evolutionary strategies.

The system also includes CLI entrypoints, Streamlit GUI flows, a legacy Tkinter GUI, reporting tools, checkpoints, diagnostics, and calibration reports. The Streamlit GUI now covers the core loop and extended pages, including Optimize & Score, Reports, Single-series, charts, and downloads.

### 1.2 Current Implementation State

The project has already moved past the original roadmap baseline. The earlier high-priority work has been completed:

- packaging and import hygiene were finished;
- CI and import smoke tests were added;
- honest EV/ROI and calibration scoreboard was implemented;
- `stat.py` was decomposed and candidate-grid logic was extracted;
- analytical core tests and coverage were added;
- the evolutionary optimizer was implemented as a real seeded genetic algorithm;
- rounding-mode de-duplication was added behind a flag;
- logging, config cleanup, artifact hygiene, and determinism-scope cleanup were completed.

The progress tracker marks all 21 TDD-plan tasks as complete. It also lists later post-plan fixes for forecast-domain clamping, Streamlit progress tracking, Tkinter display clamping, Darts progress events, and conda/CUDA installation documentation.

This means the next upgrade plan should not repeat the completed roadmap as future work. The next plan should build on the strengthened foundation.

### 1.3 Major Strengths

#### Strength 1 — Leakage discipline

The optimizer is designed so truth tables, features, and the calibrated model are trained only on TRAIN data. Resume checks also guard against mismatched grid IDs, fingerprints, config identities, and slices. This is a strong scientific and engineering property.

#### Strength 2 — Honest evaluation has been added

The project now includes a scoreboard with realized success rate, base rate, q-any calibration, net EUR, baseline net EUR, and edge EUR. This directly addresses the original risk that a complex model could create false confidence in a random domain.

#### Strength 3 — File-based stage contracts support auditability

The StatGrid, checkpoints, optimizer state, diagnostics, and summaries allow each stage to be inspected and resumed independently. This supports debugging, reproducibility of Stage 3, and user trust.

#### Strength 4 — GUI is broad and beginner-friendly

The Streamlit GUI wraps the existing CLIs instead of reimplementing pipeline logic. This keeps behavior aligned between GUI and CLI. The GUI supports the main loop, live logs, Stop, guardrails, optimization, reports, single-series forecasts, charts, and downloads.

#### Strength 5 — Optional dependency boundaries are well understood

The system degrades when model libraries are absent. Testing was adjusted so optional model absence causes skips rather than false failures. This is important because one recorded environment showed that Python 3.14 and missing compiler/tooling blocked model installation.

---

## 2. Critique

### 2.1 Main Risk: The Project Is Still Domain-Risky

The system now reports honest economic and calibration results, but the core application remains a lottery domain. The SRS states that no predictive efficacy is claimed for a genuinely random lottery. This remains the most important caveat. Any future upgrade must keep the “no guaranteed edge” message visible in reports, GUI, docs, and summaries.

**Critique:**  
The project now measures edge better, but a user may still over-read any short-term positive result. The system needs stronger statistical uncertainty reporting around the scoreboard.

### 2.2 Model Runtime Is Still Fragile Across Environments

The AS-IS file showed that none of the three model families could run in one environment because Python 3.14 lacked needed wheels and no compiler was available. Later documentation added a conda/CUDA install path, but runtime portability still depends on heavy optional stacks such as torch, darts, and chaospy.

**Critique:**  
The project has install documentation and fail-soft behavior, but it still needs a stronger model-runtime validation command. A user should be able to run one health command and receive a clear status report: installed, missing, GPU/CPU, usable, and tested.

### 2.3 Forecast Domain Safety Was Fixed Late, So It Needs Contract Protection

Post-plan fixes added clamping so tickets and forecast displays stay within valid lottery domains. This fix covered Stage 3 tickets, Stage 1 console output, Streamlit, and Tkinter display paths.

**Critique:**  
Because impossible values appeared during live testing, valid-domain enforcement should become a formal cross-stage contract. The current fix should be protected by end-to-end tests over all output paths and documented as a non-negotiable invariant.

### 2.4 Two GUI Paths Remain A Maintenance Cost

The project keeps both Streamlit and Tkinter GUIs. The v2 GUI plan records the decision to keep both.

**Critique:**  
Keeping both is acceptable, but it creates duplicated display responsibilities. The late Tkinter clamping fix confirms this risk. Shared formatting and parsing helpers should be used by both GUI paths and CLI output to avoid repeat drift.

### 2.5 Candidate Grid Evolution Needs Versioning

The candidate-grid schema is a cross-stage contract, and the SRS warns that schema changes must be migrated in both producer and consumer. Rounding de-duplication was later added behind a flag and is re-expanded losslessly on load.

**Critique:**  
The existing migration is safe, but the grid format needs explicit schema versioning. Without a version field and migration registry, future grid changes may become risky.

### 2.6 Statistical Validation Should Go Beyond One TRAIN/EVAL Split

The optimizer uses TRAIN/EVAL slicing and reports calibration and economics. This is a good base.

**Critique:**  
A single split can be noisy. A lottery-like domain requires rolling walk-forward validation, confidence intervals, bootstrap intervals, and random-baseline distributions. Without uncertainty bands, edge EUR can look more certain than it is.

### 2.7 Strategy Comparison Needs Stronger Decision Rules

The system now has greedy, MILP, bandit, and real evolutionary search.

**Critique:**  
Strategy results should be ranked with uncertainty and stability. A high edge in one EVAL window may not be robust. A “recommended strategy” should require stable performance across windows and random seeds, not only one summary result.

### 2.8 Documentation Has Grown, But It May Drift

The documentation set includes README, architecture, SRS, AS-IS, user manual, roadmap, GUI plans, TDD plan, and progress tracker. Some documents are descriptive snapshots, while others are living trackers.

**Critique:**  
The documentation volume is now large. The risk is stale or conflicting statements. A documentation index, status labels, and tests for command examples would reduce confusion.

---

## 3. Areas For Improvement

### AFI-1 — Add statistical uncertainty to the honest scoreboard

The scoreboard should include confidence intervals, bootstrap ranges, and baseline distribution percentiles. This would show whether “edge” is likely meaningful or likely noise.

### AFI-2 — Add a model-runtime health check

A dedicated health command should test imports, model availability, GPU/CPU device, minimal forecast execution, and known failure causes.

### AFI-3 — Formalize valid-value domain contracts

All outputs should guarantee series-specific domains: TS_1..TS_5 within 1–50 and TS_6..TS_7 within 1–12, based on the current domain policy. Post-plan fixes already added this behavior, so contract tests should lock it.

### AFI-4 — Version the StatGrid schema

The StatGrid should carry a schema version. Consumers should use a migration layer for old and new layouts.

### AFI-5 — Add walk-forward validation

The optimizer should be tested over multiple rolling windows. Results should include mean, median, worst case, best case, standard deviation, and confidence bands.

### AFI-6 — Add strategy stability reporting

Strategy summaries should show stability across windows and seeds. The recommendation should be based on robust performance, not a single split.

### AFI-7 — Consolidate UI output formatting

CLI, Streamlit, and Tkinter should share the same display helper for tickets, values, missing values, and q scores.

### AFI-8 — Add command-example tests for docs

Commands from README and User Manual should be extracted and smoke-tested where safe, especially `--help` and dry-run-like flows.

### AFI-9 — Add a lightweight synthetic demo dataset mode

A tiny built-in fixture or generated synthetic dataset would allow demos, CI, and tutorials without relying on full operational data.

### AFI-10 — Improve observability

Run summaries should include dependency status, model family activation, runtime duration by stage, row counts, grid size, and warning counts.

---

# 4. Project Upgrade Plan

## Milestone U1 — Scientific Reliability Upgrade

**Goal:** Make evaluation more statistically honest and less dependent on one split.

---

## EPIC U1 — Scoreboard Uncertainty And Baseline Distributions

**Priority:** P0  
**Type:** feature / analytics  
**Status:** Proposed

### What

The optimizer summary should be extended with uncertainty metrics: bootstrap confidence intervals for net EUR and edge EUR, random-baseline distribution percentiles, and confidence bands for realized ≥H rate.

### Why

The project already reports honest EV/ROI and calibration metrics. However, one EVAL result can be noisy. Uncertainty bands make the verdict harder to overinterpret.

### Tasks

#### Task U1.1 — Add bootstrap confidence intervals for strategy economics

**What:**  
Add a pure function that resamples EVAL draws with replacement and computes confidence intervals for net EUR, edge EUR, and realized ≥H rate.

**Why:**  
A single result is not enough in a noisy lottery domain. Bootstrap intervals show the likely range of outcomes.

**Acceptance criteria:**

- Given fixed seed and diagnostic rows, bootstrap output is deterministic.
- Summary JSON includes `net_eur_ci_low`, `net_eur_ci_high`, `edge_eur_ci_low`, and `edge_eur_ci_high`.
- Tests use a small fixture with known resample behavior.
- No model dependencies are required.

#### Task U1.2 — Add random-baseline distribution percentiles

**What:**  
Run many seeded random baselines and report p5, p50, p95, and strategy percentile rank.

**Why:**  
A single random baseline can be unlucky or lucky. A distribution gives a fairer control.

**Acceptance criteria:**

- Summary JSON includes baseline p5, p50, p95, and strategy percentile.
- Same seed produces the same baseline distribution.
- GUI Optimize & Score page displays the percentile rank.

#### Task U1.3 — Add a conservative verdict label

**What:**  
Add labels such as `NO_EDGE`, `WEAK_EDGE`, `UNCERTAIN`, and `ROBUST_EDGE`.

**Why:**  
Plain labels help beginner users read the result safely.

**Acceptance criteria:**

- `ROBUST_EDGE` is shown only when edge CI is above zero and calibration is within a configured threshold.
- `NO_EDGE` is shown when edge CI crosses or falls below zero.
- User Manual explains the labels in simple language.

---

## EPIC U2 — Walk-Forward Evaluation

**Priority:** P0  
**Type:** feature / validation  
**Status:** Proposed

### What

Add a walk-forward evaluation mode that repeats TRAIN/EVAL over multiple rolling windows and aggregates results.

### Why

One split can hide instability. Multiple windows provide stronger evidence about whether a strategy is stable.

### Tasks

#### Task U2.1 — Add walk-forward slice generator

**What:**  
Create a function that produces rolling TRAIN/EVAL slice pairs from ordered dataset indices.

**Why:**  
Walk-forward validation needs a safe and repeatable slice plan.

**Acceptance criteria:**

- Slice generator produces non-overlapping EVAL windows.
- TRAIN always occurs before EVAL.
- Tests cover short data, exact boundaries, and insufficient-history behavior.

#### Task U2.2 — Add `--validation walk-forward` mode

**What:**  
Extend optimizer CLI and GUI advanced options with a walk-forward mode.

**Why:**  
The existing optimizer flow should remain default, while deeper validation should be available.

**Acceptance criteria:**

- Existing optimize behavior is unchanged by default.
- Walk-forward mode writes a separate summary file.
- GUI shows progress across folds.

#### Task U2.3 — Aggregate fold results

**What:**  
Report mean, median, min, max, standard deviation, and fold count for each strategy.

**Why:**  
Strategy stability should be visible in one place.

**Acceptance criteria:**

- Summary includes per-fold rows and aggregate rows.
- CSV export is available.
- Charts show edge EUR by fold.

---

## EPIC U3 — Model Runtime Health And Environment Diagnostics

**Priority:** P0  
**Type:** feature / usability  
**Status:** Proposed

### What

Add a dedicated health-check command and GUI page for model availability, dependency status, Python version, GPU status, data health, and output-path writability.

### Why

One recorded environment showed that model availability can fail because of Python version, missing wheels, missing compiler, and missing heavy dependencies. A single health report would reduce setup confusion.

### Tasks

#### Task U3.1 — Add `dynamix-health` command

**What:**  
Create a console command that checks Python version, package install state, optional dependencies, model availability, GPU/CPU device, DATA.csv status, and Output path access.

**Why:**  
Users need one command that explains whether the system can forecast.

**Acceptance criteria:**

- Command exits with code 0 for healthy or degraded-but-usable states.
- Command exits non-zero only for fatal issues.
- JSON and human-readable output modes are supported.
- Missing torch, darts, or chaospy are shown as warnings, not fatal errors.

#### Task U3.2 — Add minimal model smoke test

**What:**  
Add an optional `--deep` health mode that tries a tiny forecast call for each installed model family.

**Why:**  
Import success does not prove runtime success.

**Acceptance criteria:**

- Each model family is reported as `available`, `missing`, `failed`, or `skipped`.
- Failures include clear next steps.
- The test is timeout-protected.

#### Task U3.3 — Add GUI Health page

**What:**  
Add a Streamlit page showing the same health report.

**Why:**  
Click-only users need the same setup clarity as CLI users.

**Acceptance criteria:**

- Health page uses the pure health-check helper.
- Status badges are shown for data, models, GPU, MILP, and output folder.
- JSON report can be downloaded.

---

## EPIC U4 — StatGrid Schema Versioning And Migration

**Priority:** P1  
**Type:** architecture / contract  
**Status:** Proposed

### What

Add an explicit StatGrid schema version, migration helpers, and compatibility tests.

### Why

The candidate grid is a cross-stage contract. Rounding de-duplication already introduced a second shape, even though it is re-expanded on load. Future changes require safer migration.

### Tasks

#### Task U4.1 — Add schema metadata file

**What:**  
Write `schema.json` into each StatGrid run folder with schema version, producer version, export mode, dedupe flag, and required columns.

**Why:**  
Consumers should know what format is being loaded.

**Acceptance criteria:**

- New StatGrid exports include `schema.json`.
- Legacy grids without schema still load as version `0`.
- Contract tests cover both cases.

#### Task U4.2 — Add migration registry

**What:**  
Create a small migration layer that converts legacy and deduped grids into the optimizer’s canonical in-memory format.

**Why:**  
Loading logic should not become scattered across `opt_data`.

**Acceptance criteria:**

- Version 0, version 1, and deduped grids load into the same canonical DataFrame shape.
- Loader logs the detected schema version.
- Unknown future versions fail with a clear message.

#### Task U4.3 — Add schema compatibility tests

**What:**  
Add golden fixtures for legacy, deduped, and schema-versioned grids.

**Why:**  
A schema contract must be testable.

**Acceptance criteria:**

- Fixtures load without model dependencies.
- Canonical output is identical where expected.
- Required columns are enforced.

---

## EPIC U5 — Valid-Domain Contract Across All Outputs

**Priority:** P1  
**Type:** quality / contract  
**Status:** Proposed

### What

Formalize and test valid ball domains across CLI, optimizer tickets, Streamlit, Tkinter, JSON, CSV, and reports.

### Why

Late fixes were needed after impossible values appeared. This invariant should become part of the system contract.

### Tasks

#### Task U5.1 — Create shared domain helper

**What:**  
Move domain logic into one shared importable helper used by CLI, GUI, optimizer, and display layers.

**Why:**  
Multiple display paths caused drift.

**Acceptance criteria:**

- One helper defines domain, clamp, round, and missing-value display behavior.
- CLI, Streamlit, and Tkinter use the same helper.
- Existing behavior remains unchanged.

#### Task U5.2 — Add output-domain contract tests

**What:**  
Test forecast JSON, ticket tables, CLI output formatter, GUI parser output, and Tkinter formatter with out-of-range inputs.

**Why:**  
Every output path must reject or clamp impossible values.

**Acceptance criteria:**

- TS_1..TS_5 outputs are always 1–50.
- TS_6..TS_7 outputs are always 1–12.
- Missing or non-finite values render as missing, not `0`.

#### Task U5.3 — Add StatGrid domain diagnostics

**What:**  
Add a diagnostic count of raw model predictions that fall outside valid domains before clamping.

**Why:**  
Prediction quality should still be auditable even when output is safely clamped.

**Acceptance criteria:**

- Summary includes out-of-domain raw prediction counts by model and TS.
- Clamped display does not hide raw diagnostic counts.
- GUI shows a warning if out-of-domain counts are high.

---

## EPIC U6 — Strategy Stability And Recommendation Rules

**Priority:** P1  
**Type:** analytics / UX  
**Status:** Proposed

### What

Create a robust strategy recommendation layer based on edge, uncertainty, calibration, and fold stability.

### Why

The system has multiple optimizers. The best strategy should not be chosen from one noisy score.

### Tasks

#### Task U6.1 — Add strategy stability score

**What:**  
Compute a stability score from walk-forward fold results, calibration, and edge distribution.

**Why:**  
Stable performance is more useful than one high result.

**Acceptance criteria:**

- Score is deterministic.
- Score penalizes high variance and poor calibration.
- Tests cover stable-good, unstable-good, and stable-bad fixtures.

#### Task U6.2 — Add recommendation block

**What:**  
Add a summary section naming the recommended strategy or saying no strategy is recommended.

**Why:**  
Users need a safe final interpretation.

**Acceptance criteria:**

- Recommendation requires positive edge and acceptable calibration.
- No recommendation is made when uncertainty is too high.
- GUI displays the recommendation with a caution note.

#### Task U6.3 — Add seed sensitivity check

**What:**  
Run selected strategies across multiple seeds where applicable and report sensitivity.

**Why:**  
Results driven by seed behavior should be marked unstable.

**Acceptance criteria:**

- Summary includes seed count and seed variance.
- Default remains fast; deeper seed checks are opt-in.
- GUI advanced settings expose seed-check count.

---

## EPIC U7 — Documentation Governance And Drift Prevention

**Priority:** P2  
**Type:** docs / test  
**Status:** Proposed

### What

Add a documentation index, command-example tests, and status markers for snapshot vs. living documents.

### Why

The documentation set is large and useful, but stale docs can become a source of errors.

### Tasks

#### Task U7.1 — Add documentation index

**What:**  
Create `docs/INDEX.md` listing each document, purpose, status, and last updated date.

**Why:**  
Readers need a map of the documentation set.

**Acceptance criteria:**

- Every major document is listed.
- Documents are marked as `living`, `snapshot`, or `historical`.
- README links to the index.

#### Task U7.2 — Test safe command examples

**What:**  
Extract safe commands from README and User Manual and run smoke tests such as `--help`.

**Why:**  
Command examples should not drift after entrypoint or packaging changes.

**Acceptance criteria:**

- All documented console scripts support `--help`.
- Broken command examples fail CI.
- Long-running commands are excluded or tested in dry-run mode only.

#### Task U7.3 — Add docs freshness check

**What:**  
Add a simple check that warns when core docs have not been reviewed after major code changes.

**Why:**  
Architecture and SRS documents can become stale after refactors.

**Acceptance criteria:**

- Check runs in CI as non-blocking at first.
- Docs with stale dates are listed.
- Maintainer can mark documents reviewed.

---

## EPIC U8 — Observability And Run Audit Pack

**Priority:** P2  
**Type:** operations / reporting  
**Status:** Proposed

### What

Each run should produce a compact audit pack with environment, dependency state, data fingerprint, model activation, timing, warnings, grid sizes, and summary metrics.

### Why

The project is file-driven and audit-friendly. A single audit pack would make support and comparison easier.

### Tasks

#### Task U8.1 — Add run audit JSON

**What:**  
Write `audit.json` for stat and optimizer runs.

**Why:**  
Run conditions should be captured in one machine-readable file.

**Acceptance criteria:**

- Audit includes Python version, package version, command, args, data fingerprint, run id, start/end time, duration, dependency status, and warning count.
- Audit is written even if the run fails.
- Tests cover success and failure cases.

#### Task U8.2 — Add audit summary to GUI

**What:**  
Show latest run audit data on the Home and Reports pages.

**Why:**  
Users should see whether latest results came from a healthy run.

**Acceptance criteria:**

- Latest audit is located safely.
- GUI displays runtime, model families used, and warnings.
- Audit JSON can be downloaded.

#### Task U8.3 — Add performance trend report

**What:**  
Track runtime and row-count trends across runs.

**Why:**  
Backtest and optimization cost can grow over time.

**Acceptance criteria:**

- Trend CSV is appended after each run.
- GUI chart shows runtime by run.
- Large regressions trigger a warning.

---

## 5. Suggested Execution Order

1. **U3 — Health diagnostics**  
   Highest operational value. Reduces setup confusion.

2. **U5 — Valid-domain contract**  
   Protects a recently fixed correctness issue.

3. **U1 — Scoreboard uncertainty**  
   Strengthens honesty and reduces overinterpretation.

4. **U2 — Walk-forward validation**  
   Improves scientific validity.

5. **U4 — StatGrid schema versioning**  
   Makes future data-contract changes safer.

6. **U6 — Strategy recommendation rules**  
   Builds on uncertainty and walk-forward results.

7. **U8 — Audit pack**  
   Improves support and long-run tracking.

8. **U7 — Documentation governance**  
   Prevents drift after new capabilities land.

---

## 6. Compact GitHub-Issue Backlog

### P0

- **U3:** Add health-check CLI and GUI page.
- **U5:** Formalize valid output domains across all output paths.
- **U1:** Add uncertainty bands to the honest scoreboard.
- **U2:** Add walk-forward validation.

### P1

- **U4:** Add StatGrid schema versioning and migration.
- **U6:** Add stability-based strategy recommendation.

### P2

- **U8:** Add run audit packs and performance trends.
- **U7:** Add documentation governance and command-example tests.

---

## 7. Final Assessment

The project has matured from a fragile, partially packaged research pipeline into a stronger, test-driven, GUI-assisted, installable system with CI, honest scoreboards, improved contracts, and post-plan live-testing fixes. The strongest remaining upgrade path is no longer basic packaging or CI. The next useful step is statistical and operational hardening: uncertainty-aware scoreboards, walk-forward validation, model health checks, schema versioning, valid-domain contracts, and audit packs.

The main architectural principle should remain unchanged: forecasting, backtesting, and optimization should stay decoupled, testable, and auditable through explicit file contracts.
