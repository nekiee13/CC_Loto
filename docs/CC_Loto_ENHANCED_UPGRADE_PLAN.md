# CC_Loto Enhanced Upgrade Plan (v2)

**Status:** Proposed
**Supersedes:** `docs/CC_Loto_PROJECT_UPGRADE_PLAN.md` (the draft plan)
**Basis:** Draft plan cross-checked against the repository at commit `570d2c8` (code, tests, CI, packaging, docs) on 2026-07-04.

---

## 0. How this plan was produced

The draft plan was evaluated claim-by-claim against the actual code. Every epic below
carries **evidence** (file and line references) so a reader can verify the gap exists
before starting work. Where the draft proposed something that *already exists*, the epic
was reframed to target only the true remaining gap. Several new areas for improvement
(AFI-11 .. AFI-18) were found during the code audit and are added as new epics.

**Guiding principles (unchanged from the draft, made explicit):**

1. **No-edge honesty is an invariant.** The SRS claims no predictive efficacy for a
   genuinely random lottery. Every new report, page, and summary must keep that message
   visible. No epic below may weaken it.
2. **Stages stay decoupled** (forecast → StatGrid → optimize), talking only through
   explicit file contracts.
3. **KISS.** Tasks are deliberately small. Each task should be finishable, testable, and
   reviewable on its own. Prefer adding a contract test over adding a framework.
4. **Fail soft on optional deps** (torch/darts/chaospy) — preserved everywhere.

---

## 1. Evaluation of the draft plan against the AS-IS state

### 1.1 What the draft got right (verified in code)

| Draft claim | Verification | Verdict |
|---|---|---|
| No bootstrap CIs / baseline percentiles (U1) | Only a single seeded random baseline exists: `opt/opt_strategies.py::random_ticket_baseline` (one seed, aggregate totals, no distribution) | ✅ Correct gap |
| No walk-forward validation (U2) | No walk-forward / rolling-fold code anywhere in `opt/` or `src/` | ✅ Correct gap |
| No health-check command (U3) | No `dynamix-health` console script in `pyproject.toml`; only fragments exist (webapp CSV header check `src/dynamix/webapp/data_io.py:91`, `darts_core --selftest`, `src/dynamix/device.py`) | ✅ Correct gap |
| Domain clamping fixed late, needs a contract (U5) | Clamp/domain logic exists in **four independent copies** — see AFI-11 below | ✅ Correct, and worse than the draft says |
| No strategy stability layer (U6) | `write_final_summary` reports one scoreboard from one EVAL slice | ✅ Correct gap |
| Docs may drift (U7) | Live drift found — see AFI-12 below | ✅ Correct, with concrete instances |
| No run audit pack (U8) | `summary_current.json` already records `code_version`, `config_identity`, `grid_fingerprint`, timestamps (`opt/opt_diagnostics.py::write_final_summary`) but no environment / dependency / timing info | ✅ Correct gap (partial overlap noted) |

### 1.2 Where the draft is out of date or imprecise

| Draft claim | Actual state | Consequence |
|---|---|---|
| U4.1: "Write `schema.json` into each StatGrid run folder" | **Already implemented.** The StatGrid exporter writes `schema.json` with `schema_version: "1.1"`, columns, dedupe flag (`src/dynamix/stat.py:352` `SCHEMA_VERSION = "1.1"`, `_write_schema_once` at `:373`) | U4 is reframed: the gap is on the **consumer** side — `opt/opt_data.py` never reads `schema.json`; it only hashes columns for resume safety (`opt_data.py:137`) |
| U4 scope | A second, unrelated schema tag exists: `tools/statgrid/statgrid_merge.py:575` writes `"schema_version": "db-1.0"` | The merge tool must be included in the same schema registry, or the two version namespaces must be explicitly documented as separate |
| AS-IS.md "51 of 52 pass" snapshot | AS-IS.md describes an older dev box (Python 3.14, no models). The intended production runtime is Windows (`f:\venv\loto_dynamix`) per its own deployment note | AS-IS.md must be labeled a dated snapshot (U7), and Windows must enter CI (new epic U11) |
| Draft treats test suite as fully wired | **`tests/test_checkpoint_loop.py` is orphaned**: it sits at `tests/` root, outside every directory in `run_tests.py::LAYER_DIRS` (`run_tests.py:43-53`), so neither `run_tests.py` nor CI ever discovers or runs it (16 test symbols, silently dead) | Immediate fix — new epic U0 |
| Draft's AFI-9 (synthetic demo data) got no epic | Confirmed missing; additionally there is **no zero-dependency model family at all** — if torch/darts/chaospy are absent, Stage 1 produces nothing (the AS-IS box proved this) | New epic U13 covers both with one mechanism |

### 1.3 Newly discovered areas for improvement (beyond the draft)

- **AFI-11 — Domain logic exists in 4 copies.** (1) `src/dynamix/constants.py:106`
  `TS_VALUE_DOMAINS`; (2) `opt/opt_config.py:29` `_default_ts_value_domains()` — the
  comment at `constants.py:105` explicitly admits "opt/ is a standalone package and
  carries its own copy"; (3) `src/dynamix/entrypoints/gui.py:143` `_round_clamp_ball`;
  (4) `src/dynamix/entrypoints/run_cli.py:100-119` a near-identical round+clamp helper.
  Four copies is how the original impossible-values bug happened.
- **AFI-12 — Live documentation drift.** `CLAUDE.md`'s intro still says the project has
  "no packaging or `requirements.txt`" while `pyproject.toml`, `requirements.txt` (32
  lines) and `requirements.lock` all exist; `CLAUDE.md`'s test-layer list omits the
  `webapp` layer that `run_tests.py:53` runs by default; `pyproject.toml:42` still says
  "to be unified in E2.2" although E2 is marked ✅ Done in PROGRESS.md.
- **AFI-13 — No static quality gates.** No ruff/flake8/mypy/pre-commit config exists
  anywhere; CI (`.github/workflows/ci.yml`) runs tests only, and `coverage report` has no
  `--fail-under`, so coverage can decay silently. Large files (`src/dynamix/stat.py`
  1379 lines, `entrypoints/gui.py` 992 lines) make unguarded drift likely.
- **AFI-14 — The intended production OS is untested.** CI runs `ubuntu-latest` only,
  but AS-IS.md says the real runtime is a Windows venv. `webapp/runner.py::stop_job`
  is explicitly POSIX-process-group based (`runner.py:141`), i.e. the GUI Stop button's
  behavior on the actual target OS is unverified.
