# TDD Implementation Plan

A test-driven execution plan for the improvements in [ROADMAP.md](ROADMAP.md), expressed as
GitHub-style **epics → tasks → acceptance criteria**. Every epic and task carries a **What**
(the change) and a **Why** (the justification), and each task is written as a
**Red → Green → Refactor** cycle so work starts from a failing test.

Grounded in the source as of 2026-06-29. Symbols referenced (e.g. `score_ticket_q`,
`eval_summary`, `build_candidate_grid_rows`) exist today; see
[architectural_and_functional_analysis.md](architectural_and_functional_analysis.md).

---

## How to use this plan

**TDD loop for every task**
1. **Red** — write the test(s) named in the task; run the relevant layer; confirm they *fail
   for the right reason* (missing behavior, not a typo).
2. **Green** — write the minimum code to pass.
3. **Refactor** — clean up with tests green.

**Test layers** (existing `run_tests.py` discovery dirs — put new tests in the right one):
`tests/core_unit`, `tests/contract`, `tests/optimization`, `tests/state_integrity`,
`tests/integration`, `tests/optional`.

**Conventions**
- Test files: `tests/<layer>/test_<area>.py`; test methods: `test_<behavior>_<condition>()`.
- Pure functions get `core_unit`/`optimization`; file/schema shapes get `contract`; resume/state
  gets `state_integrity`; multi-module flows get `integration`; anything needing torch/darts/
  chaospy/pulp gets `optional` **and must `skipTest` when the dep is absent** (never fail).
- Determinism: seed via `tests/_util.seed_everything`; assert exact values where math is exact.

**Labels used below**: `priority:P0..P3`, `type:feature|test|refactor|infra|chore`,
`layer:<test-layer>`, `effort:S|M|L`.

**Suggested execution order** (dependencies in parentheses):
`E3 → E2 → E1 → E5 → E4 → E6 → E7 → E8`. Rationale: stand up CI + import smoke tests first so
every later change is guarded; package next so tests run on an installed importable tree; then
the highest-value behavioral change (honest metrics); then deepen tests; then refactor; then
polish.

---

# EPIC E1 — Honest success metric: EV/ROI + calibration scoreboard
`priority:P0` · `type:feature`

**What.** Add a blunt, always-visible economic + calibration scoreboard to the optimizer's
final summary: per strategy on EVAL, realized ≥H rate vs. base rate, ECE of `q_any`, and net
EUR vs. a random-ticket control.

**Why.** The system is sophisticated machinery aimed at a target that may contain no signal.
Today nothing states the one honest outcome: *did this beat random, and does it make or lose
money?* Without it, calibrated-probability tooling risks lending false confidence. The pieces
(`payout_by_hits`, `ticket_cost_eur`, `eval_summary`, calibration funcs) already exist; this
epic composes them into a verdict. A "no edge" result is a valid, valuable finding.

**Definition of done.** `write_final_summary` output contains the scoreboard fields;
`orchestrator` prints them; all new logic is unit-tested with known-answer cases; no behavior
of existing strategies changes.

**Blocked by.** None (but land after E2/E3 so it ships guarded).

### Task E1.1 — Pure economics function
`type:feature` · `layer:optimization` · `effort:S`

**What.** A pure function `compute_portfolio_economics(tickets, true_ticket, *, payout_by_hits,
ticket_cost_eur) -> {gross_eur, cost_eur, net_eur, best_hits}` (place in `opt_strategies` next
to `eval_summary`/`realized_hits`, or a new `opt_economics.py`).

**Why.** Economics is currently implicit; isolating it as a pure, tested function makes the
scoreboard trustworthy and reusable by both `optimize` and `forecast` paths.

- **Red** — `tests/optimization/test_economics.py`:
  - `test_net_eur_known_case` — 3 tickets, a fixed `true_ticket`, payout `{3:10,...}`, cost 2.0
    → assert exact `gross/cost/net`.
  - `test_zero_hits_is_pure_loss` — no hits → `net == -K*cost`.
  - `test_uses_best_hits_per_ticket` — payout keyed off each ticket's own hit count.
