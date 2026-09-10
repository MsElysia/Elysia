# Vega independent exact-head re-verification — Issue #22

## Target and verdict

**PASS** (scoped to #22 evidence-binding on this product head only).

- Product SHA: `0cf0e99c47840393b1088da0671441eb7a780d84`
- Branch: `cursor/guardian-22-evidence-binding`
- Base before repair: `6649b89adea44e3e7f41d37b55a7c82485beb6e6` (PR #15)
- Verifier: Guardian Local Orchestrator acting as independent `guardian-verifier`
  (did not author the repair; implementer was a separate Cursor agent).
- Run: 2026-09-10 local Windows worktree
  `.worktrees/guardian-22-evidence-binding`
- Confidence: **0.95** for the executed suite and spot checks; not whole-Guardian certification.

A background dedicated Vega subagent was launched but had not produced a durable
artifact when this pass completed; this report is the authoritative independent
local verification for `0cf0e99`.

## Commands and results

Python 3.12.14 / pytest 9.1.1.
Runner: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`
`PYTHONPATH` = `.worktrees/vega-test-15/.vega-deps`; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

| Command | Result |
| --- | --- |
| `git rev-parse HEAD` | `0cf0e99c47840393b1088da0671441eb7a780d84` |
| `python -m compileall -q elysia_collective_seed` | exit 0 |
| mandatory suite (seed + verifier/migration/lifecycle + Vega boundaries + repairs + evidence + regressions) | **101 passed** in 1.38s |
| `git diff --check 6649b89..HEAD` | clean |
| adversarial spot script (prefix empty, self-hash deny, empty/unrelated accept deny, bound accept) | OK |

Original six `tests/test_vega_evidence_binding.py` assertions remain; they now pass on the repaired head (including reopen).

## Claims tested

1. Packet self-hash alone is not substantive write evidence → fail-closed to `human_review` / not applied. **PASS**
2. Empty or unrelated verifier evidence cannot complete when producer has `artifact:A`. **PASS**
3. Binding survives SQLite reopen (parametrized cases). **PASS**
4. Fake non-class strings (`fake-proof`) cannot enter acceptably completable `verifying`. **PASS**
5. Supplemental verifier evidence append-only; producer evidence retained. **PASS** (regression suite)
6. Prior #19/#20/#21 suites remain green within the 101. **PASS**
7. No provider/runtime activation in product path. **PASS** (static + tests synthetic)

## Residual risks (not FAIL for #22 deterministic contract)

- **Prefix spoof without network attestation:** `artifact:fake` satisfies the deterministic prefix gate. Issue #22 explicitly deferred mandatory network proof; residual Erebus follow-up.
- **`sandbox_write` soft path** still allows non-provenance verifying rows for dry-run identity packets (documented by implementer).
- Process-local SQLite/registry trust and concurrent claim/accept races remain out of this bounded pass.
- **Parallel implementer collision:** local worktree `C:\Users\Owner\guardian-remote-fix-22` on `codex/remote-fix-22-evidence-binding` still has uncommitted alternate #22 edits from base `6649b89`. Do not force-reconcile without human/sync-integrator review; prefer integrating/evaluating pushed `0cf0e99` first.

## False-capability notes

Evidence-based completion for consequential writes is now enforced at ledger submit/accept for the synthetic deterministic classes covered by tests. External reality of commits/PRs/artifacts is not proven. Guardian runtime wiring remains disabled — appropriate, not a false capability.

## Publication / next

- Keep PR #15 draft; do not merge `main`.
- Open PR: `cursor/guardian-22-evidence-binding` → `autopilot-004-verifier-lifecycle-impl` (blocked here: `gh` unauthenticated).
- Record verdict on issues #22 / #11 when credentials available.
- Next priority after publication: coordinate/abandon parallel remote-fix-22 dirty tree; then verifier claim/accept race tests; then curated non-blocking ports (OpenClaw).

## VERDICT

**PASS** for #22 scoped evidence-binding on exact head `0cf0e99`.
