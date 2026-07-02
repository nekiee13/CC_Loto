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

> **Prefer conda?** For a path-based conda environment (easy to locate and delete) and a CUDA
> GPU build of PyTorch, see [§2b](#2b-alternative-install-conda-path-based-env-with-cuda-gpu).

---

## 2b. Alternative install: conda (path-based env, with CUDA GPU)

Use this if you prefer **conda** and want the environment in a **known folder** you can locate
and delete easily, and/or you want a **CUDA GPU** build of PyTorch. A *prefix* env
(`conda create -p <path>`) lives entirely under a directory you choose — unlike a *named* env
buried in conda's central store. Python **3.11** is used deliberately: every optional model
extra (`chaospy`, `torch`, `darts`) publishes prebuilt wheels for it, so nothing builds from
source.

**1. Create the environment (Python 3.11) at a path you choose**

```bash
conda create -p ./.conda-env python=3.11 -y
conda activate ./.conda-env          # prefix envs are activated by path, not by name
```

The whole environment now lives under `./.conda-env` (use any path you like — inside or outside
the repo). To remove it later:

```bash
conda deactivate
conda env remove -p ./.conda-env     # or simply: rm -rf ./.conda-env
```

**2. Clone the repository**

```bash
git clone https://github.com/nekiee13/CC_Loto.git
cd CC_Loto
```

**3. Install core dependencies + the package**

```bash
pip install -r requirements.txt      # core runtime: pandas/numpy/scipy/scikit-learn/plotly + pulp
pip install -e . --no-deps           # make `dynamix` + `opt` importable and add the console scripts
```

`requirements.txt` lists **core** deps only; the model families (`chaospy`, `torch`, `darts`)
are commented out on purpose — install them in step 4. `--no-deps` skips re-resolving what
`requirements.txt` already provided. (Plain `pip install -e .` also works and is equivalent to
the venv quick-start in [§2](#2-quick-start-core).)

**4. Install PyTorch with CUDA, then the model families**

Install the CUDA build of PyTorch **first**, from the official index, so nothing installed later
pulls a CPU-only `torch`. Match the CUDA tag (`cu121`, `cu124`, …) to your driver — pick the
command from <https://pytorch.org/get-started/locally/>.

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124   # example: CUDA 12.4
pip install darts chaospy                                              # Darts + PCE-NARX, reusing the CUDA torch
```

- **Darts** pulls `pytorch-lightning`; installing it *after* the CUDA `torch` keeps the GPU build
  (a fresh `pip install darts` on its own can pull a CPU `torch`).
- **DynaMix** additionally needs the external DynaMix HuggingFace model package in the sibling
  `DynaMix-python/` directory — see [§6](#6-optional-model-dependencies).
- **Conda-native alternative** for PyTorch (run *before* `pip install darts`):
  `conda install pytorch pytorch-cuda=12.4 -c pytorch -c nvidia`.

**5. Verify the installation (including GPU)**

```bash
python -c "import dynamix.constants, dynamix.stat, opt.opt_config; print('install OK')"
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"   # expect True on a GPU box
python -c "from dynamix import device; print(device.describe_device())"          # expect: GPU (CUDA)
python run_tests.py --include-optional      # model-dependent tests now run instead of skipping
dynamix-cli --help
```

On a working GPU install: `torch.cuda.is_available()` prints `True`, the device label reads
`GPU (CUDA)` (also shown on the GUI Home page and sidebar), and the optional test layer runs
rather than skipping. Darts uses the GPU automatically when one is present (Lightning `auto`); to
*require* it, add `DARTS_FORCE_GPU = True` to `src/dynamix/constants.py` — this is guarded, so it
falls back to CPU (no crash) if no CUDA device is found.

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
| `torch.cuda.is_available()` is `False` on a GPU machine | a CPU-only `torch` wheel got installed (e.g. pulled in by `darts`) | reinstall the CUDA build first: `pip install torch --index-url https://download.pytorch.org/whl/cu124` ([§2b](#2b-alternative-install-conda-path-based-env-with-cuda-gpu)), then reinstall `darts` |

---

## 11. Uninstall / clean

```bash
pip uninstall dynamix-lottery
deactivate && rm -rf .venv           # remove the environment
rm -rf dynamix_lottery.egg-info Output/   # build/output artifacts (gitignored)
```
