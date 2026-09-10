# Architecture Review — RECONCILE-22 evidence/risk gates

**Date:** 2026-09-10  
**Reviewer:** Independent architecture/code review (did not implement reconcile; did not author Vega suite)  
**Exact product SHA:** `4e5a55b553a1df303b3559b5579fdab930691204`  
**Product branch/worktree:** `cursor/reconcile-22-evidence-risk-gates`  
**Vega PASS:** `codex/vega-reverify-22-reconcile` @ `d65174c` → `VEGA-RECONCILE-22-REVERIFY-20260910.md`

## VERDICT

**READY_FOR_INTEGRATION_REVIEW**

## Scope

Read-only analysis of the Codex/PR24 proof-digest stack unioned with the Cursor soft-risk allowlist port. Compared reconcile `task_ledger.py` against Cursor soft-allowlist lineage behavior and Codex evidence-binding tests/fixtures. Relied on Vega reverify PASS at the same SHA; did not weaken tests; did not merge.

## Lineage posture

| Tip | Role vs `4e5a55b` |
|-----|-------------------|
| Codex/PR24 `40964ee` | Git ancestor; base of reconcile |
| Cursor soft-allowlist `a200b05` | Behavioral port into `057e657`, **not** a merge ancestor |
| PR15 `6649b89` | Common ancestor lineage |

Union is intentional: keep Codex durable submission/claim/proof machinery; port only Cursor’s soft allowlist + prefix/bind gates + regression/adversarial modules.

## Architecture clarity

The union is readable as **one ledger authority with layered gates**, not two competing verifiers:

1. **Submit (Cursor port):** non-soft risks require at least one prefix-substantive provenance ref (`artifact:` / `commit:` / `pr:` / `pull_request:`); else persist snapshot and route `human_review` + `evidence_binding_rejected`. Soft risks (`sandbox_write`, `read_only` only) may enter `verifying` without that spelling gate.
2. **Claim (Codex):** live independent verifier lease; pins `verification_submission_digest` to the current `completion_submission_digest`.
3. **Accept (Codex + Cursor bind):** require live lease, `expected_submission_digest` matching both digests and re-hash of `completion_submission_json`, envelope/`_consistent_packet` consistency, required checks, risk allowlist, independence re-check, and `_review_binds_producer`. Non-soft additionally require kind-based substantive sources + trusted local `evidence_validator` (absent/exception/non-True → deny). Soft may skip prefix/validator write-proof but **not** digest/lease/packet/check/independence/bind gates.

Cognitive load: two “substantive” classifiers (prefix at submit vs kind+validator at accept) exist. They are **layered fail-closed filters**, not alternate completion authorities. Net effect for `repo_write` is stricter than either lineage alone (prefix spelling **and** trusted proof).

## State ownership (no dual authority)

| State | Owner | Role |
|-------|--------|------|
| `completion_submission_json` + `completion_submission_digest` | Producer submit under live execution lease | Immutable attempt snapshot / identity |
| `completion_evidence_json` / `completion_packet_id` | Same submit | Envelope mirrors; accept equality-checks vs snapshot |
| `verification_submission_digest` | Verifier claim | Claim-time pin against mid-flight snapshot swap |
| `verification_supplemental_evidence_json` | Verifier accept | Append-only notes; never substitutes for producer refs or validator input |
| `evidence_validator` | Process config (tests via `attest_local_submission`) | Trusted local proof authority; **not** persisted in SQLite |

`completion_evidence_json` duplicates `submission.evidence_refs` for legacy/query convenience but is cross-checked at accept — derived mirror, not a second truth source. Claim pin is a deliberate stale-claim guard, not a competing digest authority.

## Fail-closed behavior

- Unknown / empty / `None` / `write` / case variants → not soft; insufficient provenance → `human_review` (accept also rejects unknown risks via `{"read_only","repo_write","sandbox_write"}` allowlist).
- Soft path is **explicit allowlist** `_SOFT_EVIDENCE_RISKS = {"sandbox_write","read_only"}` (not a consequential denylist).
- Missing/wrong digest, missing claim pin, stale lease, packet envelope conflict, unbound review refs, missing validator on non-soft → accept denied.
- SQLite reopen does not reinstall proof authority (Codex regression preserved).

Residual (documented, intentional): soft risks may complete without trusted write-proof; prefix gates are spelling, not content proof. Independence + digest + lease + packet/checks remain the soft barrier. Vega probes confirmed this boundary.

## Test coverage / union completeness

Product CI pytest list unions all four evidence modules:

- `tests/test_vega_evidence_binding.py`
- `tests/test_autopilot_evidence_binding.py` (Codex proof/digest/packet/lease)
- `tests/test_autopilot_evidence_binding_regressions.py` (Cursor)
- `tests/test_vega_evidence_binding_adversarial.py` (Cursor soft-allowlist fail-closed)

Migration columns include both Codex `verification_submission_digest` and Cursor supplemental/submission columns.

Independent Vega @ `d65174c`: mandatory **147 passed**; **21/21** executable bypass probes PASS at exact `4e5a55b`. Product adversarial module matches Cursor tip thinness (unknown/empty); broader risk/soft positive matrix lives on the verification branch — acceptable given Vega PASS and Cursor tip parity, not a lost protection.

## Lineage protection check

| Protection | Status |
|------------|--------|
| Codex digest / claim pin / `expected_submission_digest` | Preserved |
| Codex `_consistent_packet` + accept re-check | Preserved |
| Codex trusted `evidence_validator` fail-closed for non-soft | Preserved |
| Codex supplemental ≠ producer proof | Preserved (Cursor append-only kept) |
| Codex independence + live lease at accept | Preserved |
| Cursor soft allowlist (not denylist) | Ported |
| Cursor prefix substantive gate + `human_review` | Ported |
| Cursor `_review_binds_producer` | Ported (adapted to Codex submission pool) |
| Cursor regression/adversarial modules | Present in product suite |

No accidental loss of either lineage’s security-relevant gates found. Cursor’s flatter submission model was replaced by richer Codex envelopes — net stronger, not weaker.

## Findings

### Non-blocking

1. **Two substantive classifiers** — keep as layered defense; optional later refactor to share one helper with explicit stage comments (not required for integration review).
2. **`get()` omits `verification_submission_digest`** — claim pin is internal; observability-only nit.
3. **Stale adversarial module docstring** (“expected FAIL until Astra repair”) — docs drift only.
4. **Trailing whitespace** in `RECONCILE-22-evidence-risk-gates-20260910.md` (Vega residual) — docs only.
5. **`a200b05` not a git ancestor** — process note, not a gate failure (behavioral port verified).

### Blocking

None.

## Decision

Proceed to integration review of `cursor/reconcile-22-evidence-risk-gates` @ `4e5a55b`. Do **not** merge to `main` from this review. Do not auto-close/delete PR24 or Cursor lineage branches.
