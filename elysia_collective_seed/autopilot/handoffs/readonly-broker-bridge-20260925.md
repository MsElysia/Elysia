# Read-only OrchestrationBroker bridge handoff

Base product: `40964ee9e334d1974702e419dff28df7c87df587` (PR #24 evidence-binding repair, independently verified but still draft/unmerged).

Scope:
- add a runtime-disconnected TaskLedger -> existing OrchestrationBroker bridge for already-claimed `read_only` tasks only;
- preserve the existing `task_id + attempt` execution identity;
- reuse the ledger's append-only `events` table for broker receipts;
- add only current-state bridge markers on the task row;
- force the broker request to `local_only=True`;
- pass no `guardian` object, so capability execution is outside this bridge;
- submit successful results into the existing verifier lifecycle;
- never submit a stale captured result after its producer lease expires.

Crash behavior:
- started/no receipt: outcome unknown, requeue so the next claim becomes a new attempt;
- result captured/live lease: retry verification submission without another inference call;
- result captured/expired lease: existing reclaim semantics create a new attempt;
- verifying/submitted: verifier lifecycle owns the task.

No runtime worker loop, provider activation, merge, deployment, external write, protected write, permission expansion, private-data expansion, or governance release is added.

Verification target: exact branch head after this handoff commit. Required evidence is repository CI plus independent falsification before any acceptance claim.