- **AFI-15 — The GUI↔CLI progress contract is informal.** The Streamlit runner scrapes
  progress from free-text logs with regexes (`runner.py:165` `_NUM_PAIR`, `:211` `_ETA`).
  Git history shows this contract already broke at least twice ("webapp progress-bar
  fix", "advance bar during Darts" commits). Nothing stops the next CLI wording change
  from silently freezing the progress bar again.
- **AFI-16 — `tools/` is a blind spot.** `tools/statgrid/statgrid_merge.py` is 632 lines
  with its own schema tag and **zero tests**; `tools/qa/`, `tools/darts/`,
  `tools/maintenance/` are likewise untested and excluded from packaging without any
  statement of support status.
- **AFI-17 — No always-available baseline forecaster.** All three model families are
  optional heavy deps. A trivial, dependency-free "naive" family (e.g. last value /
  per-series frequency sampler) would (a) make Stage 1 runnable everywhere, (b) enable a
  true end-to-end CI test, (c) provide the scientifically honest control every fancier
  model must beat, and (d) power the demo mode of draft AFI-9.
- **AFI-18 — Dual dependency declarations.** `pyproject.toml` dependencies "mirror
  requirements.txt" by hand (comment at `pyproject.toml:15`). Nothing tests that the two
  stay consistent.

---

## 2. Enhanced upgrade plan

Epic numbering keeps the draft's U1–U8 (revised where needed) and adds U0 and U9–U13.
Every task states **What** and **Why**; comments carry the evidence.

---

## Milestone M0 — Ground Truth (fix what is already wrong)

### EPIC U0 — Truth & Wiring Fixes

**Priority:** P0 · **Type:** bugfix / docs · **Status:** Proposed · **Depends on:** nothing

**What:** Fix the small set of things that are *currently false or silently broken*:
an orphaned test file, three stale doc statements, and a stale packaging comment.

**Why:** Every later epic assumes the docs describe reality and the test runner runs the
tests. These are 15-minute fixes with outsized protective value; doing them first also
gives U7 (docs governance) a clean starting point.

> **Comment:** This epic exists because the audit found the drift *now*, not
> hypothetically. Shipping it first is the cheapest possible win.

#### Task U0.1 — Re-home the orphaned checkpoint-loop test

**What:** Move `tests/test_checkpoint_loop.py` into the correct layer directory
(likely `tests/state_integrity/` or `tests/integration/`), fix imports, and confirm it
passes or mark known failures.

**Why:** It sits outside every `LAYER_DIRS` entry (`run_tests.py:43-53`), so it has
never run under `run_tests.py` or CI. A test that never runs is worse than no test — it
documents a guarantee nobody is checking.

**Acceptance criteria:**
- `python run_tests.py` discovers and executes the file (visible in the test count).
- CI runs it.
- No test file remains directly under `tests/` root (only `_*.py` helpers).

#### Task U0.2 — Add a runner guard against future orphan tests

**What:** Add one small test (or a check inside `run_tests.py`) asserting every
`tests/**/test_*.py` file is inside a directory listed in `LAYER_DIRS`.

**Why:** U0.1 fixes the instance; this prevents the class. One glob + one assert.

**Acceptance criteria:**
- Placing a `test_x.py` directly under `tests/` makes the suite fail with a clear message.
- The guard itself runs in a default layer.

#### Task U0.3 — Correct stale statements in CLAUDE.md

**What:** Fix the intro ("no packaging or `requirements.txt`" → describe the installable
package, `requirements.txt`, `requirements.lock`) and add the missing `webapp` layer to
the documented test-layer list.

**Why:** CLAUDE.md is the operating manual for AI-assisted work on this repo; false
statements there propagate directly into wrong future changes.

**Acceptance criteria:**
- CLAUDE.md no longer contradicts `pyproject.toml` / `run_tests.py`.
- The layer table matches `LAYER_DIRS` exactly (all 7 layers).

#### Task U0.4 — Resolve the "to be unified in E2.2" packaging comment

**What:** `pyproject.toml:42` still says the mixed layout (`dynamix` under `src/`, `opt`
at repo root) is "to be unified in E2.2", but E2 is closed. Either (a) record the layout
as an accepted permanent decision in the comment + architecture.md, or (b) open a real
task to move `opt/` under `src/`. **Recommendation: (a)** — the layout works, is
CI-tested, and moving `opt/` would churn every import for zero user value.

**Why:** A "temporary" comment older than the epic that was supposed to remove it is a
small lie in the build config. Decide once, write it down.

**Acceptance criteria:**
- The comment states the actual decision, not a stale intention.
- architecture.md documents the two-package layout and the reason it stays.

---

## Milestone M1 — Operational Confidence

### EPIC U3 — Model Runtime Health & Environment Diagnostics *(kept from draft, expanded)*

**Priority:** P0 · **Type:** feature / usability · **Status:** Proposed · **Depends on:** nothing

**What:** One `dynamix-health` command (and a Streamlit page reusing the same pure
helper) reporting: Python version, package install state, core deps, optional deps
(torch/darts/chaospy/pulp/streamlit), GPU/CPU device, `DATA.csv` presence + shape +
domain validity, `Output/` writability — as human text and JSON, with sane exit codes.

**Why:** The AS-IS box proved a user can sit in front of a fully "installed" repo where
zero model families work (Python 3.14, no wheels, no gcc) and only find out via a failing
pipeline. One command must answer "can this machine forecast, and if not, why".

> **Comment:** Reuse, don't rebuild: header validation exists in
> `webapp/data_io.py:91`, device probing in `dynamix/device.py`, a Darts self-test in
> `darts_core.py` (`--selftest`, line 671), and install-repair guidance in
> `tools/maintenance/fix_darts_install.py`. The health module should *call* these, and
> the known failure signatures from AS-IS.md (no cp314 wheel, no compiler) should become
> explicit detected cases with the documented remedies as "next steps" text.

#### Task U3.1 — Pure health-report builder

**What:** `dynamix/health.py` with a pure `build_health_report() -> dict` (no printing,
no exits): sections for python/env, core deps, optional deps per model family, device,
data file, output dir.

**Why:** Pure function → trivially testable, reusable by CLI and GUI without drift
(same lesson as the clamp bug).

**Acceptance criteria:**
- Returns a plain dict; unit-testable with monkeypatched importlib/filesystem.
- Missing optional deps are reported `missing` with a one-line remedy, never raising.
- No heavy import happens unless the family is actually probed.

#### Task U3.2 — `dynamix-health` console command

**What:** Console script (added to `[project.scripts]`) rendering the report as text or
`--json`; exit 0 for healthy/degraded-usable, non-zero only for fatal (no data file, no
core deps, unwritable output).

**Why:** Users need one command; scripts and CI need one JSON and one exit code.

**Acceptance criteria:**
- `dynamix-health` and `dynamix-health --json` both work after `pip install -e .`.
- Exit-code policy is tested (fatal vs degraded cases).
- Command listed in README + User Manual.

#### Task U3.3 — `--deep` model smoke probe

**What:** Optional `--deep` flag: tiny forecast call per *installed* family with a
timeout; per-family verdict `available` / `missing` / `failed` / `skipped`.

**Why:** Import success ≠ runtime success (torch can import and still fail on a CUDA
mismatch). Timeout protection because a hung model probe must not hang the health check.

**Acceptance criteria:**
- Each family reports one of the four verdicts; failures include the exception summary
  and a next step.
- Wall-clock timeout per family is enforced and tested (with a fake slow family).
- Without `--deep`, no model code is executed.

#### Task U3.4 — Streamlit Health page

**What:** New page calling `build_health_report()`, status badges (data, models, GPU,
MILP, output dir), JSON download button.

**Why:** Click-only users deserve the same answer as CLI users, from the same code path.

**Acceptance criteria:**
- Page renders with all optional deps absent (badges say missing, page never crashes).
- JSON download equals the CLI `--json` output.
- Covered by a `tests/webapp/` test using the existing GUI test approach.

#### Task U3.5 — Health smoke in CI

**What:** Add `dynamix-health --json` to the CI core job; assert exit 0 and parseable JSON.

**Why:** The health tool itself must not rot; CI is its natural consumer.

**Acceptance criteria:**
- CI fails if the command errors or emits invalid JSON.
- Runs in both Python matrix versions.

---

### EPIC U5 — Single Domain Authority & Output Contract *(kept from draft, sharpened)*

**Priority:** P0 · **Type:** quality / contract · **Status:** Proposed · **Depends on:** nothing

**What:** Collapse the four independent copies of ball-domain knowledge (AFI-11) into
one authority, then lock every output path (CLI, optimizer tickets, Streamlit, Tkinter,
JSON/CSV exports) to it with contract tests, plus ingest-side validation and raw
out-of-domain diagnostics.

**Why:** Impossible values reached users once already; the root cause (duplicated
domain logic) is still in place. Until there is one authority, every new display path
re-creates the bug.

> **Comment:** The four copies: `constants.py:106` (`TS_VALUE_DOMAINS`),
> `opt_config.py:29` (`_default_ts_value_domains`), `entrypoints/gui.py:143`
> (`_round_clamp_ball`), `entrypoints/run_cli.py:100-119`. Note `opt/` deliberately
> avoids importing `dynamix` ("standalone package"); task U5.2 respects that boundary
> with an equality contract test instead of a runtime import — KISS and zero coupling.

#### Task U5.1 — Create `dynamix/domain.py` as the single authority

**What:** One module holding: per-series `(lo, hi)` domains, `clamp(ts, value)`,
`round_half_up(value)`, `round_clamp_ball(ts, value) -> Optional[int]`, and the
missing-value display rule (non-finite → `None`, never `0`).

**Why:** One importable truth. Everything display-side becomes a caller.

**Acceptance criteria:**
- Pure module, no pandas/GUI imports, fully unit-tested (bounds, NaN, ±inf, floats).
- `TS_VALUE_DOMAINS` in `constants.py` re-exports from (or is consumed by) this module —
  one definition site.

#### Task U5.2 — Point all four call sites at the authority

**What:** Replace the private helpers in `entrypoints/gui.py` and
`entrypoints/run_cli.py` with imports of `dynamix.domain`; for `opt/`, keep its local
default but add a contract test asserting `OptConfig` domains == `dynamix.domain`
domains.

**Why:** Deletes two duplicate implementations outright; for `opt/` the equality test
gives drift protection without breaking its standalone-package property.

**Acceptance criteria:**
- `_round_clamp_ball` and the run_cli twin are gone; behavior unchanged
  (existing display tests still pass).
- New contract test fails if either domain table changes alone.

#### Task U5.3 — Output-domain contract tests on every path

**What:** One test module feeding out-of-range / NaN / non-integer inputs through:
forecast JSON writer, CLI table formatter, Tkinter formatter, Streamlit parser/formatter,
optimizer ticket construction.

**Why:** The invariant "TS_1..TS_5 ∈ 1–50, TS_6..TS_7 ∈ 1–12, missing renders as
missing" becomes executable, per path, forever.

**Acceptance criteria:**
- Every listed path has explicit cases for below-lo, above-hi, NaN, inf, float.
- All outputs in-domain or rendered-missing; `0` never appears as a ball value.
- Tests run in default layers with no optional deps.

#### Task U5.4 — Ingest-side range validation for DATA.csv

**What:** Extend the existing integer checks (`constants.py:147` block:
`TS_REQUIRE_INTEGERS`, `TS_INTEGER_TOL`) with per-series *range* validation in
`data_utils.load_lottery_data`; configurable reject-vs-warn behavior, defaulting to
hard error on out-of-domain values.

**Why:** Garbage should be caught at the door, not clamped at the exit. The exit clamp
(U5.1) then only ever handles *model* output, and a bad `DATA.csv` edit is caught the
day it happens.

**Acceptance criteria:**
- A `DATA.csv` row with `TS_6 = 13` fails loading with a message naming row and column.
- Valid historical file loads unchanged (golden check on row count).
- Behavior documented in the User Manual data section.

#### Task U5.5 — DATA.csv validation job in CI

**What:** Tiny CI step (or test) that loads the committed `DATA.csv` through the U5.4
validator.

**Why:** Draw data is updated by routine commits (e.g. `570d2c8` "data: update…").
Each such commit currently ships unchecked. This makes every data update self-verifying.

**Acceptance criteria:**
- CI fails if the committed `DATA.csv` violates schema or domains.
- Runtime under a few seconds; no model deps.

#### Task U5.6 — Raw out-of-domain diagnostics *(draft U5.3, kept)*

**What:** Count raw (pre-clamp) model predictions falling outside domains, per model ×
series, in the stat run summary; surface a warning in the GUI when the rate is high.

**Why:** Clamping protects users but can mask a model that has gone off the rails;
auditability requires the raw counts stay visible.

**Acceptance criteria:**
- Summary includes out-of-domain counts and rates by model and TS.
- Clamped display output is unaffected.
- GUI shows a warning above a configurable rate threshold.

---

## Milestone M2 — Scientific Reliability

### EPIC U1 — Scoreboard Uncertainty & Baseline Distributions *(kept from draft, refined)*

**Priority:** P0 · **Type:** feature / analytics · **Status:** Proposed · **Depends on:** nothing (U2 consumes its output)

**What:** Add bootstrap confidence intervals (net EUR, edge EUR, realized ≥H rate),
a seeded random-baseline *distribution* (p5/p50/p95 + strategy percentile), and a
conservative verdict label to the existing scoreboard.

**Why:** The scoreboard (`opt_diagnostics.py::build_strategy_scoreboard` /
`write_final_summary`) is honest but point-estimate-only, and the control is a single
seeded baseline (`random_ticket_baseline`, one seed). In a domain that is *expected* to
be random, a point estimate against one control invites over-reading; intervals and a
control distribution are the minimum honest reporting.

> **Comment:** Build on what exists. `random_ticket_baseline` is already seeded and
> deterministic — U1.2 is "call it N times with seeds 0..N-1 and take percentiles",
> not a new simulator. The new keys extend `summary_current.json`'s existing
> `scoreboard` / `baseline` blocks; the schema addition is backward-compatible
> (only additions).

#### Task U1.1 — Bootstrap CI helper (pure function)

**What:** Pure function: given per-draw diagnostic rows and a seed, resample draws with
replacement and return CI bounds for net EUR, edge EUR, realized ≥H rate.

**Why:** Deterministic, dependency-free (numpy only), testable on a tiny fixture with
hand-checkable resampling.

**Acceptance criteria:**
- Fixed seed + fixed rows → identical output (tested).
- Handles small n (≥1 draw) without crashing; documents that CIs on tiny n are wide,
  not meaningless-crash.
- No model or GUI imports.

#### Task U1.2 — Baseline distribution from repeated seeded baselines

**What:** Run `random_ticket_baseline` across N seeds (config: count, default modest);
report p5/p50/p95 of baseline net EUR and each strategy's percentile rank within that
distribution.

**Why:** One random control can be lucky. A distribution is the fair yardstick, and it
reuses existing tested code.

**Acceptance criteria:**
- Same seed set → identical distribution (tested).
- `summary_current.json` gains `baseline_distribution {p5,p50,p95,n_seeds}` and
  per-strategy `baseline_percentile`.
- Default N keeps optimize runtime increase modest (document the measured cost).

#### Task U1.3 — CI/percentile fields wired into summary + scoreboard

**What:** Add `net_eur_ci_low/high`, `edge_eur_ci_low/high`, `realized_rate_ci_low/high`
per strategy into the scoreboard block written by `write_final_summary`.

**Why:** The summary JSON is the cross-stage contract consumed by the GUI and reports;
the numbers only matter once they live there.

**Acceptance criteria:**
- Contract test (`tests/contract/test_final_summary_scoreboard.py` extended) asserts
  presence and ordering (low ≤ point ≤ high).
- Old summaries without the fields still load wherever summaries are read (GUI reports).

#### Task U1.4 — Conservative verdict label

**What:** Per-strategy label: `NO_EDGE` (edge CI ≤ 0 or crosses 0), `UNCERTAIN`
(CI too wide per configured threshold), `WEAK_EDGE`, `ROBUST_EDGE` (CI > 0 *and*
calibration within threshold). Rendered in console verdict and GUI.

**Why:** Beginners read labels, not intervals. The label must be conservative by
construction so the honest-reporting invariant survives the UI layer.

**Acceptance criteria:**
- Label logic is a pure function with a truth-table test.
- `ROBUST_EDGE` unreachable when edge CI touches zero (tested).
- User Manual explains all four labels in plain language, next to the no-edge caveat.

#### Task U1.5 — GUI display of uncertainty

**What:** Optimize & Score page shows CI ranges and baseline percentile; verdict label
gets a badge with the caution note.

**Why:** The GUI is where over-reading happens; that is where the bands belong.

**Acceptance criteria:**
- Page renders with and without the new fields (backward compatible).
- Webapp test covers both shapes.

---

### EPIC U2 — Walk-Forward Evaluation *(kept from draft, one task added)*

**Priority:** P0 · **Type:** feature / validation · **Status:** Proposed · **Depends on:** U1 (reuses CI helpers for per-fold reporting)

**What:** Optional `--validation walk-forward` mode: repeat TRAIN/EVAL over rolling
windows, aggregate per-strategy results across folds, write a separate summary.

**Why:** One split is one sample. Stability across folds is the only defensible evidence
in this domain. Default single-split behavior stays untouched.

> **Comment (leakage):** the existing leakage guards are per-run
> (`opt_data.compute_grid_fingerprint`, `opt_state.validate_resume_or_fail`,
> `opt_state.py:194`). Walk-forward multiplies slice configurations, so fold slicing
> must go through the *same* slice code path as the normal run — not a parallel
> implementation — to inherit the TRAIN-before-EVAL guarantee.

#### Task U2.1 — Fold-plan generator (pure)

**What:** Pure function: ordered dataset indices + window params → list of
(train_slice, eval_slice) pairs; EVAL windows non-overlapping; TRAIN strictly before
EVAL.

**Why:** The slice plan is the safety-critical part; isolate it and test it to death.

**Acceptance criteria:**
- Property tests: no EVAL overlap, no TRAIN/EVAL overlap, TRAIN max index < EVAL min
  index for every fold.
- Edge cases: data shorter than one window, exact-boundary fit, min-train-size not met
  (clear error).

#### Task U2.2 — `--validation walk-forward` CLI mode

**What:** Orchestrator flag; loops folds through the existing optimize path; writes
`walkforward_summary_*.json` beside (not replacing) the normal summary.

**Why:** Opt-in depth; the default workflow, checkpoints, and resume stay exactly as
they are.

**Acceptance criteria:**
- Default run output is byte-identical in structure to today (contract test).
- Each fold's fit uses only that fold's TRAIN rows (assert via fingerprint/slice info
  recorded per fold).
- Progress lines are emitted per fold (consumable by the GUI).

#### Task U2.3 — Fold resume semantics: none (documented)

**What:** Explicitly *disable* checkpoint-resume inside walk-forward runs (each
invocation recomputes all folds); state the decision in code and docs.

**Why:** KISS. Resume-across-folds multiplies the state-integrity surface
(fingerprint × fold × config identity) for marginal benefit at current run sizes.
An explicit "no resume" is a decision; silent breakage would be a bug.

**Acceptance criteria:**
- Attempting `--resume` with walk-forward exits with a clear message.
- Documented in orchestrator `--help` and User Manual.

#### Task U2.4 — Fold aggregation report

**What:** Per strategy: mean, median, min, max, std of edge EUR across folds; fold
count; per-fold rows with their CIs (from U1); CSV export; GUI chart of edge-by-fold.

**Why:** Stability must be visible in one table; this table is also U6's direct input.

**Acceptance criteria:**
- Aggregate + per-fold rows present in walk-forward summary (contract test).
- CSV export loads back cleanly in pandas.
- GUI renders the fold chart from a fixture summary.

---

### EPIC U6 — Strategy Stability & Recommendation Rules *(kept from draft)*

**Priority:** P1 · **Type:** analytics / UX · **Status:** Proposed · **Depends on:** U1, U2

**What:** A deterministic stability score over walk-forward folds + calibration, an
explicit recommendation block ("recommended strategy X" or "no recommendation"), and an
opt-in seed-sensitivity check.

**Why:** With four optimizers (greedy/MILP/bandit/evo — `opt_config.py:17`), users will
ask "which one?". The answer must be derived from stability under uncertainty, not one
lucky EVAL score — or explicitly refused when the data doesn't support any answer.

#### Task U6.1 — Stability score (pure function)

**What:** Score from fold results: penalize variance across folds, penalize poor
calibration (Brier/ECE already computed in `write_final_summary`), reward consistent
positive edge.

**Why:** Deterministic and pure → truth-table testable with synthetic fold fixtures.

**Acceptance criteria:**
- Fixtures: stable-good > unstable-good > stable-bad orderings hold.
- Score is invariant to fold order.
- Formula documented in the summary itself (name + version string).

#### Task U6.2 — Recommendation block

**What:** Summary section naming the recommended strategy only when: edge CI > 0 in a
majority of folds AND calibration within threshold AND stability score above floor;
otherwise `recommendation: none` with the failing criterion listed.

**Why:** "No recommendation" is a first-class honest answer in this domain.

**Acceptance criteria:**
- Each gate independently forces `none` (tested).
- GUI shows the recommendation with the caution note; `none` renders as a clear
  statement, not an empty widget.

#### Task U6.3 — Seed-sensitivity check (opt-in)

**What:** `--seed-check N` reruns seed-dependent strategies (bandit/evo) across N seeds;
report per-strategy seed variance; flag `SEED_SENSITIVE` when variance exceeds threshold.

**Why:** A result that changes materially with the RNG seed is noise wearing a costume.

**Acceptance criteria:**
- Default runtime unchanged (feature fully opt-in).
- Summary includes seed count and variance per checked strategy.
- Deterministic strategies (greedy/MILP) are reported `not_applicable`, not rerun.

---

## Milestone M3 — Contracts & Pipeline Completeness

### EPIC U4 — StatGrid Schema: Consumer-Side Versioning *(reframed — producer side already exists)*

**Priority:** P1 · **Type:** architecture / contract · **Status:** Proposed · **Depends on:** nothing

**What:** Make the optimizer (and merge tool) *consume* the schema version the exporter
already writes: detect version, normalize known layouts to one canonical in-memory
shape, refuse unknown versions clearly, and cover legacy/deduped/current grids with
golden fixtures.

**Why:** The draft assumed no versioning existed; in fact `stat.py:352` writes
`schema.json` v1.1 — but `opt/opt_data.py` never reads it (it only fingerprints columns
for resume). Today an old or foreign grid fails with whatever KeyError happens first
instead of "this is a v0 grid". The gap is detection + migration, not stamping.

> **Comment:** `tools/statgrid/statgrid_merge.py:575` uses a *different* tag
> (`db-1.0`) for its merged output. U4.4 pulls that into the same documented registry so
> there is one place to look up "what formats exist".

#### Task U4.1 — Schema detection in the grid loader

**What:** `opt_data` reads `schema.json` when present → version string; absent →
version `0` (legacy). Log the detected version on every load.

**Why:** Cheap detection is the foundation for every later migration decision.

**Acceptance criteria:**
- v1.1 grids log `schema 1.1`; schema-less dirs log `schema 0 (legacy)`.
- Unknown/future versions raise a clear error naming the version and the supported set.
- No behavior change for current grids beyond the log line.

#### Task U4.2 — Normalization registry

**What:** Small `{version → normalize_fn}` mapping producing the canonical DataFrame
(the shape `opt_data` already builds today); dedupe re-expansion moves inside the v1.1
normalizer.

**Why:** Today's implicit "whatever the loader does" becomes an explicit, listed set of
supported formats; adding v1.2 later = one function + one registry entry.

**Acceptance criteria:**
- v0, v1.1, and v1.1+dedupe all normalize to an identical canonical shape (tested).
- Loader body no longer branches on format outside the registry.
- Required canonical columns asserted post-normalization.

#### Task U4.3 — Golden grid fixtures

**What:** Tiny committed fixtures: legacy (no schema.json), v1.1 plain, v1.1 deduped;
contract tests load each through the registry.

**Why:** Schema compatibility must be testable without running a backtest.

**Acceptance criteria:**
- Fixtures are small (a few KB), load with no optional deps.
- Canonical outputs compared where equality is expected.
- A deliberately corrupted fixture (missing column) fails with the clear-message path.

#### Task U4.4 — Register the merge-tool schema

**What:** Document both version namespaces (`export: 0, 1.1` / `merge-db: db-1.0`) in
one short `docs/statgrid_schema.md`; make `statgrid_merge.py` validate input grids via
the same U4.1 detection.

**Why:** Two unrelated `schema_version` fields in one repo is exactly how a future
reader mixes them up.

**Acceptance criteria:**
- One doc lists all formats, producers, consumers.
- Merge tool refuses unknown input versions with the same error style.

---

### EPIC U13 — Naive Baseline Model Family & Synthetic Demo Mode *(new — from AFI-9 + AFI-17)*

**Priority:** P1 · **Type:** feature / testability / science · **Status:** Proposed · **Depends on:** nothing (unlocks e2e testing for everything else)

**What:** A zero-dependency "naive" forecaster family (registered like
DynaMix/PCE-NARX/Darts) plus a synthetic-data generator, giving: a machine-independent
Stage-1 path, a true end-to-end CI test (forecast → StatGrid → optimize), a demo mode,
and a scientific control forecast.

**Why:** Three facts compound: (1) all current model families are optional heavy deps;
(2) on the AS-IS box zero families ran, so Stage 1 produced nothing; (3)
`test_full_pipeline_simulation` fails precisely because it needs *some* model output.
One trivial always-available family fixes the demo problem, the CI-coverage problem,
and the "what should a real model beat?" problem simultaneously — three birds, one
~100-line stone.

> **Comment (science):** In a truly random lottery, *nothing should beat the naive
> family* out-of-sample beyond noise. Making that comparison a first-class scoreboard
> row is the strongest possible honest-reporting feature: it turns the no-edge caveat
> from a disclaimer into a measurement.

#### Task U13.1 — Naive forecaster family

**What:** `dynamix/naive_core.py`: deterministic, numpy-only forecasters — e.g.
`naive-last` (repeat last value) and `naive-freq` (seeded draw from the per-series
historical frequency table) — registered through the same model-family mechanism used
by the existing cores, always available.

**Why:** Zero deps → runs on every machine including CI and the AS-IS box; seeded →
deterministic tests.

**Acceptance criteria:**
- Appears in model listings; produces forecasts for all 7 series with no optional deps.
- Deterministic given seed (tested).
- Fails soft never — it has nothing to fail on.

#### Task U13.2 — Naive family flows through the backtest

**What:** Ensure `stat.py` backtests the naive family like any other, producing StatGrid
rows with correct provenance.

**Why:** The control is only useful if it lands in the same grid the optimizer eats.

**Acceptance criteria:**
- A stat run with only naive models produces a valid, schema-stamped StatGrid.
- Golden test locks a tiny naive-only grid.

#### Task U13.3 — Synthetic dataset generator

**What:** `tests/_builders.py` (or `dynamix/demo.py`) function generating a valid
synthetic `DATA.csv` (seeded, N draws, correct domains); optional `--demo` flag or
env-var pointing `DYNAMIX_DATA_FILE` at a generated file.

**Why:** Demos, tutorials, and CI must not depend on the real operational file; the
existing `DYNAMIX_DATA_FILE` override (`constants.py`) already provides the hook.

**Acceptance criteria:**
- Generated file passes U5.4 ingest validation.
- Seeded → reproducible.
- README quick-start gains a "try it without real data" section.

#### Task U13.4 — True end-to-end CI test

**What:** Integration test: synthetic data → naive forecast → stat backtest (few steps)
→ StatGrid export → optimizer (greedy only, tiny config) → summary with scoreboard.

**Why:** No CI test currently exercises the full three-stage contract chain; this is the
cheapest full-chain regression net the project can have, and it runs anywhere.

**Acceptance criteria:**
- Runs in default CI (no optional deps) in well under a minute.
- Asserts stage handoffs: grid schema present, fingerprint valid, summary contains
  scoreboard + naive baseline row.
- Replaces reliance on the environment-sensitive `test_full_pipeline_simulation` for
  chain coverage (that test stays for real-model environments).

#### Task U13.5 — Naive row on the scoreboard

**What:** Scoreboard always includes the naive family as a labeled control row; verdict
language for other strategies is phrased relative to controls ("does not beat naive").

**Why:** See the science comment above — this operationalizes the no-edge invariant.

**Acceptance criteria:**
- Scoreboard contains the control row whenever naive rows exist in the grid.
- User Manual explains why beating the naive control matters.

---

## Milestone M4 — Engineering Hygiene & Portability

### EPIC U9 — Static Quality Gates *(new — from AFI-13)*

**Priority:** P1 · **Type:** infrastructure / quality · **Status:** Proposed · **Depends on:** nothing

**What:** Introduce ruff (lint), a coverage floor, and gradual mypy — each as a separate
small task, each starting non-blocking then flipped to blocking once green.

**Why:** There is currently *no* static gate of any kind: no linter, no type checker, no
coverage threshold. With 1379-line and 992-line modules and AI-assisted development,
regressions that tests don't reach (dead imports, shadowed names, silent type drift,
coverage decay) accumulate unchecked. Gates are cheapest before the M1–M3 code lands.

