# Memory Review Decision Idempotency Smoke

This dry-run/local smoke proves that repeating Memory review decisions and the
export/store/search steps is stable: it does not create duplicate approved
records, duplicate local memory store records, or corrupted decision artifacts.

Run:

```powershell
python scripts/run_memory_review_decision_idempotency_smoke.py --json
```

The command creates a temporary transcription fixture workspace with at least
three candidates (approve, reject, and edit branches), applies the
approve/reject/edit decisions once, runs approved export + local store + search
readiness, then applies the *same* decisions again and re-runs export/store/
search. It compares first-run and second-run counts and identifiers, checks for
duplicate records, and emits JSON. The temporary workspace is removed unless
`--keep-temp` or `--base-dir` is used.

Decision idempotency coverage:

- Repeated approve/reject/edit decisions keep stable approved, rejected, and
  edited counts.
- Approved and rejected identifiers stay stable across repeated runs.
- Repeated export/store steps do not duplicate approved records or local memory
  store records (records are keyed by deterministic candidate/export/memory ids
  and the export/store files are rewritten in place).
- Reject decisions stay excluded from approved output and search.
- Edit decisions preserve the edited text after repeated runs.
- Approved-memory search readiness stays stable across passes.

Why it is safe:

- Uses local fixtures and temporary workspaces only.
- Composes the existing local ingestion/review/export/store/search helpers; no
  helper repair was required because export and store already overwrite their
  output files and resolve the latest decision per candidate.
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
python scripts/run_memory_review_decision_idempotency_smoke.py --json --base-dir .\tmp\memory-review-idempotency
```

The JSON report includes artifact paths under the supplied base directory so an
operator can inspect the review queue, decision log, approved export, and local
memory store.

## Review Decision Audit Trail

Audit-log trustworthiness is covered separately by:

```powershell
python scripts/run_memory_review_decision_audit_trail_smoke.py --json
```

That smoke applies approve/reject/edit decisions twice and then audits the
append-only `review_decisions.jsonl` log: every entry is valid JSON with the
required audit fields, records candidate identity and previous/new status,
represents all three transitions, keeps chronological timestamps, and still
resolves to the correct latest decision per candidate. Rejected candidates stay
excluded and edited text stays preserved. It uses local fixtures and temporary
workspaces only and does not use live accounts, models, embeddings, live runtime
memory/vector DB, UI actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`](MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md).

## Review Decision Tamper Evidence

Audit-log tamper detection is covered separately by:

```powershell
python scripts/run_memory_review_decision_tamper_evidence_smoke.py --json
```

That smoke proves a local-only audit checker detects corrupted
`review_decisions.jsonl` logs (malformed JSON, missing required fields,
non-chronological timestamps, unknown candidates, unsupported transitions),
returning `verdict=FAIL` with specific error messages while a clean log still
passes. It uses local fixtures and temporary workspaces only and does not use
live accounts, models, embeddings, live runtime memory/vector DB, UI actions,
browser calls, POST forms, or routes. See
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

## Review Recovery Audit Trail

Recovery action audit-trail coverage is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_trail_smoke.py --json
```

That smoke appends every quarantine/recovery step to `recovery_audit.jsonl`,
verifies the recovery audit log is valid JSONL with required fields and
chronological events, and proves recovery still uses known-good data only with
rejected candidates excluded and edited text preserved. It uses local fixtures
and temporary workspaces only and does not use live accounts, models,
embeddings, live runtime memory/vector DB, UI actions, browser calls, POST
forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md).
