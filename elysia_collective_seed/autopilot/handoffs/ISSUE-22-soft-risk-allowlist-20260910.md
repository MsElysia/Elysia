# Issue #22 residual soft-risk allowlist repair

Status: implementation complete on `cursor/guardian-22-soft-risk-allowlist`; independent Vega re-verify requested.
Starting docs head: `8cfd5c76eecea0590881dc4f7d837c1e22aecdd8`; product head under repair: `0cf0e99c47840393b1088da0671441eb7a780d84`.
Implementer: Astra/Cursor; do not treat this note as independent verification.

## Defect

`_risk_requires_substantive_evidence` used a consequential denylist (`repo_write`, `deployment`). Unknown/empty/`write` risks skipped substantive provenance and could complete. Independent Vega FAIL against `0cf0e99` with adversarial tests in `tests/test_vega_evidence_binding_adversarial.py`.

## Repair

Invert to soft allowlist: only `sandbox_write` and `read_only` skip substantive provenance. `None` and every other risk string (including empty/`write`/unknown) require deterministic write refs + required checks. Removed `CONSEQUENTIAL_WRITE_RISKS` for this gate. Original Vega evidence tests and #19/#20/#21 behavior preserved.

## Files

- `elysia_collective_seed/autopilot/task_ledger.py`
- `tests/test_vega_evidence_binding_adversarial.py` (Vega adversarial; assertions unchanged)
- `.github/workflows/elysia-autopilot-ci.yml` (includes adversarial suite)
- This handoff

## Limits / next

No providers, runtime enablement, merges, or force-push. Next role: independent Vega re-verify on the exact commit head (do not self-certify).