#### Task U9.1 — Ruff, minimal ruleset

**What:** `[tool.ruff]` in pyproject with a conservative selection (errors, unused
imports/variables, obvious bugs — not style churn); fix or `noqa` existing findings;
add a CI step.

**Why:** Highest signal per minute of any tool here; a minimal ruleset avoids a
1000-line diff and keeps the KISS promise.

**Acceptance criteria:**
- `ruff check .` is clean at merge.
- CI blocks on ruff after the initial cleanup lands.
- Ruleset choices commented in pyproject.

#### Task U9.2 — Coverage floor

**What:** Measure current line coverage in CI, set `--fail-under` a couple of points
below it, record the number in ci.yml with a comment.

**Why:** Coverage is already collected (`ci.yml:40-41`) but decays invisibly without a
floor. Ratchet later; never lower silently.

**Acceptance criteria:**
- CI fails if coverage drops below the floor.
- Floor value + rationale committed as a comment next to the flag.

#### Task U9.3 — Mypy on the contract-critical core (gradual)

**What:** Mypy limited to `opt/opt_data.py`, `opt/opt_state.py`, `dynamix/domain.py`
(from U5.1), `dynamix/health.py` (from U3.1) — the leakage/contract-critical modules —
non-blocking CI job first.

**Why:** Full-repo mypy on this codebase would be a war; typing just the modules whose
bugs are silent-and-costly is the 80/20.

