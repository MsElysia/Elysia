# Memory Review Recovery Audit Trail Smoke

This dry-run/local smoke proves every quarantine/recovery action is written to a
well-formed, chronological, operator-safe recovery audit log. The prior
checkpoint proved a corrupted `review_decisions.jsonl` can be detected,
quarantined, preserved byte-for-byte, and bypassed while latest decisions are
re-resolved from known-good clean data; this checkpoint proves the recovery
action itself leaves a trustworthy trail.

Run:

```powershell
python scripts/run_memory_review_recovery_audit_trail_smoke.py --json
```

The command creates a temporary transcription fixture workspace with three
candidates (approve, reject, and edit branches), applies the approve/reject/edit
decisions to build a valid append-only `review_decisions.jsonl`, saves a
known-good copy, corrupts the working log, detects the corruption, quarantines
the corrupt log with a manifest, recovers from the known-good copy only, and
appends every recovery step to `recovery_audit.jsonl`. The temporary workspace
is removed unless `--keep-temp` or `--base-dir` is used.

Recovery audit-trail coverage:

- Every quarantine/recovery action is appended to `recovery_audit.jsonl`.
- Expected recovery events are present: `corruption_detected`,
  `quarantine_created`, `corrupt_log_preserved`, `manifest_written`,
  `known_good_resolution_used`, `recovery_completed`.
- Every recovery audit entry is valid JSON with required fields:
  `recovery_event_id`, `event_type`, `event_at`, `source_log_path`,
  `quarantine_log_path`, `quarantine_manifest_path`, `detected_error_types`,
  `operator_required`, `dry_run`, `local_only`, `silently_repaired`,
  `live_memory_written`, `model_called`, `embeddings_used`,
  `live_vector_db_written`, `account_api_network_accessed`, `autonomy_enabled`.
- Event timestamps are chronological (non-decreasing).
- Corruption is detected before quarantine; the corrupt log is preserved
  byte-for-byte and is never trusted for latest-decision resolution.
- Recovery resolves latest decisions from known-good clean data only.
- Rejected candidates stay excluded from approved export after recovery.
- Edited text stays preserved after recovery.

Why it is safe:

- Uses local fixtures and temporary workspaces only; recovery audit logs,
  quarantine copies, and manifests are written only inside the temp workspace.
- Reuses the local-only `audit_decision_log` checker from the tamper-evidence
  smoke and the existing local ingestion/review/export helpers; no server, API,
  or core file was modified. It performs no network, model, embedding,
  live-account, runtime-memory, or vector-DB access.
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
- `operator_required: true`
- `dry_run: true`
- `local_only: true`
- `silently_repaired: false`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_recovery_audit_trail_smoke.py --json --base-dir .\tmp\memory-review-recovery-audit-trail
```

The JSON report includes artifact paths under the supplied base directory so an
operator can inspect the recovery audit log, the known-good log, the restored
log, the quarantined corrupt log, the quarantine manifest, and the approved
export.

## Recovery Audit Tamper Evidence

Recovery audit log tamper detection is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json
```

That smoke builds a clean `recovery_audit.jsonl`, then writes tampered copies
inside a temp workspace (malformed JSON line, missing required field,
non-chronological timestamp, unsupported recovery event type, unsafe metadata)
and proves a local-only audit checker returns `verdict=FAIL` with specific error
messages while the clean log still passes. It uses local fixtures and temporary
workspaces only and does not use live accounts, models, embeddings, live runtime
memory/vector DB, UI actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md).
