# UI/API Approval Route Design

**Milestone:** Design/specification only — **no implementation**  
**Date:** 2026-06-14  
**Status:** Route contract designed — **no UI route, no API route, no execution**

**Related docs:** [`LIVE_EXECUTOR_INTERFACE_DESIGN.md`](LIVE_EXECUTOR_INTERFACE_DESIGN.md), [`HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md`](HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md), [`PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`](PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md), [`LIVE_MODE_READINESS_POST_REPAIR_UPDATE.md`](LIVE_MODE_READINESS_POST_REPAIR_UPDATE.md)

**Starting checkpoint:** `865b9cb docs(autonomy): design live executor interface`

---

## 1. Purpose

Define the **future** operator approval route contract — how a human reviews and explicitly records a decision on a single harmless live-action approval packet **without executing anything**.

The route must:

- Surface pending approval packets for operator review
- Display all safety-relevant fields (packet, rollback, audit preview, dry-run trace)
- Accept explicit operator decisions (`APPROVE`, `DENY`, `REQUEST_CHANGES`, `CANCEL`, `EXPIRE`)
- Append auditable, append-only decision records
- Set `execution_permitted=false` on all responses — execution is a **separate future executor milestone**

This document does **not** add routes to `elysia/api/server.py`, control panel UI handlers, live executor code, or autonomy enablement.

---

## 2. Non-goals

This milestone and the future approval route **do not**:

- Enable autonomy or modify `config/autonomy.json`
- Implement HTTP endpoints or UI pages
- Invoke the live executor or perform file writes
- Verify harmless smoke
- Auto-approve, auto-deny, or batch-approve multiple actions
- Call mutation/proposal implementation, shell, network, browser, or tool capabilities
- Mark limited live mode ready
- Wire into `project_guardian/core.py` or autonomy loops

---

## 3. Route/UI must be approval-only, not execution

| Principle | Requirement |
|-----------|-------------|
| **Approval ≠ execution** | Recording `APPROVE` does not write files, run smoke, or call executor |
| **`execution_permitted` always false** | Route responses and stored decisions must keep `execution_permitted=false` until a future executor milestone with separate enable flags |
| **No side-effect handlers** | POST decision must only validate, serialize, and append audit — no downstream action dispatch |
| **Fail-closed on ambiguity** | Invalid packet, expired packet, hash mismatch → reject decision; no execution fallback |
| **Local-only surface** | Future route binds loopback / authenticated operator session only (per existing local-only UI patterns) |

Operator UI copy must state explicitly: *"Approval records your decision. It does not run the action."*

---

## 4. Required operator-visible fields

Every approval detail view (UI panel or API `GET` detail) must expose these fields derived from passive scaffolding:

| Field | Source | Display notes |
|-------|--------|---------------|
| **approval packet id** | `LiveActionApprovalPacket.packet_id` | Primary correlation id |
| **action category** | `request.risk_category` / `action_kind` | e.g. `HARMLESS_LIVE_SMOKE`, `LOCAL_FILE_WRITE` |
| **proposed target path** | `request.target` | Workspace-relative only for smoke |
| **proposed content hash** | `request.expected_result` or dedicated `content_hash` field | SHA-256 hex of planned bytes |
| **risk classification** | `validation.decision`, `validation.safety_verdict`, `allowlist_decision` | Include blocked/approval-required labels |
| **rollback plan summary** | `summarize_live_action_rollback_plan()` | Strategy, availability, target |
| **audit record preview** | `serialize_live_action_audit_record(audit_record)` | Read-only preview; not a write |
| **dry-run trace summary** | Linked Safe Observer trace | `trace_id`, `outcome`, `blocked`, `executed=false` |
| **expiration timestamp** | Packet `expires_at` (future field) or decision `expires_at` | ISO-8601 UTC; past expiry → not approvable |

Additional recommended fields:

- `action_id`, `packet_mode`, `ready_for_operator_review`, `reasons[]`, `safety_verdict`, `packet_content_hash` (see §6)

---

## 5. Allowed decisions

Maps to existing `OperatorDecisionKind` in `live_action_operator_decision.py`:

| Operator action | Stored value | `execution_permitted` | Effect |
|-----------------|--------------|----------------------|--------|
| **APPROVE** | `APPROVE` | `false` | Records approval; executor still blocked |
| **DENY** | `DENY` | `false` | Records denial; packet closed |
| **REQUEST_CHANGES** | `REQUEST_CHANGES` | `false` | Returns packet to proposed state; new packet required |
| **CANCEL** | `CANCELLED` | `false` | Operator withdraws review; no execution |
| **EXPIRE** | `EXPIRED` | `false` | System or operator marks packet past `expires_at` |

**APPROVE** requires: valid packet, `ready_for_operator_review=true`, non-empty `operator_id`, `reason`, `approved_scope`, matching `packet_content_hash`, and `expires_at` in the future.

All decisions produce `safety_verdict` per passive schema (e.g. `APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED` for valid approve).

---

## 6. Required safeguards

