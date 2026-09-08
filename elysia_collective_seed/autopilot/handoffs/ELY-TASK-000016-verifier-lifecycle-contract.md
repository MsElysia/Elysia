# ELY-TASK-000016 handoff

Task: Define the independent verifier lifecycle required by AUTOPILOT-004 acceptance evidence.
Branch: `autopilot-004-verifier-lifecycle-contract`
Base: `autopilot-004-dispatcher-foundation`

## Completed

Added `verifier_lifecycle_contract.md`, defining producer-to-verifier state boundaries, writer/verifier separation, verifier eligibility/lease semantics, accept/reject behavior, retry/human-review routing, audit preservation, and ten required executable tests.

## Evidence

Contract commit: `74690adf5892e46b59defb3c7d1e33dd73123117`.

The contract was derived from the AUTOPILOT-004 acceptance-gap audit and the existing ledger behavior where producer completion stops at `verifying`. It is specification-only and does not alter runtime behavior.

## Safety

No provider calls, GitHub synchronization writer, Guardian runtime integration, network/subprocess execution, merge, deployment, external posting, credential access, private-chatlog access, or authority expansion was enabled.

## Next bounded task

Implement the contract on a fresh isolated child branch using deterministic local SQLite state only. Add executable tests for writer self-verification refusal, independent verifier claim, accept/reject paths, stale/wrong-worker refusal, verifier lease expiry/reclaim, retry/human-review routing, and audit reconstruction. Then obtain independent CI/review before incorporating any implementation into Draft PR #12.
