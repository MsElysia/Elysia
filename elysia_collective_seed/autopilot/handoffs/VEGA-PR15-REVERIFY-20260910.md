# Vega independent exact-head re-verification

## Target and verdict

**FAIL** — PR #15, `autopilot-004-verifier-lifecycle-impl`, exact product SHA
`6649b89adea44e3e7f41d37b55a7c82485beb6e6`.
Run: 2026-09-10 17:38–17:42 UTC. Verification branch: `codex/vega-reverify-15-22`.
Worker: separate Vega test-engineer subagent; not the parent task that implemented
the repair. No product code was modified by this verification worker.

The #19/#20/#21 repair slice is supported by executable evidence: all 92 required
tests pass, including the six original Vega tests from `1326aa7`, unchanged.
The overall lifecycle remains unsafe for evidence-based completion: six new
assertions reproduce the already-open #22 evidence-binding defect. Do not reopen
the old disconnected-bridge finding as though that repair failed; #22 is distinct.

## Inputs and scope

Read AGENTS.md; originating #8 acceptance criteria; issues #19, #20, #21 and #22;
state_transition_policy.md; verifier_lifecycle_contract.md; completion schema;
ledger, completion validator, bridge, selector call sites; original Vega report;
repair handoff; repair diff `git diff 1326aa7..HEAD`; lifecycle, migration,
boundary and repair tests; exact-head CI workflow. Local HEAD was checked before
tests and after checks. Coordinator fetched current repository state and confirmed
the GitHub head matches this SHA; it will recheck before publishing.

Only synthetic local SQLite and seed behavior were exercised. The isolated
worktree preserves unrelated root changes. Historical snapshot and whole Guardian
runtime readiness are not certified.

## Commands and results

Working directory: `.worktrees/vega-reverify-15-22` in the repository.
Python executable: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
Python 3.12.14, pytest 9.1.1, Windows. `PYTHONPATH`:
`C:/Users/Owner/Project guardian/.worktrees/vega-test-15/.vega-deps`;
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Elevated runner access was needed for installed
dependency ACLs, not for providers or live runtime. Fresh worktree-local basetemps.

| Command (python denotes executable above) | Purpose | Result |
| --- | --- | --- |
| `python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py --basetemp .vega-pytest-base` | Exact-head mandatory acceptance suite | 92 passed, 1.40s |
| `python -m pytest -q tests/test_vega_evidence_binding.py --basetemp .vega-pytest-evidence --tb=short` | #22 falsification, live connection and SQLite reopen | 6 failed, 0.21s; assertion failures, no environment errors |
| `python -m compileall -q elysia_collective_seed tests/test_vega_evidence_binding.py` | CI compilation | Succeeded |
| Python JSON parse of every seed `*.json`, plus CI's `RUNTIME_ENABLED = True` absence assertion | Remaining deterministic CI gates | Succeeded |
| `git diff 1326aa7 HEAD -- tests/test_vega_verifier_boundaries.py tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py` | Test weakening check | Empty diff |
| `git diff --check` | Whitespace check | Succeeded |

The single modified seed test replaces its forbidden producer-release setup with
submit/independent-claim/accept; its stale-payload assertions remain intact. No
skip, xfail, or relaxed original assertions were added. CI now explicitly collects
the six Vega cases and root lifecycle/migration/repair tests and checks out the
PR source SHA. New #22 tests are preserved as failing tests on this evidence
branch; they are not yet in PR15's CI list.

## Claims tested

- Producer generic release is denied for write/unknown risk; authorized ungated
  read-only release still requires a live lease. Immutable upsert prevents risk
  downgrade and completion injection on existing tasks.
- Persisted execution budget and system rejection ceiling survive reopen;
  caller rejection arguments cannot raise policy. Exhausted release, expired
  acquisition and concurrent exhausted reacquisition fail closed to human review.
  Migration and append-only event retention tests pass.
