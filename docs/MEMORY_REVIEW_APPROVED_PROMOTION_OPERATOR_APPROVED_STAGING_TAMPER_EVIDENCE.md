# Memory Review Approved Promotion Operator-Approved Staging Tamper Evidence

This dry-run/local smoke proves that an operator-approved staging package
detects corruption and tampering before any future live memory write path
exists. It builds a clean operator-approved staging package from local
fixtures, verifies that clean package as `PASS`, then writes isolated
corrupted staging-manifest copies and checks that each one returns
`verdict=FAIL` with a specific error token.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke.py --json
```

The smoke uses the existing operator-approved staging flow as its source of
truth. It does not implement or enable live memory writes and does not write
vector DB data.

## Coverage

Operator-approved staging tamper-evidence coverage exists.

- A clean operator-approved staging package validates as `PASS`.
- A corrupted staging package validates as `FAIL`.
- Covered failures include malformed JSON, missing required manifest fields,
  missing required staged-item fields, promoted-text hash mismatch, promotion
  manifest hash mismatch, operator-handoff hash mismatch, approval-gate hash
  mismatch, rejected-candidate inclusion, staging item-count mismatch, unsafe
  metadata, and live-write unblocked flags.

## Tamper cases

- `malformed_json`
- `missing_required_manifest_field`
- `missing_required_staged_item_field`
- `promoted_text_hash_mismatch`
- `promotion_manifest_hash_mismatch`
- `operator_handoff_hash_mismatch`
- `approval_gate_hash_mismatch`
- `rejected_candidate_included`
- `staging_item_count_mismatch`
- `unsafe_metadata`
- `live_write_unblocked`

The clean staging package must continue to pass after the tampered copies are
checked.

## Why it is safe

- Uses local fixtures and temporary workspaces only.
- Writes tamper-evidence files only inside the temp workspace.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
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
python scripts/run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke.py --json --base-dir .\tmp\approved-promotion-operator-approved-staging-tamper-evidence --keep-temp
```

Then inspect:

- the clean operator-approved staging package
- `tmp\approved-promotion-operator-approved-staging-tamper-evidence\tampered_operator_approved_staging_manifests\`
