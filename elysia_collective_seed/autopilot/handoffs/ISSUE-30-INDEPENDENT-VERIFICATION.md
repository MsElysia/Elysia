# Independent checkpoint contract breaker report

Verdict: **PASS**, limited to the normative schema and pure checkpoint oracle at exact candidate **0843d9cad29a632a42946a5daf4abe4d0b93bdb0**.

Date: 2026-09-11. Role: fresh independent breaker sub-agent. No implementation authorship, architecture certification, external publishing, runtime/provider activation, or gate release performed.

## Candidate and evidence isolation

Base: e67deaa0d7a321d261a3ad7f64ee9991e19a469a.

Candidate: C:/Users/Owner/guardian-governance-checkpoint-contract. Its HEAD was checked before and after verification; worktree remains clean and unmodified.

Independent detached worktree: C:/Users/Owner/guardian-checkpoint-breaker-evidence, HEAD 0843d9cad29a632a42946a5daf4abe4d0b93bdb0.

Preserved independent adversarial tests: C:/Users/Owner/guardian-checkpoint-breaker-evidence/breaker_tests/test_independent_checkpoint.py. These are intentionally untracked verification evidence outside the candidate, not changes to the tested product.

Read independently: user task packet, AGENTS.md, full new schema/oracle/test/README/handoff files, candidate file inventory and workflow diff. Searched adjacent autopilot/tests references for production imports or misleading enforcement paths. Implementer counts were not accepted as verification; suite was rerun.

## Executed commands and results

From candidate: `git worktree add --detach C:/Users/Owner/guardian-checkpoint-breaker-evidence 0843d9cad29a632a42946a5daf4abe4d0b93bdb0`.

From independent detached worktree:

```powershell
& C:/Users/Owner/guardian-governance-checkpoint-contract/.venv/Scripts/python.exe -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_autopilot_claim_policy.py --tb=short
```

Result: **328 passed**, 4.72 seconds; Python 3.13.15, pytest 9.1.1. Includes 115 candidate contract tests and 213 existing tests.

```powershell
& C:/Users/Owner/guardian-governance-checkpoint-contract/.venv/Scripts/python.exe -m pytest -q breaker_tests --tb=short
```

Result: **47 independent tests passed**, 4.31 seconds. Twenty generated-DAG tests each compare 24 entities against an independently computed ancestor model (480 graph decisions).

From candidate: `git diff --check e67deaa0d7a321d261a3ad7f64ee9991e19a469a 0843d9cad29a632a42946a5daf4abe4d0b93bdb0` passed; `git status --short` empty; `git rev-parse HEAD` exact candidate above. Independent worktree status contains only breaker_tests as untracked evidence.

## Falsification coverage and findings

No blocking defect found within the bounded contract.

- Independently generated DAGs exercise random multi-parent ancestry, objective-only and lineage-only matching, explicit inherited references, unordered storage, multiple gates and unaffected entities. Exact gate/generation output matched an independent ancestor walk.
- A 1,100-level reverse-ordered chain remains blocked without recursive ancestry failure.
- Malformed and disconnected graph records invalidate even a read request; disconnected cycles do not escape validation.
- Renamed child scope cannot erase admitted parent scope.
- All seven mandatory write/claim action classes remain blocked with stored `released` state and no release claim, including an omitted-gate newer checkpoint. This fixture's checkpoint identifier was supplied by the coordinator's refresh, and its prose is synthetic: no independent claim is made here about live GitHub comment contents.
- Independently current pins reject omitted gates, prior generation replay, changed release state, changed scope and erased child ancestry.
- A second released gate that also blocks read remains effective, with exact generation reporting.
- A worker-selected omitted snapshot and matching worker-selected pin produce NO_MATCHING_BLOCK_NOT_AUTHORIZATION. This intentionally demonstrates the documented unimplemented source/authentication boundary; it does not authorize any action.

## Limitations and next role

This PASS proves diagnostic comparison semantics under independently admitted metadata and a trusted current pin. It does not prove source completeness/authenticity, trusted proposal classification, canonical objective naming, generation monotonicity in storage, atomic freshness at mutation, SQLite/restart/concurrency interlocks, human proof validation, repository writes, integration, merge, or deployment enforcement. Every decision continues to report UNAVAILABLE human release validation and NOT_ENFORCED external writes.

Portable JSON roundtrips are not durable production restart verification. The existing ledger tests passed but this candidate does not integrate the oracle into that ledger. Tests ran locally on Python 3.13; configured GitHub Python 3.12 CI was not executed. No cross-lineage PASS transfer or Issue #23 release is implied; Issues #29/#30/#31 remain open implementation/governance work.

Next required role: separate architecture reviewer on this exact SHA. Publishing, merging, semantic porting, provider activation and human trust-anchor selection remain outside this verdict.
