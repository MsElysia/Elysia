# Harmless Smoke Executor Implementation

**Milestone:** First enabled harmless smoke write path — **readiness remains BLOCKED**  
**Date:** 2026-05-30  
**Status:** Enabled executor implemented and tested under explicit env flag

**Starting checkpoint:** `1409504 feat(autonomy): add disabled live executor scaffold`

**Related docs:** [`DISABLED_LIVE_EXECUTOR_SCAFFOLD.md`](DISABLED_LIVE_EXECUTOR_SCAFFOLD.md), [`LIVE_EXECUTOR_IMPLEMENTATION_PLAN.md`](LIVE_EXECUTOR_IMPLEMENTATION_PLAN.md), [`PASSIVE_HARMLESS_SMOKE_APPROVAL_FLOW.md`](PASSIVE_HARMLESS_SMOKE_APPROVAL_FLOW.md), [`APPROVAL_ROUTE_EXECUTOR_WIRING_PLAN.md`](APPROVAL_ROUTE_EXECUTOR_WIRING_PLAN.md)

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/live_action_executor.py` | Enabled harmless smoke write + rollback when flag on |
| `project_guardian/tests/test_live_action_executor.py` | Disabled + enabled + rollback + wiring isolation tests |
| `project_guardian/live_action_readiness.py` | `LIVE_EXECUTOR_IMPLEMENTED=true`; smoke verification still blocked |
| `project_guardian/tests/test_live_action_readiness.py` | Executor implemented check; smoke verification still blocker |
| `docs/HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md` | This document |

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`, `project_guardian/live_action_approval_route.py`

---

## Disabled behavior (unchanged)

| `ELYSIA_LIVE_EXECUTOR_ENABLED` | Result |
|-------------------------------|--------|
| unset / false-like | `EXECUTOR_DISABLED`, `executed=false`, no writes |
| any value not in `{1,true,yes,on}` | same as above |

Rollback with executor disabled returns `EXECUTOR_DISABLED` and writes nothing.

---

## Enabled behavior

Requires **all** of:

- `ELYSIA_LIVE_EXECUTOR_ENABLED=true` (or `1` / `yes` / `on`)
- `operator_decision=APPROVE`
- `action_id=harmless_live_smoke_v1`
- `action_category=harmless_live_smoke`
- `target_path=live_smoke_workspace/approved_smoke.txt`
- `expected_content_hash` matches `compute_harmless_smoke_content_hash()`
- non-expired `expires_at`
- non-empty `approval_packet_id`, `operator_decision_id`, `rollback_plan_id`, `audit_record_id`
- `validate_harmless_smoke_paths()` passes for workspace + repo_root

On success:

- Writes exactly one file: `live_smoke_workspace/approved_smoke.txt`
- Content: `ELYSIA_APPROVED_LIVE_SMOKE\n`
- Only inside caller-supplied isolated tmp smoke workspace
- Returns `executed=true`, `execution_permitted=true`, `executor_called=true`
- Returns `before_hash` / `after_hash`, `action_category`, `target_path`, `rollback_summary`

Denials return `EXECUTION_DENIED` with specific failure codes; no writes.

---

## Target path limits

- Relative target must be exactly `live_smoke_workspace/approved_smoke.txt`
- Resolved path must stay inside `workspace_root`
- Must not resolve to repo root, user data paths, or external storage
- Enforced via `validate_harmless_smoke_paths()` on execute and rollback

---

## Rollback behavior

`rollback_harmless_smoke_write()` when executor enabled:

- **Delete strategy:** if file was created (`prior_content` omitted), deletes target file
- **Restore strategy:** if `prior_content` provided, restores that exact bytes
- Only for `live_smoke_workspace/approved_smoke.txt` inside validated workspace
- Rejects unsafe targets and paths outside smoke workspace
- Never touches repo root, user data, or external storage

---

## Proof approval route is not wired to executor

- `live_action_approval_route.py` does not import `live_action_executor`
- APPROVE via route still returns `executor_called=false`, `executed=false`
- No automatic execution on operator APPROVE

---

## Proof readiness remains blocked

- `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` evidence remains `false`
- `evaluate_live_mode_readiness()` returns `BLOCKED`
- `LIVE_EXECUTOR_IMPLEMENTED` is now `true` (executor exists) but is not a remaining blocker
- Harmless smoke verification evidence must be updated in a later milestone

---

## Safety statement

| Constraint | Status |
|------------|--------|
| Autonomy enabled | **No** — `config/autonomy.json` `enabled=false` unchanged |
| Shell / subprocess | **Absent** |
| Network / browser / API | **Absent** |
| Mutation / tools / capabilities | **Absent** |
| Repo-root writes | **Blocked** |
| User / external storage writes | **Blocked** |
| Writes | Only `approved_smoke.txt` in isolated tmp smoke workspace under `ELYSIA_LIVE_EXECUTOR_ENABLED=true` |
