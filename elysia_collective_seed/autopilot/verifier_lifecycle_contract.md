# Independent verifier lifecycle contract

Status: specification-only, runtime-disabled
Scope: AUTOPILOT-004

## Purpose

Define the minimum deterministic ledger behavior required to route consequential write work from producer completion through an independent verifier without allowing the producer to self-approve or silently broaden authority.

## Preconditions

- The producer has an active execution lease for the task.
- The submitted completion packet passes the repository completion-packet validator.
- The task's risk/authority class has not increased relative to its approved task packet.
- Any required human approval remains authoritative and cannot be replaced by verifier approval.

## Producer submission

For a write task, accepted producer submission MUST:

1. append an auditable `producer_completion_submitted` event containing packet/evidence identifiers, never secrets or private chat content;
2. release the producer execution lease;
3. transition the task to `verifying`;
4. persist the producer worker ID as `produced_by` (or equivalent immutable verification metadata);
5. prevent normal execution dispatch while verification is pending.

Producer submission MUST NOT transition a consequential write task directly to `completed`, `integrated`, deployed, merged, or any equivalent terminal/integration state.

## Verifier eligibility and claim

A verifier claim is eligible only when:

- task status is `verifying`;
- verifier worker ID differs from `produced_by`;
- verifier capability satisfies the task's verification capability/risk requirements;
- the worker is available under the worker registry;
- no unexpired verifier lease exists;
- any human/governance gate remains satisfied independently.

The producer MUST be rejected with reason `self_verification_forbidden` if it attempts to claim verification of its own consequential write.

Verifier claims SHOULD use a separate verification lease or equivalent claim record so execution leases cannot be confused with review authority.

## Verifier acceptance

A verifier acceptance MUST:

1. require an active verifier claim owned by the accepting worker;
2. record evidence references and an auditable `verification_accepted` event;
3. release the verifier claim/lease;
4. advance only to the task's pre-authorized post-verification state;
5. preserve human/governance gates and never imply merge, deployment, external posting, secret access, or broader authority.

For the current runtime-disabled seed, the safe post-verification state SHOULD be `completed` only for bounded local/specification/test work whose task packet already authorizes that terminal state. Integration into protected branches remains a separate gated action.

## Verifier rejection

A verifier rejection MUST:

1. require an active verifier claim owned by the rejecting worker;
2. append `verification_rejected` with bounded reason/evidence metadata;
3. release the verifier claim/lease;
4. return the task to `queued` when retry budget remains and no new human decision is required;
5. transition to `blocked` or `human_review` when retry budget is exhausted, evidence is contradictory, or resolution would require authority expansion.

Rejection MUST NOT discard the producer completion packet or prior evidence.

## Retry and lease rules

- Expired verifier leases may be reaped without altering producer evidence.
- Reclaiming verification does not increment the producer execution attempt counter.
- Repeated verification rejection must obey the task's bounded retry policy and cannot hot-loop indefinitely.
- A verifier cannot mutate the task objective, risk class, private-data scope, deployment authority, or acceptance criteria.

## Required executable tests

The implementation is not acceptance-complete until tests prove:

1. valid writer submission enters `verifying` and releases writer lease;
2. writer cannot claim its own verification;
3. a distinct eligible verifier can claim verification;
4. verifier acceptance produces the authorized post-verification state and audit event;
5. verifier rejection safely requeues when retry budget remains;
6. rejection blocks/routes to human review when retry/authority policy requires it;
7. stale or wrong-worker verifier decisions are refused;
8. expired verifier lease can be reclaimed without losing completion evidence;
9. no verification path proposes merge/deploy/external-post/private-data authority;
10. the full transition history is reconstructable from persistent ledger state/events alone.

## Safety boundary

This contract authorizes no provider calls, GitHub writes, Guardian runtime wiring, subprocess/network execution, deployment, merge, external posting, credential access, or private-chatlog access. Implementation must remain deterministic/local-only until the canonical Guardian runtime and governance gates permit broader integration.


## Issue #22 persisted submission binding

The SQLite implementation stores additive `completion_submission_json`,
`completion_submission_digest`, `verification_submission_digest`, and
`verification_supplemental_evidence_json` columns. The canonical submission
includes the full supplied completion packet and check records, evidence source
classes, packet identity, producer, attempt, execution lease expiry, admitted task
policy, and retry limits. Its SHA-256 digest identifies and detects modification
of the snapshot; it is not proof of work or an authenticated signature.

Acceptance requires `expected_submission_digest` matching both the persisted
submission and the verifier claim, intact current identity/policy, unique passing
required checks, current trusted registry eligibility, and a live independent
verifier lease. Snapshot validation, the completion transition, and its event
occur in one SQLite immediate transaction. Supplemental verifier references may
be empty and cannot replace the submitted evidence. Missing snapshots on legacy
rows remain readable/rejectable but cannot be accepted; migration does not invent
proof or rewrite historical events.

The trusted ledger constructor's `evidence_validator` is an explicit authority
boundary. It receives a detached JSON snapshot, must return exactly `True` after
resolving substantive artifact/claim/commit/PR evidence and independently recorded
checks against the same submission, and must be local/deterministic. Packet IDs
and bare SHA-256 values never count as substantive evidence. Reference classes
and spellings alone prove nothing. The default is no resolver and acceptance is
denied. Unknown/protected risk, human approval, or required review roles without
an implemented role authority remain denied even with a successful resolver.
No production resolver, network proof fetch, provider invocation, or runtime
integration is introduced. A constructor-installed resolver is trusted code;
installing one that returns True without checking evidence violates this API
contract. Tests use actual local artifact bytes and an independently controlled
check report bound to the exact submission digest.

Legacy direct submissions with unverified references may enter `verifying` for
inspection/rejection, but this does not certify evidence. The bridge rejects
completed packets lacking evidence instead of treating their self-hash as proof.
