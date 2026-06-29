# Progress Tracker

Living status board for the work specified in [TDD_PLAN.md](TDD_PLAN.md). Update the **Status**
and **Notes** columns as tasks move; log notable changes in the Progress Log at the bottom.
Full What/Why/TDD steps and acceptance criteria live in `TDD_PLAN.md` (this file is just the
scoreboard).

**Status legend:** ⬜ Todo · 🟡 In progress · 🔵 In review · ✅ Done · ⏸️ Blocked · ❌ Dropped

_Last updated: 2026-06-29 (E1 + E2 epics complete; E3.1/E3.2/E5.3 done)_

---

## Epic summary

| Epic | Priority | Status | Done / Total | Notes |
|------|----------|--------|--------------|-------|
| E1 — Honest EV/ROI + calibration scoreboard | P0 | ✅ Done | 4 / 4 | scoreboard in summary + console verdict |
| E2 — Packaging & import hygiene | P0 | ✅ Done | 3 / 3 | installable pkg, no sys.path hacks, lockfile, CI on editable install |
| E3 — CI + import smoke tests | P0 | ✅ Done | 2 / 2 | green core + non-blocking optional job |
| E4 — Decompose `stat.py` | P1 | ⬜ Todo | 0 / 2 | Golden test first |
| E5 — Test analytical core + coverage | P1 | 🟡 In progress | 1 / 3 | E5.3 done; E5.1/E5.2 todo |
| E6 — Resolve evolutionary stub | P2 | ⬜ Todo | 0 / 2 | E6.1 do regardless |
| E7 — De-dupe rounding storage | P2 | ⬜ Todo | 0 / 1 | Behind flag |
| E8 — Cleanup & polish | P3 | ⬜ Todo | 0 / 4 | Anytime |
| **Total** | | **🟡** | **10 / 21** | |

**Suggested order:** E3 → E2 → E1 → E5 → E4 → E7, with E6 and E8 branching off.

---

## Task board

### E1 — Honest EV/ROI + calibration scoreboard `P0`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E1.1 Pure economics function | ✅ | — | (pending) | `compute_portfolio_economics`; 4 strategy loops delegate to it |
| E1.2 Random-ticket control baseline | ✅ | — | (pending) | `random_ticket_baseline` + `build_value_pools_from_grid` (TRAIN-only, seeded) |
| E1.3 `q_any` calibration on EVAL | ✅ | — | (pending) | `qany_calibration` adapter reusing Brier/ECE |
| E1.4 Wire scoreboard into summary + console | ✅ | — | (pending) | `build_strategy_scoreboard`; `scoreboard` in summary JSON; orchestrator verdict block (quiet-safe) |

### E2 — Packaging & import hygiene `P0`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E2.1 `pyproject.toml` + package metadata | ✅ | — | (pending) | `pip install -e .` works; `dynamix`+`opt` import w/o path hacks; extras independent |
| E2.2 Finish layout; entrypoint shims | ✅ | — | (pending) | stat→`dynamix.stat`, CLIs→`dynamix.entrypoints.*`, root shims; no sys.path hacks; console scripts run |
| E2.3 Pin deps + lockfile + target Python | ✅ | — | (pending) | `requirements.lock` (resolves fresh); CI now `pip install -e .[milp]` + lockfile job (3.11/3.12) |

### E3 — CI + import smoke tests `P0`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E3.1 Import smoke tests | ✅ | — | `7ee09e1` | found+fixed `stat_report.py` import bug |
| E3.2 GitHub Actions workflow | ✅ | — | `700e1bb` | CI verified green on push: core 3.11/3.12 (blocking) + optional (non-blocking) all ✓ |

### E4 — Decompose `stat.py` `P1`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E4.1 Golden candidate-grid characterization test | ⬜ | — | — | before moving code |
| E4.2 Move logic to `src/dynamix`; re-exports | ⬜ | — | — | depends on E4.1, E2 |

### E5 — Test analytical core + coverage `P1`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E5.1 Poisson-binomial known-answer tests | ⬜ | — | — | |
| E5.2 Ticket/portfolio scoring tests | ⬜ | — | — | |
| E5.3 Skip-not-fail + coverage | ✅ | — | `700e1bb` | pipeline test skips w/o model runtime; coverage wired into CI (40% baseline) |

### E6 — Resolve evolutionary stub `P2`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E6.1 Decision gate + honesty fix | ⬜ | — | — | do regardless |
| E6.2 Implement evolutionary search (optional) | ⬜ | — | — | depends on E5.2 |

### E7 — De-dupe rounding storage `P2`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E7.1 Distinct-value grid encoding (flagged) | ⬜ | — | — | depends on E4, E1 |

### E8 — Cleanup & polish `P3`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E8.1 Unify on `logging` | ⬜ | — | — | |
| E8.2 Prune config aliases | ⬜ | — | — | prove non-use first |
| E8.3 Committed artifacts | ⬜ | — | — | `DynaMix-python/`, `DATA.csv` |
| E8.4 Scope determinism guarantee | ⬜ | — | — | SRS NFR-9 |

---

## Progress log

Record dated entries as work lands (newest first). Example format:

```
- 2026-06-29 — Plan established; 0/21 tasks started. Baseline: orchestrator import fixed,
  docs + tooling in place (see git history through commit 1bec389).
```

