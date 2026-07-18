# CC_Loto support profile (target-local controlled authority)

## Control

- Repository: `https://github.com/nekiee13/CC_Loto` (`main`)
- Record class: Controlled (see [RECORD-KEEPING.md](RECORD-KEEPING.md))
- Accepted publication baseline: `b469afc6f7e5593c60d0e5bdcfc7dead4a6bc481`
- Provenance: profile v1.0 approved by the human owner at M1; FIN accepted and Loto
  publication authorized at M3 on 2026-07-18, conditional on exact target-local review.
- Product authority: `docs/CC_Loto_ENHANCED_UPGRADE_PLAN.md`.
- This target-local profile governs support workflow only and never replaces product authority.
## Identity, roles, and authority

The human owner controls gates, authority changes, destructive recovery, hosted settings, and
releases. Claude retains ownership of `CLAUDE.md`, `.claude/`, and `CC_` records; Codex owns
`AGENTS.md`, `.agents/`, and `CX_` records. Neutral coordination and support records are shared by
contract. Each agent edits only its own infrastructure.

The enhanced product plan, the earlier completed TDD-plan progress record, architecture documents,
ROADMAP, CI, and existing test runner retain distinct scopes. Support navigation must not imply
that the enhanced U0-U19 plan is complete because the earlier plan reports 21/21. The plan's
`Proposed` header is an M1 disposition item, not an invitation for support-side editing.

## Core records and planned paths

Loto uses the same portable paths and semantics as FIN: `support/README.md`, replaceable
`support/current-status.md`, append-only `support/log.md`, `support/decisions/`, AFI/lessons/good
practices ledgers, clone-complete handoff schemas/templates/history, neutral `coordination/`, and
root `HANDOFF.md`. Existing product plan and progress files remain product authorities.

Documentation governance is integrated with enhanced-plan U7. Support publication creates only the
minimum navigation/record contract needed before U7 and leaves product documentation cleanup and
architecture correction in U7's scope.

## Enabled modules

| Module | State at initial publication | Rationale |
|---|---|---|
| Mandatory governance/records/ADR/handoff/validation/recovery core | Enabled | Portable support baseline |
| Dual-agent ownership and immutable messaging | Enabled | Both agents are expected writers |
| Multi-writer claims and generated board | Enabled | Prevent collisions |
| Lightweight human milestone gates | Enabled | Owner control without product state duplication |
| Documentation/code indexes | Deferred | Repository is small enough for native navigation initially |
| Hosted-governance adapter | Integrate existing CI only | No hosted mutation authorized |
| Release adapter | Inventory only | No release configuration or tags |
| Repo-local workflow skills | Disabled initially | Reuse shared schema and scripts first |
| Formal workflow state machine | Disabled | No demonstrated need |

## Git and hosted workflow

M3 accepted the FIN pilot and authorized Loto publication. Loto uses small reversible
commits on `main`, exact-baseline/clean-tree preflight, and independent review before push. No force
push, reset, hosted setting mutation, tag, or release is authorized. Branch protection remains
`unknown` until verified through an authorized GitHub surface.

## Native validation contract

Loto's native runner is `python run_tests.py`; the profile makes no pytest assumption. Validation
is layered:

1. fast support schema/reference/ownership/message/claim/board/handoff checks;
2. focused tests placed inside an existing discovered test layer;
3. affected native layer(s) through `run_tests.py`;
4. all required native layers when proportional to risk;
5. optional-layer results reported separately and truthfully;
6. existing core and optional CI after push.

The support transfer must not execute model, optimizer, webapp, backtest, or external DynaMix flows
unless a changed integration explicitly requires them. It does not add pytest as a dependency.

## Sensitivity and indexing

`DATA.csv`, golden fixtures, model/output data, plots, caches, and machine-private DynaMix path
values are excluded from support records and indexes. The current `DATA.csv` identity may be cited
by path and SHA-256 only. Secrets never enter Git or immutable records. Because indexing is
deferred, no external index or corpus refresh occurs during initial Loto publication.

## Scale and performance

The profile assumes one owner, two agents, low concurrency, approximately 131 tracked files, low to
moderate support-record volume, Git retention, and support checks completing in seconds. It adds no
service, database, or background process.

## Recovery and release

Capture HEAD, upstream, clean status, and allowed paths before every slice. Abort on drift,
ownership violation, undiscovered test placement, sensitive-data exposure, native-test regression,
or unexpected product changes. Revert only named support commits after approval; preserve unrelated
work and re-run preflight/native focused checks. Release creation remains out of scope.

## Installation authority

- The owner accepted this version and exact baseline SHA at M1.
- Publication was authorized at M3 subject to exact-render, dry-run, briefing, and review controls.
- Native `run_tests.py` and optional-layer semantics remain mandatory.
- U7 integration, data exclusions, and initially disabled modules remain accepted.
- Claude-owned guidance corrections remain Claude work; Codex does not edit them.