- **Green** — implement using existing `realized_hits`.
- **Refactor** — have `eval_summary` delegate to it to remove duplication.

**Acceptance criteria**
- [ ] Function is pure (no I/O), fully type-annotated.
- [ ] Known-answer tests pass with exact equality.
- [ ] `eval_summary` reuses it (no duplicated payout math).

### Task E1.2 — Random-ticket control baseline
`type:feature` · `layer:optimization` · `effort:M`

**What.** `random_ticket_baseline(cfg, value_pools, *, seed, n_tickets, n_draws) ->
economics_summary`, sampling each position from its empirical observed-value distribution
(derive `value_pools` from TRAIN truth tables / observed per-TS values).

**Why.** "Net EUR" is meaningless without a control. A seeded random portfolio drawn from the
*same value distribution* is the fair −EV baseline the strategy must beat.

- **Red** — `tests/optimization/test_baseline.py`:
  - `test_baseline_is_deterministic_under_seed` — same seed ⇒ identical tickets.
  - `test_baseline_values_within_observed_pools` — every sampled value ∈ its pool.
  - `test_baseline_economics_shape` — returns the E1.1 economics keys aggregated over draws.
- **Green** — implement with a local `random.Random(seed)`.
- **Refactor** — extract pool-building helper if reused by E6.

**Acceptance criteria**
- [ ] Deterministic given `seed`.
- [ ] Samples only from observed per-position values.
- [ ] Reuses E1.1 for economics.

### Task E1.3 — `q_any` calibration on EVAL
`type:feature` · `layer:optimization` · `effort:S`

**What.** Compute ECE/Brier of predicted `q_any` vs. realized portfolio success across EVAL
draws, via existing `opt_calibration.expected_calibration_error` / `brier_score`.

**Why.** A strategy can "win" on a lucky EVAL while being badly miscalibrated. Surfacing ECE of
`q_any` tells you whether the probabilities themselves are trustworthy — the real scientific
question.

- **Red** — `tests/optimization/test_qany_calibration.py`:
  - `test_perfect_calibration_zero_ece` — synthetic q vs. outcomes that match ⇒ ECE ≈ 0.
  - `test_overconfident_has_positive_ece` — q=0.9 with 0.1 empirical ⇒ ECE large.
- **Green** — thin adapter assembling `(q_any, success)` pairs per draw and calling the calib
  funcs.
- **Refactor** — none expected.

**Acceptance criteria**
- [ ] Produces Brier + ECE for `q_any` over EVAL.
- [ ] Reuses `opt_calibration` (no re-implementation).

### Task E1.4 — Wire scoreboard into summary + console
`type:feature` · `layer:contract` · `effort:M`

**What.** Extend `write_final_summary` to include, per strategy: `realized_ge_H_rate`,
`base_rate_ge_H`, `qany_ece`, `qany_brier`, `net_eur`, `baseline_net_eur`, `edge_eur =
net_eur - baseline_net_eur`. Print a compact verdict block in `orchestrator`.

**Why.** Insight nobody reads is worthless; the verdict must be impossible to miss in both the
JSON/CSV artifact and the console.

- **Red** — `tests/contract/test_final_summary_scoreboard.py`:
  - `test_summary_contains_scoreboard_keys` — run summary writer on a tiny synthetic
    diag/results fixture into a temp dir (use `tests/_util.TempOutputRoot`); assert all keys
    present and numeric.
  - `test_edge_eur_is_net_minus_baseline` — arithmetic identity holds.
- **Green** — assemble fields from E1.1–E1.3; write to the existing summary path.
- **Refactor** — keep summary assembly in one helper.

