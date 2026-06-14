# Live Executor Implementation Plan

**Milestone:** Implementation plan only — **no executor code, no execution**  
**Date:** 2026-06-14  
**Status:** Plan complete — **executor not implemented, readiness BLOCKED**

**Starting checkpoint:** `f16ce23 test(autonomy): add passive harmless smoke approval flow`

**Related docs:** [`LIVE_EXECUTOR_INTERFACE_DESIGN.md`](LIVE_EXECUTOR_INTERFACE_DESIGN.md), [`PASSIVE_HARMLESS_SMOKE_APPROVAL_FLOW.md`](PASSIVE_HARMLESS_SMOKE_APPROVAL_FLOW.md), [`PASSIVE_HARMLESS_SMOKE_PACKET_GENERATION.md`](PASSIVE_HARMLESS_SMOKE_PACKET_GENERATION.md), [`HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md`](HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md), [`UI_API_APPROVAL_ROUTE_DESIGN.md`](UI_API_APPROVAL_ROUTE_DESIGN.md), [`PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md`](PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md)

---

## 1. Purpose

Define the **exact** implementation sequence, safety boundaries, tests, stop conditions, rollback requirements, and verification criteria for the future tiny live executor.

This is the **last planning gate** before any live execution capability is added. The plan ensures:

- Only one allowlisted action exists initially (harmless smoke file write)
- Executor is disabled by default with separate enable flag
- Approval route never auto-executes on `APPROVE`
- Rollback is tested before readiness evidence updates
- Readiness remains **BLOCKED** until executor disabled path, smoke verified, and rollback proven

This document does **not** implement the executor, run smoke, or enable autonomy.

---

## 2. Preconditions before implementation

All must be true **before** writing `project_guardian/live_action_executor.py`:

| # | Precondition | Status at plan time |
|---|--------------|---------------------|
| 1 | Passive Phase 2 scaffolding implemented (gate, packet, decision, audit, rollback) | **Done** |
| 2 | Passive approval route scaffolding implemented and tested | **Done** |
| 3 | Passive harmless smoke packet generation implemented | **Done** |
| 4 | Passive smoke approval flow verified end-to-end (no execution) | **Done** — `f16ce23` |
| 5 | `LIVE_EXECUTOR_INTERFACE_DESIGN.md` complete | **Done** |
| 6 | Default runtime suite clean | **439 passed, 0 failed, 11 skipped** at `623ce00` |
| 7 | Safe Observer passes with zero execution | **Verified** |
| 8 | `config/autonomy.json` → `enabled=false` | **Required; unchanged** |
| 9 | `project_guardian/core.py` and `elysia/api/server.py` not wired to executor | **Required** |
| 10 | Operator sign-off on implementation plan | **Future gate** |

---

## 3. Exact future module name and boundaries

### Module

```
project_guardian/live_action_executor.py
```

### Public surface (planned)

| Function | Responsibility |
|----------|----------------|
| `is_live_executor_enabled()` | Read `ELYSIA_LIVE_EXECUTOR_ENABLED` / config; default **false** |
| `execute_live_action(...)` | Single entry point; validate → write (if enabled) → audit → result |
| `execute_harmless_smoke_write(...)` | Internal; only path that touches filesystem |
| `rollback_harmless_smoke_write(...)` | Internal; delete created file or restore snapshot |
| `serialize_live_action_execution_result(...)` | Result schema per interface design |

### Boundaries

| In scope | Out of scope |
|----------|--------------|
| One file write in isolated tmp workspace | Network, shell, browser, API |
| Hash validation before write | Mutation/proposal implementation |
| Before/after hash capture | Runtime memory cleanup |
| Append execution audit (explicit path) | Config changes |
| Rollback metadata execution (smoke only) | Repo-root or user-data writes |
| Fail-closed when disabled | Autonomy loop integration |
| No import from `core.py`, `server.py` | Auto-execute on APPROVE route |

### Test module (planned)

```
project_guardian/tests/test_live_action_executor.py
```

AST/import guards must prove executor module does not import: `subprocess`, implementer, mutation engine, bounded browser, `requests`, `project_guardian.core`.

---

## 4. Explicitly allowed first action

