# Memory Review Approved Promotion Live-Write Blockade Smoke

This dry-run/local smoke proves that even a clean, untampered,
operator-approved staging package cannot perform a live memory write. It builds
the existing operator-approved staging package, validates that clean staging and
staging tamper evidence both return `PASS`, then records simulated live-memory
and vector-DB write requests and denies them before any write occurs.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_blockade_smoke.py --json
```

The command writes:

- `approved_promotion_live_write_blockade/live_write_blockade_report.json`
- `approved_promotion_live_write_blockade/LIVE_WRITE_BLOCKADE_README.md`

## Coverage

Live-write blockade proof exists.

- A clean operator-approved staging package validates as `PASS`.
- Staging tamper evidence validates as `PASS`.
- A live memory write request is denied.
- A vector DB write request is denied.
- No live memory write is attempted.
- No vector DB write is attempted.
- No runtime memory file is created.
- No vector DB file is created.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- Future live write requires a separate explicit milestone.

## Why it is safe

- Uses local fixtures and temporary workspaces only.
- Writes the dry-run denial report only inside the temp workspace.
- Does not call any live memory writer.
- Does not create runtime memory files.
- Does not create vector DB files.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- Leaves `elysia/api/server.py`, `project_guardian/core.py`, and
  `config/autonomy.json` untouched.

Expected safety fields:

- `ready_for_operator_approved_staging: true`
- `ready_for_live_memory_write: false`
- `future_live_write_allowed: false`
- `requires_future_live_write_milestone: true`
- `live_memory_write_requested: true`
- `live_memory_write_denied: true`
- `live_memory_write_attempted: false`
- `live_memory_write_performed: false`
- `vector_db_write_requested: true`
- `vector_db_write_denied: true`
- `vector_db_write_attempted: false`
- `vector_db_write_performed: false`
- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `live_vector_db_written: false`
- `account_api_network_accessed: false`
- `autonomy_enabled: false`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_blockade_smoke.py --json --base-dir .\tmp\ap-live-write-blockade --keep-temp
```

Then inspect:

- `tmp\ap-live-write-blockade\approved_promotion_live_write_blockade\live_write_blockade_report.json`
- `tmp\ap-live-write-blockade\approved_promotion_live_write_blockade\LIVE_WRITE_BLOCKADE_README.md`

## Live-write blockade tamper evidence

Live-write blockade tamper-evidence coverage exists through:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke.py --json
```

A clean blockade report validates as `PASS`. Corrupted blockade reports
validate as `FAIL`. Covered failures include malformed JSON, missing fields,
hash mismatch, live-write allowed, live-write attempted, live-write performed,
vector write allowed, vector write attempted, vector write performed, nonzero
created-file counts, missing denial reason, future milestone disabled, and
unsafe metadata. Live memory writing is not implemented or enabled. Vector DB
writing is not implemented or enabled. This campaign does not call models, does
not call embeddings, does not use live accounts, and does not add UI actions or
routes. `elysia/api/server.py`, `project_guardian/core.py`, and
`config/autonomy.json` remain untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE_TAMPER_EVIDENCE.md).

## Final readiness packet

The final readiness packet exists. It summarizes the approved-promotion safety
chain. It is dry-run only. Live memory writing remains blocked. Vector DB
writing remains blocked. No live memory/vector write path is implemented.
Future live write requires a separate explicit milestone.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET.md`](MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET.md).
