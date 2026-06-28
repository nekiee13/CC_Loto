# Progress Tracker

Living status board for the work specified in [TDD_PLAN.md](TDD_PLAN.md). Update the **Status**
and **Notes** columns as tasks move; log notable changes in the Progress Log at the bottom.
Full What/Why/TDD steps and acceptance criteria live in `TDD_PLAN.md` (this file is just the
scoreboard).

**Status legend:** ⬜ Todo · 🟡 In progress · 🔵 In review · ✅ Done · ⏸️ Blocked · ❌ Dropped

_Last updated: 2026-06-29_

---

## Epic summary

| Epic | Priority | Status | Done / Total | Notes |
|------|----------|--------|--------------|-------|
| E1 — Honest EV/ROI + calibration scoreboard | P0 | ⬜ Todo | 0 / 4 | Highest value |
| E2 — Packaging & import hygiene | P0 | ⬜ Todo | 0 / 3 | Removes import-bug class |
| E3 — CI + import smoke tests | P0 | ⬜ Todo | 0 / 2 | Do first |
| E4 — Decompose `stat.py` | P1 | ⬜ Todo | 0 / 2 | Golden test first |
| E5 — Test analytical core + coverage | P1 | ⬜ Todo | 0 / 3 | — |
| E6 — Resolve evolutionary stub | P2 | ⬜ Todo | 0 / 2 | E6.1 do regardless |
| E7 — De-dupe rounding storage | P2 | ⬜ Todo | 0 / 1 | Behind flag |
| E8 — Cleanup & polish | P3 | ⬜ Todo | 0 / 4 | Anytime |
| **Total** | | **⬜** | **0 / 21** | |

**Suggested order:** E3 → E2 → E1 → E5 → E4 → E7, with E6 and E8 branching off.

---

## Task board

### E1 — Honest EV/ROI + calibration scoreboard `P0`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E1.1 Pure economics function | ⬜ | — | — | |
| E1.2 Random-ticket control baseline | ⬜ | — | — | |
| E1.3 `q_any` calibration on EVAL | ⬜ | — | — | |
| E1.4 Wire scoreboard into summary + console | ⬜ | — | — | depends on E1.1–E1.3 |

### E2 — Packaging & import hygiene `P0`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E2.1 `pyproject.toml` + package metadata | ⬜ | — | — | |
| E2.2 Finish layout; entrypoint shims | ⬜ | — | — | removes load-by-path |
| E2.3 Pin deps + lockfile + target Python | ⬜ | — | — | 3.11/3.12 |

### E3 — CI + import smoke tests `P0`
| Task | Status | Owner | PR / Commit | Notes |
|------|--------|-------|-------------|-------|
| E3.1 Import smoke tests | ⬜ | — | — | shared with E2.2 |
| E3.2 GitHub Actions workflow | ⬜ | — | — | |

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
| E5.3 Skip-not-fail + coverage | ⬜ | — | — | fixes AS-IS failure |

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

- 2026-06-29 — Plan established; **0 / 21** tasks started. Baseline at commit `1bec389`:
  `orchestrator.py` import fixed; docs (architecture, AS-IS, SRS, analysis, ROADMAP, TDD_PLAN)
  and tooling (jcodemunch code index, jdocmunch doc index, `.venv` + core deps) in place.