**Only** this action may be implemented in milestone 1:

| Property | Value |
|----------|-------|
| Action ID | `harmless_live_smoke_v1` |
| Action kind | `harmless_live_smoke` |
| Category | `LOCAL_FILE_WRITE` (harmless smoke allowlist) |
| Workspace | `{isolated_tmp}/` — **not** repo root |
| Target | `live_smoke_workspace/approved_smoke.txt` |
| Content | `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF) |
| Write count | **One file only** per invocation |
| Create semantics | Create if missing; overwrite if exists with exact bytes |

No other action categories, paths, or content variants are permitted in milestone 1.

---

## 5. Explicitly prohibited actions

Executor must **refuse** (fail-closed, zero side effects) for:

| Prohibited | Failure code |
|------------|--------------|
| Network | `ACTION_NOT_ALLOWLISTED` |
| Shell / subprocess | `ACTION_NOT_ALLOWLISTED` |
| Browser / WebScout | `ACTION_NOT_ALLOWLISTED` |
| API calls | `ACTION_NOT_ALLOWLISTED` |
| Mutation / proposal implementation | `ACTION_NOT_ALLOWLISTED` |
| Runtime memory cleanup | `ACTION_NOT_ALLOWLISTED` |
| Config changes | `ACTION_NOT_ALLOWLISTED` |
| Repo-root writes | `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| User data writes (Documents/Downloads/Desktop) | `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| External storage writes | `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| Multi-file writes | `ACTION_NOT_ALLOWLISTED` |
| Writes without valid APPROVE + enable flag | `EXECUTOR_DISABLED` / `OPERATOR_DECISION_NOT_APPROVED` |

---

## 6. Required executor disabled-by-default flag

| Flag | Location | Default |
|------|----------|---------|
| `config/autonomy.json` → `enabled` | Existing | **`false`** — must remain false through executor milestone 1 |
| `ELYSIA_LIVE_EXECUTOR_ENABLED` | Env (planned) | **`false`** / unset |
| Future `config/live_executor.json` → `enabled` | Optional config file | **`false`** if added |

**Rules:**

- Executor module returns `EXECUTOR_DISABLED` when flag is false — **no filesystem touch**
- Approval route must **never** set `ELYSIA_LIVE_EXECUTOR_ENABLED` or call executor on `APPROVE`
- Autonomy loop must not import or call executor while `config/autonomy.json` disabled
- Two independent gates required for any write: `ELYSIA_LIVE_EXECUTOR_ENABLED=true` **and** valid approved packet

---

## 7. Required input validation

`execute_live_action()` must validate **all** before any write:

| Input / check | Source | Reject if missing/invalid |
|---------------|--------|---------------------------|
| Executor enabled | `is_live_executor_enabled()` | `EXECUTOR_DISABLED` |
| `approval_packet_id` | Approval store | `APPROVAL_MISSING` |
| `operator_decision_id` | Decision trail | `OPERATOR_DECISION_NOT_APPROVED` |
| Operator decision | Must be `APPROVE` | `OPERATOR_DECISION_NOT_APPROVED` |
| Packet hash match | `compute_packet_content_hash()` | `CONTENT_HASH_MISMATCH` |
| Packet not expired | `expires_at` | `PACKET_EXPIRED` |
| Action ID | `harmless_live_smoke_v1` | `ACTION_NOT_ALLOWLISTED` |
| Action category | Harmless smoke only | `ACTION_NOT_ALLOWLISTED` |
| `workspace_root` | Absolute isolated tmp | `WORKSPACE_NOT_ISOLATED` |
| `target_path` | Under `live_smoke_workspace/` | `TARGET_OUTSIDE_SMOKE_WORKSPACE` |
| `expected_content_hash` | Matches `ELYSIA_APPROVED_LIVE_SMOKE\n` | `CONTENT_HASH_MISMATCH` |
| Rollback plan | Valid, `AVAILABLE` | `ROLLBACK_PLAN_MISSING` |
| Audit record | Exists pre-execution | `AUDIT_MISSING` |
| `dry_run_trace_id` | Recent blocked dry-run | `DRY_RUN_TRACE_INVALID` |

