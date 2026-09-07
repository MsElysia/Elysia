# ELY-TASK-000012 — active-lease CI repair

## Scope
Diagnose the remaining AUTOPILOT-004 seed-test failure without expanding runtime or provider authority.

## Finding
The dry-run regression `test_existing_active_lease_is_not_stolen` expects a competing worker to receive `active_lease`. After the queued-only acquisition hardening, `TaskLedger.claim()` instead returned the generic `state_not_claimable` for a live `claimed`/`running` lease owned by another worker. The task remained protected, but the observable conflict contract no longer matched the regression/API semantics.

## Repair
Preserve queued-only acquisition and explicitly classify a live lease in `claimed`/`running` as `active_lease` after atomic acquisition fails. Review/verifying/blocked/human-review states continue to return `state_not_claimable`; terminal states remain `terminal_task`.

## Safety
No provider invocation, Guardian runtime activation, networking, external posting, merge, deployment, private-data expansion, or safety/audit/rollback weakening was introduced.

## Evidence
- repaired: `elysia_collective_seed/autopilot/task_ledger.py`
- existing regression: `elysia_collective_seed/autopilot/test_dryrun_orchestrator.py::test_existing_active_lease_is_not_stolen`
- prior failing workflow: GitHub Actions run 34142894909, seed-validation step 7
- repair commit: 2ada6c0d021978539eba77e072a279e5252e6f0a

## Handoff / gate
Keep PR #12 draft and unmerged. Require executable CI on the new branch head before treating this repair as verified. If CI still fails, inspect the next concrete failing assertion and repair only that bounded defect before adding orchestration capability.