**Acceptance criteria**
- [ ] Summary artifact contains every scoreboard key, per strategy.
- [ ] `edge_eur == net_eur - baseline_net_eur`.
- [ ] Console prints a one-block verdict; `--quiet` still writes the file.
- [ ] No change to existing strategy selection/diagnostics behavior.

---

# EPIC E2 — Packaging & import hygiene
`priority:P0` · `type:refactor`

**What.** Introduce `pyproject.toml`, make `dynamix` an installable package (`pip install -e
.`), expose `console_scripts` for the entrypoints, remove all `sys.path` bootstrapping, and
finish the half-done `src/` migration.

**Why.** Every entrypoint hand-rolls `sys.path` — precisely the fragility that broke
`orchestrator.py`. Two import conventions coexisted; `stat_report.py` references a
`src.dynamix.stat` layout that does not exist. Packaging deletes this entire bug class and
makes test/CI runs reflect a real importable tree.

**Definition of done.** `pip install -e .` works; entrypoints run as console scripts; no module
contains `sys.path.insert`; tests pass against the installed package.

**Blocked by.** E3 recommended first (so CI guards the migration).

### Task E2.1 — Add `pyproject.toml` + package metadata
`type:infra` · `layer:core_unit` · `effort:M`

**What.** PEP 621 `pyproject.toml` declaring the `dynamix` package (under `src/`), core deps
(from `requirements.txt`), optional-deps extras (`[project.optional-dependencies]`:
`models = [torch, darts, chaospy]`, `milp = [pulp]`, `gui = []`), and `console_scripts`
(`dynamix-cli`, `dynamix-stat`, `dynamix-opt`, `dynamix-report`).

**Why.** A single declarative manifest replaces ad-hoc pathing and documents the real
dependency surface (including the optional/fail-soft boundary).

- **Red** — `tests/core_unit/test_packaging.py`:
  - `test_pyproject_parses_and_declares_package` — load `pyproject.toml` (tomllib), assert
    `project.name`, `src` package discovery, and the four console scripts are declared.
- **Green** — author the file.
- **Refactor** — keep `requirements.txt` as a thin pointer or generate from extras.

**Acceptance criteria**
- [ ] `python -m build` / `pip install -e .` succeeds on Python 3.11/3.12.
- [ ] Optional extras install independently of core.
- [ ] Console scripts declared.

### Task E2.2 — Decide & finish the layout; entrypoint shims
`type:refactor` · `layer:integration` · `effort:L`

**What.** Make the root entrypoints (`run_cli`, `stat`, `orchestrator`, `stat_report`, `gui`)
into package modules or `console_scripts` `main()` shims; remove the aspirational
`src.dynamix.stat` reference; ensure `stat`/`orchestrator` resolve as normal imports.

**Why.** The migration is half-finished (core under `src/dynamix`, scripts at root). Finishing
it removes the load-by-path workaround in `orchestrator.py` and the dead `stat_report.py`
branch.

- **Red** — `tests/integration/test_entrypoints_import.py`:
  - `test_all_entrypoints_importable` — import each entrypoint module; assert a callable
    `main`. (This is also the E3 smoke test; co-locate.)
  - `test_no_sys_path_insert_in_sources` — scan source files; assert zero `sys.path.insert`
    occurrences (guards the regression).
- **Green** — move/rewire modules; update `console_scripts` targets.
- **Refactor** — delete dead import branches.

**Acceptance criteria**
- [ ] Every entrypoint imports cleanly with no `sys.path` manipulation anywhere.
- [ ] `orchestrator` imports the stat module normally (no `spec_from_file_location`).
- [ ] Console scripts run end-to-end (smoke).

### Task E2.3 — Pin dependencies + lockfile + target Python
`type:infra` · `layer:core_unit` · `effort:S`

**What.** Pin core deps with compatible floors; commit a lockfile (`requirements.lock` or
`uv.lock`/`pip-tools`); document Python 3.11/3.12 as supported (3.14 lacks chaospy/torch
wheels — see [AS-IS.md](AS-IS.md)).

