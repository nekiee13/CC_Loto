# Installation Guide

How to install and verify the DynaMix Lottery Forecasting System. Reflects the packaged layout
(`pip install -e .`) introduced in E2 — see [PROGRESS.md](PROGRESS.md). For what the system
does, see [architecture.md](architecture.md); for the dependency surface, [SRS.md](SRS.md).

---

## 1. Prerequisites

- **Python 3.11 or 3.12** (recommended/tested). `requires-python` is `>=3.11`; the package
  *core* also runs on 3.13/3.14, but the optional model extras (`chaospy`, `torch`, `darts`)
  do not yet publish wheels for 3.14 — see [§6](#6-optional-model-dependencies) and
  [§9 Troubleshooting](#9-troubleshooting).
- **pip** and **venv**. On some minimal Linux images these are separate OS packages
  (`python3-venv`, `python3-pip`); install them first (see Troubleshooting).
- A **C compiler** is only needed if you install `chaospy` on a Python/OS without a prebuilt
  `numpoly` wheel (`sudo apt install build-essential`).
- **git** to clone the repository.

---

## 2. Quick start (core)

```bash
git clone https://github.com/nekiee13/CC_Loto.git
cd CC_Loto

python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate

pip install -e .                     # editable install of the `dynamix` + `opt` packages
```

That installs the **core** dependencies (`pandas`, `numpy`, `scipy`, `scikit-learn`, `plotly`)
and makes the package importable with no `PYTHONPATH`/`sys.path` tweaking. Verify:

```bash
python -c "import dynamix.constants, dynamix.stat, opt.opt_config; print('install OK')"
```

---

## 3. Dependency tiers (extras)

Install only what you need. Each optional model family **fails soft** — if its dependency is
missing, that model is disabled with a warning and the pipeline still runs.

| Install command | Adds | Enables |
|-----------------|------|---------|
| `pip install -e .` | core | data layer, backtest, optimizer (greedy) |
| `pip install -e .[milp]` | `pulp` | MILP ticket selection (else greedy fallback) |
| `pip install -e .[models]` | `chaospy`, `torch`, `darts` | PCE-NARX, DynaMix, Darts model families |
| `pip install -e .[dev]` | `coverage` | test-coverage tooling |
| combine: `pip install -e .[milp,dev]` | both | — |

GUI needs **tkinter**, which is not a pip package — see [§7](#7-gui-tkinter).

---

## 4. Reproducible install (lockfile)

For an exact, pinned dependency set. The lock pins the latest releases (e.g. numpy 2.5, which
requires Python **>=3.12**), so it targets **Python 3.12+**. On 3.11, use the loose floors
(`pip install -e .`) instead — pip will resolve 3.11-compatible versions.

```bash
pip install -r requirements.lock      # pinned core + milp runtime (Python 3.12+)
pip install -e . --no-deps            # the package itself, against the locked deps
```

Regenerate the lock after changing `pyproject.toml` dependencies:

```bash
pip install -e .[milp]
pip freeze | grep -viE '^-e |dynamix-lottery|^coverage==|^pip==|^setuptools==|^wheel==' \
  | sort -f > requirements.lock   # (re-add the header comment lines)
```

---

## 5. Console scripts vs. shims

After `pip install -e .` four console scripts are available, equivalent to running the
repo-root shim scripts:

| Console script | Shim | Purpose |
|----------------|------|---------|
| `dynamix-cli`    | `python run_cli.py`      | Stage 1 — forecasting CLI |
| `dynamix-stat`   | `python stat.py`         | Stage 2 — backtest + StatGrid export |
| `dynamix-opt`    | `python orchestrator.py` | Stage 3 — optimize / forecast |
| `dynamix-report` | `python stat_report.py`  | Print a report from a checkpoint |

(`python -m dynamix.stat`, `python -m dynamix.entrypoints.run_cli`, … also work.) The repo-root
`*.py` files are thin shims that require the package to be importable (`pip install -e .` first).

---

## 6. Optional model dependencies

These are heavy and/or platform-sensitive; install only if you need that model family.

- **`chaospy`** (PCE-NARX) — pulls `numpoly`, which builds from C source unless a wheel exists
  for your Python/OS. On Python 3.11/3.12 + Linux/macOS/Windows wheels generally exist; on
  3.14, or if no wheel is found, install a compiler first (`build-essential` / Xcode CLT / MSVC).
- **`torch`** (DynaMix) — large; also requires the external DynaMix HuggingFace model package
  (`dynamix.model.*`), loaded from a sibling `DynaMix-python/` repo if present (the empty
  `DynaMix-python/` placeholder marks where it is expected).
- **`darts`** (Darts deep models) — pulls `torch`/`pytorch-lightning`.

```bash
pip install -e .[models]          # all three; expect a long download/build
# or pick one:
pip install -e . chaospy
```

---

## 7. GUI (tkinter)

`gui.py` / `dynamix.entrypoints.gui` uses Tkinter, which ships with CPython but is a **system
package** on Linux:

```bash
sudo apt install python3-tk       # Debian/Ubuntu
```

macOS/Windows python.org builds include it. A headless machine without a display cannot launch
the GUI (it will raise a Tcl/display error); use the CLI instead.

---

## 8. Verifying the install

```bash
# Run the layered test suite (model-dependent tests skip if their deps are absent)
python run_tests.py                       # default layers
python run_tests.py --include-optional    # also run optional-dependency tests

# Smoke-check the console scripts
dynamix-cli --help
dynamix-opt --help
```

A clean core install yields `OK (skipped=N)` — skips are model-dependent tests with no model
runtime installed, which is expected.

---

## 9. Configuration

- **Input data:** `DATA.csv` at the repo root (`Date, TS_1..TS_7`, one row per draw). Override
  its location with `DYNAMIX_DATA_FILE`.
- **Output location:** defaults to `Output/` (gitignored). Override with `DYNAMIX_OUTPUT_DIR`.
- **Model cache:** override with `DYNAMIX_MODEL_CACHE_DIR`.

```bash
export DYNAMIX_DATA_FILE=/path/to/DATA.csv
export DYNAMIX_OUTPUT_DIR=/path/to/Output
```

Other tunables live in `src/dynamix/constants.py` (forecasting/stats) and `opt/opt_config.py`
(optimizer).

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No module named 'pip'` / `ensurepip` in a new venv | OS image lacks `python3-venv`/`python3-pip` | `sudo apt install python3-venv python3-pip`, recreate the venv; or bootstrap pip: `curl -sS https://bootstrap.pypa.io/get-pip.py \| .venv/bin/python` |
| `Failed building wheel for numpoly` … `gcc: not found` | `chaospy` building from source without a compiler | `sudo apt install build-essential` (Linux), or use Python 3.11/3.12 where wheels exist |
| `ModuleNotFoundError: No module named 'dynamix'` | package not installed | `pip install -e .` (the root `*.py` shims require it) |
| `pip install` picks no wheels / build errors on Python 3.14 | model extras lack 3.14 wheels | use Python **3.11/3.12** |
| `ModuleNotFoundError: No module named 'tkinter'` | Tkinter not installed | `sudo apt install python3-tk` (GUI only) |
| `PyTorch is not installed. DynaMix forecasting is disabled.` | informational | install `.[models]` only if you want DynaMix |

---

## 11. Uninstall / clean

```bash
pip uninstall dynamix-lottery
deactivate && rm -rf .venv           # remove the environment
rm -rf dynamix_lottery.egg-info Output/   # build/output artifacts (gitignored)
```
