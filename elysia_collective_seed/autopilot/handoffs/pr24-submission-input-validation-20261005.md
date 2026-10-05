# PR #24 direct submission check validation

Base: PR #24 exact `40964ee9e334d1974702e419dff28df7c87df587`.
Branch: `codex/pr24-submission-input-validation-20261005`.
Worker: Codex implementation; independent review recorded below.

## Defect and repair

Direct `submit_for_verification` accepted malformed completion checks and
released the producer execution lease. Falsey values such as `False`, `0`,
empty strings, dictionaries and tuples were silently normalized to empty lists.
Other invalid entries were persisted as the submission under review. Reject
malformed containers, blank/missing names and unknown/non-string results before
any transaction or lease mutation. Only `None` retains omission compatibility.
Known fail/skip/not_run results remain auditable; existing acceptance policy
still determines whether checks qualify for completion.

This is a local child candidate, not incorporation into PR #15. Existing #22
evidence/independence/lease/governance gates remain unchanged. Later reconciled
evidence-risk branches are separate; their PASS is not transferred to this head.

## Files

Read: AGENTS.md; Issue #11 checkpoint and PR #24 metadata; ledger, completion
validator, evidence fixture, verification tests and CI workflow.
Changed: task_ledger.py, test_autopilot_evidence_binding.py, this handoff.

## Evidence

Python 3.12.14 / pytest 9.1.1.
Before repair: 20 new public-API regressions failed on product assertions.
After repair: required suite **162 passed** (142 existing + 20 new).

```sh
python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py
```

New cases assert unchanged task row and event history, both live and after
SQLite reopen, followed by successful corrected submission under the original
lease. Existing test assertions are unchanged. Compileall, all seed JSON parsing,
runtime-disable gate and git diff --check passed.

## Review and limits

Independent reviewer PASS: 93 focused tests plus five additional disposable
SQLite reopen probes. None/empty-list compatibility, fail/skip/not_run audit
preservation and required-check acceptance denial were independently checked.
No blocking scoped finding; no tracked reviewer edits. No hosted exact-head CI
claimed for this child.
Trusted resolver installation and historical reconciliation remain separate
requirements; this repair does not create a production evidence adapter.
No merge, deployment, runtime/provider activation, live-memory mutation,
TaskLedger/executor wiring, permissions or governance release.

Next: exact-head hosted CI and integration-owner review before
any integration decision. Keep PR #15/#24 and any child draft and unmerged.
