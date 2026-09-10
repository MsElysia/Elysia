# Issue #8 execution-claim policy repair

Issue: AUTOPILOT-004 (#8), governed by master issue #11.
Branch: `codex/remote-fix-8-claim-policy`.
Base: reviewed #22 implementation `40964ee9e334d1974702e419dff28df7c87df587` (PR #24).
State: implementation/local tests complete; independent verification/review pending.
Worker: coordinating Codex acting as implementer after the implementation agent
hit the account usage limit. Independent boundary analysis preceded this change.

## Root cause and repair

The dispatcher checked human authority, risk, dependencies and worker eligibility,
but public `TaskLedger.claim` updated execution leases without those checks. Seven
independent baseline probes reproduced unauthorized acquisition, renewal and
recovery; bridge callers could also forge completed dependency state.

The ledger now owns a constructor-configured `execution_workers` registry. Missing
configuration denies execution. Every successful acquisition, renewal and expired
recovery checks validated admitted policy, registered worker availability/risk/
capabilities/allowed ID, and completed dependency rows within the same SQLite
immediate transaction. Eligibility is independent of dispatcher ranking. Live
last-attempt renewals preserve attempt accounting. Denied policy does not mutate
lease/attempt/history. Protected risk and human-approval tasks remain gated.

The bridge retains its states/workers parameters for source compatibility but
uses ledger dependency rows and trusted configuration instead. Caller descriptions
cannot establish authority. Shared policy validation rejects missing/unknown risk
and malformed safety fields without permissive defaults.

## Tests and compatibility

Command: `python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py
tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py
tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py
tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py
tests/test_autopilot_claim_policy.py` (one shell command).

Result: **213 passed**, Python 3.13.15/pytest 9.1.1; 142 inherited tests plus 71
direct policy, lifecycle, reopen, forged bridge state and transaction cases.
The transaction test attempts a concurrent dependency update after the dependency
read; SQLite refuses the writer until the claim transaction finishes.

Legitimate fixture workers are explicitly configured, and simple lease tasks now
specify their risk. Release/evidence tests for protected historical tasks seed a
test-only preexisting lease so their original downstream gate assertions remain.
The retry-migration scenario explicitly supplies admitted risk; unknown legacy risk
has a new denial regression. Concurrent budget tests use registered worker IDs.
No skips, xfails, reduced assertions or production permissive test mode introduced.
Original six issue-22 Vega test source remains unchanged.

## Remaining risk and next action

Registry configuration, initial task admission/import, Python process and direct
SQLite administrative access remain trusted boundaries. There is no worker
authentication protocol or approval-token implementation. Providers/runtime stay
disabled; no deployment or protected merge is enabled. #22 proof resolver remains
default-deny. Followup scope validation and issue #23 are separate queued work.

Next: independent verifier tests the exact committed SHA, then a different
reviewer returns READY_FOR_INTEGRATION_REVIEW or RETURN_FOR_REPAIR. Preserve draft
status and do not integrate until both stages complete.
