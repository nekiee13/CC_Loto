# CC_Loto support system

## Authority

- Product plan: `docs/CC_Loto_ENHANCED_UPGRADE_PLAN.md`
- Product documentation: `README.md (root product overview; docs/README.md is absent)`
- Support profile: `support/PROFILE.md`
- Repository: `https://github.com/nekiee13/CC_Loto` (`main`)

This index links authorities; it does not copy product requirements, backlog, progress, or
decisions. Product authority outranks support workflow where scopes conflict.

## Ownership

The human project owner approves gates, authority changes, destructive recovery, hosted-governance changes, tags, releases, and publication. Codex owns `AGENTS.md`, `.agents/`, and `CX_` records. Claude Code owns `CLAUDE.md`, `.claude/`, and `CC_` records. Coordination, support records, handoffs, schemas, templates, validators, and generated views are shared-neutral by contract. Each agent may inspect but must not edit or archive the other agent's owned infrastructure.

## Current records

- [Record classes](RECORD-KEEPING.md)
- [Current status](current-status.md)
- [Append-only event log](log.md)
- [Support decisions](decisions/README.md)
- [Areas for improvement](AFI.md)
- [Lessons learned](LESSONS-LEARNED.md)
- [Good practices](GOOD-PRACTICES.md)
- [Current handoff](../HANDOFF.md)
- [Coordination board](../coordination/BOARD.md)

## Existing decision authorities

- Product overview and native entry points: [root README](../README.md)
- Enhanced product plan (owner-designated product authority; its document header remains `Proposed`): [enhanced upgrade plan](../docs/CC_Loto_ENHANCED_UPGRADE_PLAN.md)
- Architecture and current-state authorities: [architecture](../docs/architecture.md), [AS-IS](../docs/AS-IS.md), and [architectural and functional analysis](../docs/architectural_and_functional_analysis.md)
- Product progress and roadmap: [PROGRESS](../docs/PROGRESS.md) records the earlier TDD-plan scope and does not prove completion of the enhanced plan; [ROADMAP](../docs/ROADMAP.md) retains its own scope
- Hosted governance: [existing CI](../.github/workflows/ci.yml) is **integrate-existing-CI-only**; this support slice performs no hosted mutation
- Packaging authorities: [pyproject.toml](../pyproject.toml), [runtime requirements](../requirements.txt), and [locked requirements](../requirements.lock)
- Documentation/code indexes are **deferred**. This file is clone-local navigation only; it creates or refreshes no external index or corpus.
- Release/package status: release adapter is **inventory-only**. `git ls-remote --tags origin` exited `0` with no tag refs during packet preparation; GitHub release inventory was unavailable because the `gh` client is not installed, so this index makes no live-release-count claim. Creating a tag or release is outside this transfer.

## Validation and exclusions

- Native validation entry point: `python run_tests.py --layer core-unit --pattern test*.py --verbosity 1; python run_tests.py --layer contract --pattern test*.py --verbosity 1; python run_tests.py --layer state-integrity --pattern test*.py --verbosity 1`
- Sensitive/product-data exclusions: secrets and machine-private paths; `DATA.csv` content; golden fixtures; model/output data, StatGrid, plots, caches, and generated artifacts per [PROFILE.md](PROFILE.md)

Skipped, unavailable, blocked, and not-run checks are never reported as passed.
