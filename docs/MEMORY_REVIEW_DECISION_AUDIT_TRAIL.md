# Memory Review Decision Audit Trail Smoke

This dry-run/local smoke proves the append-only `review_decisions.jsonl` audit
trail stays well-formed, chronological, and operator-safe across repeated
approve/reject/edit review decisions.

Run:

```powershell
python scripts/run_memory_review_decision_audit_trail_smoke.py --json
```

The command creates a temporary transcription fixture workspace with at least
three candidates (approve, reject, and edit branches), applies the
approve/reject/edit decisions twice, then reads the review decision log and
emits JSON. The temporary workspace is removed unless `--keep-temp` or
`--base-dir` is used.

Audit-trail coverage:

- `review_decisions.jsonl` is an append-only JSONL log.
- Every entry is checked for valid JSON.
- Every entry is checked for the required audit fields: `decision_id`,
  `candidate_id`, `previous_status`, `new_status`, `decided_at`,
  `operator_required`, `live_memory_written`, and `source_queue_path`.
- Candidate identity and previous/new status are checked on every entry.
- Approve, reject, and edit transitions are all represented.
- Timestamps are present and chronological (non-decreasing) across the log.
- Repeated decisions do not corrupt latest-decision resolution; the log grows by
  appending, and latest-decision resolution still returns the correct approve,
  reject, and edit status per candidate.
- Rejected candidates remain excluded from approved export, local store, and
  search.
- Edited text remains preserved in the edited artifact referenced by the log.

Why it is safe:

- Uses local fixtures and temporary workspaces only.
- Composes the existing local ingestion/review/export/store/search helpers; no
  helper repair was required because the review helpers already record
  `decision_id`, `previous_status`, `new_status`, `decided_at`,
  `operator_required=true`, and `live_memory_written=false` for every decision.
- Does not use live accounts.
- Does not call models.
- Does not call embeddings.
- Does not write live runtime memory or vector DB data.
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

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_decision_audit_trail_smoke.py --json --base-dir .\tmp\memory-review-audit-trail
```

The JSON report includes artifact paths under the supplied base directory so an
operator can inspect the review queue, the append-only decision log, the
approved export, the local memory store, and the edited-text artifact.

## Review Decision Tamper Evidence

Audit-log tamper detection is covered separately by:

```powershell
python scripts/run_memory_review_decision_tamper_evidence_smoke.py --json
```

That smoke builds a clean audit log, then writes tampered copies inside a temp
workspace (malformed JSON line, missing required field, non-chronological
timestamp, unknown candidate id, unsupported status transition) and proves a
local-only audit checker returns `verdict=FAIL` with specific error messages for
each while the clean log still passes. It uses local fixtures and temporary
workspaces only and does not use live accounts, models, embeddings, live runtime
memory/vector DB, UI actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md).

## Review Decision Tamper Recovery

Safe recovery/quarantine after a corrupted log is detected is covered separately
by:

```powershell
python scripts/run_memory_review_decision_tamper_recovery_smoke.py --json
```

That smoke builds a clean log and a known-good copy, corrupts the working log,
detects the corruption, quarantines the corrupt log (preserved, not repaired)
with a manifest, and re-resolves the latest decisions from the known-good copy
only. It proves the corrupt log is never trusted, rejected candidates stay
excluded, and edited text stays preserved. It uses local fixtures and temporary
workspaces only and does not use live accounts, models, embeddings, live runtime
memory/vector DB, UI actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md`](MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md).
