# AUTOPILOT-004 verifier lifecycle acceptance gap

Status: supervisor verification checkpoint
Scope: PR #15 / `autopilot-004-verifier-lifecycle-impl`

## Evidence reviewed

- `verifier_lifecycle_contract.md` from the reviewed contract branch.
- `verifier.py` at PR #15 head before this handoff.
- PR #15 metadata and exact head `611664b1a35d81947a66fa2aaf9f8a5f80cb959f`.

## Implemented and bounded

`select_verifier()` is deterministic and runtime-disabled. It rejects the producer, unavailable workers, unsupported risk/capability routes, missing verifier independence metadata, and same-independence-group workers. It selects only a distinct eligible verifier and grants no merge/deploy/external-write/private-data authority.

## Acceptance gaps against the reviewed contract

PR #15 is not acceptance-complete. The following contract requirements still need executable ledger behavior and tests:

1. Producer submission must persist evidence identifiers, release the producer execution lease, record immutable `produced_by`, enter `verifying`, and prevent normal execution dispatch.
2. Verification needs a distinct persistent lease/claim with owner and expiry; an unexpired verifier lease must block competing claims.
3. Acceptance/rejection must require the active verifier-lease owner; stale and wrong-worker decisions must fail closed.
4. Acceptance must append `verification_accepted`, release the verifier lease, and advance only to the pre-authorized post-verification state.
5. Rejection must append `verification_rejected`, preserve producer packet/evidence, release the verifier lease, and either requeue within bounded retry policy or route to `blocked`/`human_review`.
6. Expired verifier leases must be reclaimable without incrementing producer execution attempts or deleting producer evidence.
7. Persistent state/events must be sufficient to reconstruct the full transition history.
8. Tests must explicitly prove no verifier path grants or proposes merge, deploy, external-post, credential, or private-data authority.

## Implementation constraint

Implement these pieces by composing with the repository's existing deterministic local ledger/SQLite primitives where available rather than creating a second competing task ledger. Keep provider adapters and Guardian runtime wiring disabled. Do not change task objective, risk class, private-data scope, deployment authority, or acceptance criteria during verification.

## Verification gate

Do not mark PR #15 acceptance-complete or integrate it into the dispatcher lane until all ten executable tests named in `verifier_lifecycle_contract.md` pass on the exact PR head and an independent review confirms the authority boundary.

## Handoff

Next bounded step: extend the local persistent ledger with verifier-lease claim/expiry plus producer submission, accept, and reject transitions; then add the contract's ten executable tests. If existing ledger APIs conflict with this contract, preserve the contract and record the incompatibility rather than silently weakening either side.

No merge, deployment, provider invocation, external posting, credential/private-chat access, destructive archive action, or authority expansion was performed in this checkpoint.
