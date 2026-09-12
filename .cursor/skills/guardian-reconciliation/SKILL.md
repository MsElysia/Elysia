---
name: guardian-reconciliation
description: Multi-stage workflow for inventorying, comparing, consolidating, verifying, and archiving legacy Elysia / Project Guardian files. Use for Guardian historical cleanup and recovery work.
icon: git-branch
color: purple
---
# Guardian Reconciliation

Use the registered Guardian subagents and persistent task/handoff artifacts to reconcile legacy Elysia and Project Guardian material with the canonical codebase.

## Required workflow

1. Establish the canonical Guardian root and one or more legacy roots. Keep original legacy copies untouched.
2. Invoke `guardian-archaeologist` for read-only inventory and duplicate/candidate classification.
3. Use `guardian-correspondence-analyst` for files that differ, overlap in symbols, or appear unique/valuable.
4. Create bounded ledger tasks with explicit acceptance criteria.
5. Invoke `guardian-consolidator` only for approved code-recovery/merge tasks and require an isolated branch/worktree.
6. Invoke `guardian-verifier` after every code-changing task. Failed verification returns to the consolidator with precise defects.
7. Invoke `guardian-archivist` only after disposition is known and provenance is preserved.
8. Return control to `guardian-relay`, which selects the next ready task from the ledger.
9. Continue until every inventoried legacy item has a disposition or requires human review.

## Durable state

Use:
- `elysia_collective_seed/cursor_task_ledger_schema.json`
- `elysia_collective_seed/cursor_handoff_packet_schema.json`
- `elysia_collective_seed/cursor_legacy_consolidation_workflow.md`

The ledger is the durable state between agents. Do not rely on a subagent remembering another subagent's context.

## Allowed dispositions

- EXACT_DUPLICATE
- KEEP_CURRENT
- MERGE_FEATURE
- PORT_IDEA_ONLY
- RESTORE_AS_MODULE_CANDIDATE
- PRIMARY_HISTORICAL_SOURCE
- ARCHIVE_OLD
- ARCHIVE_BOTH_PENDING_REVIEW
- EXCLUDE_PRIVATE_OR_UNRELATED
- HUMAN_REVIEW

## Hard stops

Require human review before destructive deletion, constitutional/governance reinterpretation, moving private data into Git, expanding runtime authority, enabling autonomous deployment, or resolving ambiguous competing implementations based on preference rather than evidence.