Reuse existing validators: `validate_live_action_operator_decision`, `validate_harmless_smoke_paths`, `validate_live_action_rollback_plan`.

---

## 8. Required execution behavior

When **all** validations pass and executor is explicitly enabled (test-only initially):

1. **Snapshot** `before_hash` (null if file absent; SHA-256 if exists)
2. **Create** parent dir `live_smoke_workspace/` inside workspace only if needed
3. **Write** exactly `ELYSIA_APPROVED_LIVE_SMOKE\n` to `approved_smoke.txt`
4. **Compute** `after_hash` from written bytes
5. **Append** execution audit record to explicit `audit_path` only
6. **Return** result schema:

```json
{
  "status": "EXECUTION_SUCCEEDED",
  "action_id": "harmless_live_smoke_v1",
  "approval_packet_id": "<uuid>",
  "operator_decision_id": "<uuid>",
  "target_path": "live_smoke_workspace/approved_smoke.txt",
  "workspace_root": "<absolute-tmp>",
  "before_hash": "<sha256-or-null>",
  "after_hash": "<sha256>",
  "rollback_plan_id": "harmless_live_smoke_v1",
  "audit_record_id": "<uuid>",
  "dry_run_trace_id": "<uuid>",
  "executed_at": "<iso-utc>",
  "executed": true,
  "dry_run": false,
  "execution_permitted": true,
  "executor_called": true,
  "safety_verdict": "EXECUTION_SUCCEEDED"
}
```

**Note:** `execution_permitted=true` and `executed=true` appear **only** in executor result after explicit enablement — never in approval route responses.

On any validation failure: `executed=false`, no write attempted, audit records denial.

---

## 9. Required rollback behavior

Rollback function `rollback_harmless_smoke_write(...)` (planned):

| Pre-smoke state | Strategy | Action |
|-----------------|----------|--------|
| File did not exist | `DELETE_CREATED_FILE` | Delete `approved_smoke.txt` |
| File existed with baseline | `FILE_RESTORE` | Restore from `backup_path` snapshot |

**Rollback test requirements:**

1. Post-smoke: file exists with exact marker content
2. Post-rollback: file absent (create case) or baseline restored (update case)
3. No other files created or modified in workspace
4. Rollback audit line appended with `ROLLBACK_SUCCEEDED` or `ROLLBACK_FAILED`
5. Rollback must not touch paths outside `workspace_root`

Rollback execution is a **separate test milestone** after forward write is proven; not combined with approval route.

---

## 10. Required tests before any readiness upgrade

Future `project_guardian/tests/test_live_action_executor.py`:

| Test | Asserts |
|------|---------|
| `test_executor_disabled_writes_nothing` | `EXECUTOR_DISABLED`, no file, `executed=false` |
| `test_unapproved_packet_writes_nothing` | No APPROVE → deny, no file |
| `test_expired_packet_writes_nothing` | `PACKET_EXPIRED`, no file |
| `test_hash_mismatch_writes_nothing` | `CONTENT_HASH_MISMATCH`, no file |
| `test_unsafe_target_writes_nothing` | Repo root / traversal → deny, no file |
| `test_approved_harmless_smoke_writes_one_tmp_file` | Exactly one file, exact bytes, correct hash |
| `test_rollback_deletes_created_file` | Post-rollback file absent |
| `test_rollback_restores_baseline` | Pre-existing file restored |
| `test_no_repo_root_file_created` | No writes under project root |
| `test_executor_import_graph_safe` | No shell/network/browser/mutation imports |
| `test_approval_route_does_not_call_executor` | APPROVE via route → `executor_called=false` |
| `test_readiness_blocked_until_smoke_verified` | Evidence unchanged until explicit milestone |

**Readiness upgrade gate:** `LIVE_EXECUTOR_IMPLEMENTED` and `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` may only flip to `true` after **all** executor tests pass with executor briefly enabled in test env only.

---

## 11. Stop conditions

**Immediately halt implementation** if any of these occur:

| Stop condition | Action |
|----------------|--------|
| Any file written outside tmp smoke workspace | Revert; fail milestone |
| Approval route calls executor on `APPROVE` | Revert; fail milestone |
| `config/autonomy.json` modified to `enabled=true` | Revert; fail milestone |
| Executor auto-runs on module import | Revert; fail milestone |
| Repo-root file created (e.g. `test.py`) | Revert; delete artifact; fail milestone |
| Generated runtime artifacts staged | Unstage; do not commit |
| Unexpected subprocess/network/browser call in executor path | Revert; fail milestone |
| Readiness marked READY without full test gate | Revert evidence change |
| `project_guardian/core.py` or `elysia/api/server.py` wired to executor | Revert; fail milestone |

---

## 12. Verification plan

### Milestone 1 implementation verification (future)

| Step | Command | Pass criteria |
|------|---------|---------------|
| 1 | `pytest project_guardian/tests/test_live_action_executor.py -q` | All pass; disabled-by-default tests green |
| 2 | `pytest project_guardian/tests/test_live_action_passive_smoke_approval_flow.py -q` | Still pass; route does not execute |
| 3 | `pytest project_guardian/tests/test_live_action_*.py` (Phase 2) | 131+ pass |
| 4 | `python scripts/run_elysia_dry_run_report.py --mode real-planning` | `SAFE`, `any_executed: False` (unless test explicitly enables) |
| 5 | `python scripts/run_elysia_dry_run_report.py --mode real-planning --json` | `"safe": true` |
| 6 | `python scripts/run_safe_stack_smoke_tests.py` | pytest PASSED |
| 7 | `pytest --collect-only -q` | No unexpected collection errors |
| 8 | Full pytest (optional) | 439+ passed, 0 failed |

### Smoke verification milestone (future, after executor)

1. Enable executor in isolated test with approved packet
2. Write smoke file in `tmp_path` only
3. Verify content hash
4. Execute rollback
5. Verify cleanup
6. Set `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED=true` in readiness evidence only after above

---

## 13. Readiness impact

| Check | This plan | After future implementation |
|-------|-----------|----------------------------|
| `ready_for_limited_live_mode` | **`false`** | `false` until all gates pass |
| `status` | **`BLOCKED`** | `BLOCKED` until smoke verified |
| `LIVE_EXECUTOR_IMPLEMENTED` | **`false`** | `true` only after executor tests pass |
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | **`false`** | `true` only after verified smoke + rollback |
| `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED` | **`false`** | Unchanged by executor plan |

**This plan does not change readiness code or evidence.**

---

## 14. Safety statement

- **No executor implemented** in this milestone
- **No live action run**
- **No execution code added**
- **No smoke file written**
- **No autonomy enabled** — `config/autonomy.json` → `"enabled": false`
- **Limited live mode remains BLOCKED**

---

## 15. Future sequence

Strict order for implementation milestones (none started by this plan):

```
1. docs/LIVE_EXECUTOR_IMPLEMENTATION_PLAN.md     ← this document (plan only)
2. Implement live_action_executor.py              disabled-by-default stub
3. Test executor disabled path                    writes nothing
4. Test all deny paths                            writes nothing
5. Enable executor in test env only               approved smoke write in tmp
6. Test rollback                                  cleanup proven
7. Update readiness evidence                      LIVE_EXECUTOR_IMPLEMENTED=true
8. Verify smoke end-to-end                        HARMLESS_LIVE_ACTION_SMOKE_VERIFIED=true
9. Operator review                                limited live mode still BLOCKED until all blockers clear
```

**Critical rule:** Step 5 requires explicit `ELYSIA_LIVE_EXECUTOR_ENABLED=true` in test only. Production default remains disabled. Approval route never advances to step 5 automatically.

---

## Appendix: Dependency map

```
Passive scaffolding (done)
├── live_action_gate.py
├── live_action_approval_packet.py
├── live_action_operator_decision.py
├── live_action_audit.py
├── live_action_rollback.py
├── live_action_smoke_packet.py
├── live_action_approval_route.py
└── live_action_passive_smoke_flow.py

Future executor (not implemented)
└── live_action_executor.py
    ├── reads: approval store, decision trail, smoke packet validators
    ├── writes: one file in tmp workspace only
    └── never called by: approval route, core.py, server.py, autonomy loop
```