**Why.** Reproducible installs; avoids the "newest Python has no wheels" trap encountered in
this environment.

- **Red** — `test_supported_python_declared` — assert `requires-python` includes 3.11/3.12 and
  excludes versions without wheels for declared model extras.
- **Green** — pin + lock.

**Acceptance criteria**
- [ ] Lockfile committed and installable.
- [ ] `requires-python` matches reality.

---

# EPIC E3 — CI + import smoke tests
`priority:P0` · `type:infra`

**What.** GitHub Actions workflow running `run_tests.py` (core layers) plus per-entrypoint
import smoke tests on every push/PR, on a supported Python.

**Why.** No CI exists, and no test exercised the orchestrator — which is why a hard import
break shipped. CI is the cheapest possible guard for everything that follows.

**Definition of done.** Green CI badge on `main`; a broken import fails CI.

**Blocked by.** None. Do first.

### Task E3.1 — Import smoke tests
`type:test` · `layer:integration` · `effort:S`

**What.** `tests/integration/test_entrypoints_import.py` (shared with E2.2) importing
`run_cli, stat, orchestrator, stat_report` and asserting `main` is callable. `gui` only if a
display-less import is safe (else guard).

**Why.** Catches exactly the class of failure (`ModuleNotFoundError`) that previously reached
`main`.

- **Red** — write the import tests against the *current* tree; on a clean checkout
  `orchestrator` already imports (fixed earlier), so these pass — but they would have caught
  the original bug. Add a deliberately-failing temporary assertion to confirm the harness runs,
  then remove.
- **Green** — n/a (tests guard existing behavior).
- **Refactor** — n/a.

**Acceptance criteria**
- [ ] All non-GUI entrypoints import with a callable `main`.
- [ ] Test runs in the default (non-optional) layer set.

### Task E3.2 — GitHub Actions workflow
`type:infra` · `effort:M`

**What.** `.github/workflows/ci.yml`: matrix Python 3.11/3.12; `pip install -e .[milp]`;
`python run_tests.py`; a separate job `python run_tests.py --include-optional` allowed to be
non-blocking (optional deps may be heavy/unavailable).

**Why.** Enforces the guards on every change without manual effort.

- **Red** — n/a (infra); validate by opening a PR and watching the run.
- **Green** — author workflow.
- **Refactor** — cache pip.

**Acceptance criteria**
- [ ] Core job blocks merge on failure.
- [ ] Optional-deps job runs but does not block.
- [ ] Workflow triggers on push + PR to `main`.

---

# EPIC E4 — Decompose `stat.py`: extract forecasting-collection
`priority:P1` · `type:refactor`

**What.** Move the forecasting-collection and candidate-grid-row logic
(`collect_model_forecasts_for_step`, `_forecast_single_series`, `build_candidate_grid_rows`,
`apply_round`, `RoundingMode`) into an importable `src/dynamix/` module (e.g.
`forecasting_collect.py` / `candidate_grid.py`). Reduce `stat.py` to a thin CLI over it; have
`orchestrator` import the module instead of loading a script by path.

**Why.** `stat.py` is a ~1600-line god-module; the tell is `orchestrator` loading it *by file
path* (`_import_project_stat_module`) just to reuse two functions. Extraction de-couples stage 3
from the stage-2 entrypoint and makes the shared logic unit-testable in isolation.

**Definition of done.** The two functions live in `src/dynamix`; `stat.py` and `orchestrator`
both import them; behavior is byte-identical on a golden candidate-grid fixture.

**Blocked by.** E2 (clean imports make the move trivial and safe).

### Task E4.1 — Characterization test (golden grid) before moving anything
`type:test` · `layer:contract` · `effort:M`

**What.** A characterization test that runs `collect_model_forecasts_for_step` (sequential,
`executor=None`) + `build_candidate_grid_rows` on a small fixed history and snapshots the row
set (schema + values) as a golden fixture.

