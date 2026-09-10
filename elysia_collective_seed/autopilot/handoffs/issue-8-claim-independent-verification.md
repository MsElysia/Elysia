# Independent Agent C verification: PASS

Task: AUTOPILOT-004 / issue #8 execution-claim policy repair.
Exact verified commit: `e67deaa0d7a321d261a3ad7f64ee9991e19a469a`.
Detached worktree: `C:/Users/Owner/guardian-remote-verify-claim`.
Worker: independent Codex verifier Agent C; no implementation authorship, production edits, push, merge, deployment, provider call or runtime activation.

## Evidence

Python 3.13.15, pytest 9.1.1 from `C:/Users/Owner/Project guardian/.venv/Scripts/python.exe`.
Final exact-commit run: **359 passed in 5.49s** (required 213 existing tests plus 146 independent probes). No skipped or expected-failure tests.

Reproduce in this worktree:

```powershell
& 'C:/Users/Owner/Project guardian/.venv/Scripts/python.exe' -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_autopilot_claim_policy.py independent_claim_regression.py
```

`independent_claim_regression.py` is independently authored and executable. It tests policy and worker eligibility on new claims, live legacy renewals and expired legacy recovery; protected and human-gated tasks; malformed collections, booleans, risk and legacy payloads; unknown/missing registry; all non-completed dependency states; payload-status forgery; missing/self dependencies; reopen without authority; restored registry; last-attempt renewal and exhausted retry routing; reap and reacquisition; caller worker/state spoofing and stale selection; eligible non-preferred worker; producer ownership and independent completion gates.

Denied direct calls compare every durable task column and event row before/after. A SQLite trace callback at the actual lease UPDATE attempts second-connection dependency and policy changes: both writers remain locked until the claim transaction finishes. Another probe changes dependency state after bridge selection but before the real claim: mutation is denied with zero consumed attempts. Concurrent independent connections competing for ownership yield one success and one consumed attempt.

## Inputs and changes

Read root AGENTS.md; implementation handoff issue-8-claim-policy.md; Agent A CLAIM_BOUNDARY_HANDOFF.md; task_ledger.py; dispatcher.py; dryrun_orchestrator.py; existing claim and lifecycle tests; workflow elysia-autopilot-ci.yml. Only files created by this verifier are independent_claim_regression.py and this report. Tracked files remain unmodified.

## Limits and next role

PASS covers local temporary SQLite behavior at the exact SHA, not hosted CI execution or hostile process authentication. Constructor registries, task admission, arbitrary Python and administrative SQLite mutation remain trusted boundaries. No known acceptance defect found. Separate followup-scope validation stays outside this repair. Next: a distinct reviewer examines this exact candidate and evidence before any integration decision; preserve draft status pending review.
