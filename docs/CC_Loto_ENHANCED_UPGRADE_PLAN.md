# CC_Loto Enhanced Upgrade Plan (v2)

**Status:** Proposed · **Version:** 2.1
**Supersedes:** `docs/CC_Loto_PROJECT_UPGRADE_PLAN.md` (the draft plan)
**Basis:** Draft plan cross-checked against the repository at commit `570d2c8` (code, tests, CI, packaging, docs) on 2026-07-04.
**v2.1 additions:** second-pass big-picture critique (section 1.4) grounded in structural
metrics (dead-code scan, dependency cycles, complexity hotspots) and a verified data-structure
fact about `DATA.csv`; new AFI-19..23 and epics U14–U17.
**v2.2 additions:** AFI-24 (missing model-family interface) and Epic U18 — a detailed,
behavior-preserving refactoring program (family registry, `stat.py` split, GUI worker
extraction, utility dedup, strategy-module split). U18.2 supersedes U17.3.
**v2.3 additions:** Epic U19 — five oversight visualizations, each admitted only if it
exposes information no logged scalar can carry (path, place, shape, time, failure
location); companion plain-language explainer in `docs/visualization_guide.md`.

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
- **AFI-19 — The detector has never been calibrated.** The pipeline is a signal
  detector, but it has never been run against data with a *known* answer. When the
  scoreboard says "no edge", nothing distinguishes *there is no edge* from *this
  pipeline cannot detect edges*. No test anywhere plants a synthetic bias and checks
  the system finds it. (→ Epic U14)
- **AFI-20 — The positional series are order statistics with a closed-form null, and
  nothing exploits that.** Verified against `DATA.csv` (613 rows): TS_1..TS_5 are
  **strictly increasing in every single row**, and TS_6 < TS_7 in every row; the
  per-column envelopes (TS_1 max = 38, TS_5 min = 14) are classic order-statistic
  shrinkage. So the data is exactly the sorted output of a 5-of-50 + 2-of-12 draw.
  Position *k* is the *k*-th order statistic of a draw without replacement — its null
  distribution has a closed form, and positions are deterministically correlated by
  construction. The project currently estimates these analytically-known distributions
  with torch/Darts/chaospy sequence models, and has no analytic baseline to beat.
  (→ Epic U15)
- **AFI-21 — No permutation-test control.** The random-ticket baseline (U1) controls
  for ticket luck, but nothing controls for *temporal* structure: shuffling the draw
  history and re-running should destroy any real edge, and that experiment doesn't
  exist. (→ Epic U16)
- **AFI-22 — Complexity hotspots, unguarded.** Structural scan results:
  `stat.py::run_statistics` cyclomatic **74**, `entrypoints/gui.py::_run_forecast_worker`
  **77**, `stat.py::print_overlay_witness_report` **35**,
  `webapp/app.py::render_job_panel` **25 with the repo's highest churn** (12 commits/90
  days — the statistically likeliest birthplace of the next bug), and
  `tools/maintenance/fix_darts_install.py::main` **69**. Repo average is a healthy 4.9
  and there are **zero dependency cycles** — the debt is concentrated in a handful of
  giant functions, not smeared across the architecture. No complexity ceiling exists to
  stop them growing. (→ Epic U17)
- **AFI-23 — Dead code is a non-issue, but the tooling lies about it.** An automated
  dead-code scan reported 11.3% dead symbols; manual verification showed these are
  false positives (the import-graph resolver cannot follow `src/`-layout and
  try/except-guarded imports — e.g. `plotting` and `pce_narx` were flagged dead but are
  demonstrably imported). Real orphans found: `tools/darts/check_darts_params.py`
  (zero-symbol scratch script) and the never-discovered test from AFI/U0. Future
  dead-code hunting should use ruff F401/F841 or vulture, which handle src-layout
  correctly. (→ folded into U9.1 and U10.1)
- **AFI-24 — There is no common interface for forecaster model families.**
  `dynamix_core`, `pce_narx`, and `darts_core` each expose different call signatures,
  and every caller wires all families by hand with its own try/except + branching:
  `entrypoints/run_cli.py` (PCE calls at :215 and :296 with local availability
  branching), `entrypoints/gui.py` (the same wiring re-implemented inside
  `_run_forecast_worker`, lines ~730–846 — the cyclomatic-77 hotspot), and
  `candidate_grid.py` (`collect_model_forecasts_for_step` /
  `_forecast_single_series`, PCE call at :204). This triplication is the structural
  reason the domain-clamp bug had to be fixed in three places, and it means every new
  model family (U13 naive, U15 analytic) requires three coordinated edit sites instead
  of one. Secondary duplication with the same root smell: `_is_event_mode()` copied
  into four modules (`data_utils`, `pce_narx`, `plotting`, `candidate_grid`),
  `_repo_root()` copied into at least two, and `_bootstrap_import_paths()` copy-pasted
  into four test files. (→ Epic U18)

### 1.4 Second-pass critique — the bigger picture

*(Written after the structural scan; this is the assessment that motivates epics
U14–U17. Kept in the plan so the rationale survives next to the work items.)*

**As engineering, this project is an unusually good POC.** Most lottery-prediction
projects are numerology in a notebook. This one has leakage guards with fingerprinted
resume, an honest scoreboard against a random control, file contracts between decoupled
stages, fail-soft optional dependencies, layered tests, CI, and a lockfile — with zero
dependency cycles, which is structural evidence that the stage decoupling is real
rather than aspirational. The pipeline skeleton is transferable wholesale to legitimate
forecasting/quant work, and that skeleton — not the lottery edge — is the valuable
artifact.