**Why.** TDD safety net for a refactor: lock current behavior *before* moving code so the move
is provably behavior-preserving.

- **Red** — `tests/contract/test_candidate_grid_golden.py`:
  - `test_grid_rows_match_golden` — compare produced rows (sorted, normalized) to a committed
    golden JSON; **write the golden from the current implementation in the first run**, then
    freeze it.
  - `test_grid_schema_matches_required_cols` — columns ⊇ `opt_data.REQUIRED_COLS`.
- **Green** — n/a (capturing current behavior).

**Acceptance criteria**
- [ ] Golden fixture committed; test is deterministic (seeded; PCE/Darts/DynaMix absent → only
      always-available rows, or stub a fake model map).
- [ ] Schema superset assertion holds.

### Task E4.2 — Move logic to `src/dynamix`; keep `stat` re-exports
`type:refactor` · `layer:contract` · `effort:L`

**What.** Cut the functions into the new module; in `stat.py` import-and-re-export them for
backward compatibility; update `orchestrator` to import the new module directly and delete
`_import_project_stat_module`.

**Why.** Single source of truth; removes the load-by-path hack and the stdlib-`stat` collision
risk entirely.

- **Red** — reuse E4.1 golden (must still pass) + `tests/integration/test_orchestrator_uses_module.py`:
  - `test_orchestrator_imports_collector_from_package` — assert the symbol used by
    `_build_next_step_candidate_grid_via_stat` resolves to `dynamix.<module>`, not a
    path-loaded module.
- **Green** — perform the move + rewire.
- **Refactor** — remove dead `stat_report` legacy branch; thin `stat.py` CLI.

**Acceptance criteria**
- [ ] Golden grid test unchanged and green.
- [ ] `orchestrator` no longer uses `spec_from_file_location`.
- [ ] `stat.py` still runs as a CLI (re-exports preserved or call sites updated).

---

# EPIC E5 — Test the analytical core; fix skip-not-fail; coverage
`priority:P1` · `type:test`

**What.** Known-answer unit tests for the scoring core
(`poisson_binomial_prob_ge`, `score_ticket_q`, `build_ticket_pool_beam`,
`compatibility_log_bonus`, `portfolio_q_any`); convert the asserting integration test to skip
on absent deps; add coverage measurement.

**Why.** The math that decides every ticket is undertested relative to its importance, and one
integration test *fails* (not skips) when model deps are absent — a false negative observed in
[AS-IS.md](AS-IS.md). Coverage makes gaps visible.

**Definition of done.** Engine math has direct tests; the model-pipeline test skips cleanly
with no deps; `coverage` reported in CI.

**Blocked by.** None (can proceed in parallel; nicer after E3).

### Task E5.1 — Poisson-binomial known-answer tests
`type:test` · `layer:core_unit` · `effort:S`

**What.** Test `poisson_binomial_prob_ge` against closed forms.

**Why.** It is the exact-probability heart of `q`; an off-by-one in the DP silently biases
every score.

- **Red** — `tests/core_unit/test_poisson_binomial.py`:
  - `test_all_equal_p_reduces_to_binomial` — `ps=[p]*n`, compare to `scipy.stats.binom.sf`.
  - `test_H_zero_is_one`, `test_H_gt_n_is_zero`.
  - `test_two_position_hand_computation` — `ps=[0.5,0.5], H=1` ⇒ `0.75` exactly.
- **Green** — tests should pass against current code; if any fails it's a real bug to fix.

**Acceptance criteria**
- [ ] All four pass; any discrepancy triaged as a bug fix.

### Task E5.2 — Ticket/portfolio scoring tests
`type:test` · `layer:optimization` · `effort:M`

**What.** Tests for `score_ticket_q` (q × exp(bonus), clipped), `compatibility_log_bonus`
(pair/triple log-count math), `portfolio_q_any` (`1−Π(1−q)`), `build_ticket_pool_beam`
(beam ranks by Σlog p, dedupes, respects `beam`).

