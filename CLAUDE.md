# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

DynaMix Lottery Forecasting System: a three-stage pipeline (forecast → backtest/StatGrid →
portfolio optimize) over 7 positional lottery series (`TS_1`..`TS_7`). Pure Python, packaged
with setuptools as `dynamix-lottery` (`pyproject.toml`, Python `>=3.11`) and normally used as
an editable install; `requirements.txt` and `requirements.lock` are the dependency authorities.
The single input is `DATA.csv` at the repo root (`Date,TS_1..TS_7`, one row per draw event).

See [docs/architecture.md](docs/architecture.md) for the full stage-by-stage breakdown,
module responsibilities, and data flow.

## Commands

Install once (editable) so the package is importable — entrypoints live in the package now:

```bash
pip install -e .            # or: pip install -e .[milp]   (adds the pulp MILP backend)
```

```bash
# Forecast a single series / all series (stage 1)
python run_cli.py --target TS_1 --horizon 5   # or: dynamix-cli --target TS_1 --horizon 5
python run_cli.py                       # batch: all series, all models
python gui.py                           # Tkinter GUI

# Backtest + export candidate grid (stage 2)
python stat.py --statgrid-export incremental      # or: dynamix-stat ...  (none|incremental|full)
python stat.py --resume latest --statgrid-export full
python stat_report.py --checkpoint latest         # or: dynamix-report --checkpoint latest

# Optimize / forecast over StatGrid (stage 3)
python orchestrator.py --action optimize --run-id latest --optimizer all   # or: dynamix-opt ...
python orchestrator.py --action forecast --run-id latest   # next-step tickets
```

The repo-root `*.py` files (`run_cli.py`, `stat.py`, `orchestrator.py`, `stat_report.py`,
`gui.py`) are **thin shims**; the implementations live in `src/dynamix/stat.py` and
`src/dynamix/entrypoints/`. The four `dynamix-*` console scripts are equivalent entry points.

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

- **The project is an installable package; entrypoints live inside it.** Run `pip install -e .`
  once, then `import dynamix.*` / `import opt.*` resolve with no `sys.path` hacks. The backtest
  module is `dynamix.stat` (moved out of the repo root, so a plain `import stat` no longer
  collides with the stdlib), and the CLIs are `dynamix.entrypoints.{run_cli,orchestrator,
  stat_report,gui}`. Use `from dynamix import ...` / `from opt import ...`; do **not**
  reintroduce per-file `sys.path.insert` bootstrapping or flat/capitalized names like
  `import Stat` / `import Data_Utils`. `tests/integration/test_entrypoints_import.py` enforces
  both (every entrypoint imports + no `sys.path` manipulation in application sources). The one
  sanctioned exception is `dynamix_core.py`, which extends the path to load the *external*
  DynaMix model repo. `run_tests.py` keeps a path bootstrap so the suite runs without an
  editable install.

- **Leakage safety** is a hard invariant in the optimizer: truth tables and the conditional
  model are fit on TRAIN steps only; resume is guarded by a grid fingerprint + config identity
  (`opt_data.compute_grid_fingerprint`, `opt_state.validate_resume_or_fail`). Don't introduce
  EVAL data into fitting.

- `Output/` is generated and gitignored. `DynaMix-python/` is an (empty) placeholder for the
  external DynaMix repo.

## Support system and coordination

This repository carries a support workflow alongside its product code. The summary below is
deliberately short; the controlling detail lives in [support/README.md](support/README.md),
[support/PROFILE.md](support/PROFILE.md),
[coordination/TEAM_PROTOCOL.md](coordination/TEAM_PROTOCOL.md), and the installed tools under
`tools/support/`. Where this summary and those authorities disagree, the authorities win.

- **Ownership.** Claude Code owns `CLAUDE.md`, `.claude/`, and `CC_` coordination records. Codex
  owns `AGENTS.md`, `.agents/`, and `CX_` records. Read the other agent's files for context, but
  never edit, move, delete, archive, or re-index them; request changes through a coordination
  message. Coordination records without an agent prefix, schemas, templates, validators, the
  generated board, support records, and handoffs are shared-neutral: claim them before editing and
  take independent review.

- **Session start.** For support-oriented work read, in order: this file; `support/README.md` and
  `support/PROFILE.md`; `HANDOFF.md` and its immutable record when one is published;
  `support/current-status.md` and append-only `support/log.md`; `coordination/BOARD.md`, unresolved
  `coordination/messages/`, and active `coordination/claims/`; then live Git state - branch, HEAD,
  upstream, divergence, worktree, and any unfinished risky artifact. Verify that state against the
  records rather than trusting the records.

- **Coordination lifecycle.** Messages are immutable: correct or answer with a new `reply_to`
  record, never by rewriting a sent one. Claims reserve anticipated paths and must not overlap.
  Archive a message only once it is resolved **and** the counterpart has confirmed - silence is not
  confirmation - moving only `CC_` records under an immutable resolution manifest. Use
  `python tools/support/agent_coord.py .` to validate, and regenerate the board through the tool
  rather than hand-editing `coordination/BOARD.md`, which is generated state and never authority.
  When asked to check messages, inspect and independently verify actionable Claude-addressed
  messages in the same turn; never acknowledge acceptance without evidence.

- **Validation truth.** Run the support aggregate as
  `python tools/validate_support.py --root . --native-python <target-interpreter>` and native layers
  as `python run_tests.py --layer <layer>`. The support tools require PyYAML and jsonschema from a
  separate support-operator environment; the product requirements environment does not provide them
  and must not be changed to provide them. Report every check with its literal state from the
  vocabulary defined in [support/schemas/handoff.schema.json](support/schemas/handoff.schema.json) -
  that schema and `tools/validate_support.py` are the authority, not any prose copy of the list.
  `blocked` is a handoff/blocker state, never a check result. An applicable check that could not run
  fails closed; never relabel a skipped, unavailable, not-run, or excluded check as passed, and
  never let a zero exit code stand in for a check that did not execute.

- **Safe recovery.** Capture parent, upstream, divergence, clean state, and allowed paths before any
  reviewed change. Recovery is a new `git revert` of the named commits after reviewer or owner
  direction; reset, force push, history rewriting, and broad cleanup are prohibited. Preserve
  unrelated and concurrent work, then re-run the support and applicable native checks and record
  literal commands and exit codes. A revert that conflicts with later work on the same append-only
  records requires owner-directed resolution.

- **Owner gates.** Milestone gates are the owner's decision and are never inferred from completed
  work, elapsed time, or independent review. Publishing files is not milestone acceptance, and a
  passing support aggregate is evidence about the support system, not about the product test suite.
  Do not describe the two agent guidance files as synchronized unless both sides are published and
  each agent has confirmed its own side at the live tip.
