# Approval Route Executor Wiring Plan

**Milestone:** Documentation-only — **no wiring, no execution**  
**Date:** 2026-05-30  
**Status:** Plan complete — **approval route not wired, readiness BLOCKED**

**Starting checkpoint:** `49eb0b0 fix(autonomy): update readiness after harmless smoke executor`

**Related docs:** [`LIVE_READINESS_AFTER_HARMLESS_SMOKE_EXECUTOR.md`](LIVE_READINESS_AFTER_HARMLESS_SMOKE_EXECUTOR.md), [`HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md`](HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md), [`PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md`](PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md), [`LIVE_EXECUTOR_IMPLEMENTATION_PLAN.md`](LIVE_EXECUTOR_IMPLEMENTATION_PLAN.md)

---

## 1. Purpose

Define the **exact** safety checks, route behavior, stop conditions, tests, audit separation, rollback rules, and verification criteria for a future milestone that wires the passive approval route to the harmless smoke executor.

This is the **last planning gate** before operator `APPROVE` may trigger an executor call. The plan ensures:

- Default behavior remains decision-only (no execution)
- Execution requires **three** independent enable flags
- Only harmless smoke action category may execute
- All writes remain inside isolated tmp smoke workspace
- Readiness stays **BLOCKED** until route-to-executor verification evidence is explicitly updated

This document does **not** wire the route, modify API/server code, change executor behavior, or enable autonomy.

---

## 2. Current verified state

| Property | Status |
|----------|--------|
| HEAD | `49eb0b0 fix(autonomy): update readiness after harmless smoke executor` |
| `LIVE_EXECUTOR_IMPLEMENTED` | `true` — harmless smoke executor exists; disabled by default |
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | `true` — verified in isolated tmp workspace under test flag |
| `HARMLESS_LIVE_ACTION_ROLLBACK_VERIFIED` | `true` — delete/restore verified for smoke target only |
| `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED` | `true` — passive scaffolding (recording only) |
| `APPROVAL_ROUTE_EXECUTION_WIRED` | `false` — route does not call executor |
| `APPROVAL_ROUTE_OPERATOR_ENABLED` | `false` — route env gate off by default |
| `ready_for_limited_live_mode` | `false` |
| Readiness `status` | `BLOCKED` |
| `config/autonomy.json` | `"enabled": false` (unchanged) |
| Approval route imports executor | **No** |
| APPROVE calls executor | **No** |
| Non-test live execution | **None** |

**Remaining blockers:**

- `APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR`
- `APPROVAL_ROUTE_DEFAULT_DISABLED`

---

## 3. Non-goals

This plan and the future implementation milestone must **not**:

| Non-goal | Rationale |
|----------|-----------|
| Enable autonomy | `config/autonomy.json` stays `enabled=false` |
| Modify `project_guardian/core.py` | Runtime autonomy loop stays isolated |
| Modify `elysia/api/server.py` beyond thin delegation (if any) | Server remains passive delegate; no new execution paths in server layer |
| Add shell/subprocess/network/browser/API/mutation | Out of scope for harmless smoke |
| Write outside isolated tmp smoke workspace | Path validation enforced |
| Write to repo root / user data / external storage | Blocked by `validate_harmless_smoke_paths()` |
| Auto-rollback after successful execution | Rollback is explicit future operation only |
| Mark `ready_for_limited_live_mode=true` | Requires separate readiness evidence update |
| Remove `APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR` blocker without verification | Evidence update is a later milestone |
| Execute on DENY / REQUEST_CHANGES / CANCEL / EXPIRE | Decision-only for non-APPROVE |
| Execute without both executor and route-to-executor flags | Triple-gate required |

---

## 4. Exact future route behavior

### Decision-only mode (default)

When any execution gate is off, `record_operator_decision_for_packet()` behavior is **unchanged**:

- Records operator decision append-only
- Returns `executor_called=false`, `executed=false`, `execution_permitted=false`
- No filesystem writes
- `safety_verdict` remains `APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED` for APPROVE

### Execution mode (future, explicit opt-in only)

When **all** preconditions pass (see §6), `APPROVE` may call `execute_live_action()` **once** per decision:

1. Record operator decision (append-only decision audit) — **first**
2. Build `LiveActionExecutionRequest` from packet + decision + workspace context
3. Call `execute_live_action(request)` — **only if** triple-gate satisfied
4. Append separate execution audit record (see §9)
5. Return combined response with decision + execution fields (see §8)

