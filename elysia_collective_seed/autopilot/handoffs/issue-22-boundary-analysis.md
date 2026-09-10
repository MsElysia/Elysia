# Issue 22 boundary analysis

Target product: 6649b89adea44e3e7f41d37b55a7c82485beb6e6. Source evidence tests: 9b41a961af5a43ac831b8bb122fd2380a09ba8eb. Isolated detached worktree C:/Users/Owner/guardian-remote-boundary-22. No production changes.

## Executable evidence

Python C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; PYTHONPATH=C:/Users/Owner/Project guardian/.worktrees/vega-test-15/.vega-deps.

- `python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py --basetemp .boundary-pytest-baseline --tb=short`: 92 passed, 1.17s.
- `python -m pytest -q tests/test_vega_evidence_binding.py --basetemp .boundary-pytest-evidence --tb=short`: 6 failed, 0.40s, reproducing packet-self-hash admission and empty/unrelated review acceptance before/after reopen.
- `python -m pytest -q tests/test_boundary22_observations.py --basetemp .boundary-pytest-adjacent --tb=short`: 3 passed, 0.13s. These observational assertions demonstrate defects: direct submit with failed required unit check and nonexistent all-zero commit followed by accept completes; old packet A review accepts new packet B attempt with same reviewer; reopen without verifier registry accepts previous reviewer. Duplicate acceptance after completed correctly returns False.

## Smallest safe repair specification

Persist canonical completion_submission_json plus completion_submission_digest, covering task, attempt, producer, lease, packet identity, full check/evidence object, immutable task risk/check/review policy. Digest proves identity only. Preserve original evidence classes instead of promoting packet hash to artifact proof. Store verification supplemental evidence separately.

Make submit enforce producer live lease and check semantics at durable boundary. Legacy unverified submissions may remain auditable and reviewable/rejectable for compatibility, but cannot complete. Bridge missing substantive write evidence must reject or route blocked/human_review; preserve recorded packet identity if gating.

Acceptance must run one atomic read/validation/update/event transaction; require explicit expected submission digest/version, current eligible independent registered verifier with live lease, matching persisted task/attempt/policy/checks and no stale/duplicate version. Recheck required unique passing checks and substantive proof. No malformed values or validator exceptions may complete. Trusted constructor evidence-validator seam is sufficient for runtime-disabled primitive, default deny unverifiable writes; packet-provided validators, booleans, reference prefixes or SHA-shaped strings cannot attest provenance. Deterministic fixture resolver must verify actual local content/digests and independently controlled check attestation bound to the same revision/submission. Protect snapshot from validator mutation. Proof cannot grant deployment/human approval authority; protected/unknown risk and unmet human/review gates fail closed.

Additive migration preserves events/history; legacy rows without bound submission remain unverifiable. Retry replaces current object with new attempt-bound digest and retains prior events. Reopen requires same trusted configuration and repeated proof verification, not cached caller success.

## Compatibility contradiction

Original 92 include successful repo_write acceptance with arbitrary producer refs and unrelated reviewer refs (test_bridge_persists_identity_evidence_and_lease_provenance_across_reopen, test_validated_completion_reaches_independent_verifier, test_accept_requires_live_owner_and_records_decision). Keeping all literally unchanged passing would preserve the defect or require synthetic backdoor. Parent authorizes minimal stronger fixture setup retaining original lifecycle assertions, documents original negative compatibility run. Keep six new Vega tests byte-identical. Existing trusted initial put_task completed insertion is import behavior outside this current transition repair; current-task upsert and release protections remain.

No merges, deploys, providers, credential access, or runtime activation. Next action: implement bounded repair, then independent breaker on exact new SHA.
