# Memory Review Approved Promotion Tamper Evidence Smoke

This dry-run/local smoke proves that approved-promotion bundle manifests fail
closed when tampered. It builds a clean approved-promotion bundle from local
fixtures, verifies the clean `promotion_manifest.json`, then writes corrupted
manifest copies and checks that each one returns `verdict=FAIL` with a specific
error token.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_tamper_evidence_smoke.py --json
```

The smoke uses the approved-promotion bundle flow as its source of truth. It
does not promote memory into any live runtime store and does not write vector DB
data.

## Tamper cases

- `malformed_json`
- `missing_required_manifest_field`
- `missing_required_promotion_item_field`
- `promoted_text_hash_mismatch`
- `candidate_hash_mismatch`
- `rejected_candidate_included`
- `promotion_item_count_mismatch`
- `unsafe_metadata`
- `manifest_hash_mismatch`

The clean manifest must continue to pass after the tampered copies are checked.

## Why it is safe

- Uses local fixtures and temporary workspaces only.
- Writes tampered manifests only inside the temp workspace.
- Does not write live runtime memory or vector DB data.
- Does not use live accounts.
- Does not call models.
- Does not call embeddings.
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
python scripts/run_memory_review_approved_promotion_tamper_evidence_smoke.py --json --base-dir .\tmp\approved-promotion-tamper --keep-temp
```

The JSON report includes paths to the clean manifest, clean bundle artifacts,
and each tampered manifest under the supplied base directory.
