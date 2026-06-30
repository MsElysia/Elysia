# Memory Review Decision Branches Smoke

This dry-run/local smoke proves the three main Memory review decisions:

- approve a candidate
- reject a candidate
- edit a candidate, then approve it

Run:

```powershell
python scripts/run_memory_review_decision_branches_smoke.py --json
```

The command creates a temporary transcription fixture workspace with at least
three candidates, applies one decision per branch, exports approved memory,
writes a local approved-memory store under the temp workspace, and emits JSON.
The temporary workspace is removed unless `--keep-temp` or `--base-dir` is used.

The report verifies:

- the approve branch reaches approved output
- the reject branch is excluded from approved output and search
- the edit branch preserves edited text in approved output
- approved-memory search is ready from approved decisions only

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
python scripts/run_memory_review_decision_branches_smoke.py --json --base-dir .\tmp\memory-review-decisions
```

The JSON report includes artifact paths under the supplied base directory.
