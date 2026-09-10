# RECONCILE-22 evidence/risk gates (2026-09-10)

Bounded Issue #22 lineage reconciliation. Independent Vega re-verify is next; this handoff does not self-certify.

## Lineages

| Side | Tip | Role |
|------|-----|------|
| Codex / PR24 | `40964ee9e334d1974702e419dff28df7c87df587` | BASE — evidence/proof/digest/packet/lease stack |
| Cursor | `a200b05440bd47919b0b7899d767afaf64699a67` | Soft-risk allowlist + adversarial/regression tests |
| Common ancestor | `6649b89adea44e3e7f41d37b55a7c82485beb6e6` | — |
| Worktree start | `40964ee9e334d1974702e419dff28df7c87df587` | Codex tip + staged Cursor tests |

## From Codex (preserved)

- Verifier acceptance bound to persisted submission + `expected_submission_digest` / `verification_submission_digest`
- `_consistent_packet` / envelope identity consistency
- Outcome/check/evidence consistency and required-check gates
- Valid current independent verifier lease + registry re-check at accept
- Trusted local `evidence_validator` fail-closed for non-soft risks
- Producer evidence separated from supplemental verifier notes (append-only supplemental)
- SQLite reopen behavior; `tests/evidence_fixture.py`; `tests/test_autopilot_evidence_binding.py`
- Dry-run: packet digest is identity only (not appended as evidence); full packet passed for envelope consistency

## From Cursor (ported)

Soft allowlist only:

```python
_SOFT_EVIDENCE_RISKS = frozenset({"sandbox_write", "read_only"})

def _risk_requires_substantive_evidence(risk_class: object) -> bool:
    if risk_class is None:
        return True
    return str(risk_class) not in _SOFT_EVIDENCE_RISKS
```

- Prefix classifiers `artifact:` / `commit:` / `pr:` / `pull_request:` for substantive admission
- Submit: non-soft without substantive provenance → `human_review` + `evidence_binding_rejected` (snapshot persisted)
- Soft may enter `verifying` without substantive provenance
- Accept: `_review_binds_producer` (review must include every producer substantive ref)
- Union tests: `tests/test_vega_evidence_binding_adversarial.py`, `tests/test_autopilot_evidence_binding_regressions.py`

## Conflict resolutions

1. **Submit gate vs always-verifying:** Codex always entered `verifying`. Ported Cursor fail-closed route for non-soft missing substantive prefixes; soft risks keep Codex verifying entry without prefix proof.
2. **Accept proof vs soft skip:** Non-soft still require Codex trusted validator + kind-based substantive sources **and** Cursor `_review_binds_producer`. Soft skip prefix + validator write-proof only; digest/lease/packet/checks/independence always required.
3. **Supplemental storage:** Codex stored the full review list; Cursor append-only non-producer refs. Kept Cursor append-only; event detail still records producer `evidence_refs` (Codex shape) plus `supplemental_evidence_refs` as added-only.
4. **Fixture refs (`local:` / bare strings vs `artifact:`):** Strengthened lifecycle/boundary fixtures to qualifying `artifact:` refs and `attest_local_submission` + `expected_submission_digest` where accept must succeed. Did not delete assertions.
5. **Dry-run digest-as-evidence:** Kept Codex (do not append packet digest). Cursor adversarial digest-only / fake-proof cases fail closed via submit `human_review` or deny accept.
6. **Migration/CI:** Union columns include Codex `verification_submission_digest` and Cursor submission/supplemental columns; CI pytest list unions all four evidence-binding modules.

## Final SHA

`9d94f98007aa39cc51b2a7f38c446ee777483d86`

## Test commands / results

Python: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`  
`PYTHONPATH` = `…\.worktrees\vega-test-15\.vega-deps` + worktree root  
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`

```
python -m compileall -q elysia_collective_seed
python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_autopilot_evidence_binding_regressions.py tests/test_vega_evidence_binding_adversarial.py
git diff --check
```

Result: **147 passed**, `git diff --check` clean.

## Residual risks (for Vega)

- Soft path can enter `verifying` / accept without trusted write-proof by design; confirm independence + digest/lease/packet/check gates remain sufficient for `sandbox_write` / `read_only`.
- Prefix classifiers are spelling gates, not content proof; non-soft still depends on `evidence_validator`.
- Unknown / empty / malformed risk_class fail closed on submit; Codex accept risk allowlist still rejects unknown at complete.