| Safeguard | Enforcement |
|-----------|-------------|
| **Approval does not execute** | Route handler calls only `build_live_action_operator_decision()` + `validate_live_action_operator_decision()` + audit append; never calls executor |
| **Packet must be valid** | `ready_for_operator_review=true`, `validation.blocked=false`, `rollback_validation.valid=true` |
| **Expired packets cannot be approved** | Reject `APPROVE` when `now > expires_at`; auto-transition to `EXPIRED` on list/detail fetch |
| **Decision binds to packet hash/version** | Client submits `packet_content_hash` (SHA-256 of canonical `serialize_live_action_approval_packet()` JSON); mismatch → `409 PACKET_HASH_MISMATCH` |
| **Append-only auditable decisions** | Decisions written to explicit JSONL path only; no in-place mutation of prior lines |
| **No mutation/proposal implementation** | Route must not import implementer, mutation engine, or proposal `/implement` paths |
| **No shell/network/browser/API/tool execution** | Route is read + record only; no subprocess, HTTP client, bounded browser, or capability dispatch |

### Packet content hash (future)

```
packet_content_hash = SHA256(
  json.dumps(serialize_live_action_approval_packet(packet), sort_keys=True, separators=(",", ":"))
)
```

Operator must confirm hash matches displayed detail before `APPROVE`.

---

## 7. Future route shape

Routes are **design placeholders** — not implemented in this milestone. Suggested paths under a future local-only namespace (e.g. `/api/live-action/` or control-panel section):

### `GET /live-action/approval-packets/pending`

List packets with `ready_for_operator_review=true` and no terminal decision.

**Query params:** `limit`, `mode` (default `approval_gated_live_design`)

### `GET /live-action/approval-packets/{packet_id}`

Full detail including all §4 operator-visible fields and `packet_content_hash`.

### `POST /live-action/approval-packets/{packet_id}/decision`

Record operator decision. Body validated against packet; **no execution**.

**Request body (future):**

```json
{
  "decision": "APPROVE",
  "operator_id": "operator@local",
  "reason": "Harmless smoke review complete",
  "approved_scope": "live_smoke_workspace/approved_smoke.txt single-file write",
  "packet_content_hash": "<sha256-hex>",
  "conditions": []
}
```

### `GET /live-action/approval-packets/{packet_id}/trail`

Return append-only decision + audit trail for packet (decisions, audit previews, dry-run trace ids).

### UI equivalent

Control panel section **"Live Action Approval"** with:

- Pending queue table
- Detail drawer with §4 fields
- Decision buttons: Approve / Deny / Request Changes / Cancel
- Expired packets shown read-only with Expire badge
- Banner: *"Approval does not execute actions"*

---

## 8. Required response schema

### List item (`GET pending`)

```json
{
  "packet_id": "<uuid>",
  "action_id": "harmless_live_smoke_v1",
  "action_category": "HARMLESS_LIVE_SMOKE",
  "target_path": "live_smoke_workspace/approved_smoke.txt",
  "content_hash": "<sha256>",
  "risk_classification": "REQUIRE_APPROVAL",
  "safety_verdict": "READY_FOR_REVIEW",
  "expires_at": "2026-06-14T18:00:00+00:00",
  "ready_for_operator_review": true,
  "execution_permitted": false
}
```

### Detail (`GET {packet_id}`)

```json
{
  "packet_id": "<uuid>",
  "mode": "approval_gated_live_design",
  "action_category": "HARMLESS_LIVE_SMOKE",
  "action_id": "harmless_live_smoke_v1",
  "proposed_target_path": "live_smoke_workspace/approved_smoke.txt",
  "proposed_content_hash": "<sha256>",
  "content_marker": "ELYSIA_APPROVED_LIVE_SMOKE",
  "risk_classification": {
    "risk_category": "LOCAL_FILE_WRITE",
    "allowlist_decision": "REQUIRE_APPROVAL",
    "validation_decision": "REQUIRE_APPROVAL",
    "blocked": false
  },
  "rollback_plan_summary": {
    "strategy": "DELETE_CREATED_FILE",
    "availability": "AVAILABLE",
    "target": "live_smoke_workspace/approved_smoke.txt"
  },
  "audit_record_preview": { },
  "dry_run_trace_summary": {
    "trace_id": "<uuid>",
    "outcome": "dry_run_blocked_not_executed",
    "blocked": true,
    "executed": false,
    "safety_verdict": "SAFE"
  },
  "expires_at": "2026-06-14T18:00:00+00:00",
  "packet_content_hash": "<sha256>",
  "ready_for_operator_review": true,
  "execution_permitted": false,
  "safety_verdict": "READY_FOR_REVIEW",
  "reasons": []
}
```

### Decision response (`POST decision`)

```json
{
  "decision_id": "<uuid>",
  "packet_id": "<uuid>",
  "decision": "APPROVE",
  "validation": {
    "valid": true,
    "execution_permitted": false,
    "safety_verdict": "APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED",
    "reasons": []
  },
  "audit_update_preview": {
    "event_status": "APPROVED",
    "execution_permitted": false
  },
  "executed": false,
  "message": "Decision recorded. Execution remains blocked."
}
```

