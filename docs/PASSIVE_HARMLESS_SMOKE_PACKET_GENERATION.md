# Passive Harmless Smoke Packet Generation

**Milestone:** Passive packet generation only — **no execution, no smoke file write**  
**Date:** 2026-06-14  
**Status:** Scaffolding implemented and tested — **readiness remains BLOCKED**

**Starting checkpoint:** `607113f feat(autonomy): add passive approval route scaffolding`

**Related docs:** [`HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md`](HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md), [`LIVE_EXECUTOR_INTERFACE_DESIGN.md`](LIVE_EXECUTOR_INTERFACE_DESIGN.md), [`PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md`](PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md)

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/live_action_smoke_packet.py` | Passive smoke packet builder and path validation |
| `project_guardian/tests/test_live_action_smoke_packet.py` | Packet generation and rejection tests |
| `docs/PASSIVE_HARMLESS_SMOKE_PACKET_GENERATION.md` | This document |

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`, `project_guardian/live_action_readiness.py`

---

## Generated packet shape

Built via `build_harmless_smoke_approval_packet()` → `HarmlessSmokePacketResult` → `serialize_harmless_smoke_packet_response()`:

| Field | Value |
|-------|-------|
| `action_id` | `harmless_live_smoke_v1` |
| `action_kind` | `harmless_live_smoke` |
| `action_category` | `LOCAL_FILE_WRITE` |
| `relative_target_path` | `live_smoke_workspace/approved_smoke.txt` |
| `proposed_content` | `ELYSIA_APPROVED_LIVE_SMOKE` |
| `content_hash` | SHA-256 of `ELYSIA_APPROVED_LIVE_SMOKE\n` |
| `allowlist_decision` | `REQUIRE_APPROVAL` |
| `packet.execution_permitted` | `false` |
| `ready_for_operator_review` | `true` (when paths valid) |

---

## Target path rules

| Rule | Enforcement |
|------|-------------|
| Workspace must be absolute | `WORKSPACE_NOT_ABSOLUTE` |
| Workspace must not equal repo root | `WORKSPACE_IS_REPO_ROOT` |
| Target must resolve inside workspace | `TARGET_OUTSIDE_WORKSPACE` |
| No `..` traversal | `PATH_TRAVERSAL` / `TARGET_OUTSIDE_WORKSPACE` |
| No network URL targets | `NETWORK_PATH` |
| No Documents/Downloads/Desktop paths | `USER_DATA_PATH` |
| No external storage workspace/target | `EXTERNAL_STORAGE_PATH` |
| No absolute relative target | `UNSAFE_ABSOLUTE_TARGET` |

---

## Proposed content/hash

- Bytes: `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF)
- Hash: `compute_harmless_smoke_content_hash()` → SHA-256 hex (64 chars)
- Stored in `request.expected_result` and response `content_hash`

---

## Rollback metadata

Passive `LiveActionRollbackPlan`:

- `strategy`: `DELETE_CREATED_FILE` (or `FILE_RESTORE` if `file_preexists=True`)
- `availability`: `AVAILABLE`
- `target`: `live_smoke_workspace/approved_smoke.txt`
- Validated via existing `validate_live_action_rollback_plan()` — **not executed**

---

## Audit preview metadata

From `serialize_live_action_audit_record(packet.audit_record)`:

- `action_id`, `target`, `event_status`, `safety_verdict`, `rollback_info`
- Preview only — no `append_live_action_audit_record()` unless future explicit path milestone

---

## Proof no execution

- Module AST scan: no `execute_live_action`, `run_for_proposal`, `apply_mutation`, or audit append calls
- All responses include `execution_permitted=false`, `executed=false`, `executor_called=false`
- `evaluate_live_mode_readiness().ready_for_limited_live_mode` remains `false`

---

## Proof no smoke file write

- `build_harmless_smoke_approval_packet()` does not call `open()`, `write()`, or `mkdir()` on target path
- Tests assert `approved_smoke.txt` absent after packet generation

---

## Proof no executor call

- No live executor module exists or is imported
- Packet builder uses only passive gate/packet/rollback/audit scaffolding

---

## Readiness remains blocked

| Check | Status |
|-------|--------|
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | `false` |
| `LIVE_EXECUTOR_IMPLEMENTED` | `false` |
| `ready_for_limited_live_mode` | `false` |

Packet generation is a prerequisite step only; verification and executor remain future milestones.

---

## Safety statement

- **No autonomy enabled** — `config/autonomy.json` → `"enabled": false`
- **No live execution run**
- **No live executor added**
- **No harmless smoke run**
- **No smoke file created**
- **No execution code added**
