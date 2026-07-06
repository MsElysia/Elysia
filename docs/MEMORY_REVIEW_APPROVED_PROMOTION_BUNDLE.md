# Memory Review Approved Promotion Bundle Smoke

This dry-run/local smoke packages operator-approved and edited memory review
candidates into an inspectable promotion bundle. Rejected candidates are
excluded. The bundle is for future promotion inspection only and does not write
live runtime memory or vector DB data.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_bundle_smoke.py --json
```

The command creates a temporary workspace, stages local fixture candidates, runs
approve/edit/reject review decisions, then writes an `approved_promotion_bundle/`
directory with `promotion_manifest.json` and an operator README.

## Promotion bundle coverage

- Creates local fixture candidates and runs review decisions with one approved,
  one edited-then-approved, and one rejected candidate.
- Writes `approved_promotion_bundle/promotion_manifest.json` with promotion
  items, counts, review decision links, and SHA-256 hashes.
- Includes approved candidates in `promotion_items`.
- Includes edited candidates with `promoted_text` equal to the edited text.
- Preserves `original_text` separately for edited candidates.
- Excludes rejected candidates and reports `excluded_rejected_count`.
- Confirms `promotion_item_count` equals approved + edited counts.
- References review audit evidence via `source_queue_path`,
  `review_decisions_log_path`, and `review_decisions_log_sha256`.
- Recovery inspection evidence remains covered separately by the recovery
  inspection bundle smoke.
- All bundle paths stay inside the temp workspace.

## Why it is safe

- Uses local fixtures and temporary workspaces only; bundle files are written
  only inside the temp workspace.
- Does not write live runtime memory or vector DB data.
- Does not use live accounts.
- Does not call models.
- Does not call embeddings.
- Does not add UI actions, browser calls, POST forms, or routes.
- Left `elysia/api/server.py`, `project_guardian/core.py`, and
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
python scripts/run_memory_review_approved_promotion_bundle_smoke.py --json --base-dir .\tmp\approved-promotion-bundle --keep-temp
```

The JSON report includes artifact paths under the supplied base directory so an
operator can inspect the promotion manifest, README, review queue, and review
decisions log.

## Related review coverage

Decision branch coverage:

```powershell
python scripts/run_memory_review_decision_branches_smoke.py --json
```

See [`MEMORY_REVIEW_DECISION_BRANCHES.md`](MEMORY_REVIEW_DECISION_BRANCHES.md).

Recovery inspection bundle coverage:

```powershell
python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json
```

See [`MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md`](MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md).
