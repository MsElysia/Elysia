# Live Readiness After Harmless Smoke Executor

**Milestone:** Readiness evidence update — **limited live mode remains BLOCKED**  
**Date:** 2026-05-30  
**Status:** Evidence updated to reflect verified executor, smoke, and rollback

**Starting checkpoint:** `ea62f51 feat(autonomy): implement harmless smoke executor`

**Related docs:** [`HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md`](HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md), [`PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md`](PASSIVE_UI_API_APPROVAL_ROUTE_SCAFFOLDING.md), [`PASSIVE_HARMLESS_SMOKE_APPROVAL_FLOW.md`](PASSIVE_HARMLESS_SMOKE_APPROVAL_FLOW.md)

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/live_action_readiness.py` | Updated evidence and remaining blockers |
| `project_guardian/tests/test_live_action_readiness.py` | Assertions for verified evidence and remaining blockers |
| `project_guardian/tests/test_live_action_passive_smoke_approval_flow.py` | Readiness blocker assertions updated |
| `project_guardian/tests/test_live_action_executor.py` | Readiness blocker assertions updated |
| `docs/LIVE_READINESS_AFTER_HARMLESS_SMOKE_EXECUTOR.md` | This document |

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`, `project_guardian/live_action_executor.py`, `project_guardian/live_action_approval_route.py`

---

## Evidence updated

| Check | Default evidence | Meaning |
|-------|------------------|---------|
| `LIVE_EXECUTOR_IMPLEMENTED` | `true` | Harmless smoke executor implemented; disabled by default |
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | `true` | Verified in isolated tmp workspace under test flag |
| `HARMLESS_LIVE_ACTION_ROLLBACK_VERIFIED` | `true` | Delete/restore rollback verified for smoke target only |
| `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED` | `true` | Passive scaffolding implemented (recording only) |
| `APPROVAL_ROUTE_EXECUTION_WIRED` | `false` | Approval route not wired to executor on APPROVE |
| `APPROVAL_ROUTE_OPERATOR_ENABLED` | `false` | Route disabled by default (`ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED` off) |
| `AUTONOMY_CONFIG_DEFAULT_DISABLED` | `true` | `config/autonomy.json` remains `enabled=false` |

---

## Why readiness remains blocked

`evaluate_live_mode_readiness()` returns:

- `status=BLOCKED`
- `ready_for_limited_live_mode=false`
- `safety_verdict=NOT_READY_FOR_LIVE_MODE`

Verified executor/smoke/rollback evidence does **not** grant limited live mode. Remaining product gates block readiness until future milestones explicitly satisfy them.

---

## Exact remaining blockers

| Blocker key | Reason |
|-------------|--------|
| `APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR` | `APPROVAL_ROUTE_EXECUTION_WIRED=false` — APPROVE does not call executor |
| `APPROVAL_ROUTE_DEFAULT_DISABLED` | `APPROVAL_ROUTE_OPERATOR_ENABLED=false` — route env gate off by default |

`AUTONOMY_CONFIG_DEFAULT_DISABLED=true` is a **passing** safety check (autonomy not enabled), not a readiness grant.

---

## Proof approval route is not wired to executor

- `live_action_approval_route.py` does not import `live_action_executor`
- APPROVE via route returns `executor_called=false`, `executed=false`
- `APPROVAL_ROUTE_EXECUTION_WIRED` evidence remains `false`

---

## Proof autonomy config remains disabled

- `config/autonomy.json` unchanged: `"enabled": false`
- `AUTONOMY_CONFIG_DEFAULT_DISABLED` evidence remains `true` (verified disabled state)

---

## Safety statement

| Constraint | Status |
|------------|--------|
| Autonomy enabled | **No** |
| Approval route execution on APPROVE | **No** |
| Route-to-executor wiring | **No** |
| New executor behavior | **No** — executor module unchanged |
| `config/autonomy.json` | **Unchanged** (`enabled=false`) |
| Shell / network / browser / API / mutation | **Absent** |
