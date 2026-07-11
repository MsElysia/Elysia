# Memory Review Approved Promotion Operator Approval Gate Smoke

This dry-run/local smoke proves that an approved-promotion operator handoff
cannot advance to operator-approved staging unless an explicit local approval
artifact is present, valid, and tied to the current handoff hash. It does not
implement or enable live memory writes.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approval_gate_smoke.py --json
```

The command builds the existing approved-promotion operator handoff, computes
the current `operator_handoff.json` SHA-256 hash, evaluates approval artifacts,
then writes:

- `approved_promotion_operator_approval_gate/operator_approval_gate.json`
- `approved_promotion_operator_approval_gate/APPROVAL_GATE_README.md`
- `operator_approval.json`

## Approval token

The explicit dry-run approval token is:

```text
APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY
```

A valid approval artifact must include the token and:

- `handoff_sha256` matching the current handoff hash.
- `handoff_id` matching the current handoff hash.
- `approval_scope: dry_run_memory_promotion_staging_only`
- `approved_for_dry_run_staging: true`
- `approved_for_live_memory_write: false`
- `requires_explicit_operator_approval: true`
- `dry_run: true`
- `local_only: true`

## Gate coverage

- Handoff defaults to blocked and not approved.
- Missing approval fails closed.
- Invalid approval token fails closed.
- Mismatched handoff hash fails closed.
- Stale or mismatched handoff id fails closed.
- Valid explicit approval passes only for dry-run staging.
- Valid explicit approval does not allow live memory writing.
- `ready_for_operator_approved_staging` becomes `true` only for the valid
  dry-run approval case.
- `ready_for_live_memory_write` remains `false`.
- `future_live_write_allowed` remains `false`.
- Approval paths stay inside the temp workspace.

## Why it is safe

- Uses local fixtures and temporary workspaces only.
- Writes approval-gate files only inside the temp workspace.
- Does not write live runtime memory.
- Does not write vector DB data.
- Does not call models.
- Does not call embeddings.
- Does not use live accounts or API/network access.
- Does not add UI actions, browser calls, POST forms, or routes.
- Leaves `elysia/api/server.py`, `project_guardian/core.py`, and
  `config/autonomy.json` untouched.

Expected safety fields:

- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `live_vector_db_written: false`
- `account_api_network_accessed: false`
- `autonomy_enabled: false`
- `dry_run: true`
- `local_only: true`
- `operator_required: true`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approval_gate_smoke.py --json --base-dir .\tmp\approved-promotion-operator-approval-gate --keep-temp
```

Then inspect:

- `tmp\approved-promotion-operator-approval-gate\approved_promotion_operator_approval_gate\operator_approval_gate.json`
- `tmp\approved-promotion-operator-approval-gate\approved_promotion_operator_approval_gate\APPROVAL_GATE_README.md`
- `tmp\approved-promotion-operator-approval-gate\operator_approval.json`