### Mode coexistence

The route must support **both** modes indefinitely:

| Mode | When | APPROVE behavior |
|------|------|------------------|
| Decision-only | Default; any gate off | Record only |
| Execution | All gates on + all preconditions | Record + optional executor call |

`DENY`, `REQUEST_CHANGES`, `CANCEL`, `EXPIRE` always use decision-only mode.

---

## 5. Required future flags

Three **independent** environment flags. All must be truthy (`1`, `true`, `yes`, `on`) for execution:

| Flag | Default | Module | Purpose |
|------|---------|--------|---------|
| `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED` | **false** (unset) | `live_action_approval_route.py` | Route handlers reachable at all |
| `ELYSIA_LIVE_EXECUTOR_ENABLED` | **false** (unset) | `live_action_executor.py` | Executor may write when called |
| `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` | **false** (unset) | `live_action_approval_route.py` (new) | Route may call executor on APPROVE |

### Flag interaction matrix

| Route | Executor | Executes smoke | APPROVE outcome |
|-------|----------|----------------|-----------------|
| off | * | * | `403 APPROVAL_ROUTE_DISABLED` |
| on | off | off | Decision recorded; `executor_called=false` |
| on | on | off | Decision recorded; `executor_called=false` |
| on | off | on | Decision recorded; executor not called or returns `EXECUTOR_DISABLED` if called — **design: do not call executor when executor flag off** |
| on | on | on | Decision recorded; executor called if preconditions pass |

**Design choice:** When `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE=true` but `ELYSIA_LIVE_EXECUTOR_ENABLED=false`, route records decision and sets `executor_called=false` (does **not** invoke executor). This avoids leaking executor-disabled internals through route responses.

### Test enablement

Tests enable flags via `monkeypatch.setenv()` only inside isolated tmp workspace fixtures. Never set flags globally in production defaults.

---

## 6. Required preconditions before route may call executor

All must pass **before** `execute_live_action()` is invoked:

| # | Precondition | Enforced by |
|---|--------------|-------------|
| 1 | `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED=true` | `is_live_action_approval_route_enabled()` |
| 2 | `ELYSIA_LIVE_EXECUTOR_ENABLED=true` | `is_live_executor_enabled()` |
| 3 | `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE=true` | New `is_approval_route_executes_smoke_enabled()` |
| 4 | Approval packet exists and is valid | Route store + packet schema |
| 5 | Packet not expired | `is_packet_expired()` / route expiry check |
| 6 | `packet_content_hash` matches canonical hash | `compute_packet_content_hash()` |
| 7 | Operator decision is `APPROVE` | `OperatorDecisionKind.APPROVE` |
| 8 | Action category is `harmless_live_smoke` only | Packet `action_category` + executor allowlist |
| 9 | `action_id` is `harmless_live_smoke_v1` | Executor validation |
| 10 | `target_path` is `live_smoke_workspace/approved_smoke.txt` | Executor validation |
| 11 | `expected_content_hash` matches `compute_harmless_smoke_content_hash()` | Executor validation |
| 12 | Target path under isolated tmp smoke workspace | `validate_harmless_smoke_paths(workspace_root, repo_root)` |
| 13 | Rollback metadata present (`rollback_plan_id` non-empty) | Packet + executor validation |
| 14 | Audit preview present (`audit_record_id` or generated preview id) | Packet + route audit builder |
| 15 | `workspace_root` supplied and isolated (test-provided tmp path) | Route must require explicit workspace in packet or decision context |

If any precondition fails: record decision (if valid decision), do **not** call executor, return `executor_called=false`.

---

## 7. Required route behavior by decision type

| Decision | Record decision | Call executor | Write file |
|----------|-----------------|---------------|------------|
| `APPROVE` (gates on + preconditions pass) | Yes | Yes | Yes (exact smoke file only) |
| `APPROVE` (any gate off) | Yes | No | No |
| `APPROVE` (precondition fail) | Yes | No | No |
| `DENY` | Yes | No | No |
| `REQUEST_CHANGES` | Yes | No | No |
| `CANCEL` / `CANCELLED` | Yes | No | No |
| `EXPIRE` / `EXPIRED` | Yes | No | No |

### Hard refusal cases (never call executor)

