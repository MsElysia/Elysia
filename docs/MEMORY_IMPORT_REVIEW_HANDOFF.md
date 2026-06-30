# Memory Import Review Handoff Smoke

This dry-run/local smoke proves that Project Guardian Memory imports can hand off
local fixture data into the review/search workflow without live execution.

Run:

```powershell
python scripts/run_memory_import_review_handoff_smoke.py --json
```

The command defaults to all currently supported local fixture source types:

- `transcription`
- `chatgpt_export`
- `email_export`

It creates temporary workspaces, runs the existing local preview/apply staging
logic, verifies review queue artifacts, approves local fixture candidates,
prepares the approved-memory export/store/search path, emits JSON, and removes
the temporary workspace unless `--keep-temp` or `--base-dir` is used.

Expected safety fields:

- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `live_vector_db_written: false`
- `account_api_network_accessed: false`
- `autonomy_enabled: false`

Safety boundaries:

- Uses local fixtures and temporary workspaces only.
- Does not use live accounts.
- Does not call models.
- Does not call embeddings.
- Does not write live runtime memory or vector DB data.
- Does not add UI actions, browser calls, POST forms, or routes.
- Does not modify `elysia/api/server.py`, `project_guardian/core.py`, or
  `config/autonomy.json`.

To inspect artifacts after a run:

```powershell
python scripts/run_memory_import_review_handoff_smoke.py --json --base-dir .\tmp\memory-handoff-smoke
```

The JSON report includes per-source artifact paths under the supplied base
directory.
