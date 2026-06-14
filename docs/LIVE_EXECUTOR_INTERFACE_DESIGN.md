# Live Executor Interface Design

**Milestone:** Design/specification only — **no implementation**  
**Date:** 2026-06-14  
**Status:** Interface designed — **executor not implemented, disabled by default**

**Related docs:** [`HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md`](HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md), [`PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`](PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md), [`LIVE_MODE_READINESS_POST_REPAIR_UPDATE.md`](LIVE_MODE_READINESS_POST_REPAIR_UPDATE.md), [`UI_API_APPROVAL_ROUTE_DESIGN.md`](UI_API_APPROVAL_ROUTE_DESIGN.md)

**Starting checkpoint:** `baeeba3 docs(autonomy): define harmless live action smoke`

---

## 1. Purpose

Define the **future** live executor boundary — the single runtime component that may perform allowlisted live actions **only after** all passive Phase 2 scaffolding has validated an approval packet.

The executor must later be:

- **Tiny** — one action per invocation; harmless smoke first
- **Allowlisted** — fixed action categories; deny by default
- **Auditable** — audit record exists before and after execution attempt
- **Rollback-aware** — rollback plan validated before execution
- **Local-only** — isolated temp workspace writes only (initial scope)
- **Disabled by default** — no execution without explicit future enablement flags

This document does **not** implement the executor, add API routes, run live actions, or enable autonomy.

---

## 2. Non-goals

This milestone and the future executor **do not**:

- Enable autonomy or modify `config/autonomy.json`
- Add UI/API approval routes
- Implement file-writing live actions now
- Verify harmless smoke now
- Wire into `project_guardian/core.py`, `elysia/api/server.py`, or autonomy loops
- Support network, shell, browser, mutation, memory cleanup, or config changes
- Mark limited live mode ready
- Replace Safe Observer dry-run as the verified runtime mode

---

## 3. Executor must be disabled by default

| Gate | Default | Notes |
|------|---------|-------|
| `config/autonomy.json` → `enabled` | **`false`** | Autonomous loops must not invoke executor |
| Future `live_executor.enabled` (config or env) | **`false`** | Separate explicit flag; not added in this milestone |
| `execution_permitted` on approval packet | **`false`** | Passive build always false until operator approves |
| Operator decision | **none / deny** | `APPROVE` required per invocation |
| Harmless smoke verified | **`false`** | `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED=false` |

**Fail-closed rule:** If any gate is false or missing → return `EXECUTOR_DISABLED` (or more specific failure) with **zero side effects**.

The executor module must not be importable in a way that auto-executes on load. No background threads, no hooks into `run_once`, autonomy, or capability execution.

---

## 4. Required inputs

Future `execute_live_action(...)` (name TBD) must receive **all** of the following. Omission of any field → deny without execution.

| Input | Type / source | Requirement |
|-------|---------------|-------------|
| `approval_packet_id` | UUID string | From `LiveActionApprovalPacket.packet_id` |
| `operator_decision_id` | UUID string | From operator decision record |
| `action_category` | enum / string | Must match allowlisted harmless smoke category |
| `action_id` | string | e.g. `harmless_live_smoke_v1` |
| `target_path` | relative path | Workspace-relative only: `live_smoke_workspace/approved_smoke.txt` |
| `workspace_root` | absolute path | Isolated temp dir; validated inside executor |
| `expected_content_hash` | SHA-256 hex | Must match planned write bytes |
| `rollback_plan_id` | string | Links to `LiveActionRollbackPlan.action_id` |
| `audit_record_id` | string | Pre-execution audit record must exist |
| `dry_run_trace_id` | UUID string | Fresh Safe Observer / dry-run trace proving blocked-not-executed cycle completed |

Optional correlation fields (recommended):

- `request_id`, `packet_mode`, `operator_identity`

---

## 5. Required preconditions

All must pass **before** any filesystem or runtime side effect:

### Config and enablement

1. `config/autonomy.json` → `enabled=false` does **not** permit autonomous execution; executor is never called from autonomy loop while disabled
2. Future `live_executor.enabled` must be **`true`** explicitly (separate milestone)
3. `execution_permitted=true` only after operator `APPROVE` on valid packet