**Central critique: the instrument was built but never calibrated.** Every measurement
device is validated against known references before its readings are trusted. This
pipeline reads "no edge" on real data — but it has never been pointed at data where the
right answer is known. Until it demonstrably (a) reports NO_EDGE on synthetic pure-random
data and (b) *finds* a deliberately planted bias, its null result is uninterpretable.
Calibration transforms the project's claim from "I hunted an elusive target and found
nothing" into "I built a **validated** detector and it reads zero" — a scientifically
complete result, and a far stronger POC. This is Epic U14, and it is the single highest-
value addition in this plan.

**Second: sequence models were brought to a histogram fight.** With the order-statistic
structure now verified (AFI-20), each position's null distribution is *computable
exactly*. Under the fair-lottery hypothesis there is no temporal signal, so the correct
first models are: the analytic order-statistic null (free, exact), then a frequency
sampler (cheap, empirical). Heavy sequence models (torch/DynaMix, Darts, PCE-NARX) are
the most expensive possible way to approximate a known histogram, and they should have
to *beat* the analytic null out-of-sample to justify their runtime. Epic U15 adds the
analytic family and — as a bonus — a direct fairness test of the lottery itself
(empirical vs theoretical position distributions).

**Third: effort allocation is inverted.** Four portfolio optimizers (greedy/MILP/
bandit/evo) sit on top of a single TRAIN/EVAL split. The optimizer layer can only be as
good as the probabilities feeding it; when those are near-flat, differences between
MILP and evolutionary search are noise being polished. The plan's ordering already
corrects this (uncertainty and walk-forward land before more optimizer work), and U16
adds the missing temporal control: a permutation test in which any edge that survives
history-shuffling is by definition an artifact.

**Hygiene verdict:** dead code is effectively absent (AFI-23); the real debt is five
giant functions (AFI-22). The remedy is containment (a complexity ceiling so they stop
growing) plus extract-on-touch (any task that modifies one pulls the touched logic out
into a pure, tested helper) — not a big-bang refactor.

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

## Milestone M6 — Scientific Instrument Validation *(new in v2.1)*

### EPIC U14 — Detector Calibration: Planted-Signal Validation *(new — from AFI-19)*

**Priority:** P0 · **Type:** science / validation · **Status:** Proposed · **Depends on:** U13 (synthetic generator, naive family), U1 (verdict labels)

**What:** Prove the pipeline can tell signal from noise on data where the truth is
known: it must report NO_EDGE on synthetic pure-random draws, and it must *detect* a
deliberately planted bias. Then measure the smallest bias it can see at the real
dataset's size (power analysis) and stamp the result into the reports.

**Why:** This is the highest-value epic in the plan. Without it, every scoreboard
verdict on real data is uninterpretable — "no edge found" could mean "no edge exists"
or "this instrument is blind". With it, the project's null result becomes a validated
measurement, which is the strongest scientific claim a random-domain POC can make.

> **Comment:** This epic deliberately reuses everything: U13.3's generator (extended
> with a bias parameter), the normal three-stage pipeline unmodified, and U1's verdict
> labels as the detection criterion. The pipeline under test is the *production*
> pipeline — a special "test mode" would defeat the purpose.

#### Task U14.1 — Biased synthetic generator

**What:** Extend the U13.3 synthetic generator with a bias specification, e.g.
`bias={"ball": 7, "weight": 1.3}` — ball 7 drawn 30% more often than fair — while all
outputs stay valid sorted draws in-domain. Seeded and deterministic.

**Why:** A planted, quantified, reproducible signal is the known reference every
calibration needs.

**Acceptance criteria:**
- Generated data passes U5.4 ingest validation and the sortedness property.
- Empirical frequency of the biased ball in a large generated sample matches the
  requested weight (statistical test in the unit test, fixed seed).
- `weight=1.0` reproduces the unbiased generator byte-for-byte (same seed).

#### Task U14.2 — Null calibration: NO_EDGE on pure-random data

**What:** Integration test: full pipeline (naive + any available families → StatGrid →
optimize) on seeded pure-random synthetic data must yield a scoreboard verdict of
`NO_EDGE` (or `UNCERTAIN`, never an edge claim) for every strategy.

**Why:** A detector that finds edges in white noise is worse than no detector. This
test makes false-positive behavior a CI failure.

**Acceptance criteria:**
- Deterministic given fixed seeds (no flaky statistical assertions).
- Runs in default CI without optional deps (naive family suffices).
- A comment documents the seed-selection so a future seed change is a conscious act.

#### Task U14.3 — Detection calibration: planted bias is found

