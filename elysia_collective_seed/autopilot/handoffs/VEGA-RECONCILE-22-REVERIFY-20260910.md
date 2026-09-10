# VEGA RECONCILE-22 REVERIFY — 2026-09-10

Independent adversarial exact-head verification. Verifier did **not** implement the reconciliation and did **not** modify product code.

## TARGET SHA

`4e5a55b553a1df303b3559b5579fdab930691204`  
Product branch/worktree: `cursor/reconcile-22-evidence-risk-gates` @
`C:\Users\Owner\Project guardian\.worktrees\reconcile-22-evidence-risk-gates`  
Verification branch/worktree: `codex/vega-reverify-22-reconcile` @
`C:\Users\Owner\Project guardian\.worktrees\vega-reverify-22-reconcile` (from exact `4e5a55b`)

Lineages claimed:

| Tip | Role | Ancestry vs HEAD |
|-----|------|------------------|
| Codex/PR24 `40964ee` | evidence/proof/digest/lease stack | **ancestor** (`merge-base --is-ancestor` exit 0) |
| Cursor soft-allowlist `a200b05` | soft-risk allowlist + adversarial tests | **not** a git ancestor (logic ported into `057e657`) |
| Base PR15 `6649b89` | lifecycle boundaries | **ancestor** (exit 0) |

## VERDICT

**PASS**

No material evidence-binding or risk-classification bypass found at exact SHA `4e5a55b`. Soft path remains explicitly allowlisted to `sandbox_write` / `read_only` only. Codex `repo_write` proof/digest/lease paths still hold.

## CONFIDENCE

**High** (mandatory pytest 147/147; compileall clean; 21/21 executable reverify probes green; lineage ancestry checked). Residual: `git diff --check 40964ee..HEAD` fails on trailing whitespace in the reconcile **handoff markdown only** (not product Python). Soft-allowlist tip `a200b05` is behavioral port, not merge-ancestor.

## Commands + results

Environment:

- Python: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`
- `PYTHONPATH=C:\Users\Owner\Project guardian\.worktrees\vega-test-15\.vega-deps` + product worktree root
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
- Product cwd: reconcile worktree at exact SHA

```
git rev-parse HEAD
→ 4e5a55b553a1df303b3559b5579fdab930691204  (MATCH; not BLOCKED)

python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py
  tests/test_autopilot_verifier_ledger_migration.py
  tests/test_autopilot_verifier_lifecycle.py
  tests/test_vega_verifier_boundaries.py
  tests/test_autopilot_lifecycle_repairs.py
  tests/test_vega_evidence_binding.py
  tests/test_autopilot_evidence_binding.py
  tests/test_autopilot_evidence_binding_regressions.py
  tests/test_vega_evidence_binding_adversarial.py
→ 147 passed in 2.11s

python -m compileall -q elysia_collective_seed
→ exit 0

git diff --check 40964ee..HEAD
→ exit 2  (trailing whitespace in
   elysia_collective_seed/autopilot/handoffs/RECONCILE-22-evidence-risk-gates-20260910.md
   lines 55, 60, 61 only — docs, not product gates)
```

Verification-branch executable probes (no product edits):

```
# on codex/vega-reverify-22-reconcile @ 4e5a55b + probe tests only
python -m pytest -q tests/test_vega_reconcile22_reverify_probes.py
→ 21 passed in 0.44s
```

## Bypass attempts (executable)

### Evidence-binding family

| Attempt | Result |
|---------|--------|
| Unrelated review evidence (`artifact:B` vs producer `artifact:A`) | **BLOCKED** — accept False, status not completed |
| Conflicting packet identity (`packet:B` id vs `packet:A` body) | **BLOCKED** — submit rejected / non-verifying |
| Stale verifier lease (accept after lease expiry) | **BLOCKED** |
| Producer-controlled / self-hash evidence (`sha256:` packet id as sole ref) | **BLOCKED** — `human_review`; `is_substantive_write_ref` False |
| Malformed review evidence (`[]`, blank, non-str, `None`) | **BLOCKED** |
| Missing / wrong `expected_submission_digest` | **BLOCKED**; correct digest still accepts |
| Accept without claim pin | **BLOCKED** |
| SQLite close/reopen between submit and accept (no validator reinstall) | **BLOCKED**; reinstalling trusted fixture still accepts (authority not from DB) |

### Risk-classification family

| `risk_class` | Submit without substantive | Soft? |
|--------------|----------------------------|-------|
| `unknown_risk` | `human_review` / not verifying | no |
| `""` (empty) | fail-closed | no |
| `write` | fail-closed | no |
| missing / `None` (payload patched) | fail-closed | no |
| `Sandbox_Write` / `READ_ONLY` / `Repo_Write` | fail-closed (case-sensitive) | no |
| `sandbox_write` | may enter `verifying`; complete only with claim+digest | **yes** |
| `read_only` | same soft path | **yes** |

Allowlist at HEAD matches intended Cursor semantics:

```python
_SOFT_EVIDENCE_RISKS = frozenset({"sandbox_write", "read_only"})

def _risk_requires_substantive_evidence(risk_class: object) -> bool:
    if risk_class is None:
        return True
    return str(risk_class) not in _SOFT_EVIDENCE_RISKS
```

### Codex `repo_write` proof / digest / lease

- Insufficient provenance → `human_review`
- Happy path with `artifact:` + `attest_local_submission` + live lease + correct digest → `completed`
- Wrong digest / stale lease → accept denied

## Material new bypass?

**None.** No failing-by-design product-gate tests required. Verification branch adds `tests/test_vega_reconcile22_reverify_probes.py` as executable evidence only (does not change product code).

## Residual risks

1. Soft `sandbox_write` / `read_only` may complete without trusted write-proof by design; independence + digest + lease + packet/check gates remain the barrier (confirmed).
2. Prefix classifiers are spelling gates; non-soft still depends on configured `evidence_validator` (absent → fail-closed).
3. Cursor tip `a200b05` is not a merge ancestor of `4e5a55b`; reconcile is a port onto Codex `40964ee`. Behavioral equivalence checked; git-history equivalence is not claimed.
4. `git diff --check 40964ee..HEAD` whitespace in reconcile handoff markdown — clean up in a docs-only follow-up if process gates are strict.

## Next task

- Optional docs-only fix for trailing whitespace in `RECONCILE-22-evidence-risk-gates-20260910.md`.
- Proceed to merge/review of `cursor/reconcile-22-evidence-risk-gates` at `4e5a55b` from an evidence/risk-gate perspective (PASS).
- If git-history inclusion of `a200b05` is required (not just behavioral port), record that as a separate process decision — not a gate FAIL.
