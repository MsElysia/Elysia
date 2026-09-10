# VEGA ISSUE #22 SOFT-ALLOWLIST REVERIFY — 2026-09-10

Independent adversarial exact-head verification. Verifier did **not** implement the soft-allowlist repair.

## TARGET SHA

`a200b05440bd47919b0b7899d767afaf64699a67`  
Product branch verified: `cursor/guardian-22-soft-risk-allowlist` (worktree `guardian-22-soft-risk-allowlist`)  
Prior FAIL SHA: `0cf0e99c47840393b1088da0671441eb7a780d84`  
Prior FAIL report/tests: `codex/vega-reverify-22-evidence` @ `c5f5924`  
Verification branch (this handoff): `codex/vega-reverify-22-soft-allowlist`

## VERDICT

**PASS** (#22 soft-risk allowlist residual closed)

## CONFIDENCE

**High** (mandatory suite green; prior FAIL adversarial blob identical and green; live ledger probes close unknown/empty/`write`/missing/`None`; binding + release paths fail-closed)

## Commands + results

Environment:

- Python: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`
- `PYTHONPATH=C:\Users\Owner\Project guardian\.worktrees\vega-test-15\.vega-deps` (+ worktree root for imports)
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
- Cwd: implementer worktree at exact SHA `a200b05`

```
git rev-parse HEAD
→ a200b05440bd47919b0b7899d767afaf64699a67  (MATCH; not BLOCKED)

python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py
  tests/test_autopilot_verifier_ledger_migration.py
  tests/test_autopilot_verifier_lifecycle.py
  tests/test_vega_verifier_boundaries.py
  tests/test_autopilot_lifecycle_repairs.py
  tests/test_vega_evidence_binding.py
  tests/test_autopilot_evidence_binding_regressions.py
  tests/test_vega_evidence_binding_adversarial.py
→ 103 passed in 1.37s

python -m compileall -q elysia_collective_seed
→ exit 0

git diff --check 8cfd5c7..HEAD
→ exit 0
```

Adversarial test integrity vs prior FAIL:

```
git hash-object tests/test_vega_evidence_binding_adversarial.py
git rev-parse c5f5924:tests/test_vega_evidence_binding_adversarial.py
→ both 229ec929f8d0796cd5444fc6c960d31e7855e9a1  (byte-identical; assertions not weakened)
```

## Soft allowlist inversion (MUST CONFIRM)

In `task_ledger.py` at `a200b05`:

```python
_SOFT_EVIDENCE_RISKS = frozenset({"sandbox_write", "read_only"})

def _risk_requires_substantive_evidence(risk_class: object) -> bool:
    if risk_class is None:
        return True
    return str(risk_class) not in _SOFT_EVIDENCE_RISKS
```

| risk_class | requires substantive evidence |
|---|---|
| `sandbox_write` | no (soft) |
| `read_only` | no (soft) |
| `unknown_risk` | **yes** |
| `""` | **yes** |
| `write` | **yes** |
| `None` / missing key | **yes** |
| `repo_write` / `deployment` | **yes** |
| case/whitespace variants of soft names (`Sandbox_Write`, `sandbox_write `) | **yes** (fail-closed) |

## Claims tested

| # | Claim | Result |
|---|--------|--------|
| 1 | Soft path is allowlist-only (`sandbox_write` / `read_only`); everything else requires provenance | **CONFIRMED** (code + unit + ledger probes) |
| 2 | Prior adversarial tests from `c5f5924` now PASS without weakened assertions | **CONFIRMED** (blob identical; 2/2 green) |
| 3 | Original 6 evidence tests + regressions + #19/#20/#21 suites still green | **CONFIRMED** (103 passed incl. all listed suites) |
| 4 | `unknown_risk` / `""` / `write` / `None` / missing cannot complete without substantive provenance | **CONFIRMED** (submit → `human_review`; unbound accept never reached) |
| 5 | Soft risks still may complete with identity-only packets + non-empty review notes | **CONFIRMED** (expected; not a defect) |
| 6 | Accept without binding (`note:only` / empty) denied when producer has `artifact:A` | **CONFIRMED** (`accepted=False`; bound accept succeeds) |
| 7 | `release(..., completed)` blocked for write/unknown/empty/`None`/`sandbox_write`; allowed only for bare `read_only` | **CONFIRMED** (matches #20 policy) |
| 8 | Prefix spoof residual | **KNOWN / NON-MATERIAL** (deterministic string prefixes only; not network-validated) |

## Residual risks (non-FAIL)

- **Prefix binding is syntactic:** any non-empty `artifact:` / `commit:` / `pr:` / `pull_request:` token counts; values are not fetched or verified against a remote. Intentional local deterministic gate.
- **Case-insensitive prefix matching** accepts `ARTIFACT:A` as substantive; still requires the same token in review evidence.
- **Soft completion path** remains for exact `sandbox_write` / `read_only` only (identity packets + any non-empty review notes when no substantive refs were admitted).
- No provider/runtime activation, merges, or force-push observed in this verification path.

## New adversarial tests

**None added.** No material new bypass found beyond known prefix-spoof residual. Prior FAIL tests already cover the repaired hole.

## Safety

- Product code unchanged by this verifier.
- Report-only commit on `codex/vega-reverify-22-soft-allowlist` from `a200b05`.
- Ledger remains local SQLite; probes used synthetic workers only.

## NEXT TASK recommendation

1. Treat #22 soft-allowlist residual as **closed** at `a200b05`.
2. Orchestrator/merge gate: include adversarial suite in CI (already wired in repair commit) before merging the product branch.
3. Optional follow-on (out of #22 scope): stronger evidence token validation if prefix-spoof becomes a threat model requirement.
