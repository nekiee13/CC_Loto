# CC_Loto team protocol

## Ownership

The human project owner approves gates, authority changes, destructive recovery, hosted-governance changes, and releases. Codex owns `AGENTS.md`, `.agents/`, and `CX_` records. Claude Code owns `CLAUDE.md`, `.claude/`, and `CC_` records. Coordination records without an agent prefix, schemas, templates, validators, claims, the generated board, support logs, and handoffs are shared-neutral by contract. An agent may inspect but must not edit or archive the other agent's owned infrastructure or prefixed records.

Each agent edits and archives only its owned infrastructure/record prefix. Shared-neutral files
require a non-overlapping claim and review.

## Messages

Messages are immutable. Correct or respond through a new `reply_to` record. Active records remain
in `messages/`; only resolved and confirmed records move intact to `archive/` with a resolution
manifest. Blockers require `resolved`, `owner-accepted`, or `deferred-until` disposition.

## Claims

Claims reserve anticipated paths. Exact and ancestor/descendant overlaps fail. Expiry releases
exclusivity but implies neither completion nor safe takeover.

## Review and synchronization

Reviewers reproduce evidence proportional to risk and classify findings. Every finding receives an
explicit disposition. One agent cannot declare the other agent's side synchronized; counterpart
confirmation is required.

## Validation

Unknown, unavailable, skipped, blocked, not-run, and not-configured are not passed. Generated
`BOARD.md` is a view, never authority. Target write gates in `support/PROFILE.md` remain in
force regardless of coordination state.
