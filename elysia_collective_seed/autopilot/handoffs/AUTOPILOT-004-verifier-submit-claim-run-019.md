# AUTOPILOT-004 verifier submit/claim implementation checkpoint

Status: bounded implementation checkpoint
Scope: PR #15 / `autopilot-004-verifier-lifecycle-impl`

## Durable change
Implemented the first two persistent verifier lifecycle operations in the existing SQLite `TaskLedger`:

- `submit_for_verification(...)` requires the producer's live execution lease, immutably binds `produced_by`, persists packet/evidence references, clears the execution lease, enters `verifying`, and records `producer_completion_submitted`.
- `claim_verification(...)` uses a separate verifier lease, forbids producer self-verification, refuses competing live verifier claims, permits owned renewal and expired-lease replacement, and does not increment the producer execution attempt count.
- `get(...)` now exposes the bounded verifier lifecycle fields needed for deterministic tests and audit inspection.

Implementation commit: `a5be458c024b603914f6df5b5270b3923a743552`.

## Safety boundary
This remains local SQLite state-transition code only. It does not invoke providers, execute Guardian runtime code, merge/deploy, post externally, access credentials/private chatlogs, or expand private-data authority.

## Verification status
No passing-test claim is made in this checkpoint. Existing lifecycle tests should now exercise submit/claim behavior; exact-head test evidence is still required.

## Handoff
Next bounded step: implement active-owner `accept_verification`, bounded `reject_verification`, and `reap_expired_verification`, preserving producer packet/evidence and attempt counts. Then run the migration plus ten lifecycle tests on the exact PR head and keep PR #15 draft until independent review confirms the authority boundary.
