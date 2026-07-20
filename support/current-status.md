# CC_Loto current support status

- Observed at UTC: `2026-07-20T00:56:12Z`
- HEAD: `this status is recorded by evidence commit B, whose parent is guidance-correction content commit A 416691248cb4f69586ddd483a942c56e5be60cf6`
- Upstream relation: `the two local guidance-correction commits remain unpushed; origin/main remains at published Slice 5 tip fd7e96fd4a7569a7aeeddfff04e8d2c4ec7ddf7e`
- Worktree: `clean required at evidence commit B before final-tree validation and reviewer handoff`
- Support milestone: `M3 authorized Loto publication; Slices 1, 2, 3, 3c, and 5 are published and closed; this Claude-owned guidance correction awaits committed-object review; M4 remains closed`
- Product plan reference: `docs/CC_Loto_ENHANCED_UPGRADE_PLAN.md`

## Active work

- Content commit A modifies exactly root [CLAUDE.md](../CLAUDE.md), replacing a stale sentence that
  claimed `sys.path` bootstrapping and no packaging or requirements file. The replacement states the
  verified facts: the project is packaged with setuptools as `dynamix-lottery`, targets Python
  `>=3.11`, is normally used as an editable install, and takes `requirements.txt` and
  `requirements.lock` as dependency authorities.
- The stale sentence also contradicted the same file's own later sections, which already described
  an installable package and prohibited reintroducing per-file `sys.path.insert` bootstrapping. The
  correction removes that internal contradiction and preserves those sections unchanged.
- Roles were reversed for this slice: Claude Code authored the Claude-owned change and Codex was the
  independent reviewer. Codex accepted the pre-write packet with no findings and did not edit any
  Claude-owned file.
- This status and the appended events form evidence commit B. Neither A nor B is pushed until Codex
  independently reviews the committed objects and explicitly authorizes the push.
- Validators/tests, aggregate validation, rollback evidence, and the M4 decision remain later
  separately gated work.

## Messages, claims, and blockers

The installed target-local coordination queue remains empty; cross-agent review is conducted through
the Wiki workspace neutral channel. Push is blocked pending Codex's independent review of local A
and B.

## Guidance pair state

The two agent guidance files are **not** synchronized, and this correction does not make them so.
Codex-owned `AGENTS.md` carries support read-order, ownership, literal validation-state, recovery,
and owner-gate anchors; Claude-owned `CLAUDE.md` remains a product-development guidance file that
carries none of them. Whether `CLAUDE.md` should carry support workflow at all is an owner-scoped
decision and belongs to a separate briefed and reviewed slice. No record may report the pair as
synchronized until that work exists and both agents confirm their own side.

## Validation state

At content commit A `416691248cb4f69586ddd483a942c56e5be60cf6`, the separate support-operator
interpreter provided PyYAML `6.0.3` and jsonschema `4.26.0`; `python tools/support/agent_coord.py .`
exited `0` with 0 errors and 0 warnings, and `coordination/BOARD.md` remained byte-identical.
CC_Loto product requirements were not changed and its product environment is not claimed
support-capable.

With output and model-cache directories redirected outside the repository, target-native commands
`python run_tests.py --layer core-unit --pattern test*.py --verbosity 1`, `python run_tests.py
--layer contract --pattern test*.py --verbosity 1`, and `python run_tests.py --layer
state-integrity --pattern test*.py --verbosity 1` exited `0`, `0`, and `0`: 42, 25, and 3 tests
passed (70/70). Optional, optimizer, integration, and webapp layers were not made applicable by a
documentation-only change and were **not run**; that is a not-run state, not a pass. The committed
`CLAUDE.md` object matches the reviewed authority, and `AGENTS.md` is unchanged.

## Exact next action

- Owner: `codex (independent reviewer), then claude-code (implementer)`
- Prerequisites: evidence commit B exists; worktree is clean; `B^ == A`; A changes exactly one path
  and B exactly two; committed objects match their reviewed authorities
- Action: independently review local commits A and B, then authorize or reject one fast-forward push
  containing exactly A followed by B
- Stop condition: any amended/rebased commit, unexpected path, byte mismatch, stale board,
  coordination error, native-layer regression, target drift, synchronization overclaim, or reviewer
  finding

## Evidence

- Slice preparation, local commit, review, and validation events in [log.md](log.md)
- Handoff state in [HANDOFF.md](../HANDOFF.md)
- Record classes in [RECORD-KEEPING.md](RECORD-KEEPING.md)
- Sensitivity, native-runner, module, and recovery authority in [PROFILE.md](PROFILE.md)
