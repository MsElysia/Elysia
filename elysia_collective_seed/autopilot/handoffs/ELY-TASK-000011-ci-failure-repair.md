# ELY-TASK-000011 — CI failure diagnosis and repair

## Scope
Independent supervisor verification of AUTOPILOT-004 completion-to-ledger integration after CI run 34138632289 failed in the seed test step.

## Finding
The new completion path intentionally maps a producer `completed` packet to `verifying`, then releases the producer lease. `TaskLedger.release()` rejected `verifying` because it was classified as an active lease state. This made the independent-verification handoff impossible and caused the newly collected orchestration test to fail.

A second state-safety issue was repaired at the same boundary: `claim()` previously allowed acquisition from any non-terminal state. That could permit a review/verifying/blocked task to be leased again without an explicit gate transition.

## Repair
- Active execution lease states are now only `claimed` and `running`.
- `verifying`/`review` remain persisted non-dispatchable states but may exist without the producer lease.
- New lease acquisition is atomically restricted to `status='queued'`.
- Lease renewal is restricted to active execution states.
- Expiry reaping is restricted to active execution states.
- Non-queued, non-terminal claims return `state_not_claimable` rather than silently acquiring.

## Safety
No provider invocation, Guardian runtime wiring, network/subprocess execution, merge, deployment, external posting, credential access, or private-data scope was added. PR #12 remains draft and targets the isolated Elysia Collective seed branch.

## Evidence
- Failed workflow: GitHub Actions run 34138632289, seed test step failed while compile and JSON validation passed.
- Repair commit: c406a0dbf8163c43b1275dcba0bfdcf0d1bd9fd7.

## Handoff / gate
Wait for CI on the repaired branch head. If green, independently verify the completion-to-`verifying` transition and queued-only claim invariant before adding verifier-result application. Do not merge or enable runtime/provider adapters.
