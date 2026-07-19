# {{PROJECT_NAME}} paired-guidance semantic anchors

| Anchor | Required shared meaning | Codex implementation | Claude implementation | Documented difference/rationale | Verification |
|---|---|---|---|---|---|
| read-order | Guidance, handoff, status, messages/claims, Git, unfinished work | {{CODEX_READ_ORDER}} | {{CLAUDE_READ_ORDER}} | {{READ_ORDER_DIFFERENCE}} | {{READ_ORDER_CHECK}} |
| ownership | Each agent edits only its owned infrastructure and prefix | {{CODEX_OWNERSHIP_TEXT}} | {{CLAUDE_OWNERSHIP_TEXT}} | {{OWNERSHIP_DIFFERENCE}} | {{OWNERSHIP_CHECK}} |
| truthful-validation | Literal check states; no implied pass | {{CODEX_VALIDATION_TEXT}} | {{CLAUDE_VALIDATION_TEXT}} | {{VALIDATION_DIFFERENCE}} | {{VALIDATION_CHECK}} |
| safe-recovery | Evidence-first, scoped, approval-gated recovery | {{CODEX_RECOVERY_TEXT}} | {{CLAUDE_RECOVERY_TEXT}} | {{RECOVERY_DIFFERENCE}} | {{RECOVERY_CHECK}} |
| target-gates | M2/M3 and later owner gates cannot be inferred | {{CODEX_GATE_TEXT}} | {{CLAUDE_GATE_TEXT}} | {{GATE_DIFFERENCE}} | {{GATE_CHECK}} |

Each agent authors its own columns. A shared reviewer verifies semantics without rewriting either
agent's infrastructure.