| Condition | Route behavior |
|-----------|----------------|
| Packet expired before decision | Reject or record EXPIRED; no executor |
| `packet_content_hash` mismatch | `403 PACKET_HASH_MISMATCH`; no executor |
| Unsafe target path | No executor; `execution_permitted=false` |
| Non-smoke action category | No executor; decision may still record with execution blocked |
| Missing workspace_root | No executor |
| Duplicate terminal decision | `DECISION_ALREADY_RECORDED`; no executor |

---

## 8. Required response fields

Every `record_operator_decision_for_packet` response must include:

| Field | Type | Decision-only | Execution |
|-------|------|---------------|-------------|
| `decision` | string | Recorded value | Recorded value |
| `decision_recorded` | bool | `true` | `true` |
| `executor_called` | bool | `false` | `true` if executor invoked |
| `execution_permitted` | bool | `false` | `true` only on executor success |
| `executed` | bool | `false` | `true` only on executor success |
| `execution_result` | object \| null | `null` | Present when `executor_called=true` |
| `rollback_result` | object \| null | `null` | Only in explicit rollback tests/helpers |
| `safety_verdict` | string | `APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED` | `EXECUTION_SUCCEEDED` or denial verdict |
| `approval_packet_id` | string | Present | Present |
| `operator_decision_id` | string | Present | Present |

`execution_result` shape mirrors `serialize_live_action_execution_result()`:

- `status`, `before_hash`, `after_hash`, `target_path`, `failure_code`, `rollback_summary`, etc.

---

## 9. Required audit behavior

### Decision audit (unchanged)

- Append-only store write via `build_operator_decision_audit_update()`
- Records operator id, decision, reason, timestamp, packet hash binding
- Written **before** any executor call

### Execution audit (new, separate)

- New append-only record type: `execution_audit`
- Written **after** executor returns (success or denial)
- Must reference:
  - `approval_packet_id`
  - `operator_decision_id`
  - `execution_result.status`
  - `before_hash` / `after_hash` (if applicable)
- Must **not** overwrite or mutate decision audit records

### Trail endpoint

`get_approval_decision_trail()` returns decision records; future milestone may add execution audit entries as separate trail items with `record_type: execution`.

---

## 10. Required rollback behavior

| Rule | Detail |
|------|--------|
| No auto-rollback | Route must **not** rollback after successful APPROVE execution |
| Explicit rollback only | `rollback_harmless_smoke_write()` called by test helper or future explicit rollback endpoint |
| Target limit | `live_smoke_workspace/approved_smoke.txt` only |
| Strategies | Delete created file OR restore `prior_content` |
| Route response | `rollback_result` only populated in rollback-specific tests, not in normal APPROVE flow |

---

## 11. Required tests before implementation

All tests run under isolated `tmp_path` smoke workspace. No repo-root writes.

### Gate tests (no execution)

| # | Test | Expected |
|---|------|----------|
| 1 | Default route APPROVE (all flags off) | Decision recorded; `executor_called=false`; no file |
| 2 | Route on, `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE=false` | Decision recorded; no executor call |
| 3 | Route on, executor flag off, executes-smoke on | Decision recorded; `executor_called=false`; no file |
| 4 | Both execution flags on, executor off | No executor call (design choice §5) |

### Negative decision tests

| # | Test | Expected |
|---|------|----------|
| 5 | DENY | `executor_called=false`; no file |
| 6 | REQUEST_CHANGES | `executor_called=false`; no file |
| 7 | CANCEL | `executor_called=false`; no file |
| 8 | EXPIRE / expired packet | `executor_called=false`; no file |

### Validation failure tests

| # | Test | Expected |
|---|------|----------|
| 9 | Expired packet APPROVE | No executor; no file |
| 10 | Hash mismatch | No executor; no file |
| 11 | Unsafe target | No executor; no file |
| 12 | Non-smoke action category | No executor; no file |

### Success path tests (all three flags on)

| # | Test | Expected |
|---|------|----------|
| 13 | Valid APPROVE | `executor_called=true`, `executed=true`; exact file content |
| 14 | File is only artifact in workspace | Single `approved_smoke.txt` |
| 15 | `execution_result` populated | Contains before/after hash |
| 16 | Decision audit + execution audit separate | Both present in trail |

### Rollback tests

| # | Test | Expected |
|---|------|----------|
| 17 | Rollback deletes created file | Target removed |
| 18 | Rollback restores prior content | Exact bytes restored |
| 19 | Rollback rejects unsafe target | No repo writes |

### Safety isolation tests