**Acceptance criteria:**
- Listed modules pass `mypy --strict` (or documented per-module relaxations).
- CI job exists; flipped to blocking once green for two weeks.
- Config lists the covered modules explicitly, with a one-line "why these".

---

### EPIC U11 — Target-Platform CI (Windows + newer Python) *(new — from AFI-14)*

**Priority:** P1 · **Type:** infrastructure / portability · **Status:** Proposed · **Depends on:** nothing

**What:** Add a Windows core-test CI job and a non-blocking newer-Python (3.13/3.14)
job; fix whatever the Windows job flushes out (known suspect: POSIX-only process-group
handling in the GUI job runner).

**Why:** AS-IS.md states the intended production runtime is a **Windows** venv, yet CI
is ubuntu-only — the project has never continuously tested its own target OS.
`webapp/runner.py:141` (`stop_job`) is explicitly POSIX-process-group based, so the GUI
Stop button is unverified on the platform it will actually run on. Separately, the
AS-IS box's Python-3.14 wheel fiasco shows newer interpreters need early warning.

#### Task U11.1 — `windows-latest` core job

**What:** Add Windows to the core matrix (one Python version is enough), non-blocking
initially.

**Why:** Discover the actual failure list before promising anything.

**Acceptance criteria:**
- Job runs the default layers on windows-latest.
- Failures are catalogued as issues; job flipped to blocking once green.

