# VEGA ISSUE #22 REVERIFY — 2026-09-10

Independent adversarial exact-head verification. Verifier did not implement the repair.

## TARGET SHA

`0cf0e99c47840393b1088da0671441eb7a780d84`  
Branch verified: `cursor/guardian-22-evidence-binding` (worktree `guardian-22-evidence-binding`)  
Base before repair: `6649b89adea44e3e7f41d37b55a7c82485beb6e6`  
Verification branch (this handoff + adversarial tests): `codex/vega-reverify-22-evidence`

## VERDICT

**FAIL** (#22 scope — residual material bypass)

## CONFIDENCE

**High** (mandatory suite green; bypass reproduced with live ledger APIs)

## Commands + results

Environment:

- Python: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`
- `PYTHONPATH=C:\Users\Owner\Project guardian\.worktrees\vega-test-15\.vega-deps`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
- Cwd: implementer worktree at exact SHA `0cf0e99`

```
git rev-parse HEAD
→ 0cf0e99c47840393b1088da0671441eb7a780d84  (MATCH; not BLOCKED)

python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py
  tests/test_autopilot_verifier_ledger_migration.py
  tests/test_autopilot_verifier_lifecycle.py
  tests/test_vega_verifier_boundaries.py
  tests/test_autopilot_lifecycle_repairs.py
  tests/test_vega_evidence_binding.py
  tests/test_autopilot_evidence_binding_regressions.py
→ 101 passed in 1.33s

python -m compileall -q elysia_collective_seed
→ exit 0

git diff --check 6649b89..HEAD
→ exit 0
```

Adversarial probes (ephemeral script, then committed failing tests on this branch):

- `unknown_risk` + matching verifier → submit to `verifying` with `["only-identity"]` → accept `["unrelated:note"]` → **`completed`**
- empty `risk_class=""` / `risk_class="write"` → same fail-open completion path
- `repo_write` digest-only dry-run → `applied=False`, stays `claimed` (good)
- `release(..., completed)` on `repo_write` → False (good; #20)
- `put_task` upsert cannot rewrite status to `completed` (good)
- unbound `artifact:B` accept denied; bound accept appends supplemental only (good)
- null `completion_submission_json` accept denied (good)
- digest-as-sole-evidence / raw commit without prefix → `human_review` (good)

Adversarial pytest (this branch; expected red until Astra repair):

```
python -m pytest -q tests/test_vega_evidence_binding_adversarial.py
→ expected FAIL (demonstrates residual bypass)
```

## Claims tested

| # | Claim | Result |
|---|--------|--------|
| 1 | Packet self-hash alone is not substantive write evidence; `repo_write` without artifact/commit/PR fails closed | **CONFIRMED** (`test_vega_evidence_binding` + dry-run probe) |
| 2 | `accept_verification` cannot complete with empty/unrelated evidence when producer has `artifact:A` | **CONFIRMED** |
| 3 | Binding survives SQLite close/reopen | **CONFIRMED** (parametrized reopen + regression reopen) |
| 4 | Fake non-class evidence strings fail closed for consequential (`repo_write`/`deployment`) writes | **CONFIRMED** |
| 5 | Verifier supplemental evidence is separate; cannot erase/replace producer binding | **CONFIRMED** |
| 6 | Prior lifecycle repairs #19/#20/#21 still pass | **CONFIRMED** (lifecycle + repairs suites green) |
| 7 | Original 6 Vega evidence tests unchanged vs `9b41a96` | **CONFIRMED** (blob identical: `48ce7e0de67579ed916f069a688d25d462a5dd88`) |
| 8 | Easiest bypass search | **MATERIAL BYPASS FOUND** (see below) |

## Residual bypasses

### Material — risk allowlist inverted (FAIL trigger)

`_risk_requires_substantive_evidence` only requires provenance for `repo_write` and `deployment`. Any other string (`unknown_risk`, `""`, `write`, typos) is treated as soft: no substantive refs required; `_review_binds_producer` sees an empty required set and accepts any non-empty review notes.

Implementer handoff (`ISSUE-22-evidence-binding-20260910.md` §3) claimed **unknown risk** must require provenance. Code does not.

**Smallest Astra repair:** invert to fail-closed soft allowlist:

```python
_SOFT_EVIDENCE_RISKS = frozenset({"sandbox_write", "read_only"})

def _risk_requires_substantive_evidence(risk_class: object) -> bool:
    if risk_class is None:
        return True
    return str(risk_class) not in _SOFT_EVIDENCE_RISKS
```

Keep `sandbox_write` soft for local dry-run identity packets; treat everything else (including unknown/empty) as consequential.

### Non-material / known limits (not FAIL alone)

- Prefix strings (`artifact:…`) are not network-validated; intentional deterministic binding only.
- Default synthetic reviewer only registers `repo_write`, so unknown risks stay stuck in `verifying` without a matching verifier — but a registry that includes the custom risk completes without provenance.
- No provider/runtime activation observed in this repair path.

## Original 6 evidence tests

`tests/test_vega_evidence_binding.py` is **byte-identical** to `9b41a96`. Six parametrized cases still assert fail-closed on digest-only write proof and unbound accept; spirit and assertions unchanged.

## Safety

- No provider calls, Guardian runtime enablement, network evidence validation, merges, or force-push.
- Ledger remains local SQLite; dry-run/orchestrator paths only.

## NEXT TASK recommendation

1. **Astra:** apply the soft-risk allowlist inversion above in `task_ledger.py`; ensure adversarial tests in `tests/test_vega_evidence_binding_adversarial.py` turn green; re-run mandatory suite.
2. **Vega:** re-verify on the new product SHA; flip this handoff to PASS only after unknown/empty/`write` risk classes fail closed.
3. Do not merge #22 until that residual is closed (or explicitly scoped out with a documented policy change — not recommended).
