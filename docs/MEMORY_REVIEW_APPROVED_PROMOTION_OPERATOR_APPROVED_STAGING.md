# Memory Review Approved Promotion Operator-Approved Staging Smoke

This dry-run/local smoke takes a valid operator handoff plus a valid explicit
operator approval and creates an operator-approved staging package. Staging
happens only after both the handoff and the approval gate pass. It does not
implement or enable live memory writes.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approved_staging_smoke.py --json
```

The command builds the existing approved-promotion bundle, tamper-evidence
checks, operator handoff, and approval gate, then writes:

- `approved_promotion_operator_approved_staging/operator_approved_staging_manifest.json`
- `approved_promotion_operator_approved_staging/STAGING_README.md`

## Approval token

The explicit dry-run approval token is:

```text
APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY
```

## Staging coverage

- Staging only happens after a valid handoff and valid explicit operator approval.
- Missing or invalid approval fails closed and does not create a PASS staging
  manifest.
- Valid approval allows dry-run staging only.
- Staging includes approved and edited promotion items.
- Edited promoted text is preserved.
- Rejected items remain excluded and the exclusion is counted.
- Staging includes promotion, handoff, and approval-gate SHA-256 hashes.
- Approval token phrase is recorded.
- Tamper-evidence verdict must be `PASS`.
- Approval-gate verdict must be `PASS`.
- `ready_for_operator_approved_staging` becomes `true` only after valid approval.
- Staging is not live memory write readiness.
- `ready_for_live_memory_write` remains `false`.
- `future_live_write_allowed` remains `false`.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- Staging paths stay inside the temp workspace.

## Why it is safe

- Uses local fixtures and temporary workspaces only.
- Writes staging files only inside the temp workspace.
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
- `ready_for_operator_approved_staging: true`
- `ready_for_live_memory_write: false`
- `future_live_write_allowed: false`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approved_staging_smoke.py --json --base-dir .\tmp\approved-promotion-operator-approved-staging --keep-temp
```

Then inspect:

- `tmp\approved-promotion-operator-approved-staging\approved_promotion_operator_approved_staging\operator_approved_staging_manifest.json`
- `tmp\approved-promotion-operator-approved-staging\approved_promotion_operator_approved_staging\STAGING_README.md`

## Operator-approved staging tamper evidence

Operator-approved staging tamper-evidence coverage exists through:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke.py --json
```

That smoke builds a clean operator-approved staging package, validates it as
`PASS`, then proves corrupted copies validate as `FAIL`. Covered failures
include malformed JSON, missing fields, hash mismatches, rejected inclusion,
count mismatch, unsafe metadata, and live-write unblocked. Live memory writing
is not implemented or enabled. Vector DB writing is not implemented or enabled.
This campaign does not call models, does not call embeddings, does not use live
accounts, and does not add UI actions or routes. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` remain untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING_TAMPER_EVIDENCE.md).
