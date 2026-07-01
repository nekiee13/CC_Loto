# Software Requirements Specification (SRS)

**System:** DynaMix Lottery Forecasting System
**Version:** reverse-engineered from source as of 2026-06-29
**Related:** [architecture.md](architecture.md) ·
[architectural_and_functional_analysis.md](architectural_and_functional_analysis.md) ·
[AS-IS.md](AS-IS.md)

> This SRS is *descriptive*: it specifies the requirements the existing implementation
> satisfies, recovered from the code, so they can be reviewed, tested, and evolved. Items
> inferred from implementation (rather than an original spec) are marked **(derived)**.

---

## 1. Introduction

### 1.1 Purpose
Specify the functional and non-functional requirements of the DynaMix Lottery Forecasting
System: a pipeline that forecasts 7 positional lottery series, backtests those forecasts, and
selects an optimized portfolio of up to 5 tickets per draw.

### 1.2 Scope
The system shall, from a CSV of historical draws:
1. produce per-series numeric forecasts using multiple models;
2. backtest forecasts via rolling-origin evaluation and export a labelled "candidate grid";
3. learn a calibrated hit-probability model and select a ticket portfolio maximizing the
   probability of achieving ≥ H position-hits;
4. emit diagnostics, calibration metrics, and next-step ticket forecasts.

Out of scope: ticket purchasing, live data ingestion, user authentication, and any claim of
predictive efficacy on a genuinely random lottery.

### 1.3 Definitions
| Term | Meaning |
|------|---------|
| TS / position | One of the 7 ordered series `TS_1..TS_7` in a draw |
| Event | A single draw row; identity is row order (`EventID`) in event mode |
| Candidate grid (StatGrid) | Per (step × ts × model × rounding) table with `pred/rounded/true/hit/abs_err` |
| `hit` | 1 if a rounded candidate equals the realized value, else 0 — the optimizer's label |
| Ticket | A 7-tuple of integers (one value per position) |
| `q` | Modelled probability a ticket achieves ≥ H hits |
| `q_any` | Probability ≥ 1 ticket in the portfolio succeeds |
| H / hit threshold | Minimum position-hits counted as success |
| Run id | Timestamped identifier for a StatGrid run or optimizer run |

### 1.4 References
IEEE Std 830 (structure); project source under `src/dynamix/`, `stat.py`, `opt/`,
`orchestrator.py`; configuration in `constants.py` and `opt/opt_config.py`.

---

## 2. Overall description

### 2.1 Product perspective
A standalone, file-driven, three-stage batch pipeline (forecast → backtest → optimize). Stages
are decoupled and communicate only through files on disk, enabling independent execution,
inspection, and resumption. **(derived)**

### 2.2 Product functions (summary)
Data loading/validation; multi-model forecasting; rolling-origin backtest with candidate-grid
export; conditional-probability modelling; portfolio optimization (4 strategies); next-step
ticket forecasting; checkpointing/resume; diagnostics, calibration, and reporting.

### 2.3 User classes
- **Operator** — runs the CLI stages, updates `DATA.csv`, reads tickets/reports.
- **Analyst/Developer** — tunes configuration, inspects StatGrid/state, extends models or
  strategies.
- **GUI user** — runs forecasts interactively via the Tkinter app.

### 2.4 Operating environment
Python (pure-Python entrypoints; no install step). Core libraries: pandas, numpy,
scikit-learn, plotly. Optional: torch + DynaMix HF model, darts, chaospy, pulp, tkinter. Runs
on the intended Windows runtime; portable to Linux/macOS subject to dependency availability.

### 2.5 Constraints
- Input must be `DATA.csv` with `Date, TS_1..TS_7`. **(derived)**
- TS values are treated as integers (validated/coerced). **(derived)**
- Filesystem paths are anchored to the repository root (env-overridable). **(derived)**

### 2.6 Assumptions and dependencies
- The operator manually updates `DATA.csv` over time.
- Optional model dependencies may be absent; the system must degrade, not fail. **(derived)**
- Sufficient history exists (≥ `STATS_MIN_HISTORY` for stats; ≥ `MIN_HISTORY_LENGTH` for
  core forecasting). **(derived)**

---

## 3. External interface requirements

### 3.1 Data interfaces
- **EIR-1** The system shall read draws from a CSV resolvable via `DYNAMIX_DATA_FILE` or the
  default `DATA.csv` at the repo root, with columns `Date, TS_1..TS_7`.
- **EIR-2** The system shall write StatGrid shards to
  `Output/Reports/Exports/StatGrid/<run_id>/` as append-only gzip CSV with a one-time schema
  file.
- **EIR-3** The system shall write optimizer artifacts under
  `Output/Reports/Optimization/` (`State/`, `Diagnostics/`, `Graphs/`) and stats checkpoints
  under `Output/Stats/`.
- **EIR-4** The candidate-grid records shall include at least
  `{dataset_index, ts, model, rounding_id, rounded, true, hit, pred, abs_err}`.

