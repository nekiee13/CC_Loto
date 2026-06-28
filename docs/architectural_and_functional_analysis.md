# Architectural and Functional Analysis

In-depth analysis of the DynaMix Lottery Forecasting System. For the short orientation,
see [architecture.md](architecture.md); for current environment state, see [AS-IS.md](AS-IS.md).

> Scope: this describes how the system is built and what each part does. Grounded in the
> source as indexed on 2026-06-29. The lottery domain (7 positional integer series per draw)
> is modelled as a multivariate time-series forecasting + portfolio-selection problem.

---

## 1. Purpose and shape

The system answers one operational question per draw: **given the history of 7 positional
series, which up-to-5 tickets (each a 7-tuple of integers) maximize the probability of
landing ≥ H position-hits?** It does this in three decoupled stages connected by files on
disk, so each stage can be run, resumed, and inspected independently:

```
            stage 1                stage 2                      stage 3
  DATA.csv ─► forecasting ─► numeric  ─► backtest + StatGrid ─► candidate ─► optimizer ─► tickets
             models          forecasts    (rolling-origin)        grid CSV    (cond. prob.)   + diagnostics
  (run_cli / gui)            (per step)   (stat.py)               shards      (orchestrator)
```

The decoupling is deliberate: stage 2 turns *model predictions* into a labelled dataset
(`hit`/`abs_err` per candidate), and stage 3 learns *which predictions tend to hit* and
composes them into a ticket portfolio. Stage 3 never re-runs the forecasting models during
optimization — it consumes the grid.

---

## 2. Component map

| Layer | Module(s) | Entry point | Responsibility |
|-------|-----------|-------------|----------------|
| Config | `src/dynamix/constants.py` (`C`), `opt/opt_config.py` (`OptConfig`) | — | All tunables, paths, domain mode |
| Data | `src/dynamix/data_utils.py` | — | Load/validate/normalize `DATA.csv` |
| Models | `dynamix_core.py`, `pce_narx.py`, `darts_core.py` | `run_cli.py`, `gui.py` | Per-series numeric forecasts |
| Backtest | `stat.py` | `python stat.py` | Rolling-origin loop, StatGrid export, checkpoints |
| Reporting | `stat_report.py` | `python stat_report.py` | Human report from a checkpoint |
| Optimizer | `opt/opt_*.py` | `orchestrator.py` | Slice → fit engine → strategies → diagnostics |

The `opt/` package: `opt_config` (config + CLI), `opt_data` (grid load, slicing, fingerprint),
`opt_features` (truth tables + feature engineering), `opt_engine` (conditional-probability
model + ticket scoring), `opt_strategies` (greedy/MILP/bandit/evo + selection), `opt_state`
(resumable state), `opt_diagnostics` + `opt_calibration` (reports).

---

## 3. Domain data model

**Input** (`DATA.csv`): `Date, TS_1..TS_7`, one row per draw.

**Index semantics** (`constants.INDEX_MODE`):
- `"event"` (operative default): each row is one event keyed by `EventID` 0..N-1 in **file
  order**. Timestamps are metadata, not identity; duplicate dates are allowed. Forecast steps
  are named `ForecastStep` (t+1..t+H). This is the path the whole system is tuned for.
- `"calendar"`: strict daily-frequency date index; exists but is not the default.

**TS domain validation**: values are validated/coerced to integers (`TS_REQUIRE_INTEGERS`,
`TS_COERCE_FLOATS_TO_INT`), reflecting that lottery positions are discrete.

**The candidate-grid schema** (the contract between stage 2 and stage 3), one row per
(`dataset_index` × `ts` × `model` × `rounding_id`), produced by `build_candidate_grid_rows`:

| Column | Meaning |
|--------|---------|
| `dataset_index`, `step_num`, `step_label`, `step_date` | which draw step |
| `ts` | which position (`TS_1`..`TS_7`) |
| `model` | which forecasting model produced `pred` |
| `rounding_id` | which rounding mode mapped `pred` → integer |
| `pred` | raw model output (float) |
| `rounded` | integer candidate value |
| `true` | actual drawn value (0 for unknown/forecast step) |
| `hit` | `1` if `rounded == true` else `0` — **the optimizer's training label** |
| `abs_err` | `|pred − true|` |
| `window_rounds`, `index_mode`, `export_mode`, `run_id` | provenance |

The optimizer requires the subset `{dataset_index, ts, model, rounding_id, rounded, true, hit,
pred, abs_err}` (`opt_data.REQUIRED_COLS`).

---

