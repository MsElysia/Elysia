# Elysia / Project Guardian architecture checkpoint

Safe-stack slice: conversation memory, brain trace visibility, self-improvement proposals (review-only), prompt contracts, memory ranking, and **live-execution governance** (planning-only).

## Final safe-stack checkpoint

- Current final checkpoint: `docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md`
- Scope: final safe-stack audit after UI marker repair and governance visibility work.
- Latest safe-stack smoke result: `python scripts/run_safe_stack_smoke_tests.py` -> **386 passed, 3 warnings** (Safe stack smoke gate).
- CI: `.github/workflows/safe-stack-smoke.yml` runs the same smoke script (no secrets, no servers, no autonomy).
- Live execution remains disabled and autonomy remains unwired.
- One-shot UI repair scripts: `scripts/maintenance/one_shot/` (historical; not runtime/CI/smoke). Guard: `test_one_shot_ui_scripts_quarantined.py`.

## Governance and operator confirmations

- **Store:** `data/runtime/operator_confirmations.jsonl` via `project_guardian/governance/operator_confirmation_store.py`
- **Guard:** `project_guardian/governance/live_execution_guard.py`
- **Visibility (read-only):** `project_guardian/governance/operator_confirmation_visibility.py`

### Operator confirmation diagnostics API

```text
GET /api/governance/operator-confirmations
GET /api/governance/operator-confirmations/<operator_confirmation_id>
```

Implemented on **Runtime API** and **UI control panel** (same routes). Responses are sanitized; list default `limit=25`. No create/update/consume endpoints.

## Safety invariants

1. Live execution remains disabled unless explicitly gated in config (defaults unchanged).
2. Autonomy is not wired through confirmation or visibility paths.
3. Confirmations are validated but not marked used by runtime/API visibility.
4. No raw prompts or TDA traces in governance API payloads.

## Related documentation

- `docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md` - final safe-stack checkpoint and endpoint/control-panel inventory.
- `docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md` - git/commit hygiene before safe-stack release.
- `docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md` - live-exec governance snapshot.
- `docs/LIVE_EXECUTION_GOVERNANCE_PLAN.md` - planning doc (static tests in `test_live_execution_governance_docs.py`).
- `docs/OPERATOR_CONFIRMATION_CONTEXT_PLAN.md` - confirmation context schema.

## Test entry points

Safe stack smoke (milestone gate):

```bash
python scripts/run_safe_stack_smoke_tests.py
```

Targeted checks:

```bash
python -m pytest project_guardian/tests/test_operator_confirmation_visibility.py -q
```
