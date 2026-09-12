# ELY-TASK-000013 — expired-lease CI repair

## Scope
Diagnose the next bounded AUTOPILOT-004 seed-test failure after the active-lease conflict repair, without expanding runtime/provider authority.

## Finding
`test_same_worker_reacquires_expired_lease_as_new_attempt` requires an expired execution lease to be reclaimable as a new attempt. `TaskLedger.claim()` only acquired rows whose persisted status was `queued`, so an expired `claimed`/`running` row could not be reclaimed unless a separate `reap_expired()` call happened first. That contradicted the existing regression and left claim semantics dependent on an external cleanup race.

## Repair
The atomic acquisition UPDATE now permits either (a) eligible queued work or (b) an expired `claimed`/`running` execution lease. Live leases remain protected, and `verifying`, `review`, `blocked`, `human_review`, and terminal states remain non-claimable. Reclaim increments `attempt` exactly once.

## Evidence
- repaired file: `elysia_collective_seed/autopilot/task_ledger.py`
- regression: `elysia_collective_seed/autopilot/test_task_ledger.py::test_same_worker_reacquires_expired_lease_as_new_attempt`
- prior failing head: `5ffe2c3fd30a198b3b3384ab00738e8ab2a1584a`
- prior workflow: GitHub Actions run `34151581011`, failing at seed-test step 7
- repair commit: `3c1f995d3b856dd3db2e70b69c4026ae570067dd`

## Safety
No provider invocation, Guardian runtime activation, networking, external posting, merge, deployment, private-data expansion, or safety/audit/rollback weakening was introduced.

## Handoff / gate
Keep PR #12 draft and unmerged. Require executable CI on the new branch head before treating this repair as verified. If CI still fails, diagnose only the next concrete assertion before adding orchestration capability.