#### Task U11.2 — Windows-safe job stop

**What:** Make `runner.py` `start_job`/`stop_job` handle Windows (no `os.killpg`;
use appropriate process-group creation flags and termination), with the POSIX path
unchanged.

**Why:** A Stop button that leaks orphan `dynamix-stat` processes on the production OS
is a real operational bug, just an undiscovered one.

**Acceptance criteria:**
- Unit test (mock/subprocess-based) covers both platform branches.
- Stopping a job on Windows terminates the child tree (verified in the U11.1 job).

#### Task U11.3 — Non-blocking Python 3.13/3.14 job

**What:** Add a `continue-on-error` core job on newer Python.

**Why:** The AS-IS environment failure was a *forecastable* wheel-availability problem;
this job forecasts the next one. Pairs with `dynamix-health`, which reports the same
facts machine-locally.

**Acceptance criteria:**
- Job present, non-blocking, matrix documented.
- Failures produce an issue label, not a red main.

---

### EPIC U12 — Structured Progress Protocol *(new — from AFI-15)*

**Priority:** P2 · **Type:** contract / UX · **Status:** Proposed · **Depends on:** nothing

**What:** Replace the regex-scraping GUI↔CLI progress contract with one documented,
machine-readable progress line format, emitted by a shared helper and parsed by the
existing parser as a first-class case (regex fallback retained for old logs).

