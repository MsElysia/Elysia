# Passive UI/API Approval Route Scaffolding

**Milestone:** Passive scaffolding — **approval recording only, no execution**  
**Date:** 2026-06-14  
**Status:** Scaffolding implemented and tested — **readiness remains BLOCKED**

**Starting checkpoint:** `007bfe1 docs(autonomy): design ui api approval route`

**Related docs:** [`UI_API_APPROVAL_ROUTE_DESIGN.md`](UI_API_APPROVAL_ROUTE_DESIGN.md), [`LIVE_EXECUTOR_INTERFACE_DESIGN.md`](LIVE_EXECUTOR_INTERFACE_DESIGN.md), [`HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md`](HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md), [`APPROVAL_ROUTE_EXECUTOR_WIRING_PLAN.md`](APPROVAL_ROUTE_EXECUTOR_WIRING_PLAN.md)

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/live_action_approval_route.py` | Passive route handlers, store, hash binding, expiry checks |
| `project_guardian/tests/test_live_action_approval_route.py` | Approval-only route tests |
| `elysia/api/server.py` | Thin Flask routes delegating to passive handlers |
| `docs/PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md` | This document |

**Not changed:** `project_guardian/core.py`, `config/autonomy.json`, `project_guardian/live_action_readiness.py`

---

## Route/handler shapes added

| Method | Path | Handler |
|--------|------|---------|
| `GET` | `/api/live-action/approval-packets/pending` | `list_pending_approval_packets` |
| `GET` | `/api/live-action/approval-packets/<packet_id>` | `get_approval_packet_detail` |
| `POST` | `/api/live-action/approval-packets/<packet_id>/decision` | `record_operator_decision_for_packet` |
| `GET` | `/api/live-action/approval-packets/<packet_id>/trail` | `get_approval_decision_trail` |

**Enable gate:** `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED=true` (default **off**). When disabled, all routes return `403 APPROVAL_ROUTE_DISABLED`.

---

## Proof approval is not execution

- Handlers call only `build_live_action_operator_decision`, `validate_live_action_operator_decision`, and append-only store writes.
- Every success and error response includes:
  - `execution_permitted: false`
  - `executed: false`
  - `executor_called: false`
- Tests assert no filesystem writes after `APPROVE` or `DENY`.
- `APPROVE` records `safety_verdict: APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED` via passive operator-decision validation.

---

## Proof no executor call exists

- `live_action_approval_route.py` AST scan: no calls to `execute_live_action`, `run_for_proposal`, `apply_mutation`, or `dispatch`.
- Module does not import `project_guardian.core`, implementer, or mutation paths.
- Server routes delegate only to passive handlers; `/implement` remains fail-closed 403.

---

## Proof harmless smoke is not run

- No `harmless_live_smoke` action registration in default store.
- No file write to `live_smoke_workspace/approved_smoke.txt` in tests or handlers.
- No live executor module exists or is imported.

---

## Proof readiness remains blocked

| Check | Status |
|-------|--------|
| `ready_for_limited_live_mode` | `false` |
| `LIVE_EXECUTOR_IMPLEMENTED` | `false` |
| `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED` | `false` (scaffolding only; readiness evidence unchanged) |
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | `false` |

Passive scaffolding records decisions but does not satisfy full route implementation readiness or remove executor/smoke blockers.

---

## Safety statement

- **No autonomy enabled** — `config/autonomy.json` → `"enabled": false`
- **No live execution run**
- **No live executor added**
- **No execution code added**
- **No harmless smoke run**
- **Approval routes disabled by default** until `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED=true`
