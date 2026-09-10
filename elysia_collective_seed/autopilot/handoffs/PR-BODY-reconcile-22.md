## Summary
Bounded reconciliation of two independently developed Issue #22 repair lineages onto PR #15 (`autopilot-004-verifier-lifecycle-impl`).

- **Codex / PR #24 lineage** (`40964ee`): durable submission/digest binding, packet envelope consistency, claim-pinned digest, independent lease/registry, trusted local proof validation, supplemental evidence separation.
- **Cursor lineage** (`a200b05`): fail-closed soft-risk allowlist — only `sandbox_write` / `read_only` may skip substantive write-proof; `unknown_risk`, empty, `write`, missing/invalid fail closed to `human_review`.

This branch **does not merge either lineage wholesale**. It preserves the union of proven invariants. PR #24 and Cursor branches remain intact until reconciliation evidence is durable.

Exact candidate: `4e5a55b553a1df303b3559b5579fdab930691204`

Independent verification:
- Vega **PASS** — `codex/vega-reverify-22-reconcile` @ `d65174c`
- Architecture review **READY_FOR_INTEGRATION_REVIEW** — `codex/review-reconcile-22` @ `e5e23a2`

## Test plan
- [x] Union suite 147 tests
- [x] Independent Vega PASS (evidence-binding AND risk-classification bypass attempts)
- [x] Fresh architecture review → READY_FOR_INTEGRATION_REVIEW
- [ ] Human integration review; keep draft until then
- [ ] Confirm no merge to `main`

## Gates
- DO NOT MERGE until human integration review
- Does not delete or close PR #24 / Cursor lineage automatically
- No provider/runtime activation
- Supersedes competing #22 candidates **only after** this reconciliation evidence is accepted
