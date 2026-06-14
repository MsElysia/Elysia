# Approval Route Executor Wiring Implementation

**Milestone:** Triple-gated route-to-executor wiring — **readiness remains BLOCKED**  
**Date:** 2026-05-30  
**Status:** Wiring implemented and tested under explicit triple gates

**Starting checkpoint:** `ed3be08 docs(autonomy): plan approval route executor wiring`

**Related docs:** [`APPROVAL_ROUTE_EXECUTOR_WIRING_PLAN.md`](APPROVAL_ROUTE_EXECUTOR_WIRING_PLAN.md), [`HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md`](HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md), [`LIVE_READINESS_AFTER_HARMLESS_SMOKE_EXECUTOR.md`](LIVE_READINESS_AFTER_HARMLESS_SMOKE_EXECUTOR.md)

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/live_action_approval_route.py` | Triple-gate execution wiring for harmless smoke APPROVE |
| `project_guardian/live_action_passive_smoke_flow.py` | Register workspace/repo context with smoke packets |
| `project_guardian/tests/test_live_action_approval_route_executor_wiring.py` | Triple-gate wiring tests |
| `project_guardian/tests/test_live_action_executor.py` | Module-level import guard updated |
| `docs/APPROVAL_ROUTE_EXECUTOR_WIRING_IMPLEMENTATION.md` | This document |

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`, `project_guardian/live_action_readiness.py`

---

## Triple gates

All three must be truthy (`1`, `true`, `yes`, `on`) for APPROVE to call executor:

| Flag | Default | Purpose |
|------|---------|---------|
| `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED` | off | Route handlers reachable |
| `ELYSIA_LIVE_EXECUTOR_ENABLED` | off | Executor may write when called |
| `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` | off | Route may invoke executor on APPROVE |

If executor flag is off, route does **not** call executor even when executes-smoke flag is on.

---

## Default decision-only behavior

| Condition | APPROVE outcome |
|-----------|-----------------|
| Any gate off | Decision recorded; `executor_called=false`; no write |
| Non-smoke packet | Decision recorded; no executor call |
| Missing workspace context | Decision recorded; no executor call |

`DENY`, `REQUEST_CHANGES`, `CANCEL`, `EXPIRE` never call executor.

---

## Enabled behavior (all gates + valid smoke APPROVE)

1. Record operator decision (append-only decision audit)
2. Build `LiveActionExecutionRequest` from packet + stored workspace
3. Call `execute_live_action()`
4. Append separate execution audit record
5. Return response with `executor_called`, `execution_permitted`, `executed`, `execution_result`

Writes exactly `live_smoke_workspace/approved_smoke.txt` with `ELYSIA_APPROVED_LIVE_SMOKE\n` inside isolated tmp workspace only.

---

## Non-executing decisions

| Decision | Executor called |
|----------|-----------------|
| DENY | Never |
| REQUEST_CHANGES | Never |
| CANCEL | Never |
| EXPIRE | Never |
| APPROVE on expired packet | Never (409 before record) |
| APPROVE with hash mismatch | Never (409 before record) |
| APPROVE with unsafe workspace | Called but denied; no write |

---

## Audit behavior

- **Decision audit:** unchanged append-only via `store.append_decision()`
- **Execution audit:** separate JSONL line with `record_type: execution_audit`, references `approval_packet_id` and `operator_decision_id`

---

## Rollback behavior

- Route does **not** auto-rollback after successful execution
- Rollback via explicit `rollback_harmless_smoke_write()` in tests/helpers only
- Limited to harmless smoke target inside validated workspace

---

## Proof no shell/network/browser/API/mutation

- Route calls only `execute_live_action()` (Path.write_bytes only)
- No subprocess, network, browser, API, or mutation imports added
- Executor imported lazily inside gate/execution helpers only

---

## Proof no repo-root/user/external writes

- Path validation via `validate_harmless_smoke_paths()` on executor call
- Tests assert no repo-root `approved_smoke.txt`
- Unsafe workspace override blocked by executor validation

---

## Proof `config/autonomy.json enabled=false`

- File unchanged; autonomy not enabled
- Safe Observer continues to report zero execution in default runtime

---

## Readiness remains blocked

| Evidence | Status |
|----------|--------|
| `APPROVAL_ROUTE_EXECUTION_WIRED` | `false` (evidence not updated this milestone) |
| `APPROVAL_ROUTE_OPERATOR_ENABLED` | `false` |
| `ready_for_limited_live_mode` | `false` |
| `status` | `BLOCKED` |

Wiring exists behind triple gates but readiness evidence and product gates remain unchanged until a future evidence-update milestone.

---

## Safety statement

| Constraint | Status |
|------------|--------|
| Autonomy enabled | **No** |
| Default route execution on APPROVE | **No** |
| Triple gates required | **Yes** |
| `config/autonomy.json` | **Unchanged** (`enabled=false`) |
| Auto-rollback on success | **No** |
