# Issue #22 evidence-binding repair handoff

Status: implementation complete on `cursor/guardian-22-evidence-binding`; independent Vega verifier requested.
Starting product head: `6649b89adea44e3e7f41d37b55a7c82485beb6e6` (PR #15 exact head).
Implementer: Astra/Cursor; do not treat this note as independent verification.

## Defect

Verifier acceptance could complete on a live lease alone. Dry-run completion always appended the packet self-hash into evidence and treated it as write proof. Issue #22 falsifiers in `tests/test_vega_evidence_binding.py` capture both gaps.

## Repair

1. **Identity vs proof:** packet `sha256:` digests remain completion identity and may appear in evidence, but do not satisfy substantive write evidence.
2. **Persisted submission snapshot:** `submit_for_verification` stores additive `completion_submission_json` + `completion_submission_digest` (integrity only) covering packet id, producer, attempt, normalized evidence, commits/PRs/claims/checks, and admitted risk/policy fields. Legacy `completion_packet_id` / `completion_evidence_json` retained.
3. **Risk-aware minimum evidence:** for `repo_write` / `deployment` / unknown risk, require deterministic provenance prefixes (`artifact:`, `commit:`, `pr:` / `pull_request:`) plus required passing checks. Missing/fake strings fail closed to `human_review` with `evidence_binding_rejected` (not an acceptably completable `verifying` row). `sandbox_write` remains soft for local dry-run identity packets.
4. **Atomic accept binding:** `accept_verification` requires live verifier lease, loads/re-hashes the persisted submission, re-checks minimum evidence, rejects empty/unbound review evidence, appends verifier-only refs to `verification_supplemental_evidence_json`, and completes only when producer binding remains satisfied.
5. Prior #19/#20/#21 lease, retry-ceiling, independence, and migration behavior preserved.

## Files

- `elysia_collective_seed/autopilot/task_ledger.py`
- `elysia_collective_seed/autopilot/dryrun_orchestrator.py`
- `tests/test_vega_evidence_binding.py` (unchanged assertions)
- `tests/test_autopilot_evidence_binding_regressions.py` (new)
- Fixture reconciliations to qualifying `artifact:` refs in lifecycle/Vega/repair/dry-run stale-path tests
- `.github/workflows/elysia-autopilot-ci.yml` includes #22 suites
- This handoff

## Limits / next

No providers, runtime enablement, network evidence validation, merges, or force-push. Suggested next role: independent Vega verifier on the exact commit head against the mandatory suite (original 92 + 6 evidence + new regressions).