- Validated completion now reaches persistent submit, releases the producer lease,
  retains producer/packet/evidence/check/lease provenance, and permits eligible
  independent verifier acceptance. Stale producer and self-review regressions pass.
- Substantive evidence admission and acceptance binding are not enforced (#22).

## Reproducible #22 failures

Preserved in `tests/test_vega_evidence_binding.py`; no product changes.

1. `test_packet_self_hash_is_not_substantive_write_evidence` (two cases): claim a
   repo_write task requiring unit check; apply a schema-valid completed packet
   reporting the check as passing with no commits, PRs, artifacts or claim evidence.
   Expected: submission refused or blocked/human_review. Actual: applied/verifying,
   packet ID and sole evidence both
   `sha256:b27994afb1a7029a65b55b3b2163c21c62d29c8ccb2b701c3e8c8a76808492db`.
   Close/reopen preserves the same state. Source: dryrun_orchestrator.py:151–164.
2. `test_verifier_acceptance_requires_persisted_submission_binding` (four cases):
   submit packet:A with artifact:A under a live producer lease; eligible independent
   reviewer claims; accept with `[]` or `["artifact:B"]`, with and without SQLite
   close/reopen before acceptance. Expected: denial of unbound acceptance. Actual:
   returns true, persists completed, releases verifier lease and appends accepted
   event containing empty/unrelated evidence. Producer artifact:A remains stored,
   but the acceptance does not identify or validate it. Source: task_ledger.py:212–217.

This is executable confirmation of existing #22, not a new duplicate finding.
The fixtures make no assertion that artifact:A is externally real; they isolate
missing binding to the admitted submission. Network lookup is neither required
nor performed. Specific evidence classes remain underspecified and must be
defined by the bounded repair. Mere string comparison cannot establish reality.
Fake-commit/resolver behavior and every evidence class are not covered here.

## Runtime reachability and false-capability evidence

The local public bridge now executes
`validate_and_apply_completion -> submit_for_verification -> claim_verification
-> accept_verification -> SQLite state/events`, as the original and repair tests
demonstrate. The former disconnected local path is corrected. Search of the seed
and project_guardian Python call sites found no Guardian runtime invocation of
these methods. Runtime-disabled operation is explicit and appropriate, not a
false-capability finding. An evidence-based completion claim is unsupported:
the executable #22 cases demonstrate a completed row with no bound review evidence.

## Safety, confidence and limitations

No merge, deploy, force-push, provider activation, permission expansion, private
data exposure, or substantive product repair. Test identities/data are synthetic.
Confidence: **0.99** in the exact reproduced state transitions and repaired
original cases; not a probability of overall Guardian health. This is not
security against arbitrary in-process code/SQLite mutation;
initial task admission and registry configuration remain trusted. Concurrent
verifier claim/accept races and complete human-gate enforcement were not newly
certified by this pass. Existing green tests do not establish all governance.

## Smallest Astra repair and handoff

Use existing #22. Persist the validated submission/check/evidence object under
review; distinguish packet identity from substantive evidence; define deterministic
minimum evidence policy for the bounded task/risk; atomically require acceptance
to bind that submission and required checks, preserving supplemental verifier
evidence separately. Missing/unverifiable evidence must deny completion or route
to blocked/human_review. Retain append-only provenance and SQLite reopen coverage.
Do not introduce mandatory live network proof or enable providers. Add these
falsification cases to mandatory CI without weakening them; reconcile any fixture
updates with explicit evidence policy. Request independent Vega re-verification
on the next exact head, including all 92 original checks plus #22 regressions.

Erebus questions: what minimum local evidence classes satisfy each risk/task,
and what explicit acceptance binding identifies the submission/version being
approved? Which trusted gate attests required checks independently of producer
claims? Follow-up priority after #22: deterministic verifier-claim/accept races.

Coordinator owns deduplicated publication and reviewed-SHA/verdict references.
Keep PR15 draft/unmerged; original repair evidence can be recorded against
#19/#20/#21 without certifying the overall PR or closing #22.