**Why:** `runner.py` scrapes `(\d+)\s*/\s*(\d+)` and `eta=` out of free log text
(`runner.py:165,211`); git history shows two separate progress-display bugs already
shipped ("webapp progress-bar fix", "advance bar during Darts"). Every CLI wording
change is one silent GUI freeze away. A one-line structured format
(e.g. `@progress {"stage":"stat","current":12,"total":40,"eta_s":93}`) ends the class.

#### Task U12.1 — Progress emitter helper

**What:** `dynamix/progress.py`: `emit_progress(stage, current, total, eta_s=None)`
printing the structured line; adopt it in `stat.py` and orchestrator loops (keeping
existing human-readable lines).

**Why:** One writer function = one format forever; human logs stay pretty.

**Acceptance criteria:**
- Structured lines appear in stat/opt logs alongside existing output.
- Emitter is pure string formatting, unit-tested.

#### Task U12.2 — Parser upgrade + contract test

**What:** `parse_progress`/`parse_eta` prefer structured lines, fall back to the
current regexes; one contract test feeds emitter output straight into the parser.

**Why:** The emit→parse round-trip test is the actual contract — it fails at the PR
that breaks the format, not in the user's GUI.

**Acceptance criteria:**
- Round-trip test: emitted line parses to identical values.
- Old free-text logs still parse (regression fixtures from the two historical bugs).
- Tkinter GUI's progress path uses the same parser or emitter (no third dialect).

