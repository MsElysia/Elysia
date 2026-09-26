# Issue #83: PR #82 broker result identity repair

Task: PR82-BROKER-RESULT-IDENTITY. Worker: Codex. Date: 2026-09-26.
Implementation complete locally; fresh independent Vega verification requested for the resulting commit. No independent PASS claimed.

## Authority and isolation

Newest explicit checkpoint read before changes: CURRENT ENGINEERING CHECKPOINT, 2026-09-26, Issue #11 comment 5849391026:
https://github.com/MsElysia/Elysia/issues/11#issuecomment-5849391026

Read Issue #83 and Vega report PR #82 comment 5849389367. Inspected live PR metadata: draft PR #82 remains at d619bcc06dd0b9c75d15c3553c607fc2f94b9854. That is the exact starting parent of this repair.
Repair branch: codex/pr82-broker-result-identity-repair.

Files read: AGENTS.md; orchestration_bridge.py; task_ledger.py bridge capture/recovery, release and event paths; existing bridge tests; project_guardian/orchestration/types.py PipelineResult; CI workflow; original Vega breaker.
Files changed:
- elysia_collective_seed/autopilot/orchestration_bridge.py
- elysia_collective_seed/autopilot/test_orchestration_bridge.py
- breaker_tests/test_vega_pr82_broker_result_identity.py (copied unchanged)
- breaker_tests/test_vega_pr82_throwing_identity_accessor.py (Vega follow-up breaker, copied unchanged)
- elysia_collective_seed/autopilot/handoffs/PR82-BROKER-RESULT-IDENTITY-REPAIR.md

## Invariant and failure handling

Immediately after broker return, before reading output or constructing the receipt, require a nonempty exact built-in string result.task_id and an exact built-in string expected task_id, with exact equality. No coercion, result mutation or output relabeling occurs. Ordinary exceptions reading task_id are contained and mapped to rejection. Missing attributes default to rejection; malformed values and hostile string subclasses reject before equality.

Mismatch returns BridgeRunResult(submitted=False, state='result_identity_mismatch', error='broker_task_identity_mismatch') without a digest. No receipt, completion packet, capture call or verification submission occurs. The existing durable broker_execution_started event remains and no downstream database mutation occurs. There is no dedicated rejection-event API in this bridge; preserve its established started/no-result recovery path rather than introduce a ledger API or store any mismatched result fields. After reopen, retry requeues the unknown attempt without invoking the broker; a fresh claim permits the next attempt.

Correctly bound ordinary broker failures retain their existing capture/requeue behavior. Correctly bound successful results retain normal capture and verifier submission.

## Evidence

Original breaker retained byte-for-byte from f6c016f702eb30327672714f0b983bf70341697b, path breaker_tests/test_vega_pr82_broker_result_identity.py. Confirmed failure 1/1 before repair (submitted=True), pass after repair.

Focused command: python -m pytest -q elysia_collective_seed/autopilot/test_orchestration_bridge.py breaker_tests/test_vega_pr82_broker_result_identity.py
Current focused coverage: 28 tests pass within the full run (5 inherited bridge tests, 21 new regressions, 2 retained breakers).

Full inherited CI selection plus breaker:
python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py breaker_tests/test_vega_pr82_broker_result_identity.py
Latest result: 170 passed with both breaker_tests files selected, including all 147 inherited tests unchanged.

Compileall, seed JSON parsing, runtime-disabled prompt guard, git diff --check: pass.
Tests used C:/Users/Owner/Project guardian/.venv/Scripts/python.exe, entirely synthetic brokers; no live model execution.

Traps prove zero capture calls, zero completion-packet construction, and zero verification submissions for wrong/malformed IDs. Database dumps immediately before broker return and after rejection are identical. Output sentinel absent from all durable records. Tests cover empty/null/missing/non-string IDs, equality-spoofing and throwing string subclasses, original-object identity preservation, close/reopen recovery, and successful exact-ID submission on a fresh attempt.

Existing local_only routing and no-Guardian-argument tests pass; added authority-requirement refusal tests pass. Product delta is twelve lines in the existing bridge. No ledger/schema change, governance persistence, claim enforcement, authenticated-source repair, new adapter, capability execution, Git/external-write capability or runtime wiring.

## Independent review follow-up

Vega independently returned FAIL for 1b536988f687eab13e95df6fa11e1cd21e627aff: a throwing task_id accessor escaped as RuntimeError. Vega confirmed the original breaker and prior 166 tests passed, but preserved a new failing accessor breaker. This successor contains Exception only while reading task_id, preserving BaseException/process-control behavior. The new breaker is retained unchanged, and three additional CI-discovered traps prove RuntimeError/ValueError/TypeError accessors cause zero capture/packet/submission calls and zero database mutation after broker return. Latest full run: 170 passed. Fresh independent exact-head verification requested again; the earlier FAIL is not treated as acceptance.

## Handoff

Exact resulting SHA: obtain with git rev-parse HEAD on this branch (commit cannot contain its own SHA); also reported in the chat handoff.
Exact-head hosted CI: unavailable for this local unpushed repair; predecessor CI does not transfer.
Fresh Vega request: independently falsify the resulting exact commit, rerun the original breaker, probe alternate identity bypasses and recovery, and verify unchanged read-only authority. Do not transfer previous verdicts. Keep all merge/deployment/provider/capability/external-write authority disabled.

Broker task identity binding: ENFORCED
Wrong-task result durable capture: BLOCKED
Wrong-task verification submission: BLOCKED
Capability execution authority: DISABLED
External write authority: DISABLED
