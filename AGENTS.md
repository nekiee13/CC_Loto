# CC_Loto Codex Guidance

## Scope and authority

These instructions govern Codex work in this repository. The human owner controls milestone
decisions, authority changes, destructive recovery, hosted settings, tags, releases, and product
scope. The owner-designated product authority is `docs/CC_Loto_ENHANCED_UPGRADE_PLAN.md`; the root
`README.md`, architecture/current-state documents, `PROGRESS.md`, `ROADMAP.md`, CI, and the native
test runner retain their distinct scopes. Support records link those authorities and do not replace
or silently reinterpret them.

The enhanced plan retains its `Proposed` document header. Earlier TDD-plan progress does not prove
completion of the enhanced plan. Always inspect current Git and product evidence instead of relying
on copied status text.

## Ownership boundary

- Codex owns `AGENTS.md`, `.agents/`, Codex configuration/indexes, and `CX_` coordination records.
- Claude Code owns `CLAUDE.md`, `.claude/`, Claude configuration/indexes, and `CC_` coordination
  records. Codex may read them for shared context but must not edit, move, delete, archive, or
  re-index them.
- `coordination/`, shared support records, schemas, templates, validators, and handoffs are neutral
  by contract. Use immutable messages and claims; never rewrite a sent message.
- Repo-local workflow skills are disabled initially. Do not create `.agents/` content unless a
  later owner-approved, separately reviewed slice enables it.
- When Codex changes its own side of a dual-agent contract, record Claude synchronization as
  pending; never claim both sides are synchronized without Claude's confirmation.

## Session start and coordination

For support-oriented work, read in order:

1. this `AGENTS.md` and any nearer nested Codex guidance;
2. `support/README.md` and `support/PROFILE.md`;
3. `HANDOFF.md` and its immutable record when one is published;
4. `support/current-status.md` and the append-only `support/log.md`;
5. `coordination/BOARD.md`, unresolved `coordination/messages/`, and active
   `coordination/claims/`;
6. live Git branch, HEAD/upstream/divergence, worktree state, and unfinished risky artifacts.

Use `python tools/support/agent_coord.py .` for read-only coordination validation. Use the installed
tool's claim, message, release, and status operations rather than hand-editing generated
`coordination/BOARD.md`. Keep only unresolved communication active. Once resolution is confirmed,
create an immutable resolution manifest and archive only Codex-owned `CX_` records; ask Claude Code
to archive its own `CC_` records.

When the owner asks to check messages, inspect and independently verify actionable Codex-addressed
messages in the same turn. Never acknowledge acceptance without evidence. Preserve the complete
immutable message lifecycle and regenerate/validate the board after coordination state changes.

## Repository and product boundaries

- Project: DynaMix Lottery Forecasting System, an installable Python package with `dynamix` under
  `src/` and `opt` at repository root. Root entrypoint files are thin shims.
- Packaging authority: `pyproject.toml` defines setuptools package `dynamix-lottery` version
  `0.1.0`, Python `>=3.11`, mixed discovery under `src` and `.`, and optional dependency groups.
  Runtime/locked dependency authorities are `requirements.txt` and `requirements.lock`.
- `DATA.csv` is tracked product input. Do not expose its content in support records or indexes;
  cite only path and SHA-256 when identity evidence is explicitly required.
- Do not modify controlled product data, model/output artifacts, StatGrid, plots, caches, generated
  results, dependencies, hosted configuration, product plans, or architecture scope unless the
  owner explicitly places that change in the task.
- Documentation/code indexes remain deferred. Do not create or refresh an external index/corpus
  without a later owner-approved claim and exact exclusion review.

## Native commands and validation truth

Install the package from repository authority when setup is required:

```bash
python -m pip install -e .
```

Use the repository's layered `unittest` runner, not pytest:

```bash
python run_tests.py
python run_tests.py --layer core-unit --pattern test*.py --verbosity 1
python run_tests.py --layer contract --pattern test*.py --verbosity 1
python run_tests.py --layer state-integrity --pattern test*.py --verbosity 1
python run_tests.py --include-optional
```

The optional layer and heavy model families are not required unless the task makes them applicable.
Missing optional dependencies must remain fail-soft where the product contract says so. Report each
check literally as passed, failed, skipped, not-run, unknown, not-configured, or unavailable;
`blocked` is a handoff/blocker state, never a check result. Never relabel a missing, timed-out, or
excluded check as passed. Redirect output and model-cache paths outside the
repository for support-only validation when practical.

The support operator requires PyYAML and jsonschema. The separately accepted support environment
may run `tools/support/agent_coord.py`; this does not imply that the product-requirements
environment contains those packages, and support publication must not silently add them to product
dependencies.

## Git workflow and safe recovery

This is a single-owner repository. Prefer small direct commits on `main`; use a pull request only
when the owner requests one or an external constraint requires it. Cross-agent review occurs through
immutable coordination messages and committed evidence. Before every reviewed slice, capture the
exact parent, upstream, divergence, clean state, allowed paths, and rollback scope.

Do not discard local commits or working-tree changes as routine synchronization. On divergence or
recovery work, stop writes and first capture:

```bash
git status --short
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count HEAD...origin/main
git log --oneline --decorate --graph -n 20
```

Identify the exact commits and paths at risk, active claims/messages, intended recovery point, and
preservation evidence. Prefer fast-forward synchronization, preserving work on a named branch, or a
reviewed `git revert` of identified commits. Destructive discard, force push, recursive deletion,
history rewriting, or broad cleanup requires explicit owner approval naming the target, recovery
point, backup/preservation evidence, validation commands, and stop conditions. After approved
recovery, rerun Git, support, and applicable native checks and record literal commands and exits.

## Working rules

- Inspect actual files and Git state before trusting paths or status copied from another machine.
- Keep changes minimal and preserve unrelated work in a dirty tree. Stop if an overlapping change
  cannot be safely separated.
- Use target-native `tools/` placement and `run_tests.py` semantics; do not import FIN paths,
  pytest assumptions, Wiki runtime dependencies, or machine-private paths.
- Treat `docs/context/`, historical exports, examples, stale AS-IS snapshots, and proposed plans as
  non-authoritative unless a current controlled document promotes a requirement from them.
- Never report a validation as passed when it was skipped, blocked, unavailable, or not run.
- Before publishing support changes, require exact committed-object review and clean live-tip
  closure. Recovery is revert-only unless the owner explicitly approves another named operation.
- M4 cannot be inferred from completed slices. Aggregate validation, rollback evidence,
  independent review, and the owner's explicit decision remain separate gates.

## Completion checklist

Before handing off a change:

1. verify exact Git identity, path scope, and worktree state;
2. run coordination validation and the proportional native layers;
3. confirm no product-data/output/cache or cross-agent-owned path entered the change;
4. record literal commands, integer exits, unavailable checks, blockers, and recovery scope;
5. update only the appropriate replaceable/append-only support records;
6. use `python tools/support/make_handoff.py` when publishing an operational handoff, and verify the
   resulting pointer, immutable record, event, and generated board lifecycle;
7. keep owner gates and later slices closed unless their explicit evidence and decisions exist.