**What:** Same pipeline on data with a *strong* planted bias (magnitude chosen so
detection is unambiguous at the fixture's draw count) must produce a verdict of at
least `WEAK_EDGE` for the best strategy, and the fairness diagnostic (U15.4, once it
exists) must flag the biased ball.

**Why:** The complement of U14.2 — proves the instrument is not blind. Together they
bracket the detector's behavior.

**Acceptance criteria:**
- Deterministic given fixed seeds; runs in default CI.
- Test documents the planted bias magnitude and why it must be detectable at that n.
- Failure message distinguishes "pipeline errored" from "pipeline ran but missed the
  signal".

#### Task U14.4 — Power sweep: minimal detectable bias

**What:** Opt-in script (not CI): grid over bias magnitude × history length, K seeds
per cell → detection-rate table written to `docs/detector_power.md` with the row
closest to the real dataset's size (~613 draws) highlighted.

**Why:** This answers the question that contextualizes *all* real-data results: "what
is the smallest edge this instrument could even see given ~613 draws?" Any real
per-ball bias smaller than that threshold is invisible by construction — a fact users
deserve to see next to the scoreboard.

**Acceptance criteria:**
- Script is seeded, resumable-or-fast, and documented; runtime bounded and stated.
- Output table includes detection rate per (bias, n) cell and the highlighted
  real-data row.
- `docs/INDEX.md` (U7.1) lists the report as a dated snapshot.

#### Task U14.5 — Instrument-status stamp in reports

**What:** Scoreboard/summary gains a short block: calibration suite version, date of
last U14.2/U14.3 pass, and a one-line pointer to the power table ("edges below ~X%
per-ball bias are undetectable at n=613").

**Why:** The no-edge caveat becomes quantitative. A verdict shown next to the
instrument's measured sensitivity cannot be over-read in either direction.

**Acceptance criteria:**
- Block present in summary JSON and GUI Optimize & Score page.
- Wording reviewed against the SRS no-efficacy statement (consistency, not
  contradiction).

---

### EPIC U15 — Analytic Order-Statistic Null Model *(new — from AFI-20)*

**Priority:** P1 · **Type:** science / feature · **Status:** Proposed · **Depends on:** U13 (model-family mechanism)

**What:** Implement the exact null distribution of each position (k-th order statistic
of 5-of-50, resp. 2-of-12, without replacement), register it as a zero-dependency
"analytic" forecaster family, and add a fairness diagnostic comparing `DATA.csv`'s
empirical position distributions against the theory.

**Why:** The verified row-level sortedness (AFI-20) means every position's marginal
under the fair-lottery hypothesis is *known in closed form* — no learning required.
This gives (a) the scientifically correct baseline every learned model must beat,
(b) a direct test of whether the lottery source deviates from fairness at all (the
only question with a possible edge behind it), and (c) it is nearly free: the pmf is
one hypergeometric-style formula.

> **Comment (the formula):** for a draw of m balls from {1..N}, the k-th order
> statistic X₍ₖ₎ satisfies P(X₍ₖ₎ = x) = C(x−1, k−1)·C(N−x, m−k) / C(N, m). Two
> parameters (N=50, m=5 and N=12, m=2) cover all seven series. A property test against
> Monte Carlo sampling pins the implementation.

#### Task U15.1 — Record the draw-structure fact

**What:** Document in `architecture.md` (and SRS data section): TS_1..TS_5 are the
sorted balls of one 5-of-50 draw, TS_6..TS_7 of one 2-of-12 draw — verified strictly
monotone in all 613 rows. Add the row-sortedness check to U5.4's ingest validation.

**Why:** The whole epic rests on this fact; it must be written down and enforced at
ingest so a future data-source change cannot silently invalidate the analytic model.

**Acceptance criteria:**
- Docs state the structure and the verification date/row count.
- Ingest validation rejects a row where TS_1..TS_5 is not strictly increasing (or
  TS_6 ≥ TS_7), with a clear message.

#### Task U15.2 — Order-statistic pmf module

**What:** Pure module `dynamix/order_stats.py`: `pmf(k, N, m)` → exact distribution
vector; mean/mode/quantile helpers. numpy-only.

**Why:** One small, exactly-testable module is the foundation for the family, the
fairness test, and any future distributional scoring.

**Acceptance criteria:**
- pmf sums to 1 (exact within float tolerance) for all seven (k, N, m) combos.
- Property test: agreement with a seeded Monte Carlo sampler (KS distance below
  threshold at large sample size).
- Closed-form mean matches the textbook formula m·... — asserted for known cases.

#### Task U15.3 — "analytic" forecaster family

**What:** Register an always-available family whose per-position forecast is derived
from the exact null (configurable point summary: mode or expected value), flowing
through stat backtest and StatGrid like every other family.

**Why:** The provably optimal fair-lottery point forecast, at zero runtime cost —
the floor every learned model must beat to claim anything.

**Acceptance criteria:**
- Appears in model listings; produces in-domain forecasts for all 7 series, no
  optional deps.
- Backtest rows carry correct provenance; golden test on a tiny grid.
- Deterministic (it's a constant per position, given the domain).

#### Task U15.4 — Lottery fairness diagnostic

**What:** Report + GUI section: per position, empirical `DATA.csv` distribution vs
analytic pmf (chi-square or exact multinomial test), p-values with multiple-testing
correction; plus per-ball raw frequency vs expectation for the unsorted view.

**Why:** This is the *actual* scientific question of the project — "does this lottery
deviate from fair?" — answered directly instead of through model residuals. It is also
U14.3's detection oracle for planted biases.

**Acceptance criteria:**
- Runs on real and synthetic data; output includes test statistic, p-value, and a
  plain-language line ("consistent with a fair draw" / "deviation detected at ball X").
- On U14.1 biased fixtures, the diagnostic flags the planted ball (tested).
- Multiple-testing handling documented (7 positions + 62 balls ≠ free lunch).

#### Task U15.5 — Analytic family on the scoreboard

**What:** Scoreboard treats the analytic family as the reference control row (alongside
naive from U13.5); verdict phrasing for learned models becomes relative: "does not beat
the analytic null".

**Why:** Beating random tickets is a low bar; beating the exact null is the honest one.

**Acceptance criteria:**
- Control row present whenever analytic rows exist in the grid.
- User Manual explains the hierarchy: analytic null ≥ naive ≥ random tickets.

---

### EPIC U16 — Permutation-Test Control *(new — from AFI-21)*

**Priority:** P1 · **Type:** science / validation · **Status:** Proposed · **Depends on:** U1 (edge metrics), ideally after U2

**What:** An opt-in control mode that destroys temporal structure (deterministically
shuffles draw order) and re-runs the optimizer: any "edge" that survives is an
artifact; the distribution of shuffled-history edges yields an empirical p-value for
the real edge.

**Why:** The random-ticket baseline controls for ticket luck; nothing controls for
*time*. Every forecasting model in the pipeline claims temporal signal; permutation is
the classic, assumption-free test of exactly that claim.

#### Task U16.1 — Deterministic history-permutation mode

**What:** `--control permutation --control-seed S`: permute the event order of the
grid's truth rows (marginals preserved, time destroyed) via the existing slicing
machinery, then run the standard optimize; summary is written to a separate
`control_*.json`, clearly labeled.

**Why:** Operating at StatGrid level keeps it cheap (no re-forecasting) and reuses the
leakage-safe slice path unchanged.

**Acceptance criteria:**
- Same seed → identical permutation → identical control summary.
- Control summaries are unambiguously labeled and never overwrite real summaries.
- Fingerprint/resume machinery refuses to mix control and real state.

#### Task U16.2 — Permutation p-value report

**What:** Run K seeded permutations (config, default small), collect the null
distribution of edge EUR, report the real edge's percentile as an empirical p-value in
the scoreboard; GUI shows it beside the baseline percentile from U1.2.

**Why:** "Real edge at the 54th percentile of shuffled-history edges" is the single
most honest sentence this system can print.

**Acceptance criteria:**
- Deterministic given the seed set; K and runtime documented.
- Scoreboard gains `permutation_p` per strategy; contract test updated.
- User Manual explains the interpretation in one paragraph.

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

### EPIC U17 — Complexity Hotspot Containment *(new — from AFI-22)*

**Priority:** P2 · **Type:** quality / refactor policy · **Status:** Proposed · **Depends on:** U9.1 (ruff)

**What:** Stop the five giant functions from growing (complexity ceiling) and adopt an
extract-on-touch rule. *(v2.2 note: the targeted extraction formerly here as U17.3 is
superseded by Epic U18, which does it as part of a structured refactoring program —
`run_statistics` via U18.2, `_run_forecast_worker` via U18.3.)*

**Why:** The scan shows the repo's average complexity is a healthy 4.9 with zero
dependency cycles — the debt is concentrated in `run_statistics` (74),
`_run_forecast_worker` (77), `print_overlay_witness_report` (35), `render_job_panel`
(25 + highest churn), and `fix_darts_install.main` (69). Churn × complexity is the
best-known predictor of where the next bug appears. Containment plus opportunistic
extraction is the KISS response; a big-bang refactor is explicitly *not* proposed.

#### Task U17.1 — Complexity ceiling in ruff

**What:** Enable mccabe (`C901`) with the max set just above the current worst
offender, plus per-file ignores listing the five known functions by name; document the
ratchet rule (ceiling only ever moves down).

**Why:** Free regression-stop: nothing new may be born this complex, and the known
five are grandfathered explicitly rather than silently.

**Acceptance criteria:**
- CI fails if any *new* function exceeds the ceiling.
- The grandfathered list is in config with a comment linking this epic.
- Ceiling value + ratchet rule documented.

#### Task U17.2 — Extract-on-touch rule

**What:** One paragraph in CLAUDE.md (and CONTRIBUTING if created): any task that
modifies logic inside a grandfathered function must extract the touched logic into a
pure, tested helper as part of the same change.

**Why:** Converts every future feature that grazes a hotspot into a small down-payment
on the debt, with zero dedicated refactor budget.

**Acceptance criteria:**
- Rule written where AI-assisted and human contributors will actually see it.
- The grandfathered list in U17.1 is referenced as the trigger set.

*(Task U17.3 removed in v2.2 — superseded by U18.2.)*

---

### EPIC U18 — Maintainability Refactoring Program *(new in v2.2 — from AFI-24, AFI-22)*

**Priority:** P1 · **Type:** refactor / architecture · **Status:** Proposed · **Depends on:** U9.1 + U17.1 (refactor under lint + complexity ceiling); **enables** U13, U15, and shrinks two AFI-22 hotspots

**Objective (measurable):** after this epic,
1. adding a new forecaster family is a **one-file change** (today: three edit sites);
2. no application module exceeds **~700 lines**, and `run_statistics` /
   `_run_forecast_worker` drop below cyclomatic **40** (today: 74 / 77);
3. every one of the copy-pasted utilities (`_is_event_mode`, `_repo_root`,
   `_bootstrap_import_paths`) has **exactly one definition**;
4. all of it is **behavior-preserving**, proven by unchanged golden/contract tests —
   bit-identical StatGrid and forecast outputs.

**Why this epic exists:** the macro-architecture is healthy (zero cycles, clean stage
contracts), so this is *not* a redesign. The maintenance pain is concentrated at module
level, and most of it has one root cause: the missing model-family interface (AFI-24).
Fixing that first makes tasks U13.1/U13.2 and U15.3 trivial, guts the worst complexity
hotspot for free, and removes the class of "fix the same bug in three places" defects
(of which the domain clamp was the first instance).

> **Ground rules for every task in this epic (the "how" that eases the process):**
> 1. **One task = one focused commit (or short commit series), pushed to `main`.**
>    This is a single-developer, PR-free repo — frequent small commits are the unit of
>    work. Never mix a move with a behavior change in one commit; if a bug is found
>    mid-refactor, note it and fix it in its own commit.
> 2. **Lock first.** Before touching a file, confirm which golden/contract tests cover
>    it; if coverage is thin, add a characterization test *before* moving code.
> 3. **Re-export shims.** Old import paths keep working via re-exports for one epic's
>    grace period (`dynamix.stat` already demonstrates the pattern from the
>    `candidate_grid` extraction — reuse it verbatim).
> 4. **Mechanical moves stay mechanical.** Use `git mv` where possible and keep
>    function bodies byte-identical in move commits, so the diff stays trivially
>    checkable (future-you is the reviewer).
> 5. Run `python run_tests.py` plus ruff before every push; green CI on `main` is the
>    signal that a task is done.

#### Task U18.1 — Introduce the model-family registry

**What:** Create `src/dynamix/families.py` defining the minimal interface and registry:

```python
class ForecastFamily(Protocol):
    name: str                                  # "dynamix" | "pce" | "darts" | ...
    def is_available(self) -> bool: ...        # import-guard lives HERE (fail-soft)
    def forecast(self, history: pd.DataFrame, ts: str,
                 horizon: int) -> pd.DataFrame | None: ...
    # Output contract: DataFrame indexed 1..horizon with a "forecast" float column,
    # raw (unclamped) model values — clamping stays a display/ticket concern (U5).

REGISTRY: list[ForecastFamily] = [DynamixFamily(), PceFamily(), DartsFamily()]
def available_families() -> list[ForecastFamily]: ...
```

Write one adapter per existing core (`DynamixFamily`, `PceFamily`, `DartsFamily`)
that wraps the current functions **without modifying the cores themselves**: the
adapter normalizes each core's signature (e.g. `pce_narx.predict_pce_narx(data,
target_col, forecast_horizon)`) to the interface, and moves the caller-side
try/except-import into `is_available()` with the existing warning text preserved.

**Why:** This is the single missing abstraction (AFI-24). The adapters isolate all
signature quirks in one file each; the fail-soft optional-dependency pattern required
by CLAUDE.md is preserved but now lives in exactly one place per family.

**Acceptance criteria:**
- Registry + three adapters exist; unit tests cover `is_available()` under simulated
  missing imports and the output contract shape for a stub family.
- No caller is migrated yet (that is U18.1b–d) — this task is purely additive, zero
  behavior change.
- A stub `FakeFamily` test helper lands in `tests/_builders.py` for later tasks.

#### Task U18.1b — Migrate `candidate_grid.py` to the registry

**What:** Replace the family branching in `collect_model_forecasts_for_step` /
`_forecast_single_series` with iteration over `available_families()`.

**Why first:** it is the only caller with a golden lock
(`tests/contract/test_candidate_grid_golden.py`), so it proves the registry faithful
before the less-tested callers move.

**Acceptance criteria:**
- Candidate-grid golden test passes **unchanged** (bit-identical rows, including
  provenance/model-name strings).
- No `import pce_narx` / `import darts_core` remains in `candidate_grid.py` — only
  `families`.
- Per-family error capture (`_err`) behavior preserved: one family failing still
  yields rows for the others.

#### Task U18.1c — Migrate `entrypoints/run_cli.py` to the registry

**What:** Replace the hand-wired family calls (PCE at :215/:296 and the
DynaMix/Darts equivalents) with registry iteration; console output (model names,
warnings for missing families) stays textually identical.

**Why:** Second caller; kills the second copy of the wiring.

**Acceptance criteria:**
- `dynamix-cli --target TS_1 --horizon 5` output is unchanged on a machine with and
  without optional deps (compare captured output in tests where feasible).
- Forecast-display tests (`tests/core_unit/test_forecast_display.py`) pass unchanged.

#### Task U18.1d — Extract a shared forecast service; migrate the Tkinter worker

**What:** Create `dynamix/forecast_service.py`: one function that takes (history,
series list, horizon) and returns structured result rows by iterating the registry —
i.e., the *logic* currently embedded in `gui.py::_run_forecast_worker` (lines
~669–860). The Tkinter worker then shrinks to: call service → hand rows to widgets →
post progress events. `run_cli` may adopt the same service where it reduces code.

**Why:** `_run_forecast_worker` is the repo's worst hotspot (cyclomatic 77) because it
does model wiring + formatting + widget updates in one method. The registry removes
the wiring; this task removes the formatting; only widget code remains — and widget
code in the legacy GUI is deliberately left untouched (it is frozen legacy; polishing
it is review burden with no payoff).

**Acceptance criteria:**
- `_run_forecast_worker` cyclomatic complexity < 40 (measured; U17.1 grandfather entry
  updated downward).
- GUI display tests (`test_gui_forecast_display.py`) pass unchanged.
- The service is pure w.r.t. UI (no tkinter imports) and unit-tested with `FakeFamily`.

#### Task U18.2 — Split `stat.py` along its existing seams *(supersedes U17.3)*

**What:** `src/dynamix/stat.py` (1379 lines, 61 symbols) becomes three modules along
boundaries that already exist in the file:
- `dynamix/backtest.py` — the rolling-origin loop (`run_statistics` and its step
  helpers); while moving, extract 2–3 pure helpers (per-step scoring, per-model
  accumulation — the pieces U5.6 and U13.2 will touch anyway);
- `dynamix/overlay_report.py` — `print_overlay_witness_report` (cyclo 35) and overlay
  bookkeeping;
- `dynamix/statgrid_export.py` — the exporter class with `SCHEMA_VERSION`,
  `schema.json`/manifest/shard writing (already fully self-contained).

`dynamix/stat.py` remains as a re-export facade (same pattern as the
`candidate_grid` extraction) so `dynamix-stat`, `stat.py` shim, tests, and the
webapp runner keep working untouched.

**Why:** 1379 lines is the single hardest file to review; the three responsibilities
are already non-overlapping inside it, so the split is a move, not a redesign. It also
gives U4 (schema work) a small, dedicated home instead of a corner of a giant file.

**Acceptance criteria:**
- Golden/contract tests pass unchanged; a full `--statgrid-export incremental` run on
  fixture data produces byte-identical shards + schema.json.
- `run_statistics` cyclomatic < 40; no new module exceeds ~700 lines.
- `from dynamix import stat` and all current entrypoints work unchanged (the
  entrypoint-import test enforces this).

#### Task U18.3 — Single-home the copy-pasted utilities

**What:** Mechanical dedup, one commit per utility:
- `_is_event_mode()` (4 copies: `data_utils`, `pce_narx`, `plotting`,
  `candidate_grid`) → keep the `data_utils` implementation, import everywhere else;
- `_repo_root()` (`data_utils`, `webapp/runner`, …) → one home in `data_utils` (or
  `constants`), imported elsewhere;
- `_bootstrap_import_paths()` (4 test files: `test_constants`, `test_data_utils`,
  `test_integration`, `test_stat_logic`) → one `tests/_bootstrap.py`, imported by all.

**Why:** Four copies of a 3-line function is pure reviewer noise and a drift seed;
this is an hour of mechanical work that permanently ends "which copy is
authoritative?".

**Acceptance criteria:**
- `search: def _is_event_mode` returns exactly one hit in application code; same for
  the other two.
- Full suite green; no behavior change.
- ruff F401 (unused imports) clean after the sweep.

#### Task U18.4 — Split `opt_strategies.py` by strategy *(opportunistic — ride U6)*

**What:** When U6 touches strategies, split `opt/opt_strategies.py` (895 lines) into
`opt/strategies/{greedy,milp,bandit,evo}.py` plus `opt/economics.py`
(`compute_portfolio_economics`, `random_ticket_baseline`, ticket sampling);
`opt_strategies` stays as a re-export facade.

**Why:** Ranked last deliberately: the file is already function-modular, so the pain
is navigation, not correctness risk — it does not justify its own PR, but it becomes
nearly free when U6 is editing those functions anyway (extract-on-touch, U17.2).

**Acceptance criteria:**
- Optimization + determinism test layers pass unchanged (seeded runs bit-identical).
- Public names still importable from `opt.opt_strategies`.
- Executed as part of, or immediately after, U6 — not as a standalone campaign.

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

### EPIC U19 — Oversight Visualizations (lean) *(new in v2.3)*

**Priority:** P1 · **Type:** analytics / UX · **Status:** Proposed · **Depends on:** per task — U19.2→U1, U19.3→U15, U19.4→U16; U19.5/.6 need only data that exists today
**Companion doc:** [visualization_guide.md](visualization_guide.md) — plain-language
explanation of every chart, what it exposes, and how to read it.

**What:** Exactly five charts, each admitted under one strict test: *it must expose
information that no logged scalar metric can carry.* Every logged metric in this
project is an aggregate over draws, cells, or time; aggregation destroys four kinds of
information — **path, place, shape, time** — and the domain's extreme payout skew
(totals dominated by rare multi-hit events) makes aggregates the least trustworthy
numbers in the project. Each chart is the anti-aggregation instrument for one specific
failure mode:

| Chart | Rescues | The scalar it corrects |
|---|---|---|
| U19.2 Equity curve + null envelope | path | `edge_eur` can't distinguish steady drift from one lucky spike |
| U19.3 Empirical vs analytic overlay | place | the fairness p-value says *that* something is off, never *where* |
| U19.4 Permutation-null histogram | shape | a permutation p-value's reliability depends on the null's (heavy) tail |
| U19.5 Rolling hit-rate timeline | time | whole-run hit rate hides regime change and mid-run model death |
| U19.6 Backtest coverage map | failure location | fail-soft design lets a family die silently; counts shrink, nothing shouts |

**Why "lean":** a longer candidate list was triaged against the same test; ball-level
whisker charts, model×series heatmaps, fold dot plots, and a mission-control dashboard
were **cut or reduced to logged metrics** because tables carry their content. This
epic is deliberately not a dashboard program.

> **Comment (architecture):** one pure module + two surfaces, no new dependencies.
> Chart builders live in `dynamix/viz.py` as pure functions (`DataFrame in → plotly
> Figure out`, no I/O — plotly is already a core dependency). Consumers: (a) a
> Streamlit "Insights" page, and (b) a static, self-contained **run report** HTML
> written to `Output/reports/` per run — an auditable file artifact, consistent with
> the project's file-contract philosophy, viewable offline without the app. Figure
> builders are tested on fixtures by asserting figure *data* (trace values), never
> pixels.

#### Task U19.1 — Viz foundation: pure builders + two surfaces

**What:** Create `dynamix/viz.py` (empty registry of builders + shared styling
helpers), the run-report writer (assembles available figures into one
self-contained HTML in `Output/reports/`), and a Streamlit "Insights" page skeleton
that renders whatever builders have data available.

**Why:** One foundation so each later chart task is: write one builder + one fixture
test, done. Report and page pick it up automatically.

**Acceptance criteria:**
- Builders are pure (no file/network I/O, no streamlit imports).
- Run report is a single self-contained HTML file (no CDN references).
- Missing data → chart section is skipped with a note, never an error.

#### Task U19.2 — Equity curve inside the null envelope *(data: U1.2)*

**What:** Cumulative net EUR per strategy over EVAL draws, drawn over the p5–p95 band
of the seeded random-baseline population from U1.2 (the "luck cloud").

**Why:** Rescues **path**. `edge_eur = +40` is identical for "steady accumulation"
and "one lucky spike on draw 37"; the first is interesting, the second is guaranteed
noise. Only the trajectory against the luck cloud separates them — it is a visual
sequential test of the random-walk null.

**Acceptance criteria:**
- Band computed from the per-draw baseline population (not from summary aggregates).
- Fixture test: a synthetic "one-spike" series and a synthetic "steady-drift" series
  produce visibly different trace data (asserted numerically).
- Renders in both surfaces; guide section 3 linked from the chart title.

#### Task U19.3 — Empirical vs analytic position distributions *(data: U15.2)*

**What:** Seven small-multiple panels: observed value histogram per TS as bars, exact
order-statistic pmf (U15.2) as a line.

**Why:** Rescues **place**. The chi-square score says a deviation exists; the overlay
shows whether it is concentrated (potentially exploitable ball bias), smeared
(multiplicity noise), or edge-of-domain (data-entry artifact) — three different
actions behind one identical p-value. Doubles as the visual oracle for U14's planted
bias: the bump must appear at the planted ball.

**Acceptance criteria:**
- Line is the exact pmf, not a Monte Carlo approximation.
- Fixture test on U14.1 biased data: the planted ball's bar/line gap is the maximum
  gap in its panel (asserted on trace data).
- Panel note reminds the reader of the multiplicity caveat (a few bars always poke
  out by chance).

#### Task U19.4 — Permutation-null histogram *(data: U16.2)*

**What:** Histogram of edge EUR across the K shuffled-history runs, with a vertical
marker at the real-history edge and its percentile annotated.

**Why:** Rescues **shape**. The permutation p-value's meaning depends on the null's
tail: shuffled histories also hit jackpots, so the null pile is heavily
right-skewed, and "just past p95" inside a long tail is weak evidence. The rank alone
cannot carry that; the pile can.

**Acceptance criteria:**
- Marker + percentile match `permutation_p` from the U16.2 summary exactly.
- Fixture test with a known small null set asserts bin contents and marker position.
- Chart caption states K (number of shuffles).

#### Task U19.5 — Rolling hit-rate timeline *(data: exists today in backtest rows)*

**What:** Per model family: hit rate over a configurable sliding window of backtest
steps, recomputed each step.

**Why:** Rescues **time**. Whole-run hit rate assumes exchangeability; the two live
violations — lottery equipment change and silent mid-run model death under fail-soft
— both appear as a step change here and as nothing in the aggregate. Distinguishes
"never good" from "fine until step 214, then died".

**Acceptance criteria:**
- Window size configurable; default documented.
- Fixture test: synthetic rows with a planted break at a known step produce a level
  shift at that step in the trace data.
- Buildable from any existing StatGrid run (no new pipeline output required).

#### Task U19.6 — Backtest coverage map *(data: exists today in StatGrid rows)*

**What:** Grid of backtest step × (model, series), colored by outcome: hit / miss /
failed / skipped.

**Why:** Rescues **failure location** — the operational chart. Fail-soft (a design
virtue everywhere else) lets a model family die mid-run while the run "succeeds";
counts shrink quietly. The map shows *what died at exactly which step* as an empty
stripe with a visible onset — a five-minute diagnosis instead of a lost evening, and
a guard against optimizing over a grid with a hole in it.

**Acceptance criteria:**
- All four statuses visually distinct; legend fixed.
- Fixture test: rows with a family absent after step k produce the empty stripe
  starting at k (asserted on trace data).
- Insights page shows it first (it is the "was the run healthy?" gate — guide §8).

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
| 4 | **U1** Scoreboard uncertainty | P0 | Core honesty upgrade; U2/U6/U14 build on its CI helpers and verdict labels |
| 5 | **U9** Static quality gates + **U17** (ceiling + extract-on-touch rule) | P1 | Gates land *before* the refactor wave and the M2/M3 code volume, so every later change is made under lint + a no-growth complexity guarantee |
| 6 | **U18** first wave (U18.1–.1d, U18.3: registry, caller migrations, utility dedup) | P1 | The registry makes every later model family a one-file change and guts the cyclomatic-77 hotspot; done under fresh U9 gates, locked by existing goldens |
| 7 | **U13** Naive baseline + demo + e2e CI | P1 | Now a one-file family thanks to U18.1; its e2e test then guards all remaining work; U14 needs its generator |
| 8 | **U14** Detector calibration | P0 | The plan's highest-value epic; needs only U13's generator + U1's verdicts; after it, every later result is interpretable |
| 9 | **U2** Walk-forward | P0 | Needs U1's per-fold CI reporting; feeds U6 |
| 10 | **U16** Permutation control | P1 | Cheap once U1/U2 exist; completes the control set (tickets, folds, time) |
| 11 | **U15** Analytic null model | P1 | One-file family via U18.1; the scientifically correct baseline; also upgrades U14.3's detection oracle |
| 12 | **U18** second wave (U18.2: `stat.py` split) | P1 | Lands before U4/U5.6 so schema and diagnostics work happens in the new small `statgrid_export.py`, not a corner of a 1379-line file |
| 13 | **U4** Schema consumer-side versioning | P1 | Contract hardening before any future grid change; U10 depends on its fixtures |
| 14 | **U6** Stability & recommendation (+U18.4 strategies split rides along) | P1 | Consumes U1 + U2 outputs; recommendation gates can now also require beating the analytic null |
| 15 | **U11** Windows + newer-Python CI | P1 | Do before declaring the GUI production-ready on the target OS |
| 16 | **U8** Audit pack | P2 | Reuses U3 collector; most valuable once runs get longer (post walk-forward) |
| 17 | **U12** Progress protocol | P2 | Quality-of-life; regression fixtures already exist from history |
| 18 | **U10** tools/ status + tests | P2 | Depends on U4 fixtures; includes deleting/labeling the orphan `check_darts_params.py` |
| 19 | **U7** Docs governance | P2 | Last so the index is written against the post-upgrade doc set (U0 already fixed the acute drift) |
| — | **U19** Oversight visualizations *(phased — no single slot)* | P1 | U19.1 (foundation), .5 and .6 can land **any time** (their data exists today); .2 lands with U1, .3 with U15, .4 with U16 — each chart ships in the same wave as the epic that produces its data |

---

## 4. Compact GitHub-issue backlog

### P0
- **U0** — Fix orphaned test discovery + stale doc/packaging statements *(4 tasks)*
- **U3** — `dynamix-health` CLI + `--deep` probe + GUI page + CI smoke *(5 tasks)*
- **U5** — Single domain authority, output/ingest contracts, OOD diagnostics *(6 tasks)*
- **U1** — Bootstrap CIs, baseline distribution, verdict labels, GUI bands *(5 tasks)*
- **U2** — Walk-forward: fold plan, CLI mode, no-resume rule, aggregation *(4 tasks)*
- **U14** — Detector calibration: biased generator, null test, detection test, power sweep, instrument stamp *(5 tasks)*

### P1
- **U18** — Refactoring program: family registry + 3 caller migrations, `stat.py` split, utility dedup, strategies split *(7 tasks)*
- **U13** — Naive model family, synthetic data, true e2e CI, control scoreboard row *(5 tasks)*
- **U9** — Ruff, coverage floor, targeted mypy *(3 tasks)*
- **U15** — Order-statistic null: fact record, pmf module, analytic family, fairness diagnostic, scoreboard control *(5 tasks)*
- **U16** — Permutation control mode + empirical p-value *(2 tasks)*
- **U4** — Schema detection, normalization registry, golden fixtures, merge-tool registry *(4 tasks)*
- **U6** — Stability score, recommendation gates, seed sensitivity *(3 tasks)*
- **U11** — Windows CI, Windows-safe stop, 3.13/3.14 canary *(3 tasks)*
- **U19** — Oversight visualizations: foundation + equity/envelope, distribution overlay, permutation histogram, rolling timeline, coverage map *(6 tasks, phased)*

### P2
- **U17** — Complexity ceiling + extract-on-touch rule *(2 tasks; extraction moved to U18)*
- **U8** — audit.json, GUI audit surface, runtime trends *(3 tasks)*
- **U12** — Progress emitter + parser round-trip contract *(2 tasks)*
- **U10** — tools/ inventory + merge-tool tests *(2 tasks)*
- **U7** — Docs index, command smoke tests, freshness tripwire *(3 tasks)*

**Total: 20 epics, 79 tasks** — deliberately many small tasks over few large ones.

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
4. **Reframing (v2.1).** The second-pass critique (section 1.4) changes what the
   project's success criterion is. The target lottery is presumed random, so the
   winning outcome is not "find an edge" but "prove the instrument would have found
   one". That reframing produces the v2.1 epics: calibrate the detector against
   planted signals (U14), replace learned approximations of a known distribution with
   the exact analytic null and test the lottery's fairness directly (U15), close the
   temporal-control gap with permutation tests (U16), and contain the five complexity
   hotspots where the next bug is statistically likeliest to appear (U17). With U14
   and U15 in place, the sentence this project can print at the end — "a calibrated
   detector, validated on planted signals, finds this lottery consistent with a fair
   draw and no strategy that beats the exact null" — is a complete, defensible
   scientific result. That is the strongest form this POC can take.
5. **Refactoring program (v2.2).** The maintainability audit found the macro-
   architecture healthy and the debt concentrated: one missing abstraction (the
   model-family interface, AFI-24) explains the forecast-wiring triplication, the
   worst complexity hotspot, and the three-edit-site cost of new model families.
   Epic U18 fixes it as a sequence of small, behavior-preserving, golden-locked moves
   — registry first (making U13/U15 one-file changes), then the `stat.py` split, then
   mechanical dedup — under the U9/U17 gates, with explicit ground rules so each
   commit stays reviewable as a pure move.
6. **Oversight visualizations (v2.3).** Because the domain's payout skew makes
   aggregates the least trustworthy numbers in the project, five charts (U19) act as
   anti-aggregation instruments — one each for path, place, shape, time, and failure
   location. Everything that a table could carry was cut from the epic; the
   plain-language rationale and reading instructions live in
   `docs/visualization_guide.md`.

The architectural constants remain untouched: three decoupled stages, file contracts,
leakage-safe fitting, fail-soft optional dependencies, and the visible no-edge message.