**Why.** These compose into selection; locking their semantics prevents silent regressions
during E4/E6 refactors.

- **Red** — `tests/optimization/test_engine_scoring.py` with small hand-built
  `TruthHistoryTables`, `shortlists`, and a stub fitted model (or inject `p_hit` directly):
  - `test_qany_formula`, `test_compat_bonus_uses_log1p_counts`,
    `test_beam_respects_width_and_dedupes`, `test_score_is_clipped`.
- **Green** — fix any exposed defects.
- **Refactor** — extract test builders into `tests/_builders.py` (already present).

**Acceptance criteria**
- [ ] Each scoring function has a known-answer test.
- [ ] Tests do not require torch/darts/chaospy/pulp.

### Task E5.3 — Skip-not-fail + coverage
`type:test` · `layer:integration` · `effort:S`

**What.** Change `test_full_pipeline_simulation` to `skipTest` when zero model families are
available; add `coverage` config and a CI step.

**Why.** A missing optional dep is an environment condition, not a defect; failing on it
produces false red. Coverage quantifies the gaps this epic targets.

- **Red** — `test_full_pipeline_skips_without_models` — with all model flags forced off, the
  test reports *skipped*, not failed.
- **Green** — implement the skip guard; wire `coverage run -m … run_tests.py` in CI.

**Acceptance criteria**
- [ ] No-deps environment yields skips, never failures, across the default layers.
- [ ] Coverage summary emitted in CI; baseline % recorded.

---

# EPIC E6 — Resolve the evolutionary stub
`priority:P2` · `type:feature`

**What.** Either implement `run_evolutionary` as a real search over strategy parameters, or
mark it `experimental` and remove `evo` from the default `--optimizer` choices until it does.

**Why.** It is presented as a first-class optimizer but is a deterministic stub. Shipping a stub
as a real feature is misleading and inflates the system's apparent capability.

**Definition of done.** `evo` either does genuine optimization with tests, or is clearly gated
as experimental and excluded from defaults.

**Blocked by.** E5.2 (scoring tests give a fitness oracle).

### Task E6.1 — Decision gate + honesty fix (do this regardless)
`type:chore` · `layer:contract` · `effort:S`

**What.** Add a capability flag/label; if not implemented, `--optimizer evo` prints an
"experimental/stub" warning and is excluded from `all`.

**Why.** Immediate honesty even before implementation lands.

- **Red** — `tests/contract/test_optimizer_choices.py::test_evo_marked_experimental` — `all`
  does not silently include a stub; selecting `evo` surfaces the experimental status.
- **Green** — implement gating.

**Acceptance criteria**
- [ ] `all` excludes the stub; explicit `evo` is clearly labeled.

### Task E6.2 — Implement evolutionary search (optional, if pursued)
`type:feature` · `layer:optimization` · `effort:L`

**What.** Population over `{max_overlap_k, shortlist_m, beam, hit_threshold}`; fitness = EVAL
`edge_eur` (from E1) or mean `q_any`; seeded selection/mutation/crossover for `evo_generations`/
`evo_pop_size`.

**Why.** Turns a placeholder into a genuine hyper-strategy search with a meaningful objective.

- **Red** — `tests/optimization/test_evolutionary.py`:
  - `test_evolution_is_deterministic_under_seed`.
  - `test_evolution_improves_or_matches_initial_fitness` on a synthetic grid where the optimum
    is known.
- **Green** — implement.
- **Refactor** — share fitness with strategy eval.

**Acceptance criteria**
- [ ] Deterministic under `seed`.
- [ ] Never returns worse-than-initial best fitness on the fixture.

---

# EPIC E7 — De-duplicate rounding-mode storage
`priority:P2` · `type:refactor`

**What.** Store distinct rounded values with the set of modes that produced each, instead of one
candidate-grid row per rounding mode.

**Why.** The 7 rounding modes mostly yield identical integers (differing only at `.5`
boundaries), inflating the grid ~7× (≈220k rows at 562 draws). Distinct-value storage cuts I/O
and optimizer load time with no information loss.

