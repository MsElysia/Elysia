# Phase 1d-B.1 — dry-run decision trace baseline

**Date:** 2026-05-28  
**Milestone:** Phase 1d-B.1 dry-run decision trace  
**Implementation commit:** `e19c28e` — `feat(autonomy): add dry-run decision trace`

This baseline records the clean-HEAD implementation of the Phase 1 dry-run decision trace. It does **not** authorize real autonomy or live execution.

---

## Changed implementation files

- `project_guardian/autonomy_dry_run_guard.py`
- `project_guardian/tests/test_dry_run_autonomy_phase1_contract.py`

No `project_guardian/core.py` or `elysia/api/server.py` hunks were staged. No config changes.

---

## What was added

- New result field: **`decision_trace`** on the Phase 1 dry-run result.
- Helpers:
  - `build_dry_run_decision_trace(...)` — builds the serializable, observation-only trace.
  - `_classify_proposed_action_kind(...)` — side-effect-free coarse action-kind classification.
- Wired only into the existing Phase 1 dry-run path (`_autonomy_phase1_dry_run`), in both the normal proposal return and the `max_cycles_per_request` early return.

---

## Required trace fields

| Field | Meaning |
|-------|---------|
| `trace_id` | Unique id for this trace record |
| `timestamp` | ISO-8601 UTC creation time |
| `source` | Entry source (e.g. `run_autonomous_cycle`) |
| `cycle_id` | Dry-run cycle id |
| `proposed_action` | Raw proposed action string |
| `proposed_action_kind` | Coarse classification |
| `proposed_action_summary` | Truncated human label |
| `dry_run` | Always `true` in Phase 1 |
| `executed` | Always `false` in Phase 1 |
| `block_reasons` | Guard/policy reasons |
| `live_execution_guard` | Compact guard metadata |
| `capability_called` | Always `false` in Phase 1 |
| `mutation_called` | Always `false` in Phase 1 |
| `proposal_implementation_called` | Always `false` in Phase 1 |
| `legacy_executor_reached` | Always `false` in Phase 1 |
| `notes` | Optional free-text note |

---

## Execution invariants

- `dry_run=true`
- `executed=false`
- `capability_called=false`
- `mutation_called=false`
- `proposal_implementation_called=false`
- `legacy_executor_reached=false`

The trace is observation-only and must not influence action selection, scoring, routing, or execution.

---

## Verified gates

| Gate | Result |
|------|--------|
| Targeted dry-run contract tests | **25 passed, 3 warnings** |
| Safe-stack smoke | **411 passed, 3 warnings** |
| Full collection (Cursor) | **441 tests collected** |
| Full collection (Codex) | **400 tests collected in 9.53s** (clean temp worktree) |

**Collection count mismatch** (441 vs 400) remains documented as environment/path/discovery-dependent unless separately investigated (see `docs/PHASE1C2_COLLECTION_REPAIR_BASELINE.md`). The safe-stack smoke count rose 408 → 411 because three new decision-trace contract tests were added to the already-included Phase 1 contract file.

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

**PASS** for Phase 1d-B.1 implementation baseline.
