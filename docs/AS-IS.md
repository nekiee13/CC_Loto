# As-Is State

Snapshot of the repository and working environment as of **2026-06-29**.
For the design/architecture, see [architecture.md](architecture.md).

## Repository

- Branch `main` at `c322e13`, in sync with `origin/main` (pushed). Working tree clean.
- History is linear (no merge commits); the docs/orchestrator-fix work was fast-forward
  merged and its feature branch deleted.
- Code is indexed by jcodemunch as `nekiee13/CC_Loto` (57 Python files, 756 symbols).

## What works

- **`orchestrator.py` imports cleanly** (was broken). It now bootstraps `src/` onto
  `sys.path`, imports `from dynamix import data_utils`, and loads the repo-root `stat.py`
  by file path via `_import_project_stat_module()` instead of the stdlib-colliding
  `import stat`. Verified at runtime.
- **Test suite: 51 of 52 pass**, 3 skipped (via `python run_tests.py`). The data layer,
  `stat.py` backtest logic, and the `opt/` optimizer (greedy/MILP/bandit/evolutionary,
  calibration, state) all pass.

## Working environment

- Virtual environment at `.venv/` (gitignored), **Python 3.14.4** (system interpreter).
  pip was bootstrapped manually (the OS image shipped without pip/ensurepip and without
  passwordless sudo).
- Installed: `pandas 3.0.4`, `numpy 2.5.0`, `scipy 1.18.0`, `scikit-learn 1.9.0`,
  `plotly 6.8.0`, `pulp 3.3.2` (all cp314 wheels; no compilation).
- Run things with `.venv/bin/python ...`.

## Known limitations (this machine)

None of the three forecasting model families can run here, so no model produces a forecast
on this box:

| Model | Missing dep | Why it can't be installed here |
|-------|-------------|--------------------------------|
| PCE-NARX | `chaospy` (→ `numpoly`) | No cp314 wheel; builds from C source but there is **no `gcc`** |
| DynaMix | `torch` + HF model | No cp314 wheel (and heavy) |
| Darts   | `darts` (→ torch) | Same as torch |

Root cause: Python 3.14 is newer than the available scientific-extension wheels, combined
with no C compiler and no passwordless sudo. To enable models here, either install a
compiler (`sudo apt install build-essential`, then `pip install chaospy`) or recreate the
venv against an older Python (3.11/3.12) that has prebuilt wheels.

The single failing test, `test_full_pipeline_simulation`, is a direct consequence: it asserts
at least one model produced output, but all three are absent. It is an environment limitation,
not a code defect. (Sibling tests `skip` in the same situation; this one asserts instead.)

## Deployment note

The intended runtime is a separate Windows environment (a `loto_dynamix` virtualenv under
`f:\venv\`) where the full model stack is already installed.