- 2026-06-29 — **E1 epic complete (4/4) → honest scoreboard.** The optimizer now ships a blunt
  EV/ROI + calibration verdict. E1.1 `compute_portfolio_economics` (pure `{gross,cost,net,best_hits}`)
  is the single source of payout math — the four strategy loops (greedy/milp/bandit/evo) now
  delegate to it (note: `eval_summary` aggregates per-draw `profit` and never duplicated the
  per-ticket payout math, so the dedup target was the strategy loops). E1.2 `random_ticket_baseline`
  samples each position from TRAIN-only observed pools (`build_value_pools_from_grid`, leakage-safe,
  seeded → deterministic) as the fair −EV control. E1.3 `qany_calibration` adapter reuses
  Brier/ECE on `(q_any, success)` pairs. E1.4 `build_strategy_scoreboard` composes them into a
  per-strategy `{realized_ge_H_rate, base_rate_ge_H, qany_ece, qany_brier, net_eur,
  baseline_net_eur, edge_eur}`; `write_final_summary` writes a `scoreboard` block to the summary
  JSON and the orchestrator prints a one-block verdict (skipped under `--quiet`, file still
  written). New tests: `test_economics`, `test_baseline`, `test_qany_calibration` (optimization),
  `test_final_summary_scoreboard` (contract). Suite: **76 tests, OK (skipped=5)**. No existing
  strategy selection/diagnostics behavior changed. **10 / 21**.
- 2026-06-29 — **E2.3 CI fix.** First E2.3 push went red: the `lockfile` job failed on Python
  3.11 because the lock pins numpy 2.5.0 (requires >=3.12). The lock is a 3.12+ snapshot; scoped
  its CI job to 3.12 and documented that 3.11 uses the pyproject floors (the `core` 3.11 job
  passed). Other jobs were green.
- 2026-06-29 — **E2.3 done → Epic E2 complete (3/3).** Added `requirements.lock` (pinned
  core + `milp` runtime; verified it resolves a full fresh install). Switched CI to the editable
  package: `core` and `optional` jobs now `pip install -e .[milp] ...`, and a new blocking
  `lockfile` matrix job (3.11/3.12) installs `requirements.lock` + the package and smoke-imports
  it. `test_packaging.py` gains lockfile assertions. `requires-python >=3.11`. Suite: 61 tests,
  OK (skipped=5). **6 / 21**. CI cross-version verification pending push.
- 2026-06-29 — **E2.2 done.** Moved entrypoints into the package: `stat.py` → `dynamix.stat`
  (kills the `import stat` stdlib collision), and `run_cli`/`orchestrator`/`stat_report`/`gui`
  → `dynamix.entrypoints.*`. Removed all `sys.path` bootstrapping and the orchestrator's
  load-by-path (`_import_project_stat_module`); orchestrator now does `from dynamix import stat`.
  Repo-root `*.py` are thin shims; four `dynamix-*` console scripts run end-to-end (`--help`
  exit 0). New `test_no_sys_path_insert_in_sources` guards against regressions (one sanctioned
  exception: `dynamix_core` extends the path to load the *external* DynaMix model repo). Docs
  synced: CLAUDE.md, README.md (install step), architecture.md. Suite: 61 tests, OK (skipped=5).
  **5 / 21**. Follow-ups: E2.3 (pin/lock deps; switch CI to `pip install -e .[milp]`); the deep
  `SRS.md` / `architectural_and_functional_analysis.md` still describe the pre-E2.2 module
  locations and want a refresh.
- 2026-06-29 — **E2.1 done.** Added `pyproject.toml` (PEP 621): `dynamix-lottery` package
  discovering namespace `dynamix` (src/) + regular `opt` (root); core deps; extras
  `milp`/`models`/`gui`/`dev`; four `dynamix-*` console scripts (targets wired in E2.2).
  `tests/core_unit/test_packaging.py` pins the manifest. Verified: `pip install -e .` succeeds,
  and from outside the repo `import dynamix.constants` / `import opt.opt_config` work with **no
  sys.path hacks**. Extras install independently. Suite: 60 tests, OK (skipped=5). **4 / 21**.
  Note: console scripts are declared but not runnable until E2.2 moves the entrypoints into
  `dynamix.entrypoints`.
- 2026-06-29 — **E3.2 + E5.3 done.** Added `.github/workflows/ci.yml` (blocking core job on
  Python 3.11/3.12 from `requirements.txt` + pulp + coverage; non-blocking optional-deps job).
  To make the core job green, completed E5.3: `test_full_pipeline_simulation` now *skips* when
  no model runtime (torch/darts/chaospy) is installed instead of failing, and coverage is wired
  into CI (40% baseline). Local suite: 54 tests, **OK (skipped=5)**, 0 failures. CI itself is
  unverified until pushed to GitHub (Actions can't run locally). **3 / 21**.
- 2026-06-29 — **E3.1 done** (`tests/integration/test_entrypoints_import.py`). Smoke test
  surfaced and fixed a real bug: `stat_report.py`'s `_import_project_stat_module()` could never
  find the repo-root `stat.py` (it relied on `import stat`, which resolves to the stdlib);
  now loads it by file path like `orchestrator.py`. Suite: 54 tests, only the pre-existing
  `test_full_pipeline_simulation` fails (deferred to E5.3). **1 / 21**.
- 2026-06-29 — Plan established; **0 / 21** tasks started. Baseline at commit `1bec389`:
  `orchestrator.py` import fixed; docs (architecture, AS-IS, SRS, analysis, ROADMAP, TDD_PLAN)
  and tooling (jcodemunch code index, jdocmunch doc index, `.venv` + core deps) in place.