### Passive scaffolding validation (already implemented)

4. `validate_live_action_request()` → not blocked; requires approval or allowed per policy
5. `build_live_action_approval_packet()` → `ready_for_operator_review=true` for smoke
6. Operator decision → **`APPROVE`** (not `deny`, not `request_changes`)
7. `validate_live_action_rollback_plan()` → `valid=true`, `availability=AVAILABLE`
8. Audit record created and retrievable by `audit_record_id`

### Harmless smoke constraints

9. Action must be allowlisted as **harmless smoke** (`harmless_live_smoke_v1` / `HARMLESS_LIVE_SMOKE`)
10. `target_path` must resolve **inside** `{workspace_root}/live_smoke_workspace/`
11. **No repo-root paths** — workspace must not be project root or subdirectory of repo without isolation guard
12. **No user data paths** — reject home, Documents, Downloads, etc.
13. **No external storage paths** — reject paths from `external_storage.json` resolution
14. Path must not contain `..`, symlinks escaping workspace, or absolute paths outside workspace
15. Content write must match `expected_content_hash` exactly (bytes `ELYSIA_APPROVED_LIVE_SMOKE\n`)

### Trace and audit

16. `dry_run_trace_id` must reference a recent blocked-not-executed dry-run record
17. Audit record must exist **before** execution with status `APPROVED` or equivalent
18. Rollback plan must exist **before** execution

---

## 6. Prohibited actions

Executor must **refuse** (fail-closed) these categories unconditionally in initial implementation:

| Prohibited | Executor response |
|------------|-------------------|
| Network | `ACTION_NOT_ALLOWLISTED` |
| Shell / subprocess | `ACTION_NOT_ALLOWLISTED` |
| Browser / WebScout | `ACTION_NOT_ALLOWLISTED` |
| API calls | `ACTION_NOT_ALLOWLISTED` |
| Mutation / proposal implementation | `ACTION_NOT_ALLOWLISTED` |
| Runtime memory cleanup | `ACTION_NOT_ALLOWLISTED` |
| Config changes | `ACTION_NOT_ALLOWLISTED` |
| Repo-root writes | `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| User data writes | `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| External storage writes | `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| Multi-file writes | `ACTION_NOT_ALLOWLISTED` (smoke = single file only) |
| Writes without approval | `APPROVAL_MISSING` / `OPERATOR_DECISION_NOT_APPROVED` |

---

## 7. Future execution result schema

Passive-serializable result returned by executor (no execution in this milestone):

```json
{
  "status": "EXECUTION_SUCCEEDED",
  "action_id": "harmless_live_smoke_v1",
  "approval_packet_id": "<uuid>",
  "operator_decision_id": "<uuid>",
  "target_path": "live_smoke_workspace/approved_smoke.txt",
  "workspace_root": "<absolute-tmp-path>",
  "before_hash": "<sha256-or-null-if-created>",
  "after_hash": "<sha256>",
  "rollback_plan_id": "harmless_live_smoke_v1",
  "audit_record_id": "<uuid>",
  "dry_run_trace_id": "<uuid>",
  "executed_at": "2026-06-14T12:00:00+00:00",
  "executed": true,
  "dry_run": false,
  "safety_verdict": "EXECUTION_SUCCEEDED",
  "failure_code": null,
  "detail": null
}
```

### Status values

| `status` | Meaning |
|----------|---------|
| `EXECUTION_SUCCEEDED` | Single allowed write completed; hashes recorded |
| `EXECUTION_FAILED` | Attempted but write/audit update failed |
| `EXECUTION_DENIED` | Preconditions failed; no write attempted |
| `EXECUTOR_DISABLED` | Executor or live-executor flag off |

### `safety_verdict` values

- `EXECUTION_SUCCEEDED`
- `EXECUTION_FAILED`
- `EXECUTION_DENIED`
- `EXECUTOR_DISABLED`

---

## 8. Failure modes

| Code | When | Side effects |
|------|------|--------------|
| `EXECUTOR_DISABLED` | `live_executor.enabled=false` or module not enabled | None |
| `APPROVAL_MISSING` | Packet id invalid or packet not found | None |
| `OPERATOR_DECISION_NOT_APPROVED` | Decision missing, deny, or request_changes | None |
| `ACTION_NOT_ALLOWLISTED` | Category/action_id not in harmless smoke allowlist | None |
| `TARGET_OUTSIDE_SMOKE_WORKSPACE` | Path escapes workspace, repo root, user data, external storage | None |
| `AUDIT_MISSING` | `audit_record_id` not found or incomplete | None |
| `ROLLBACK_PLAN_MISSING` | Plan invalid or `availability != AVAILABLE` | None |
| `CONTENT_HASH_MISMATCH` | Planned bytes ≠ `expected_content_hash` | None |
| `DRY_RUN_TRACE_INVALID` | Trace missing or indicates execution occurred | None |
| `WORKSPACE_NOT_ISOLATED` | Workspace root overlaps repo root | None |

All failure modes must append or update audit with `executed=false`, `blocked=true` when audit path is explicit.

---

## 9. Required tests before implementation

Future test module (e.g. `project_guardian/tests/test_live_executor_interface.py`) — **not created in this milestone**:

| Test | Asserts |
|------|---------|
| `test_executor_disabled_by_default` | Call without enable flag → `EXECUTOR_DISABLED`, no writes |
| `test_executor_denies_without_approve` | Deny decision → no write |
| `test_executor_denies_repo_root_target` | Repo path → `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| `test_executor_denies_hash_mismatch` | Wrong hash → `CONTENT_HASH_MISMATCH` |
| `test_executor_denies_missing_audit` | No audit → `AUDIT_MISSING` |
| `test_executor_denies_missing_rollback` | Invalid plan → `ROLLBACK_PLAN_MISSING` |
| `test_executor_accepts_harmless_smoke_happy_path` | Approved smoke in tmp workspace → single file, correct hash |
| `test_executor_does_not_touch_autonomy_config` | `config/autonomy.json` unchanged |
| `test_executor_prohibited_categories` | Network/shell/browser requests denied |
| `test_executor_result_schema` | Result dict matches §7 fields |