---

### EPIC U10 — `tools/` Support Status & Test Coverage *(new — from AFI-16)*

**Priority:** P2 · **Type:** quality / docs · **Status:** Proposed · **Depends on:** U4 (merge tool shares schema registry)

**What:** Declare a support status for everything under `tools/`, and give the one
substantial tool (`statgrid_merge.py`, 632 lines) smoke + core-logic tests.

**Why:** `tools/` is production-adjacent code (it rewrites StatGrids, with its own
schema tag) living entirely outside the test suite and the packaging story. Untested
grid-rewriting code is a data-corruption risk wearing a utility belt.

#### Task U10.1 — Tools inventory + status labels

**What:** Short `tools/README.md`: per tool — purpose, supported/experimental/dev-only,
how invoked; linked from the docs index (U7.1).

**Why:** Cheapest possible expectation-setting.

**Acceptance criteria:**
- Every `tools/**` script listed with a status.
- Docs index links it.

#### Task U10.2 — Merge-tool smoke + core tests

**What:** Tests for `statgrid_merge.py`: `--help` smoke; merge of two tiny fixture grids
(reuse U4.3 fixtures) verifying row counts, dedupe behavior, and the `db-1.0` stamp.

**Why:** It rewrites the pipeline's central artifact; a fixture merge test is the
minimum bar.

**Acceptance criteria:**
- Tests run in a default layer with no optional deps.
- A corrupted input fixture produces the U4-style clear error.

---

## Milestone M5 — Observability & Governance

### EPIC U8 — Run Audit Pack *(kept from draft, deduplicated against existing summary)*

**Priority:** P2 · **Type:** operations / reporting · **Status:** Proposed · **Depends on:** U3 (reuses health report)

**What:** `audit.json` per stat/optimizer run: environment (python, OS, package
version, git SHA), dependency/model-family activation (from the U3.1 health builder),
timing per stage, row/grid counts, warning count — written even on failure. GUI shows
the latest audit; a trend CSV tracks runtime/rows across runs.

**Why:** `summary_current.json` already carries `code_version` + `config_identity` +
fingerprints — but nothing records *environment* or *timing*, and nothing is written
when a run dies. "What was different about Tuesday's run?" should be a file diff, not
archaeology.

> **Comment:** U8 deliberately *reuses* `build_health_report()` (U3.1) for the
> environment block — one collector, two consumers, no drift.

#### Task U8.1 — `audit.json` writer

**What:** Start-of-run: write audit with env + command + args + data fingerprint;
end-of-run (or crash, via try/finally): append end time, duration, status, warning count.

**Why:** Even-on-failure is the whole point — failed runs are the ones you investigate.

**Acceptance criteria:**
- Audit written for success and simulated-crash cases (tested).
- Contains git SHA when available, `unknown` otherwise (no hard git dependency).
- Documented key set; additions allowed, removals are contract breaks.

#### Task U8.2 — GUI audit surface

**What:** Home/Reports pages show latest audit (runtime, families active, warnings);
JSON downloadable.

**Why:** "Were the latest results produced by a healthy run?" belongs next to the
results.

**Acceptance criteria:**
- Missing/partial audit renders gracefully.
- Webapp test with fixture audits (complete + crashed).

#### Task U8.3 — Runtime trend CSV

**What:** Append one row per run (run id, stage durations, grid rows, warnings) to
`Output/trends.csv`; simple GUI chart; warning when runtime jumps beyond a factor
threshold.

**Why:** Backtest cost grows with data and models; a trend line turns "it feels slower"
into a number.

**Acceptance criteria:**
- Append is atomic-ish (no corruption on concurrent/crashed runs — write temp + rename
  or tolerate partial last line on read).
- Chart renders from fixture CSV.

---

### EPIC U7 — Documentation Governance *(kept from draft, grounded in found drift)*