**Definition of done.** Grid encodes distinct `rounded` values + originating mode set; optimizer
consumes the new shape; row count drops materially on real data; results are unchanged.

**Blocked by.** E4 (candidate-grid logic extracted/tested), E1 economics stable.

### Task E7.1 — Distinct-value grid encoding (behind a flag)
`type:refactor` · `layer:contract` · `effort:L`

**What.** Add `rounding_ids` (set) per distinct `(ts, model, rounded)` and emit one row per
distinct value; gate behind `--statgrid-dedupe` initially.

**Why.** A flag lets you compare old vs. new outputs and migrate safely.

- **Red** — `tests/contract/test_grid_dedupe.py`:
  - `test_dedupe_preserves_distinct_values` — union of values identical to legacy.
  - `test_dedupe_row_count_le_legacy` — strictly ≤, and < when modes collide.
  - `test_optimizer_results_unchanged_under_dedupe` — same selected tickets on a fixture.
- **Green** — implement encoder + reader update in `opt_data`.
- **Refactor** — once validated, make dedupe the default; keep `REQUIRED_COLS` compatible.

**Acceptance criteria**
- [ ] No distinct candidate value lost.
- [ ] Row count reduced on real data; optimizer output identical.
- [ ] Consumer (`opt_data`) handles both shapes during migration.

---

# EPIC E8 — Cleanup & polish
`priority:P3` · `type:chore`

**What.** Unify logging, prune dead config aliases, address committed artifacts, and scope the
determinism claim.

**Why.** Reduces tech debt accumulated across refactors and tightens the honesty of the docs.

### Task E8.1 — Unify on `logging`
`type:chore` · `layer:core_unit` · `effort:M`
**What.** Replace `print("[OPT]…")`/`print("[STAT]…")` with module loggers; keep console
handler. **Why.** Greppable, level-controlled output for long backtests.
- **Red** — `test_no_bare_bracket_prints_in_sources` (scan for `print("[OPT]`/`[STAT]`).
- [ ] Sources use `logging`; `--quiet` maps to log level.

### Task E8.2 — Prune config aliases
`type:chore` · `layer:core_unit` · `effort:S`
**What.** Remove aliases nothing reads (`DARTS_EPOCHS`, `OUTPUT_PLOTS_DIR`, `PROJECT_ROOT`).
**Why.** Dead config misleads. — Use `check_references`/grep to prove non-use first.
- [ ] Each removed name has zero references repo-wide before deletion.

### Task E8.3 — Committed artifacts
`type:chore` · `effort:S`
**What.** Remove or document the empty `DynaMix-python/` placeholder; decide whether `DATA.csv`
belongs in git (sample vs. operational). **Why.** Repo hygiene; avoid shipping operational data.
- [ ] Placeholder removed or `README` documents its purpose; data policy stated.

### Task E8.4 — Scope the determinism guarantee
`type:chore` · `layer:contract` · `effort:S`
**What.** Update SRS/NFR-9 to scope reproducibility to the optimizer; note torch+multiprocessing
are not bit-reproducible. **Why.** Avoid over-claiming.
- [ ] `SRS.md` NFR-9 scoped; an integration test asserts optimizer determinism only.

---

## Cross-epic Definition of Done

- [ ] CI green on `main` (E3), package installable (E2).
- [ ] Honest scoreboard visible in every optimize run (E1).
- [ ] Engine math + scoring under known-answer tests; no false-fail on missing deps (E5).
- [ ] `stat.py` no longer loaded by path; forecasting-collection is an importable module (E4).
- [ ] `evo` is honest; rounding storage de-duplicated; polish landed (E6–E8).

## Dependency graph

```
E3 ─┐
E2 ─┼─► E1 ─► E5 ─► E4 ─► E7
    │              └► E6
    └──────────────────────► E8 (anytime)
```
