# Memory Review Decision Tamper Recovery Smoke

This dry-run/local smoke proves that when a corrupted `review_decisions.jsonl`
audit log is detected, it can be safely isolated/quarantined and the
last-known-good review state can be re-resolved without trusting corrupted data.
The prior checkpoint proved corrupted audit logs are detected; this checkpoint
proves safe recovery behavior.

Run:

```powershell
python scripts/run_memory_review_decision_tamper_recovery_smoke.py --json
```

The command creates a temporary transcription fixture workspace with three
candidates (approve, reject, and edit branches), applies the approve/reject/edit
decisions to build a valid append-only `review_decisions.jsonl`, and saves a
known-good copy. It then corrupts the working log (a malformed JSON line plus a
missing required field), detects the corruption, quarantines the corrupt log,
and re-resolves the latest decisions from the known-good copy only. The
temporary workspace is removed unless `--keep-temp` or `--base-dir` is used.

Tamper-recovery/quarantine coverage:

- The clean audit log returns `verdict=PASS` and resolves to the expected
  approve/reject/edit latest decisions.
- The corrupted working log returns `verdict=FAIL` and the specific error types
  are captured (for example `malformed_json` and `missing_required_field`).
- Corruption is detected before any recovery step runs.
- The corrupt log is copied into a temp-only `quarantine/` directory and its
  content is preserved exactly (it is not overwritten or silently repaired).
- A quarantine manifest (`quarantine_manifest.json`) is written recording the
  original log path, the quarantine log path, the known-good log path, the
  detected error types, a quarantine timestamp, `dry_run=true`,
  `local_only=true`, `silently_repaired=false`, `live_memory_written=false`, and
  `operator_required=true`.
- The corrupt log is never trusted for latest-decision resolution: loading latest
  decisions from the corrupt log raises, so recovery uses the known-good copy.
- The recovered latest decisions match the known-good pre-corruption state.
- The rejected candidate stays excluded from the approved export after recovery.
- The edited text stays preserved after recovery.

Why it is safe:

- Uses local fixtures and temporary workspaces only; corrupt logs, quarantine
  copies, and manifests are written only inside the temp workspace.
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

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_decision_tamper_recovery_smoke.py --json --base-dir .\tmp\memory-review-tamper-recovery
```

The JSON report includes artifact paths under the supplied base directory so an
operator can inspect the known-good log, the restored log, the quarantined
corrupt log, the quarantine manifest, and the approved export.

## Review Recovery Audit Trail

Recovery action audit-trail coverage is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_trail_smoke.py --json
```

That smoke appends every quarantine/recovery step to `recovery_audit.jsonl`,
verifies the recovery audit log is valid JSONL with required fields and
chronological events (`corruption_detected`, `quarantine_created`,
`corrupt_log_preserved`, `manifest_written`, `known_good_resolution_used`,
`recovery_completed`), and proves recovery still uses known-good data only with
rejected candidates excluded and edited text preserved. It uses local fixtures
and temporary workspaces only and does not use live accounts, models,
embeddings, live runtime memory/vector DB, UI actions, browser calls, POST
forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md).

## Recovery Audit Tamper Evidence

Recovery audit log tamper detection is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json
```

That smoke proves a local-only audit checker detects corrupted
`recovery_audit.jsonl` logs (malformed JSON, missing required fields,
non-chronological timestamps, unsupported recovery event types, unsafe metadata),
returning `verdict=FAIL` with specific error messages while a clean log still
passes. It uses local fixtures and temporary workspaces only and does not use
live accounts, models, embeddings, live runtime memory/vector DB, UI actions,
browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md).

## Recovery Audit Tamper Recovery

Safe recovery/quarantine after a corrupted recovery audit log is detected is
covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_recovery_smoke.py --json
```

That smoke builds a clean `recovery_audit.jsonl` and a known-good copy, corrupts
the working log, detects the corruption, quarantines the corrupt log (preserved,
not repaired) with a manifest, and re-resolves recovery audit state from the
known-good copy only. It proves the corrupt recovery audit log is never trusted
and no silent repair occurs. It uses local fixtures and temporary workspaces
only and does not use live accounts, models, embeddings, live runtime memory,
vector DB writes, UI actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_RECOVERY.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_RECOVERY.md).