Pre-implementation gate: default runtime suite clean (**439 passed, 0 failed, 11 skipped** at `623ce00` / post-repair).

---

## 10. Readiness impact

| Check | Status |
|-------|--------|
| `ready_for_limited_live_mode` | **`false`** |
| `status` | **`BLOCKED`** |
| `LIVE_EXECUTOR_IMPLEMENTED` | **`false`** — design only; implementation future |
| `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED` | **`false`** — unchanged |
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | **`false`** — unchanged |
| `AUTONOMY_CONFIG_DEFAULT_DISABLED` | **`true`** — by design |

This document satisfies **interface design** only. Readiness blocker `LIVE_EXECUTOR_IMPLEMENTED` remains active until a future milestone implements and tests the executor behind `live_executor.enabled=false` default.

---

## 11. Safety statement

- **No live executor implemented**
- **No live action run**
- **No API/server route added**
- **No execution code added**
- **No rollback execution code added**
- **No autonomy enabled** — `config/autonomy.json` → `"enabled": false`
- **Limited live mode remains BLOCKED**

---

## Appendix: Interface flow (design only)

```
                    ┌─────────────────────────┐
                    │  Safe Observer dry-run   │
                    │  (blocked, trace id)     │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │ validate_live_action_    │
                    │ request()                │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │ build_live_action_       │
                    │ approval_packet()        │
                    │ execution_permitted=false│
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │ Operator APPROVE         │
                    │ (future UI/API route)    │
                    │ see UI_API_APPROVAL_     │
                    │ ROUTE_DESIGN.md          │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │ Audit + rollback valid   │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │ live_executor.enabled?   │──no──► EXECUTOR_DISABLED
                    └───────────┬─────────────┘
                                │ yes
                    ┌───────────▼─────────────┐
                    │ execute_live_action()    │
                    │ (FUTURE — not implemented)│
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │ Result schema §7         │
                    │ + audit update           │
                    │ + rollback available     │
                    └─────────────────────────┘
```

Steps involving `execute_live_action()` are **out of scope** for this milestone.