### 3.2 Command-line interfaces
- **EIR-5** `run_cli.py` shall accept `--target`, `--horizon`, `--window`, `--no-window`.
- **EIR-6** `stat.py` shall accept `--resume [latest|path|step]` and
  `--statgrid-export {none|incremental|full}`.
- **EIR-7** `orchestrator.py` shall accept `--action {optimize|forecast}`, `--run-id`,
  `--optimizer {all|greedy|milp|bandit|evo}`, slicing flags (`--slice-mode`, `--train-frac`,
  `--train-end-step`, `--eval-start-step`, `--eval-end-step`), policy/search flags
  (`--max-tickets`, `--max-overlap-k`, `--shortlist-m`, `--beam`, `--hit-threshold`),
  `--resume`, and reporting flags.
- **EIR-8** `stat_report.py` shall print a report from a checkpoint (`--checkpoint latest|path|step`).

### 3.3 Environment overrides
- **EIR-9** The system shall honor `DYNAMIX_DATA_FILE`, `DYNAMIX_OUTPUT_DIR`, and
  `DYNAMIX_MODEL_CACHE_DIR`.

---

## 4. Functional requirements

### 4.1 Data management
- **FR-1** Load, validate, and normalize `DATA.csv`, selecting `TS_1..TS_7`.
- **FR-2** Support `INDEX_MODE` `"event"` (row-order identity, duplicate dates allowed) and
  `"calendar"` (daily frequency); event mode is the default.
- **FR-3** Validate/coerce TS values to integers under configurable tolerance.
- **FR-4** Enforce a minimum history length and report a clear error otherwise.

### 4.2 Forecasting (Stage 1)
- **FR-5** Forecast each TS for a horizon `FH` (≤ `FH_MAX`) using available model families:
  DynaMix (zero-shot ALRNN/LSTM/GRU), PCE-NARX, and Darts (GRU/LSTM/TCN/NBEATS/Transformer/TFT).
- **FR-6** Run in single-series or batch (all-series) mode and present a Markdown table of the
  t+1 step.
- **FR-7** Optionally restrict training to the last `TRAINING_WINDOW_ROUNDS` rows.
- **FR-8** When a model family's dependency is unavailable, skip it with a warning and continue
  (fail-soft).

### 4.3 Backtest & candidate-grid export (Stage 2)
- **FR-9** Perform a rolling-origin backtest: at each step, train on prior history and forecast
  the next draw.
- **FR-10** Expand each float prediction into integer candidates under all rounding modes
  (truncate, floor, ceil, half-to-even, half-up, half-down, half-away-from-zero).
- **FR-11** Score each candidate against the realized value (`hit`, `abs_err`).
- **FR-12** Export the candidate grid under modes `none`, `incremental`, or `full`
  (full = recompute+export checkpoint-covered steps, then continue).
- **FR-13** Parallelize per-series forecasting across worker processes, capturing structured
  per-worker errors without aborting the run.
- **FR-14** Persist resumable checkpoints periodically and continue from `latest`/path/step.
- **FR-15** Record auxiliary diagnostics (hit distribution, multi-hit counts, overlay
  witnesses).

### 4.4 Optimization (Stage 3)
- **FR-16** Load a StatGrid run (explicit id or `latest`) and order its steps.
- **FR-17** Split steps into TRAIN/EVAL via positional or index slicing (default `train_frac`
  0.8) and print how slicing flags were interpreted.
- **FR-18** Build truth-history tables (frequency, recency/gap, pair/triple co-occurrence)
  **over TRAIN only**.
- **FR-19** Fit a calibrated hit-probability model (logistic regression + isotonic calibration)
  on TRAIN-derived candidate features.
- **FR-20** Build per-TS shortlists (top `shortlist_m` by `p_hit`) with a guaranteed fallback
  candidate per position.
