# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

DynaMix Lottery Forecasting System: a three-stage pipeline (forecast → backtest/StatGrid →
portfolio optimize) over 7 positional lottery series (`TS_1`..`TS_7`). Pure Python, run
directly from the repo root with `sys.path` bootstrapping; no packaging or `requirements.txt`.
The single input is `DATA.csv` at the repo root (`Date,TS_1..TS_7`, one row per draw event).

See [docs/architecture.md](docs/architecture.md) for the full stage-by-stage breakdown,
module responsibilities, and data flow.

## Commands

```bash
# Forecast a single series / all series (stage 1)
python run_cli.py --target TS_1 --horizon 5
python run_cli.py                       # batch: all series, all models
python gui.py                           # Tkinter GUI

# Backtest + export candidate grid (stage 2)
python stat.py --statgrid-export incremental      # none|incremental|full
python stat.py --resume latest --statgrid-export full
python stat_report.py --checkpoint latest

# Optimize / forecast over StatGrid (stage 3)
python orchestrator.py --action optimize --run-id latest --optimizer all
python orchestrator.py --action forecast --run-id latest   # next-step tickets
```

### Tests

Tests use a custom layered `unittest` runner (not pytest). It puts both repo root and
`src/` on `sys.path`, which is required for the `from dynamix import ...` imports to resolve.

```bash
python run_tests.py                              # default layers (excludes optional)
python run_tests.py --include-optional           # add optional-dependency tests
python run_tests.py --layer core-unit            # one layer
python run_tests.py --layer core-unit --pattern test_constants.py   # single file
python run_tests.py --failfast
```

Layers (dir → name): `tests/core_unit` (core-unit), `tests/contract` (contract),
`tests/optimization` (optimization-core), `tests/state_integrity` (state-integrity),
`tests/integration` (integration), `tests/optional` (optional). The `optional` layer covers
heavy/optional deps (Darts, torch, the DynaMix HF model) and is skipped unless requested.

Prefer `run_tests.py` over invoking `python -m unittest` directly — a bare unittest run from
the repo root will fail to import `dynamix.*` because `src/` won't be on the path.

## Conventions and gotchas

- **Config is centralized** in `src/dynamix/constants.py` (imported as `C`). All filesystem
  paths are anchored to `REPO_ROOT` and can be overridden by env vars `DYNAMIX_DATA_FILE`,
  `DYNAMIX_OUTPUT_DIR`, `DYNAMIX_MODEL_CACHE_DIR`. The optimizer has its own config dataclass
  `OptConfig` in `opt/opt_config.py`. Change defaults there, not inline.

- **`INDEX_MODE = "event"`** is the operative mode: each row is one draw event keyed by
  `EventID` (0..N-1) in file order; dates are metadata, not identity, and duplicates are
  allowed. Slicing/indexing in the optimizer is positional (`slice_mode=pos`) by default.
  `calendar` mode exists but is not the default path.

- **Optional dependencies fail soft.** Darts and the DynaMix HF model are wrapped in
  try/except at import; missing deps disable a model family with a warning rather than
  erroring. Preserve this pattern when touching `dynamix_core.py` / `darts_core.py` and their
  callers in `run_cli.py` / `stat.py`.

- **All entrypoints bootstrap `src/` onto `sys.path` and use the src-based package import**
  (`from dynamix import data_utils as DU`). `orchestrator.py` additionally loads the repo-root
  `stat.py` by file path (`_import_project_stat_module`) rather than `import stat`, because a
  plain `import stat` resolves to the Python stdlib `stat` module. Keep this pattern — do not
  reintroduce flat/capitalized names like `import Stat` / `import Data_Utils` (they don't exist
  under the `src/dynamix` layout and break on case-sensitive filesystems). Test helpers
  (`tests/core_unit/test_data_utils.py`, `stat_report.py`) deliberately try multiple module
  names; mirror that when adding tests.

- **Leakage safety** is a hard invariant in the optimizer: truth tables and the conditional
  model are fit on TRAIN steps only; resume is guarded by a grid fingerprint + config identity
  (`opt_data.compute_grid_fingerprint`, `opt_state.validate_resume_or_fail`). Don't introduce
  EVAL data into fitting.

- `Output/` is generated and gitignored. `6.3.0` at the repo root is a stray pip-install log,
  not a source file. `DynaMix-python/` is an (empty) placeholder for the external DynaMix repo.
