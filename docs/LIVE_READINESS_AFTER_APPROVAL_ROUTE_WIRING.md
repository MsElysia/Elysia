# Live Readiness After Approval Route Wiring

**Milestone:** Readiness evidence update — **limited live mode remains BLOCKED**  
**Date:** 2026-05-30  
**Status:** Route wiring verified; readiness evidence updated

**Starting checkpoint:** `7d07b47 feat(autonomy): wire approval route to smoke executor`

**Related docs:** [`APPROVAL_ROUTE_EXECUTOR_WIRING_IMPLEMENTATION.md`](APPROVAL_ROUTE_EXECUTOR_WIRING_IMPLEMENTATION.md), [`LIVE_READINESS_AFTER_HARMLESS_SMOKE_EXECUTOR.md`](LIVE_READINESS_AFTER_HARMLESS_SMOKE_EXECUTOR.md), [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md), [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md)

---

## Evidence updated

| Check | Default | Meaning |
|-------|---------|---------|
| `APPROVAL_ROUTE_EXECUTION_WIRED` | `true` | Route calls harmless smoke executor when gated |
| `APPROVAL_ROUTE_EXECUTION_TRIPLE_GATED` | `true` | Requires three env flags for execution |
| `APPROVAL_ROUTE_DEFAULT_DECISION_ONLY` | `true` | Default APPROVE records only |
| `APPROVAL_ROUTE_NON_APPROVE_NEVER_EXECUTES` | `true` | DENY/REQUEST_CHANGES/CANCEL/EXPIRE never execute |
| `APPROVAL_ROUTE_EXECUTION_VERIFIED_IN_TMP_WORKSPACE` | `true` | Verified in pytest isolated tmp workspace |
| `LIMITED_LIVE_PROFILE_NOT_DECLARED` | `false` | Blocker — profile not declared |
| `OPERATOR_LIMITED_LIVE_RUNBOOK_MISSING` | `false` | Blocker — runbook missing |
| `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` | `false` | Blocker — triple gates off in production |
| `AUTONOMY_CONFIG_DISABLED` | `false` | Blocker — `config/autonomy.json` still disabled |

**Removed blocker:** `APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR` (replaced by verified wiring evidence + accurate remaining blockers)

**Safety verification (passing, not readiness grant):** `AUTONOMY_CONFIG_DEFAULT_DISABLED=true` confirms config remains disabled by design.

---

## Route wiring verified

Implementation in `project_guardian/live_action_approval_route.py`:

- Triple gates: `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED`, `ELYSIA_LIVE_EXECUTOR_ENABLED`, `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE`
- Default APPROVE: decision-only when any gate off
- All gates on + valid smoke APPROVE: calls `execute_live_action()` in tmp workspace tests only
- No auto-rollback on success

Route wiring does **not** imply autonomy is enabled.

---

## Why readiness remains blocked

`evaluate_live_mode_readiness()` returns:

- `status=BLOCKED`
- `ready_for_limited_live_mode=false`
- `safety_verdict=NOT_READY_FOR_LIVE_MODE`

Verified route wiring is necessary but not sufficient for limited live mode. Remaining product/safety gates intentionally block readiness.

---

## Remaining blockers

| Blocker key | Reason |
|-------------|--------|
| `LIMITED_LIVE_PROFILE_NOT_DECLARED` | Operator limited-live profile not declared |
| `OPERATOR_LIMITED_LIVE_RUNBOOK_MISSING` | Operator runbook for limited-live not published |

**Next docs milestone:** [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md), [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md) (declared in separate commit; readiness evidence update is a future milestone).
| `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` | Triple execution gates remain off by default |
| `AUTONOMY_CONFIG_DISABLED` | `config/autonomy.json` `enabled=false` |

---

## Triple-gate behavior

| Gate | Default |
|------|---------|
| `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED` | off |
| `ELYSIA_LIVE_EXECUTOR_ENABLED` | off |
| `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` | off |

All three required for route APPROVE to invoke executor.

---

## Default decision-only behavior

When any gate is off, APPROVE returns `executor_called=false`, `executed=false`, `execution_permitted=false` and writes nothing.

---

## Proof no autonomy enabled

- `config/autonomy.json` unchanged: `"enabled": false`
- No runtime autonomy loop changes
- Safe Observer: zero execution in default real-planning mode

---

## Safety statement

| Constraint | Status |
|------------|--------|
| Autonomy enabled | **No** |
| Route behavior changed this milestone | **No** |
| Executor behavior changed this milestone | **No** |
| Non-test live execution | **None** |
| `config/autonomy.json` | **Unchanged** (`enabled=false`) |
