# Phase 1d-D.1 — bounded dry-run batch runner baseline

**Date:** 2026-05-29  
**Milestone:** Phase 1d-D.1 bounded dry-run batch runner  
**Implementation commit:** `2c2cb86` — `feat(autonomy): add bounded dry-run batch runner`

This baseline records the clean-HEAD implementation of the bounded dry-run batch runner. It does **not** authorize real autonomy or live execution.

---

## Changed implementation files

- `project_guardian/autonomy_dry_run_guard.py`
- `project_guardian/tests/test_dry_run_autonomy_phase1_contract.py`

No `project_guardian/core.py` or `elysia/api/server.py` hunks were staged. No config changes.

---

## What was added

- Helper: **`run_phase1_dry_run_batch(run_cycle, *, max_cycles=3, requested_cycles=3, persist=False) -> dict`**
- Support helpers:
  - `DryRunBatchSafetyError`
  - `_inspect_dry_run_cycle`

### Required batch result fields

| Field | Meaning |
|-------|---------|
| `batch_id` | Unique id for this batch run |
| `started_at` | ISO-8601 UTC start time |
| `completed_at` | ISO-8601 UTC completion time |
| `requested_cycles` | Cycles requested |
| `completed_cycles` | Cycles actually run |
| `all_dry_run` | True iff every cycle had `dry_run=true` |
| `any_executed` | True iff any cycle executed (must be false) |
| `execution_call_count` | Guarded execution attempts (always 0) |
| `legacy_fallback_reached` | True iff legacy executor reached (must be false) |
| `reports` | Per-cycle `dry_run_report` objects (deep-copied) |
| `summary` | Aggregated rollup |
| `warnings` | Non-fatal anomalies |

---

## Behavior

- helper-only
- injected `run_cycle` callable
- does not import/construct `GuardianCore`
- bounded for-loop only
- no background loop
- no retry loop
- no daemon
- no server route
- no persistence
- `persist=True` ignored with warning `persistence_not_implemented_ignored`
- JSON-serializable result
- non-mutating; reports are deep-copied (input cycle results not modified)

---

## Fail-closed conditions

The runner raises `DryRunBatchSafetyError` (running 0 cycles for input validation) when:

- `run_cycle` not callable
- invalid `requested_cycles` (non-int)
- `requested_cycles < 0`
- `requested_cycles > max_cycles`
- missing `dry_run_report`
- `executed=true`
- `dry_run!=true`
- `legacy_executor_reached=true`
- `capability_called=true`
- `mutation_called=true`
- `proposal_implementation_called=true`

`requested_cycles=0` returns a valid empty batch result without invoking `run_cycle`.

---

## Verified gates

| Gate | Result |
|------|--------|
| Targeted dry-run contract tests | **44 passed, 3 warnings** |
| Safe-stack smoke | **430 passed, 3 warnings** |
| Full collection (Cursor) | **441 tests collected** |
| Full collection (Codex) | **400 tests collected in 9.09s** (clean temp worktree) |

**Collection count mismatch** (441 vs 400) remains documented as environment/path/discovery-dependent unless separately investigated (see `docs/PHASE1C2_COLLECTION_REPAIR_BASELINE.md`). The safe-stack smoke count rose 419 → 430 because eleven new batch-runner contract tests were added to the already-included Phase 1 contract file.

---

## Safety statements

- **No real autonomy run.**
- **No live execution run.**
- **No tools/capabilities/mutation/proposal implementation/WebScout/browser activity.**
- **No scoring/action-selection/archetype/legacy-harvest/server-route changes.**
- `project_guardian/core.py` and `elysia/api/server.py` remained dirty/unstaged.
- `config/autonomy.json`: **enabled=false** (unchanged).
- Phase 1 autonomy remains dry-run only; `dry_run_only:false` remains ignored/blocked.

---

## Final verdict

**PASS** for Phase 1d-D.1 implementation baseline.