## 4. Stage 1 — Forecasting layer

Three model families, each a thin wrapper that takes a history `DataFrame` and returns
forecasts. All three are **optional and fail-soft**: a missing dependency disables that family
with a warning rather than raising (toggled by `HAS_TORCH`/`HAS_DARTS`/`chaospy` import
guards). With none installed, the pipeline still runs but produces no forecasts.

| Family | Module | Method(s) | Notes |
|--------|--------|-----------|-------|
| DynaMix | `dynamix_core.py` | `run_dynamix_forecast` → `{forecast_df,…}` | Zero-shot ALRNN/LSTM/GRU loaded from a HuggingFace model; needs `torch` + the external DynaMix repo (`_resolve_dynamix_repo_dir`, `_import_dynamix`). Architecture chosen by series dimensionality (`_select_model_name_for_dims`: ALRNN ≤1 dim, LSTM ≤3, GRU ≤100). |
| PCE-NARX | `pce_narx.py` | `predict_pce_narx` → `DataFrame[PCE_Pred,…]` | Sparse polynomial-chaos NARX: builds lagged regression matrix (`_build_narx_dataset_from_df`, `PCE_LAGS`), scales features, fits `chaospy` PCE with Lasso-CV. Univariate by default (`PCE_USE_OTHER_TS_AS_EXOG=False`). Needs `chaospy`. |
| Darts | `darts_core.py` | `run_darts_forecast(model_type=…)` | Wraps Darts deep models GRU/LSTM/TCN/NBEATS/Transformer/TFT (`_build_model`); `DARTS_USE_MULTIVARIATE=False` forces per-series independence. Needs `darts`/`torch`. |

The CLI (`run_cli.py`) runs **single mode** (one series, all models) or **batch mode** (all
series, all models) and prints a Markdown table of the t+1 step. A training window
(`TRAINING_WINDOW_ROUNDS`, default 235) optionally restricts each fit to the last N rows.

---

## 5. Stage 2 — Backtest and StatGrid export (`stat.py`)

`run_statistics(resume_arg, export_mode)` is a **rolling-origin backtest**: for each step it
trains on history up to that point and forecasts the next draw, then scores predictions
against the realized row.

