# Roadmap & Critique

Prioritized improvement plan for the DynaMix Lottery Forecasting System, with the critique
that motivates each item. Grounded in a read of the source as of 2026-06-29. See
[architectural_and_functional_analysis.md](architectural_and_functional_analysis.md) and
[SRS.md](SRS.md) for the system being critiqued.

> Severity scale: **P0** do first / highest value · **P1** important · **P2** worth doing ·
> **P3** cleanup.

---

## Strengths to preserve (don't regress these)

- **Leakage discipline** — truth tables/features/model fit on TRAIN only; TRAIN-relative
  reference points; resume guarded by grid fingerprint + config identity + slice
  (`validate_resume_or_fail`).
- **Calibration-first evaluation** — Brier/ECE + reliability plot of `q_any` vs empirical
  success is the right instrument for a probabilistic system.
- **Resumability & provenance** — atomic dual-format state writes, run-id lineage, hardened
  unpickler, structured per-worker error capture.
- **File-decoupled stages** — each stage runs, resumes, and is inspected independently.

---

## P0 — Make the success metric honest

**Problem.** The pipeline (calibrated logreg → Poisson-binomial `q` → MILP portfolio) is
sophisticated, but if draws are i.i.d. it is modelling noise, and nothing currently states a
blunt outcome. There is no prominent EV/ROI readout: given `ticket_cost_eur=2.0` and the
payout table, what was realized net profit per draw vs. a random-ticket baseline?

**Why it matters.** The risk is "the appearance of rigor" — calibrated-probability tooling
lending false confidence to a possibly money-losing strategy. The honest scoreboard is one
number, and the pieces already exist.

**Action.** In the final summary, surface per strategy on EVAL: realized ≥H rate vs. base
rate; whether `q_any` is actually calibrated (ECE); and net EUR vs. a random-ticket control.
If there is no edge, that is a *finding*, not a failure.

---

## P0 — Package the project; delete the `sys.path` hacks

**Problem.** No `pyproject.toml`/install step. Every entrypoint hand-rolls `sys.path`
bootstrapping — exactly the fragility that broke `orchestrator.py`. Two import conventions
coexisted. The `src/` migration is half-finished: core modules moved under `src/dynamix/`, but
`stat.py`/`orchestrator.py`/`gui.py` remain root scripts, and `stat_report.py` references a
`src.dynamix.stat` layout that doesn't exist.

**Action.** Add `pyproject.toml`, support `pip install -e .`, expose `console_scripts` for the
entrypoints, and remove all `sys.path` bootstrapping. Pin dependencies and add a lockfile.
Target Python 3.11/3.12 (3.14 lacks wheels for chaospy/torch — see [AS-IS.md](AS-IS.md)).
Finish the `src/` migration and delete the aspirational dead import path.

---

## P0 — Add CI and an import smoke test

**Problem.** No CI, and no test exercised the orchestrator — which is why a hard import break
shipped undetected.

**Action.** GitHub Actions running `run_tests.py` plus a 3-line "can it import" smoke test per
entrypoint, on every push, on a supported Python version.

---

## P1 — Extract forecasting-collection out of `stat.py`

**Problem.** `stat.py` is a ~1600-line god-module mixing config, rounding, the exporter,
parallel forecasting, stats aggregation, checkpointing, reporting, and the CLI. The tell:
`orchestrator.py` loads it *by file path* just to reuse `collect_model_forecasts_for_step` /
`build_candidate_grid_rows`.

**Action.** Move the forecasting-collection and candidate-grid-row logic into `src/dynamix/`
as an importable module; reduce `stat.py` to a thin CLI over it; have `orchestrator.py` import
the module instead of loading a script.

---

## P1 — Test the engine math; fix assert-vs-skip; measure coverage

**Problem.** The scoring core (`poisson_binomial_prob_ge`, `score_ticket_q`, beam search,
`compatibility_log_bonus`) is undertested relative to its importance. One integration test
*asserts* instead of *skipping* when no model deps are present (the failure observed in
[AS-IS.md](AS-IS.md)). No coverage measurement is configured.

**Action.** Known-answer unit tests for the engine math; make optional-dependency tests skip,
not fail; wire up coverage reporting.

---

## P2 — Resolve the evolutionary stub

**Problem.** `run_evolutionary` is a deterministic stub but is presented as a first-class
optimizer (selectable via `--optimizer evo`). Shipping a stub as a real feature is misleading.

**Action.** Implement it, or mark it `experimental` and remove it from the default choices
until it does something.

---

## P2 — De-duplicate rounding-mode storage

**Problem.** Storing all 7 rounding variants per (step, ts, model) is largely redundant — most
modes yield identical integers except at `.5` boundaries — inflating the candidate grid ~7×
(already ≈220k rows at 562 draws).

**Action.** Store distinct rounded values with the set of modes that produced each, instead of
one row per mode.

---

## P3 — Cleanup

- **Unify output discipline** — replace `print("[OPT]…")`/`print("[STAT]…")` with the
  `logging` module consistently; structured logs make long backtests greppable.
- **Prune config cruft** — backward-compat aliases that nothing reads (`DARTS_EPOCHS`,
  `OUTPUT_PLOTS_DIR`, `PROJECT_ROOT`).
- **Committed artifacts** — remove or document the empty `DynaMix-python/` placeholder;
  reconsider whether `DATA.csv` should live in git if it is operational data.
- **Scope the determinism claim** — seeds are set, but torch + multiprocessing are not
  bit-reproducible; scope the reproducibility guarantee to the optimizer, not the model layer.

---

## Summary

| Priority | Item | Value |
|----------|------|-------|
| P0 | Honest EV/ROI + calibration scoreboard | Tells you if the method works at all |
| P0 | Packaging (`pyproject.toml`, install, console_scripts) | Removes the whole class of import/path bugs |
| P0 | CI + import smoke tests | Prevents shipped breakage |
| P1 | Extract forecasting-collection from `stat.py` | De-god-modules the core; kills load-by-path |
| P1 | Engine-math tests + skip-not-fail + coverage | Confidence in the analytical core |
| P2 | Resolve evo stub; de-dupe rounding storage | Honesty + efficiency |
| P3 | Logging, config cruft, artifacts, determinism scope | Polish |

**Net assessment.** The engineering instincts are strong (leakage safety, calibration,
resumability), but the project is over-built relative to a half-finished foundation
(packaging/tests/CI) and under-honest about whether the method works (no EV reality check).
Doing the three P0 items yields the most value fastest.
