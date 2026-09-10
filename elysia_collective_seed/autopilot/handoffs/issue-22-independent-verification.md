# Issue #22 independent verification: PASS after repair

Current verified candidate: `40964ee9e334d1974702e419dff28df7c87df587`.
The complete required suite (142 tests) plus 12 independently authored public-API
probes passed together: **154 passed in 2.63s**, Python 3.13.15, pytest 9.1.1.
All four previously failing packet conflicts now fail closed. A new positive
case proves a consistent full packet completes after SQLite reopen and its
original packet remains intact. The other seven independent negative/positive
cases remain passing. No production changes or tracked changes in this worktree.

Retest command (same worktree and interpreter):

```powershell
& 'C:/Users/Owner/Project guardian/.venv/Scripts/python.exe' -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_issue22_independent_verification.py
# 154 passed in 2.63s
```

`git rev-parse HEAD` confirms the exact new SHA. The original six Vega tests
still have blob `48ce7e0de67579ed916f069a688d25d462a5dd88`, matching `9b41a961`.
Additional files read for retest: completion_validator.py and repaired
task_ledger.py. Next role: independent reviewer for exact candidate
`40964ee9e334d1974702e419dff28df7c87df587`; no merge/deploy/runtime approval implied.

## Prior failed candidate retained for provenance

Candidate: `7c2a51ac0ea91ee7973104ade4dd616c5e4c54d4`.
Worker: independent Codex verifier agent `/root/verify_22`.
Detached worktree: `C:/Users/Owner/guardian-remote-verify-22`.
Interpreter: `C:/Users/Owner/Project guardian/.venv/Scripts/python.exe` (Python 3.13.15).

The exact candidate passes all 130 workflow tests, but an additional public-API
regression demonstrates inconsistent completion data can be accepted. A submission
whose `completion_checks` marks the required `bytes` check pass and whose
`completion_packet.checks` marks that same check fail is accepted and completed.
The resolver independently verifies a real temporary artifact, its persisted
hash report, the exact submission digest, and the passing top-level check.
It does not correct contradictory packet metadata on the ledger's behalf.
Additional public-path probes also reproduce acceptance when the packet names a
different task, a different packet ID, or a blocked outcome.

The ledger records both versions, but `accept_verification` validates only the
top-level checks. Integrity binding does not establish semantic consistency.
Production fix recommendation: reject conflicting packet and explicit submission
fields at submission and/or acceptance; add regression coverage. Reviewer stage
must wait for repair and independent verification PASS of the new exact SHA.

## Executable evidence

From this worktree in PowerShell:

```powershell
& 'C:/Users/Owner/Project guardian/.venv/Scripts/python.exe' -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py
# 130 passed in 2.18s
& 'C:/Users/Owner/Project guardian/.venv/Scripts/python.exe' -m pytest -q tests/test_issue22_independent_verification.py
# 4 failed, 7 passed in 0.42s
```

Failure: `test_conflicting_completion_packet_and_checks_fail_closed` at line 92,
for all four parameters: `checks`, `task_id`, `packet_id`, `outcome`.
Seven successful cases cover missing artifact, invalid artifact bytes, missing
external report, expired producer lease, expired verifier lease, SQLite reopen
and duplicate acceptance, and stale submission digest across retry attempts.
All exercise public methods and actual temporary local files/databases. No SQL
tampering, network, provider calls, application boot, or production-code edits.

The original six `tests/test_vega_evidence_binding.py` tests remain byte-identical
relative to `9b41a961`: both Git blob IDs are
`48ce7e0de67579ed916f069a688d25d462a5dd88`; Git diff is empty.

Files read: AGENTS.md, issue-22-evidence-binding.md handoff, CI workflow,
task_ledger.py, test_vega_verifier_boundaries.py, test_autopilot_evidence_binding.py,
evidence_fixture.py. Changed: only this report and the new independent test file.
Uncertainty/limit: local SQLite contract only; trusted evidence authority is test
setup and is not a production proof adapter. No deployment/runtime authority is
assessed or enabled.