- **FR-21** Generate a ticket pool via beam search (`beam`) maximizing summed log `p_hit`.
- **FR-22** Score each ticket `q` = Poisson-binomial P(#hits ≥ H) × co-occurrence compatibility
  bonus; score a portfolio as `q_any = 1 − Π(1 − q_i)`.
- **FR-23** Select up to `max_tickets` (default 5) tickets honoring a pairwise overlap cap
  `max_overlap_k`, using greedy, MILP (Σq), bandit, or evolutionary strategies; MILP shall fall
  back to greedy when `pulp` is unavailable.
- **FR-24** Evaluate selected portfolios on EVAL and compute economics from configured payouts
  and ticket cost.
- **FR-25** Write diagnostics, a calibration report (Brier, ECE, reliability plot), and a final
  summary with full provenance.

### 4.5 Next-step forecast action
- **FR-26** In `--action forecast`, fit on TRAIN, build a next-step candidate grid from current
  `DATA.csv`, select tickets, and write `forecast.json` plus operator-friendly console output.
- **FR-27** Since truth is unknown for the next step, set `true/hit/abs_err` to zero in a
  tie-break-safe manner.

### 4.6 Configuration
- **FR-28** Centralize forecasting/stats configuration in `constants.py` and optimizer
  configuration in the `OptConfig` dataclass; expose a deterministic `config_identity()`.

---

## 5. Non-functional requirements

### 5.1 Reliability & integrity
- **NFR-1 (Leakage safety)** Truth tables, features, and the model shall be fit on TRAIN steps
  only; feature reference points shall be TRAIN-relative.
- **NFR-2 (Resume integrity)** Resuming a run shall be refused unless grid run id, grid
  fingerprint, config identity, and slice all match the saved state.
- **NFR-3 (Atomic state)** State writes shall be atomic (temp file + replace) and dual-format
  (pickle.gz + JSON).
- **NFR-4 (Fail-soft)** Absence of any optional dependency shall disable only the affected
  feature, not abort the pipeline.
- **NFR-5 (Safe deserialization)** Checkpoint loading shall constrain class resolution
  (hardened unpickler).

### 5.2 Performance
- **NFR-6** Per-step forecasting shall support multi-process parallelism bounded by
  `STATS_MAX_WORKERS`.
- **NFR-7** A configurable training window shall bound per-step training cost.
- **NFR-8** Export and checkpoint flushing shall be incremental to bound memory.

### 5.3 Determinism & reproducibility
- **NFR-9** **Scope: the optimizer (Stage 3) only.** Given an identical candidate grid (StatGrid)
  and identical configuration, optimizer outputs shall be reproducible (fixed seeds, deterministic
  feature ordering, deterministic fill-to-K). This guarantee does **not** extend to Stage-1
  forecasting or the Stage-2 backtest: the neural models (torch) and the multiprocessing forecast
  workers are **not** bit-reproducible across runs, hardware, or thread counts, so the StatGrid
  itself is treated as a fixed *input* to the reproducibility claim rather than a reproducible
  *output*. Enforced by `tests/integration/test_optimizer_determinism.py` (asserts optimizer
  determinism only).
- **NFR-10** All results shall carry provenance (run ids, fingerprint, slice interpretation,
  config identity).

### 5.4 Maintainability & portability
- **NFR-11** Core library code shall live under `src/dynamix/`; entrypoints shall bootstrap
  `src/` onto `sys.path` without requiring installation.
- **NFR-12** All filesystem paths shall be anchored to the repo root and overridable by
  environment variables.
- **NFR-13** A layered test suite (`run_tests.py`) shall cover core-unit, contract,
  optimization, state-integrity, integration, and optional layers.

### 5.5 Usability
- **NFR-14** CLI stages shall emit progress with elapsed-time and (optionally) ETA reporting.
- **NFR-15** A GUI (`gui.py`) shall provide interactive forecasting and echo results to both
  the GUI and stdout.

---

## 6. Data requirements

- **DR-1** Input: `DATA.csv` — `Date` (`%d/%m/%Y`) + integer `TS_1..TS_7`.
- **DR-2** Candidate-grid record: provenance (`run_id, dataset_index, step_num, step_label,
  step_date, index_mode, export_mode, window_rounds`), keys (`ts, model, rounding_id`), and
  measurements (`pred, rounded, true, hit, abs_err`).
- **DR-3** Optimizer state: run identity, grid fingerprint, slice info, strategy params,
  results, forecast metadata.
- **DR-4** Economics: payout-by-hits map (`{3:10, 4:50, 5:2000, 6:50000, 7:1000000}` default)
  and ticket cost (€2.0 default).

---

## 7. Constraints and known limitations

- **CON-1** Exactly 7 positional series are assumed (`EXPECTED_NUM_SERIES = 7`).
- **CON-2** The candidate-grid schema is a cross-stage contract; changes must be migrated in
  both `stat.py` (producer) and `opt_data.REQUIRED_COLS` (consumer).
- **CON-3** PCE-NARX requires `chaospy`; despite being the nominal baseline, it is not
  dependency-free.
- **CON-4** The evolutionary strategy is presently a deterministic stub.
- **CON-5** The system makes no claim of real-world predictive advantage; it is a forecasting/
  optimization framework applied to lottery data.

---

## 8. Requirement traceability (summary)

| Area | Requirements | Primary modules |
|------|--------------|-----------------|
| Data | FR-1..4, DR-1 | `data_utils.py` |
| Forecasting | FR-5..8 | `dynamix_core.py`, `pce_narx.py`, `darts_core.py`, `run_cli.py` |
| Backtest/StatGrid | FR-9..15, DR-2 | `stat.py` |
| Optimization | FR-16..25, DR-3..4 | `opt/*.py`, `orchestrator.py` |
| Forecast action | FR-26..27 | `orchestrator.py`, `stat.py` |
| Config | FR-28 | `constants.py`, `opt_config.py` |
| Integrity/NFRs | NFR-1..15 | `opt_state.py`, `opt_data.py`, `stat.py`, `run_tests.py` |
