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

## Review Decision Idempotency

Repeated-decision safety is covered separately by:

```powershell
python scripts/run_memory_review_decision_idempotency_smoke.py --json
```

That smoke applies the same approve/reject/edit decisions twice and re-runs
export/store/search each time. It proves repeated decisions keep stable counts,
approved/rejected identifiers stay stable, repeated export/store steps do not
duplicate approved or local memory store records, rejected candidates stay
excluded from approved output and search, and edited text stays preserved. It
uses local fixtures and temporary workspaces only and does not use live
accounts, models, embeddings, live runtime memory/vector DB, UI actions, browser
calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`](MEMORY_REVIEW_DECISION_IDEMPOTENCY.md).

## Review Decision Audit Trail

Audit-log trustworthiness is covered separately by:

```powershell
python scripts/run_memory_review_decision_audit_trail_smoke.py --json
```

That smoke applies approve/reject/edit decisions twice and audits the append-only
`review_decisions.jsonl` log: every entry is valid JSON with the required audit
fields, records candidate identity and previous/new status, represents all three
transitions, keeps chronological timestamps, and still resolves to the correct
latest decision per candidate. Rejected candidates stay excluded and edited text
stays preserved. It uses local fixtures and temporary workspaces only and does
not use live accounts, models, embeddings, live runtime memory/vector DB, UI
actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`](MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md).
