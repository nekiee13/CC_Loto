# CC_Loto support recordkeeping

| Class | Mutation rule |
|---|---|
| Controlled | Reviewed edit or controlled superseding version |
| Immutable | Never edit after publication; create a correction/successor |
| Append-only | Append events; correct by referencing a prior event |
| Replaceable | Replace validated current view; retain Git/log evidence |
| Curated ledger | Preserve identity, evidence, and state transitions |
| Generated | Regenerate from authority; never hand-treat as history |
| Historical | Retain as non-current context with successor link |

## Published path classes

| Target-local path | Class |
|---|---|
| `support/README.md` (arrives with the index-closure slice) | Controlled |
| `support/PROFILE.md` | Controlled |
| `support/RECORD-KEEPING.md` | Controlled |
| `support/current-status.md` | Replaceable |
| `support/log.md` | Append-only |
| `support/decisions/README.md` | Controlled register |
| Proposed `support/decisions/ADR-SUP-NNNN-slug.md` | Controlled proposal |
| Accepted `support/decisions/ADR-SUP-NNNN-slug.md` | Immutable; change only by a new superseding ADR |
| `support/AFI.md` | Curated ledger |
| `support/LESSONS-LEARNED.md` | Curated ledger |
| `support/GOOD-PRACTICES.md` | Curated ledger |
| `HANDOFF.md` | Replaceable pointer to an immutable validated handoff |
| `coordination/BOARD.md` | Generated view; never authoritative history |

The class map is target-local authority. A proposed ADR becomes immutable when accepted; acceptance
does not imply that its implementation state is `implemented`.

Use UTC timestamps and stable IDs. Records must not contain secrets, credentials, personal data,
private path values, or product data prohibited by `support/PROFILE.md`.

States and validation outcomes are literal. Unknown, unavailable, skipped, blocked, not-run, and
not-configured are not synonyms for passed.
