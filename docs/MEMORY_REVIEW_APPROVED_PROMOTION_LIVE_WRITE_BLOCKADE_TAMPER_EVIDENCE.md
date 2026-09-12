# Memory Review Approved Promotion Live-Write Blockade Tamper Evidence

This dry-run/local smoke proves that a live-write blockade report cannot be
silently corrupted to claim that live memory or vector DB writes were allowed,
attempted, performed, or safe. It builds a clean blockade report from local
fixtures, verifies that clean report as `PASS`, then writes isolated corrupted
copies and checks that each one returns `verdict=FAIL` with a specific error
token.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke.py --json
```

## Coverage

Live-write blockade tamper-evidence coverage exists.

- A clean blockade report validates as `PASS`.
- Corrupted blockade reports validate as `FAIL`.
- Covered failures include malformed JSON, missing fields, hash mismatch,
  live-write allowed, live-write attempted, live-write performed, vector write
  allowed, vector write attempted, vector write performed, nonzero created-file
  counts, missing denial reason, future milestone disabled, and unsafe
  metadata.

## Tamper cases

- `malformed_json`
- `missing_required_report_field`
- `source_staging_manifest_hash_mismatch`
- `clean_staging_invalid`
- `staging_tamper_evidence_failed`
- `live_memory_write_allowed`
- `live_memory_write_not_denied`
- `live_memory_write_attempted`
- `live_memory_write_performed`
- `live_memory_write_path_created`
- `vector_db_write_allowed`
- `vector_db_write_not_denied`
- `vector_db_write_attempted`
- `vector_db_write_performed`
- `vector_db_write_path_created`
- `runtime_memory_files_created_nonzero`
- `vector_db_files_created_nonzero`
- `ready_for_live_memory_write_true`
- `future_live_write_allowed_true`
- `future_milestone_not_required`
- `missing_denial_reason`
- `unsafe_metadata`

The clean blockade report must continue to pass after the tampered copies are
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
python scripts/run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke.py --json --base-dir .\tmp\ap-live-write-blockade-tamper --keep-temp
```

Then inspect:

- the clean live-write blockade report
- `tmp\ap-live-write-blockade-tamper\tampered_live_write_blockade_reports\`

## Final readiness packet

The final readiness packet exists. It summarizes the approved-promotion safety
chain. It is dry-run only. Live memory writing remains blocked. Vector DB
writing remains blocked. No live memory/vector write path is implemented.
Future live write requires a separate explicit milestone.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET.md`](MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET.md).

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_packet_smoke.py --json
```

## Final readiness packet tamper evidence

Final readiness packet tamper-evidence exists. A clean final readiness packet
validates `PASS`. Corrupted packet copies validate `FAIL`. Covered failures
include hash mismatches, item edits, rejected inclusion, safety-chain edits,
live-write flag changes, missing blocked reasons, missing future milestone
requirement, and unsafe metadata. Live memory writing remains blocked. Vector
DB writing remains blocked. No live memory/vector write path is implemented.
Future live write requires a separate explicit milestone.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET_TAMPER_EVIDENCE.md).