**Parallelism.** Per-step forecasting fans out across series with a `ProcessPoolExecutor`
(`STATS_MAX_WORKERS`, default `cpu_count−1`); `_forecast_single_series` runs each series's
models in a worker and returns `{model: {ts: pred}}` plus structured `WorkerError`s.
`collect_model_forecasts_for_step` aggregates them (and runs sequentially when `executor=None`,
which is how the orchestrator's forecast path reuses it safely).

**Rounding as candidate expansion.** Each float `pred` is expanded into integer candidates
under **7 rounding modes** (`RoundingMode`: TRUNCATE, FLOOR, CEIL, HALF_TO_EVEN, HALF_UP,
HALF_DOWN, HALF_AWAY_FROM_ZERO) via `apply_round`. This multiplies the candidate space so the
optimizer can later learn which (model, rounding) combinations actually hit.

**Export modes** (`--statgrid-export`): `none`, `incremental` (only steps computed this run),
`full` (recompute+export all checkpoint-covered steps, then continue — implemented by
`rebuild_full_export_from_checkpoint_coverage`, since checkpoints don't store per-step
predictions). `CandidateGridExporter` buffers rows and flushes append-only gzip CSV shards to
`Output/Reports/Exports/StatGrid/<run_id>/`, writing the schema once.

**Checkpoints.** `save_checkpoint`/`load_checkpoint` persist `Stats` aggregates to
`Output/Stats/stats_checkpoint_step_<n>.pkl` every `STATS_CHECKPOINT_EVERY_STEPS`; `--resume
latest|<path>|<step>` continues. A hardened `_StatUnpickler` constrains class resolution on
load. Beyond the grid, stage 2 also tracks hit distributions, multi-hit counts, and "overlay
witnesses" (`build_overlay_witness_for_step`) — diagnostic records of strong near-misses.

---

## 6. Stage 3 — Optimization (`orchestrator.py` + `opt/`)

`_run_optimize` orchestrates: resolve grid run → load grid → order steps → slice → fingerprint
→ load/resume state → fit engine on TRAIN → run strategies on EVAL → write diagnostics +
calibration + summary.

### 6.1 Slicing (`opt_data.resolve_slices`)
Splits ordered `dataset_index` steps into TRAIN/EVAL. `slice_mode="pos"` interprets cut points
as 1-based positions; `"index"` as literal `dataset_index` values (with rightmost-≤ / leftmost-≥
resolution). Default `train_frac=0.8`. The orchestrator prints an explicit interpretation
("train_end interpreted as position=P ⇒ dataset_index=…") for auditability.

### 6.2 Resume safety (leakage + identity)
`compute_grid_fingerprint` hashes grid shape + sampled content; `load_state_or_init` keys runs
as `opt_YYYYMMDD_HHMMSS` with atomic pickle.gz + JSON writes; `validate_resume_or_fail` refuses
to resume unless `grid_run_id`, fingerprint, `config_identity()`, and slice all match. This is
the guardrail that keeps a resumed run from silently mixing incompatible data/config.

### 6.3 Truth tables and features (`opt_features`)
`build_truth_history_tables` computes, **over TRAIN only**, frequency counts (global and
per-TS), last-seen positions (recency/gap), and pair/triple co-occurrence of realized values
(canonicalized by TS name). `compute_candidate_features_for_step` turns each grid candidate
into the engineered feature vector the model consumes:
`abs_err_bin, rank_bin, consensus_count, freq_global_bin, freq_ts_bin, gap_global_bin,
gap_ts_bin, parity, low_high, pred_minus_rounded, pred_minus_rounded_abs`. A `ref_pos`/`ref_steps`
reference point keeps frequency/gap features leakage-safe relative to the step being scored.

### 6.4 The conditional-probability engine (`opt_engine.ConditionalProbEngine`)
This is the analytical core. It learns **P(hit | features)** and composes calibrated
per-candidate probabilities into ticket- and portfolio-level scores.

- **Fit** (`fit_on_train`): builds features per TRAIN step, fits
  `LogisticRegression` wrapped in `CalibratedClassifierCV(method="isotonic", cv=3)` — so the
  emitted `p_hit` is an isotonically **calibrated** probability, which matters because the
  downstream objective multiplies many of them.
- **Shortlists** (`build_shortlists_for_step`): per TS, score all candidates and keep the top
  `shortlist_m` by `p_hit`. A `_fallback_value_for_ts` (TRAIN truth frequency) guarantees every
  position has at least one option, recording a fallback event.
- **Ticket pool** (`build_ticket_pool_beam`): beam search across the 7 positions maximizing
  Σ log `p_hit`, keeping `beam` partials per step; yields candidate 7-tuples with scores.
- **Ticket score `q`** (`score_ticket_q`): the 7 position probabilities go into a
  **Poisson-binomial** DP (`poisson_binomial_prob_ge`) giving exact `P(#hits ≥ H)`; this is
  multiplied by `exp(compatibility_log_bonus)`, an additive log-bonus from TRAIN pair/triple
  co-occurrence (`pair_weight·Σlog(1+count) + triple_weight·Σlog(1+count)`), then clipped.
  So `q` rewards tickets whose positions are *individually likely* **and** *jointly plausible*.
- **Portfolio** (`portfolio_q_any`): `q_any = 1 − Π(1 − q_i)` — probability that *at least one*
  selected ticket succeeds.

### 6.5 Strategies (`opt_strategies`)
All four consume the pool/shortlists and select up to `max_tickets` (default 5) tickets, then
evaluate on EVAL steps producing diagnostic rows + a summary.

| Strategy | `run_*` | Selection idea |
|----------|---------|----------------|
| Greedy | `run_greedy` | `select_portfolio_greedy`: iteratively add the ticket with best marginal `q_any` gain, respecting `max_overlap_k`. |
| MILP | `run_milp` | `select_milp_sum_q`: ILP maximizing Σ`q` s.t. exactly K tickets and pairwise overlap ≤ `max_overlap_k` (needs `pulp`; **auto-falls back to greedy** if absent). |
| Bandit | `run_bandit` | ε-style selection over predefined arms (`bandit_arms`, each a `{max_overlap_k, shortlist_m, beam, hit_threshold}` preset). |
| Evolutionary | `run_evolutionary` | Population search over parameterizations (currently a deterministic stub per its docstring). |

`fill_to_k_deterministic` enforces exactly-K with the overlap cap; `realized_hits` /
`eval_summary` compute hit counts and economics from `payout_by_hits`
(`{3:10, 4:50, 5:2000, 6:50000, 7:1000000}`) and `ticket_cost_eur=2.0`.

### 6.6 Diagnostics and calibration (`opt_diagnostics`, `opt_calibration`)
Writes `diagnostics_current.csv` + history, a calibration report, and a final summary. Quality
of the probability estimates is measured with **Brier score** and **Expected Calibration
Error** (`calibration_table`, `compute_calibration_metrics_from_df`), plus a reliability-plot
HTML (`reliability_plot_html`) of `q_any` vs empirical success. These close the loop: they tell
you whether the engine's probabilities are trustworthy, not just whether tickets hit.

---

## 7. Forecast action (next-step tickets)

`orchestrator.py --action forecast` (`_run_forecast`) skips EVAL: it fits the engine on TRAIN,
then builds a **next-step candidate grid directly from current `DATA.csv`** (Option B,
`_build_next_step_candidate_grid_via_stat`, reusing stage-2 forecasting with `executor=None`),
and selects tickets (MILP-sum-`q`, greedy fallback). Truth is unknown, so `true/hit/abs_err`
are zero-filled (tie-break safe). Output is `forecast.json` under the run's state dir, plus
console-friendly ticket lines and `q_any`.

---

## 8. Configuration surface

- **`constants.py`** — paths (anchored to `REPO_ROOT`, env-overridable via
  `DYNAMIX_DATA_FILE`/`DYNAMIX_OUTPUT_DIR`/`DYNAMIX_MODEL_CACHE_DIR`), `INDEX_MODE`, TS columns,
  per-model toggles/epochs/lags, training window, stats cadence. Imported everywhere as `C`.
- **`OptConfig`** (`opt_config.py`) — frozen dataclass: directory layout under
  `Output/Reports/Optimization/`, slicing, ticket policy (`max_tickets_per_draw`,
  `max_overlap_k`, `hit_threshold`), candidate pool (`shortlist_m`, `beam`), feature bins,
  co-occurrence weights, economics, strategy params, `seed`, and `config_identity()` /
  `base_strategy_params()` / `which_optimizers()` helpers. Built from CLI by `build_config`.

---

## 9. Cross-cutting concerns

- **Leakage safety** is a first-class invariant: truth tables, features, and the model are all
  fit on TRAIN steps only; feature reference points are TRAIN-relative; resume is fingerprint-
  and identity-guarded.
- **Determinism**: fixed seeds (`seed`, `PCE_RANDOM_STATE`), deterministic feature column order,
  deterministic fill-to-K, atomic state writes.
- **Fail-soft dependency boundaries**: every optional model and `pulp` is import-guarded; the
  pipeline degrades instead of crashing.
- **Path discipline**: all I/O is anchored to `REPO_ROOT`, so moving code under `src/` doesn't
  break input/output locations; entrypoints bootstrap `src/` onto `sys.path` themselves.
- **Provenance everywhere**: grid `run_id`, fingerprint, slice interpretation, and config
  identity are threaded into state and reports so any result can be traced to its inputs.

---

## 10. Module → function quick index

- **data_utils**: `load_lottery_data` (validate/normalize), `print_markdown_table`.
- **stat**: `run_statistics` (loop), `collect_model_forecasts_for_step`, `apply_round`,
  `build_candidate_grid_rows`, `CandidateGridExporter`, checkpoint/overlay helpers.
- **opt_data**: `load_statgrid_run`, `resolve_slices`, `compute_grid_fingerprint`.
- **opt_features**: `build_truth_history_tables`, `compute_candidate_features_for_step`.
- **opt_engine**: `ConditionalProbEngine` (`fit_on_train`, `build_shortlists_for_step`,
  `build_ticket_pool_beam`, `score_ticket_q`, `poisson_binomial_prob_ge`,
  `compatibility_log_bonus`, `portfolio_q_any`, `fill_to_k_deterministic`).
- **opt_strategies**: `run_greedy`/`run_milp`/`run_bandit`/`run_evolutionary`,
  `select_portfolio_greedy`, `select_milp_sum_q`, `eval_summary`.
- **opt_state**: `load_state_or_init`, `save_state`, `validate_resume_or_fail`.
- **opt_diagnostics / opt_calibration**: report writers, `brier_score`,
  `expected_calibration_error`, `calibration_table`, `reliability_plot_html`.

---

## 11. Observations

- The evolutionary strategy is documented as a deterministic stub — a likely extension point.
- PCE-NARX, nominally the "always available" baseline, in fact needs `chaospy`; without it the
  only zero-extra-dependency path through stage 1 is empty (see [AS-IS.md](AS-IS.md)).
- Stages communicate purely through files (StatGrid shards, state, JSON), which makes the
  system inspectable and resumable but means schema changes to the candidate grid are a
  cross-stage contract (`opt_data.REQUIRED_COLS`) and must be migrated on both sides.
