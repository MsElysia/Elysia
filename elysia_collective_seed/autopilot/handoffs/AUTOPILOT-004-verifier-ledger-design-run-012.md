# AUTOPILOT-004 verifier ledger implementation design

Status: supervisor implementation checkpoint
Scope: PR #15 / `autopilot-004-verifier-lifecycle-impl`

## Decision

Extend the existing `TaskLedger`; do not create a second ledger. Keep execution lease fields (`claimed_by`, `lease_expires_at`) separate from verification claim fields so review authority cannot be confused with execution authority.

## Minimal persistent schema extension

Add nullable task columns:

- `produced_by TEXT`
- `completion_packet_id TEXT`
- `completion_evidence_json TEXT`
- `verification_claimed_by TEXT`
- `verification_lease_expires_at TEXT`
- `verification_rejections INTEGER NOT NULL DEFAULT 0`

Evidence storage is identifiers/references only. No secrets, credentials, private chat text, or raw historical corpus belongs in these fields.

## Bounded ledger API

Implement these deterministic local-only operations:

1. `submit_for_verification(task_id, producer_worker_id, packet_id, evidence_refs, now=None)`
   - requires producer's active execution lease;
   - writes immutable `produced_by` on first submission;
   - persists packet/evidence references;
   - clears execution claim/lease;
   - enters `verifying`;
   - appends `producer_completion_submitted`.

2. `claim_verification(task_id, verifier_worker_id, lease_seconds=900, now=None)`
   - requires `verifying`;
   - rejects `verifier_worker_id == produced_by` as `self_verification_forbidden`;
   - requires caller eligibility to have been established by the verifier-routing layer;
   - renews only the owning live verifier lease;
   - refuses competing live claims;
   - permits reclaim after expiry without incrementing producer `attempt`;
   - appends `verification_claimed` / `verification_lease_renewed`.

3. `accept_verification(task_id, verifier_worker_id, evidence_refs, next_status='completed', now=None)`
   - requires active unexpired verifier lease owned by caller;
   - only allows a pre-authorized safe local post-verification state;
   - clears verifier claim/lease;
   - appends `verification_accepted`;
   - never grants/proposes merge, deploy, external-post, credential, private-data, or runtime authority.

4. `reject_verification(task_id, verifier_worker_id, reason, evidence_refs, max_rejections, require_human=False, now=None)`
   - requires active unexpired verifier lease owned by caller;
   - preserves producer packet/evidence;
   - increments bounded verification rejection count, not producer execution attempt;
   - requeues only while policy permits; otherwise routes to `blocked` or `human_review`;
   - clears verifier claim/lease;
   - appends `verification_rejected` with bounded metadata.

5. `reap_expired_verification(now=None)`
   - clears only expired verifier claims;
   - preserves `produced_by`, completion packet/evidence, producer attempt count, and `verifying` state;
   - appends `verification_lease_expired`.

## Invariants

- `claim()` remains unable to acquire `verifying` work.
- Producer execution attempt count is changed only by execution acquisition, never verifier claim/reclaim/rejection.
- `produced_by` cannot be silently replaced by a later verifier or retry path.
- Acceptance/rejection by a stale or non-owner worker fails closed with no state mutation.
- Human/governance gates are not satisfiable by verifier approval.
- Verification APIs do not mutate objective, risk class, source/private-data scope, deployment authority, or acceptance criteria.
- Existing event ordering remains sufficient to reconstruct producer submission, verifier claims/expiry, decision, and resulting state.

## Test mapping

Implement the reviewed contract's ten tests directly against a temporary SQLite ledger. Add explicit assertions that producer packet/evidence survive rejection and expired-verifier reclaim, that producer `attempt` is unchanged by verification operations, and that event order reconstructs the lifecycle without external state.

## Migration constraint

Because `_init_schema()` currently uses `CREATE TABLE IF NOT EXISTS`, adding columns only to the CREATE statement is insufficient for an existing SQLite file. The implementation must use an idempotent local migration (for example `PRAGMA table_info(tasks)` plus bounded `ALTER TABLE ... ADD COLUMN` for missing columns) and add a regression test opening a pre-extension ledger schema. Do not drop/recreate the table or discard historical events.

## Handoff

Next bounded implementation step: add the idempotent schema migration and the five ledger operations above, then implement the ten contract tests plus the existing-ledger migration regression. Keep PR #15 draft/unmerged until exact-head CI and independent review pass.

No provider invocation, Guardian runtime wiring, subprocess/network execution, merge, deployment, external posting, credential/private-chat access, destructive archive action, or authority expansion is authorized by this design.