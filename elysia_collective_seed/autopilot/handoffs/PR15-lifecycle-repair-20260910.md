# PR #15 lifecycle repair handoff

Status: implementation complete; independent Vega re-verification requested.
Target: `autopilot-004-verifier-lifecycle-impl`, issues #20, #19, #21 (in that repair order).
Starting product head: `46f77f5dd0fe594d30b1f3e9e5573c8d7ad37f1e`.
Vega evidence/tests retained from `1326aa7` without changes.
Implementer: Codex; separate from the requested final Vega verifier.

## Changes and policy

1. **#20:** Generic release cannot complete consequential writes or unknown-risk work, and requires the current unexpired execution lease. Direct read-only completion remains available only without human, review-role, required-check or verification-capability gates. Generic release cannot create a metadata-free `verifying` row. Producer submission is the only execution-to-verification transition.
2. **#19:** Two additive SQLite columns snapshot execution and rejection budgets. Execution policy is validated from the admitted task's positive integer max_attempts (default 3); verification uses the persisted system ceiling of 2. The legacy max_rejections argument remains accepted for source compatibility but is ignored, including attempts to raise or lower it. Acquisition checks and mutation execute under BEGIN IMMEDIATE. Exhausted acquisition, retry release/reap and rejection route to human_review; live last-attempt renewal and successful verification remain permitted. Invalid legacy limits yield zero budget and fail closed on acquisition. Existing historical rows/events are retained.
3. **#21:** Successful validated completion calls submit_for_verification, binds the current live producer lease, and persists producer ID, supplied packet ID (or deterministic SHA-256 ID for legacy packets), evidence references and check results. Submission audit records include attempt and producer lease expiry. Required checks come from the persisted task as well as caller requirements. Explicit packet/evidence fields are represented in the completion schema and malformed evidence is refused.
4. CI explicitly collects the verifier, migration, lifecycle, unchanged Vega and repair suites alongside seed tests. PRs targeting autopilot branches trigger the workflow, and checkout selects the exact source head rather than a synthetic merge ref.

**Admission boundary:** put_task is initial trusted task admission, not a worker permission-granting operation. Subsequent upserts preserve the entire original payload and status, including queued metadata; they only update timestamp and append an event recording actual/requested status. This prevents callers changing risk, retry policy, required checks or state through an upsert. There is no new authority-changing update API. Direct SQLite mutation and arbitrary hostile Python code in the orchestrator process are not security boundaries claimed by this patch.

## Files read and changed

Read AGENTS.md, Vega report/tests, PR metadata, lifecycle/state/orchestrator contracts, task/completion schemas, ledger/dispatcher/bridge/validator, seed and root verifier/migration/lifecycle tests, and CI workflow. Changes are restricted to task_ledger.py, dryrun_orchestrator.py, completion_validator.py, completion_packet_schema.json, CI, new repair regressions, one seed-test setup, and this handoff.

The existing stale-payload regression previously created a completed write through the forbidden release bypass. Its setup now submits and independently verifies the write; all original stale-input assertions remain. Vega's six tests and existing root lifecycle/migration/selector tests are unchanged. No tests are skipped or xfailed.

## Validation

Python 3.12.14 / pytest 9.1.1 on Windows. Full acceptance suite before commit: **92 passed** (43 seed, 17 existing focused, 6 Vega, 26 repair).

```text
python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py
python -m compileall -q elysia_collective_seed tests/test_autopilot_lifecycle_repairs.py
git diff --check
```

Local runner: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`; PYTHONPATH points to existing isolated `.worktrees/vega-test-15/.vega-deps`, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, with fresh worktree-local basetemp. Elevated test execution is necessary for this machine's dependency-file ACLs; tests use only synthetic SQLite, no providers or live runtime.

New regressions cover unknown/write/read-only release, stale lease denial, immutable admission policy, malformed retry limits, concurrent expired acquisition, persisted rejection ceilings regardless of caller argument, packet/check/evidence/lease provenance across reopen, deterministic legacy packet identity, persisted required checks, malformed evidence, expired completion and legacy migration/retry preservation.

An independent pre-handoff agent reviewed the working diff and separately ran all 6 Vega plus 26 repair cases: **32 passed**, no blocking findings. This is not final exact-head Vega certification. Final commit SHA, post-commit test result and hosted exact-head CI receipt will be posted on PR #15 and master issue #11 after publication, avoiding a self-referential commit hash in this file.

## Independent Vega request

Verify the published exact PR head against all three issues and the unchanged 1326aa7 falsification cases. Specifically attempt release/upsert bypasses, rejection-limit overrides, expired and concurrent acquisitions, database reopen, required-check omission and validated producer-to-independent-verifier acceptance. Confirm event provenance survives rejection/retry and that CI collects the root tests. Record PASS/FAIL/PARTIAL/BLOCKED/NEEDS_REVIEW independently. Keep issues open pending that verdict.

## Limits and next action

No providers, Guardian runtime wiring, merges, deployment, permission expansion or unrelated features were added. This patch does not certify all Guardian governance. The prior verifier-claim/accept concurrency question and process-local registry trust remain outside these three repairs. If Vega confirms these repairs, queue any separate verified defects as bounded tasks; do not broaden this patch or activate the runtime.
