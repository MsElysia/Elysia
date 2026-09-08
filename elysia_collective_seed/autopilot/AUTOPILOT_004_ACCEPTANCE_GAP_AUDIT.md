# AUTOPILOT-004 acceptance-gap audit

Date: 2026-09-08
Base: `autopilot-004-dispatcher-foundation` at the current PR #12 head when this audit branch was created.
Scope: static/read-only acceptance review plus this documentation artifact. No provider execution, deployment, external posting, private-data access, or runtime enablement.

## Purpose

AUTOPILOT-004 requires more than unit-level dispatcher behavior. This audit records which acceptance surfaces already have concrete seed evidence and which still need bounded implementation or verification before issue #8 can be considered complete.

## Evidence already present

- Persistent SQLite task ledger with claim/lease semantics.
- Dependency and human-approval dispatch gates.
- Worker capability/risk matching.
- Completion-packet validation before state mutation.
- Completed worker reports transition to `verifying`, rather than self-declaring terminal completion.
- Failed/partial work returns to the queue.
- Active leases cannot be stolen and stale task payloads cannot reopen terminal tasks.
- Task schema now recognizes the runtime lifecycle states `verifying` and `human_review`.
- CI runs compile, JSON parsing, seed pytest, and a runtime-enable guard on autopilot branches.

Representative executable evidence: `test_dryrun_orchestrator.py`, `test_task_ledger.py`, `test_dispatcher.py`, and `test_schema_runtime_alignment.py`.

## Remaining acceptance gaps

### 1. Full synthetic task graph

**Status: not yet demonstrated end-to-end.**

Current tests exercise individual lifecycle properties, but AUTOPILOT-004 explicitly requires a synthetic dependency graph to run end-to-end without conversational memory shared between workers. Add one deterministic test that persists multiple tasks, resolves dependencies from ledger state, dispatches them in order, records completion packets, routes write work through independent verification, and proves the final graph state from the ledger alone.

### 2. Independent verification completion path

**Status: partially implemented.**

Worker completion correctly stops at `verifying`, which is the safe behavior. The remaining bounded requirement is an explicit verifier claim/result path that proves a different worker can accept or reject the result and that only successful independent verification permits integration/terminal progression. The writer must not be eligible to verify its own write task.

### 3. Retry/backoff and blocked-state behavior

**Status: partial evidence.**

Attempts, lease recovery, failed/partial requeue, and blocked dispatch are represented. Add deterministic tests for max-attempt exhaustion and retry/backoff timing/state so a repeatedly failing worker cannot hot-loop forever.

### 4. Duplicate follow-up prevention

**Status: not established by the inspected dry-run evidence.**

Add a stable follow-up identity/deduplication test proving repeated processing of the same completion packet cannot create duplicate successor tasks.

### 5. GitHub Issue/PR synchronization adapter

**Status: not acceptance-proven.**

Implement only a disabled/dry-run synchronization surface at this stage. Tests should prove that proposed issue/PR mutations are rendered as auditable intents while external writes remain disabled by default.

### 6. Provider adapters

**Status: design-only/disabled requirement remains.**

Codex/Cursor/ChatGPT worker adapters should remain disabled until the canonical Guardian runtime gate is cleared. A provider-neutral interface and deterministic fake adapter are sufficient for AUTOPILOT-004 testing; no credentials or live provider calls are required.

## Recommended next bounded task

Implement the **independent verifier lifecycle** first, on a new isolated child branch, because the synthetic graph acceptance test depends on it. Minimum proof:

1. writer claims and submits a valid completion;
2. task enters `verifying` and writer lease is released;
3. a distinct verifier is selected/claimed;
4. verifier acceptance advances the task to its allowed post-verification state;
5. verifier rejection returns the task to a safe retry/blocked state with evidence;
6. writer cannot verify its own write;
7. all transitions remain ledger-auditable and deterministic;
8. no external provider/runtime is enabled.

## Handoff

This audit is intentionally documentation-only. It changes no runtime behavior and grants no authority. The next implementer should use this file as the acceptance checklist, create a fresh isolated branch from the verified AUTOPILOT-004 foundation, and leave executable tests plus a completion handoff. Integration remains subject to independent CI/review and the existing local-archive/runtime gates.