**Priority:** P2 · **Type:** docs / test · **Status:** Proposed · **Depends on:** U0 (starts from corrected docs)

**What:** A docs index with status labels (living / snapshot / historical), smoke tests
for documented commands, and a lightweight freshness check.

**Why:** Drift is not hypothetical — U0 fixed three live instances (CLAUDE.md intro,
missing webapp layer, stale pyproject comment), and AS-IS.md describes a machine that no
longer matches the conda/CUDA install path added later. Twelve docs and growing needs a
map and a tripwire.

#### Task U7.1 — `docs/INDEX.md`

**What:** Table: document, one-line purpose, status label, last-reviewed date. Mark
AS-IS.md `snapshot (dated)`; README links the index.

**Why:** Readers need to know which docs are load-bearing and which are history.

**Acceptance criteria:**
- All 12+ docs listed with status and date.
- README links it; new-doc guidance says "add yourself to the index".

#### Task U7.2 — Documented-command smoke tests

**What:** Test that every console script in `[project.scripts]` (plus `dynamix-health`
when it lands) exits 0 on `--help`; extract-and-check the command names cited in README
and User Manual against the installed script set.

**Why:** Entry points renamed during packaging work are exactly the kind of thing docs
lag on; `--help` smoke is nearly free.

**Acceptance criteria:**
- All console scripts `--help` pass in CI.
- A README command referring to a nonexistent script fails the test.
- Long-running examples excluded by an explicit allowlist, not by silence.

#### Task U7.3 — Freshness tripwire (non-blocking)

**What:** CI notice (not failure) when `architecture.md`/`SRS.md` are older than the
last N substantive `src/` changes; maintainer clears it by bumping the reviewed-date in
INDEX.md.

**Why:** A nag, not a gate — governance that blocks merges on doc dates gets deleted
within a month.

**Acceptance criteria:**
- Non-blocking CI annotation listing stale docs.
- Review-date bump silences it; procedure documented in INDEX.md.

---

## 3. Suggested execution order

Rationale: truth first, then the tools that make everything else verifiable, then
science, then hardening. Independent tracks can interleave.

| Order | Epic | Priority | Why here |
|---|---|---|---|
| 1 | **U0** Truth & wiring fixes | P0 | 15-minute fixes; everything downstream assumes docs and test runner tell the truth |
| 2 | **U3** Health diagnostics | P0 | Unblocks humans *and* U8 reuses its collector; immediately useful on every machine |
| 3 | **U5** Domain authority + contracts | P0 | Protects the recently-fixed correctness bug before new display surface (U1.5, U3.4) is added |
| 4 | **U1** Scoreboard uncertainty | P0 | Core honesty upgrade; U2/U6 build on its CI helpers |
| 5 | **U13** Naive baseline + demo + e2e CI | P1 | Early because its e2e test then guards all remaining work; scoreboard control row lands with U1 fresh |
| 6 | **U2** Walk-forward | P0 | Needs U1's per-fold CI reporting; feeds U6 |
| 7 | **U9** Static quality gates | P1 | Cheapest before the M2/M3 code volume lands — but after the P0 rush so the initial cleanup doesn't conflict |
| 8 | **U4** Schema consumer-side versioning | P1 | Contract hardening before any future grid change; U10 depends on its fixtures |
| 9 | **U6** Stability & recommendation | P1 | Consumes U1 + U2 outputs |
| 10 | **U11** Windows + newer-Python CI | P1 | Do before declaring the GUI production-ready on the target OS |
| 11 | **U8** Audit pack | P2 | Reuses U3 collector; most valuable once runs get longer (post walk-forward) |
| 12 | **U12** Progress protocol | P2 | Quality-of-life; regression fixtures already exist from history |
| 13 | **U10** tools/ status + tests | P2 | Depends on U4 fixtures |
| 14 | **U7** Docs governance | P2 | Last so the index is written against the post-upgrade doc set (U0 already fixed the acute drift) |

---

## 4. Compact GitHub-issue backlog

### P0
- **U0** — Fix orphaned test discovery + stale doc/packaging statements *(4 tasks)*
- **U3** — `dynamix-health` CLI + `--deep` probe + GUI page + CI smoke *(5 tasks)*
- **U5** — Single domain authority, output/ingest contracts, OOD diagnostics *(6 tasks)*
- **U1** — Bootstrap CIs, baseline distribution, verdict labels, GUI bands *(5 tasks)*
- **U2** — Walk-forward: fold plan, CLI mode, no-resume rule, aggregation *(4 tasks)*

### P1
- **U13** — Naive model family, synthetic data, true e2e CI, control scoreboard row *(5 tasks)*
- **U9** — Ruff, coverage floor, targeted mypy *(3 tasks)*
- **U4** — Schema detection, normalization registry, golden fixtures, merge-tool registry *(4 tasks)*
- **U6** — Stability score, recommendation gates, seed sensitivity *(3 tasks)*
- **U11** — Windows CI, Windows-safe stop, 3.13/3.14 canary *(3 tasks)*

### P2
- **U8** — audit.json, GUI audit surface, runtime trends *(3 tasks)*
- **U12** — Progress emitter + parser round-trip contract *(2 tasks)*
- **U10** — tools/ inventory + merge-tool tests *(2 tasks)*
- **U7** — Docs index, command smoke tests, freshness tripwire *(3 tasks)*

**Total: 14 epics, 52 tasks** — deliberately many small tasks over few large ones.

---

## 5. Final assessment

The draft plan's direction is correct: the project's next frontier is statistical and
operational hardening, not packaging or CI bootstrap (those are genuinely done). This
enhanced plan makes three kinds of changes:

1. **Corrections.** U4 was re-scoped to the consumer side because the producer already
   stamps `schema.json` v1.1; several "add X" items became "extend the X that exists"
   (baseline → baseline distribution; summary metadata → audit pack).
2. **Grounding.** Every epic now cites the file/line evidence for its gap, so work can
   start without re-deriving the analysis.
3. **Additions.** The audit surfaced gaps the draft could not see from the docs alone:
   an orphaned test file (U0), no static gates (U9), the untested target OS (U11), the
   twice-broken progress contract (U12), the untested grid-rewriting tool (U10), and —
   the most scientifically interesting one — the absence of a zero-dependency naive
   control model (U13), which turns the project's own "no guaranteed edge" doctrine into
   a measurable scoreboard row.

The architectural constants remain untouched: three decoupled stages, file contracts,
leakage-safe fitting, fail-soft optional dependencies, and the visible no-edge message.