| # | Test | Expected |
|---|------|----------|
| 20 | No repo-root files created | `ROOT/approved_smoke.txt` absent |
| 21 | Approval route AST: no forbidden imports when wired | No subprocess/mutation/core |
| 22 | Readiness remains BLOCKED after wiring tests | Until evidence milestone |

### Test modules (planned additions)

- `project_guardian/tests/test_live_action_approval_route_executor_wiring.py` (new)
- Updates to `test_live_action_approval_route.py`, `test_live_action_passive_smoke_approval_flow.py`

---

## 12. Stop conditions

**Abort implementation immediately** if any of:

| # | Stop condition |
|---|----------------|
| 1 | Approval route executes by default (any flag unset still writes) |
| 2 | Route executes without **both** `ELYSIA_LIVE_EXECUTOR_ENABLED` and `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` true |
| 3 | DENY, REQUEST_CHANGES, CANCEL, or EXPIRE calls executor |
| 4 | Expired or hash-mismatched packet calls executor |
| 5 | Any write outside isolated tmp smoke workspace |
| 6 | Any write to repo root, user data, or external storage |
| 7 | `config/autonomy.json` modified or autonomy enabled |
| 8 | `project_guardian/core.py` or runtime autonomy loop wired |
| 9 | Shell, subprocess, network, browser, API, or mutation introduced |
| 10 | Generated runtime artifacts staged in commit |
| 11 | `ready_for_limited_live_mode` set true without explicit readiness milestone |
| 12 | `APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR` blocker removed without verification evidence |

---

## 13. Verification plan (post-implementation)

Run in order after future wiring milestone:

| Step | Command | Pass criteria |
|------|---------|---------------|
| 1 | `pytest project_guardian/tests/test_live_action_approval_route_executor_wiring.py -q` | All pass |
| 2 | `pytest project_guardian/tests/test_live_action_approval_route.py -q` | All pass |
| 3 | `pytest project_guardian/tests/test_live_action_executor.py -q` | All pass |
| 4 | `pytest project_guardian/tests/test_live_action_passive_smoke_approval_flow.py -q` | All pass |
| 5 | `pytest tests/test_elysia_api_approval_implementation.py tests/test_approval_store_smoke.py -q` | All pass |
| 6 | `pytest project_guardian/tests/test_live_action_readiness.py -q` | BLOCKED until evidence update |
| 7 | Passive Phase 2 targeted suite (10 modules) | All pass |
| 8 | `python scripts/run_elysia_dry_run_report.py --mode real-planning` | SAFE, `any_executed: false` |
| 9 | `python scripts/run_elysia_dry_run_report.py --mode real-planning --json` | `"safe": true` |
| 10 | `python scripts/run_safe_stack_smoke_tests.py` | All pass |
| 11 | `pytest --collect-only -q` | 450+ collected |
| 12 | Full runtime (optional) | 439 passed baseline or better |

---

## 14. Readiness impact

| Item | This plan milestone | Future wiring milestone | Future evidence milestone |
|------|---------------------|-------------------------|---------------------------|
| `APPROVAL_ROUTE_EXECUTION_WIRED` | `false` (unchanged) | `true` after verified wiring | — |
| `APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR` blocker | **Remains** | Removed only after evidence update | Explicit commit |
| `ready_for_limited_live_mode` | `false` | `false` | `false` until all gates satisfied |
| `status` | `BLOCKED` | `BLOCKED` | `BLOCKED` until operator-enable + autonomy opt-in gates |

**This plan does not change readiness evidence or code.**

---

## 15. Safety statement

| Constraint | Status |
|------------|--------|
| Wiring implemented | **No** |
| Route execution on APPROVE added | **No** |
| Executor behavior changed | **No** |
| API/server code changed | **No** |
| Autonomy enabled | **No** |
| `config/autonomy.json` | **Unchanged** (`enabled=false`) |
| Shell / network / browser / API / mutation | **Absent** |
| Non-test live execution | **None** |

---

## Planned implementation sequence (future milestone)

1. Add `is_approval_route_executes_smoke_enabled()` and `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` gate
2. Add `_maybe_execute_harmless_smoke_after_approve()` private helper in `live_action_approval_route.py`
3. Import `execute_live_action` only inside helper (lazy import acceptable)
4. Build `LiveActionExecutionRequest` from packet fields + workspace context
5. Append execution audit record separately from decision audit
6. Extend response schema with `execution_result`
7. Add wiring tests per §11
8. Run verification plan §13
9. **Do not** update readiness evidence in wiring milestone — separate evidence commit after verification
