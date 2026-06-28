# Architecture

DynaMix Lottery Forecasting System: a three-stage pipeline that forecasts 7 positional
lottery series (`TS_1`..`TS_7`) per draw, backtests those forecasts into a "candidate
grid", then runs a portfolio optimizer over the grid to select up to 5 tickets per draw.
Pure Python; no packaging (`pip install`), no `requirements.txt` — modules are run
directly from the repo root and resolve imports via `sys.path` bootstrapping.

The single input is `DATA.csv` at the repo root: `Date,TS_1..TS_7`, one row per draw event.

## Stages

1. **Forecasting** — `src/dynamix/` package, driven by `run_cli.py` (CLI) or `gui.py` (Tkinter).
   Produces numeric next-step forecasts per series from several model families:
   - `dynamix_core.py` — DynaMix zero-shot ALRNN/LSTM/GRU loaded from a HuggingFace model
     (optional; degrades gracefully if the `dynamix` model package or repo isn't present).
   - `pce_narx.py` — sparse PCE-NARX (polynomial chaos, Lasso-CV); always available.
   - `darts_core.py` — Darts deep models (GRU/LSTM/TCN/NBEATS/Transformer/TFT). Optional
     dependency boundary: import failure disables Darts, it does not crash callers.
   - `data_utils.py` (load/clean/format), `plotting.py`, `constants.py`.

2. **Backtest + StatGrid export** — `stat.py` (repo root). Rolling-origin backtest using
   `ProcessPoolExecutor`. For every step it exports a candidate grid row per
   (TS position × model × rounding mode) with `pred, rounded, true, hit, abs_err`, written
   as append-only gzip CSV shards under `Output/Reports/Exports/StatGrid/<run_id>/`.
   Resumable via pickle checkpoints under `Output/Stats/*.pkl`. `stat_report.py` prints a
   report from a checkpoint.

3. **Optimization** — `opt/` package, driven by `orchestrator.py`. Loads a StatGrid run,
   slices it into TRAIN/EVAL (leakage-safe), fits `ConditionalProbEngine`
   (`opt_engine.py`, calibrated logistic regression) on TRAIN truth-frequency tables
   (`opt_features.py`), then runs portfolio strategies (`opt_strategies.py`:
   greedy / MILP / bandit / evolutionary) to pick tickets maximizing expected payout.
   Writes diagnostics + calibration (`opt_diagnostics.py`, `opt_calibration.py`) and state
   (`opt_state.py`) under `Output/Reports/Optimization/`. The `--action forecast` path
   skips backtesting and generates next-step tickets directly from current `DATA.csv`.

## Data flow

`DATA.csv` → `stat.py` → `StatGrid/<run_id>/` → `orchestrator.py` → tickets +
`forecast.json` / diagnostics.
