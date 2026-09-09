# AUTOPILOT-004 verifier atomic-claim handoff — run 020

## Task

- Issues: #16 (AUTOPILOT-004A), #17 (AUTOPILOT-004B)
- PR lane: #15, `autopilot-004-verifier-lifecycle-impl`
- Objective: close the exact-head CI failure and require independent-verifier
  eligibility at the ledger claim transition.

## Starting state

- Starting SHA: `a64349434419214e26048ab6682b82a930a2558a`
- Isolated implementation branch: `codex/guardian-004b-ci-fix`
- Existing subsystem: `elysia_collective_seed/autopilot/task_ledger.py`
- Initial CI-equivalent seed test result: 40 passed, 3 failed. All three
  failures expected `active_lease` but received `state_not_claimable`.

## Implementation

- `VerificationDecision` now records the producer identity for which it was
  issued.
- `TaskLedger.claim_verification()` fails closed without an affirmative
  decision, when the selected verifier differs, or when the decision belongs
  to a different producer attempt.
- Same-group and missing-group selector outcomes cannot acquire a ledger lease.
- Active execution leases are classified as `active_lease` before the generic
  non-claimable-state fallback, repairing the reproduced seed-suite failure.

## Tests

- Focused verifier, migration, and lifecycle suite: 13 passed.
- CI-equivalent `python -m pytest -q elysia_collective_seed`: 43 passed.
- Python compileall for changed implementation/test surfaces: passed.
- `git diff --check`: passed (Git emitted only line-ending conversion warnings).
- Implementation commit: `e6a2fa5df9fc51a5c991d7fd74e1c4bcb9e2ac34`.
- Exact implementation-head GitHub Actions run: `34411704839`, Elysia
  Autopilot CI run 144, `seed-validation` passed in 17 seconds.

The local runner used pytest 8.3.5 directly from temporary wheel paths and an
explicit worktree-local `--basetemp` because the host's default pytest temp
directory was inaccessible.

## Evidence and risks

- Direct ledger calls can no longer bypass a blocked/missing verifier decision.
- A decision is bound to both the selected verifier and current producer.
- This remains a local deterministic primitive. It does not invoke providers,
  wire Guardian runtime, post externally, deploy, merge, or expand data access.
- The decision object is not a cryptographic capability. Any future process or
  network boundary must replace it with a persisted or signed authorization
  artifact rather than trusting serialized caller input.

## Verification request

Independently verify the exact commit produced by this handoff, rerun the 13
focused tests and 43 seed tests, and confirm that fabricated/missing/mismatched
decisions cannot acquire a verifier lease. Keep PR #15 draft and unmerged until
exact-head CI is green and the authority-boundary review passes.
