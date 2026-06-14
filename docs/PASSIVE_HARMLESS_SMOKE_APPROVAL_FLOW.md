# Passive Harmless Smoke Approval Flow

**Milestone:** Passive integration tests only — **approval is not execution**  
**Date:** 2026-06-14  
**Status:** Flow verified in tests — **readiness remains BLOCKED**

**Starting checkpoint:** `e3bd4db feat(autonomy): add passive harmless smoke packet`

**Related docs:** [`PASSIVE_HARMLESS_SMOKE_PACKET_GENERATION.md`](PASSIVE_HARMLESS_SMOKE_PACKET_GENERATION.md), [`PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md`](PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md), [`HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md`](HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md)

---

## Passive flow shape

```
build_harmless_smoke_approval_packet()
        │
        ▼
register_harmless_smoke_packet_for_approval(store)
        │
        ▼
GET list pending ──► GET packet detail
        │
        ▼
POST operator decision (APPROVE / DENY)
        │
        ▼
GET decision/audit trail
        │
        ▼
(STOP — no executor, no file write)
```

Approval route enabled in tests only via `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED=true`.

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/live_action_passive_smoke_flow.py` | Glue: register smoke packet with approval store |
| `project_guardian/tests/test_live_action_passive_smoke_approval_flow.py` | End-to-end passive flow tests |
| `docs/PASSIVE_HARMLESS_SMOKE_APPROVAL_FLOW.md` | This document |

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`, `project_guardian/live_action_readiness.py`

---

## Proof approval is not execution

- APPROVE returns `safety_verdict: APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED`
- All route responses include `execution_permitted=false`, `executed=false`, `executor_called=false`
- No function in flow glue writes files or dispatches actions

---

## Proof no executor call

- Flow glue imports only smoke packet builder and approval route store
- AST scan: no `execute_live_action`, `run_for_proposal`, or implementer calls
- `executor_called=false` on every response step

---

## Proof no smoke file write

- Target path `live_smoke_workspace/approved_smoke.txt` never created
- Tests assert file absent before and after full APPROVE flow
- `register_harmless_smoke_packet_for_approval()` does not touch filesystem

---

## Proof no live action run

- No live executor module invoked
- `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` remains `false`
- Safe Observer unchanged; autonomy config unchanged

---

## Proof readiness remains blocked

After full passive APPROVE flow:

- `ready_for_limited_live_mode` = `false`
- Blockers remain: `LIVE_EXECUTOR_IMPLEMENTED`, `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED`

---

## Safety statement

- **No autonomy enabled** — `config/autonomy.json` → `"enabled": false`
- **No live execution run**
- **No live executor added**
- **No harmless smoke run**
- **No smoke file created**
- **Approval route disabled by default** outside explicit test env