### Error response (all routes)

```json
{
  "error_code": "PACKET_HASH_MISMATCH",
  "message": "Submitted packet_content_hash does not match server packet",
  "execution_permitted": false,
  "executed": false
}
```

| HTTP status | `error_code` examples |
|-------------|----------------------|
| 400 | `INVALID_DECISION`, `MISSING_OPERATOR_ID`, `PACKET_NOT_READY` |
| 403 | `APPROVAL_ROUTE_DISABLED` |
| 404 | `PACKET_NOT_FOUND` |
| 409 | `PACKET_HASH_MISMATCH`, `PACKET_EXPIRED`, `DECISION_ALREADY_RECORDED` |
| 422 | `VALIDATION_FAILED` |

---

## 9. Required audit fields

Every decision recorded via the future route must produce an append-only audit line (explicit path only) containing:

| Field | Requirement |
|-------|-------------|
| `event_id` | UUID |
| `timestamp` | UTC ISO-8601 |
| `packet_id` | Approval packet id |
| `decision_id` | Operator decision id |
| `action_id` | From packet request |
| `operator_id` | Authenticated operator identity |
| `decision` | `APPROVE` / `DENY` / `REQUEST_CHANGES` / `CANCELLED` / `EXPIRED` |
| `event_status` | Per `build_operator_decision_audit_update()` |
| `packet_content_hash` | Hash at decision time |
| `target_path` | From packet |
| `content_hash` | Planned write hash |
| `rollback_plan_summary` | Snapshot at decision time |
| `dry_run_trace_id` | Linked trace |
| `execution_permitted` | **`false`** always at route layer |
| `executed` | **`false`** always at route layer |
| `blocked` | `false` for valid approve; `true` for deny/blocked |
| `route_source` | `ui` or `api` |
| `safety_verdict` | From validation result |

Audit append uses `append_live_action_audit_record(path=...)` only — never default/global paths.

---

## 10. Required tests before implementation

Future test module (e.g. `project_guardian/tests/test_live_action_approval_route.py`) — **not created in this milestone**:

| Test | Asserts |
|------|---------|
| `test_route_disabled_by_default` | No handler registered / returns 403 when flag off |
| `test_list_pending_returns_only_reviewable_packets` | Blocked packets excluded |
| `test_detail_includes_all_operator_fields` | §4 fields present |
| `test_approve_does_not_execute` | POST APPROVE → no file write, `executed=false` |
| `test_approve_requires_packet_hash` | Wrong hash → 409, no decision stored |
| `test_expired_packet_cannot_approve` | Past `expires_at` → EXPIRED, approve rejected |
| `test_deny_records_audit_no_execution` | DENY → audit line, zero side effects |
| `test_request_changes_does_not_execute` | REQUEST_CHANGES → no write |
| `test_cancel_and_expire_no_execution` | CANCELLED/EXPIRED → no write |
| `test_decision_append_only` | Second APPROVE on same packet → 409 |
| `test_trail_returns_decision_and_audit` | GET trail includes full history |
| `test_no_mutation_or_implementer_import` | Route module import graph excludes execution paths |
| `test_autonomy_config_unchanged` | `config/autonomy.json` `enabled=false` after route tests |

Pre-implementation gate: passive Phase 2 tests green (94 passed); default runtime **439 passed, 0 failed, 11 skipped**.

---

## 11. Readiness impact

| Check | Status |
|-------|--------|
| `ready_for_limited_live_mode` | **`false`** |
| `status` | **`BLOCKED`** |
| `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED` | **`false`** — design only; implementation future |
| `LIVE_EXECUTOR_IMPLEMENTED` | **`false`** — unchanged |
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | **`false`** — unchanged |
| `AUTONOMY_CONFIG_DEFAULT_DISABLED` | **`true`** — by design |

This document satisfies **route contract design** only. The `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED` blocker remains active until a future milestone implements and tests the routes behind an explicit `approval_route.enabled=false` default.

---

## 12. Safety statement

- **No UI route implemented**
- **No API route implemented**
- **No live executor implemented**
- **No live action run**
- **No execution code added**
- **No rollback execution code added**
- **No autonomy enabled** — `config/autonomy.json` → `"enabled": false`
- **Limited live mode remains BLOCKED**

---

## Appendix: Approval flow (design only)

```
  Passive packet build                Future approval route          Future executor
  ─────────────────────              ─────────────────────          ───────────────
  build_live_action_approval_packet
           │
           ▼
  GET pending / detail  ──►  Operator reviews §4 fields
           │
           ▼
  POST decision (APPROVE) ──► validate + audit append
           │                  execution_permitted=false
           │                  executed=false
           ▼
  (STOP — route ends here)
           │
           │  separate milestone, separate enable flag
           ▼
  execute_live_action()   ──►  NOT IN SCOPE
```

Steps right of POST decision involving `execute_live_action()` are **out of scope** for this milestone and for the approval route itself.
