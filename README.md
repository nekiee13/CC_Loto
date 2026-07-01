# DynaMix Lottery Forecasting System

A three-stage pipeline that forecasts 7 positional lottery series (`TS_1`..`TS_7`) per draw,
backtests those forecasts into a "candidate grid", then runs a portfolio optimizer over the
grid to select up to 5 tickets per draw.

```
DATA.csv ──▶ stat.py ──▶ StatGrid/<run_id>/ ──▶ orchestrator.py ──▶ tickets + diagnostics
 (input)     (backtest)   (candidate grid)       (optimize/forecast)
```

See [docs/architecture.md](docs/architecture.md) for the full module-by-module breakdown.

## Requirements & install

Pure Python. Install the package (editable) to make `dynamix`/`opt` importable — this replaces
the old per-file `sys.path` bootstrapping:

```bash
python -m venv .venv && . .venv/bin/activate    # Python 3.11/3.12 recommended
pip install -e .            # core; or: pip install -e .[milp]   (adds pulp MILP backend)
```

Dependency surface:

- **Core:** `pandas`, `numpy`, `scipy`, `scikit-learn`, `plotly`
- **Optional extras (fail-soft, disables a feature if missing):** `models` = `torch` + the
  DynaMix HuggingFace model + `darts` + `chaospy` (PCE); `milp` = `pulp`; GUI needs `tkinter`
  (system `python3-tk` on Linux).

## Input data

A single file `DATA.csv` at the repo root, one row per draw event:

```
Date,TS_1,TS_2,TS_3,TS_4,TS_5,TS_6,TS_7
30/05/2017,3,10,25,32,43,1,3
...
```

Each row is treated as one event (`INDEX_MODE = "event"`): order is identity, dates are
metadata, and duplicate dates are allowed. You update `DATA.csv` over time as new draws occur.

**Data policy:** `DATA.csv` is tracked in git as the canonical reference draw history — it is
public lottery-draw results (no secrets or personal data), so it ships with the repo and is
updated in place. It is the single required input; the test suite and pipeline assume it exists
at the repo root. Point elsewhere with the `DYNAMIX_DATA_FILE` environment variable if you keep
your operational history outside the repo.

## Usage

```bash
# 1. Forecast next step (per series or batch)
python run_cli.py --target TS_1 --horizon 5
python run_cli.py                  # all series, all models
python gui.py                      # Tkinter GUI

# 2. Backtest + export the candidate grid
python stat.py --statgrid-export incremental      # none|incremental|full
python stat.py --resume latest --statgrid-export full
python stat_report.py --checkpoint latest         # print a report from a checkpoint

# 3. Optimize / forecast over the StatGrid
python orchestrator.py --action optimize --run-id latest --optimizer all
python orchestrator.py --action forecast --run-id latest   # next-step tickets
```

Outputs are written under `Output/` (gitignored): StatGrid shards, optimizer state,
diagnostics, calibration reports, and `forecast.json`.

## Configuration

Central config is `src/dynamix/constants.py` (data columns, `INDEX_MODE`, model toggles,
training window, paths). Filesystem paths are anchored to the repo root and can be overridden
via environment variables: `DYNAMIX_DATA_FILE`, `DYNAMIX_OUTPUT_DIR`, `DYNAMIX_MODEL_CACHE_DIR`.
The optimizer has its own config dataclass `OptConfig` in `opt/opt_config.py`.

## Tests

Tests use a custom layered `unittest` runner (not pytest) that puts both the repo root and
`src/` on `sys.path`:

```bash
python run_tests.py                            # default layers (excludes optional)
python run_tests.py --include-optional         # add optional-dependency tests
python run_tests.py --layer core-unit          # run one layer
python run_tests.py --layer core-unit --pattern test_constants.py   # single file
```

Run via `run_tests.py` rather than `python -m unittest` directly — a bare unittest run from
the repo root will fail to import `dynamix.*` because `src/` won't be on the path.

## Project layout

```
DATA.csv               Input draw history
run_cli.py, gui.py     Stage 1 entrypoints (forecasting)
stat.py, stat_report.py  Stage 2 (backtest + StatGrid export / reporting)
orchestrator.py        Stage 3 entrypoint (optimize / forecast)
src/dynamix/           Forecasting library + central config (constants.py)
opt/                   Optimizer package (engine, strategies, state, diagnostics)
tests/                 Layered unittest suites
tools/                 Maintenance / QA / StatGrid utilities
docs/                  Architecture notes
```

## Notes

Entrypoints import the forecasting library via `from dynamix import ...` (run `pip install -e .`
so `dynamix`/`opt` resolve without `sys.path` hacks). The backtest module is `dynamix.stat`
(renamed out of the repo root so a plain `import stat` no longer collides with the standard
library).

**`DynaMix-python/` placeholder:** this directory holds the *external* DynaMix HuggingFace model
repo, which `src/dynamix/dynamix_core.py` adds to `sys.path` at runtime. It is not tracked in git
(gitignored) — clone or place the external repo there yourself if you want the DynaMix model
family. When absent, that model family fails soft (disabled with a warning); the rest of the
pipeline runs normally.
