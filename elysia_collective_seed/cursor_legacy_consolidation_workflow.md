# Cursor Legacy Guardian/Elysia Consolidation Workflow

## Goal

Systematically reconcile old local Guardian/Elysia folders with the current canonical project without deleting historical evidence or confusing file existence with working capability.

## Phase A — Forensic inventory (read-only)

Run a static inventory over every legacy folder before editing anything.

For each file record:
- absolute/relative path
- size and modified time
- SHA-256
- extension/type
- whether it parses as Python
- top-level classes/functions
- imports
- obvious TODO/placeholder/stub signals
- likely historical generation (`legacy`, `backup`, `proposal`, `runtime`, `unknown`)

Then compare against the canonical Guardian tree and assign one of:

- `EXACT_DUPLICATE` — identical content already exists
- `SAME_PATH_SAME_CONTENT`
- `SAME_PATH_DIFFERENT_CONTENT`
- `SYMBOL_OVERLAP` — shares classes/functions with current code
- `UNIQUE_LEGACY` — no obvious current counterpart
- `LIKELY_SUPERSEDED`
- `POTENTIAL_RECOVERY` — old file appears to contain capability/design not present in current tree
- `DATA_OR_HISTORY`
- `NEEDS_HUMAN_REVIEW`

No files move or change in this phase.

## Phase B — Correspondence analysis

For every `SAME_PATH_DIFFERENT_CONTENT`, `SYMBOL_OVERLAP`, `UNIQUE_LEGACY`, or `POTENTIAL_RECOVERY` record:

1. identify the likely current counterpart;
2. compare public APIs, classes, functions, imports, tests, and docs;
3. determine whether the older file contains behavior absent from the current file;
4. distinguish implementation from comments/design/stubs;
5. create a reconciliation record.

Reconciliation disposition:

- `KEEP_CURRENT`
- `MERGE_FEATURE`
- `PORT_IDEA_ONLY`
- `ARCHIVE_OLD`
- `ARCHIVE_BOTH_PENDING_REVIEW`
- `RESTORE_AS_MODULE_CANDIDATE`
- `PRIMARY_HISTORICAL_SOURCE`

## Phase C — Staging consolidation

All code changes happen in an isolated branch/worktree.

Rules:
- never edit the only known copy of a legacy file;
- never delete files during first consolidation;
- copy historical material to a versioned archive before replacement;
- preserve hashes and source paths in the archive manifest;
- add tests for any recovered behavior before considering it integrated;
- prefer adapting current Guardian modules over resurrecting parallel subsystems;
- Constitution/Covenant, Rebuild Manifest, original Elysia/Erebus docs, and other identity/governance sources are Genesis material, not ordinary cleanup targets.

## Phase D — Verification

Independent verifier checks:
- recovered feature actually exists in the new implementation;
- tests exercise it;
- no current functionality was lost;
- archive contains provenance for replaced material;
- no credentials/private databases/logs were accidentally committed;
- boot-path analyzer still identifies the intended live module;
- readiness scanner does not classify the recovered module as a stub.

## Phase E — Archive

Recommended archive structure:

```text
archive/
  legacy_guardian/
    manifest.jsonl
    by-era/
      2024/
      2025/
      2026/
    superseded-code/
    abandoned-experiments/
    design-only/
    raw-unknown/
```

Archive records should include the original path, SHA-256, date if known, why it was archived, current counterpart if any, and reconciliation task/commit IDs.

## Cursor agent workflow

Use a parent Relay/Orchestrator with specialist subagents rather than allowing arbitrary agent creation.

```text
Relay
  |
  +--> Archaeologist (read-only inventory)
  |
  +--> Correspondence Analyst (read-only comparison)
  |
  +--> Consolidator (isolated write branch)
  |
  +--> Verifier (independent read/test pass)
  |
  +--> Archivist (manifest/provenance)
  |
  `--> Relay chooses next bounded task
```

Each specialist ends by emitting a structured handoff packet. The Relay chooses the next registered role and launches it with the necessary context.

## Why not let agents freely create successor agents?

Cursor supports subagents spawning subagents, but unconstrained recursive role creation makes provenance, cost, and authority difficult to reason about. For Elysia, successor creation should be bounded to a registry of approved roles. New role definitions can be proposed, but adoption is a separate reviewed change.

## Cursor features to exploit

- project subagents in `.cursor/agents/`
- isolated worktrees/VMs for concurrent modifications
- `/multitask` for parallel read-only inventory/comparison
- `/goal` for the long-lived consolidation objective
- background subagents for large directory scans
- Cloud Agent subscriptions/automations later for CI/review follow-up
- Self-Hosted `My Machines` for operating against the local Guardian checkout while tool execution remains on the user's machine

## First real run

1. Freeze a read-only backup of all legacy folders.
2. Point Cursor at a workspace containing canonical Guardian plus legacy roots.
3. Run Archaeologist across all roots.
4. Generate `legacy_inventory.json` and reconciliation queue.
5. Review highest-value `POTENTIAL_RECOVERY` items first.
6. Consolidate one module family at a time.
7. Verify independently.
8. Archive only after verification.
