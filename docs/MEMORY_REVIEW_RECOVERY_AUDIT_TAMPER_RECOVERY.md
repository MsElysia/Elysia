# Memory Review Recovery Audit Tamper Recovery Smoke

This dry-run/local smoke proves that when a corrupted `recovery_audit.jsonl`
log is detected, it can be safely isolated/quarantined and recovery audit state
can be re-resolved from a known-good copy without trusting corrupted data. The
prior checkpoint proved corrupted recovery audit logs are detected; this
checkpoint proves safe recovery behavior for the recovery audit log itself.

Run:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_recovery_smoke.py --json
```

The command creates a temporary workspace, runs the existing recovery audit-trail
flow to build a valid `recovery_audit.jsonl`, and saves a known-good copy. It
then corrupts the working log (a malformed JSON line plus unsafe metadata such as
`dry_run=false`), detects the corruption, quarantines the corrupt log, writes a
quarantine manifest, and re-resolves recovery audit state from the known-good
copy only. The temporary workspace is removed unless `--keep-temp` or
`--base-dir` is used.

Recovery audit tamper-recovery/quarantine coverage:

- The clean recovery audit log returns `verdict=PASS`.
- The corrupted working log returns `verdict=FAIL` and the specific error types
  are captured (for example `malformed_json` and `unsafe_metadata`).
- Corruption is detected before any recovery step runs.
- The corrupt log is copied into a temp-only `quarantine/` directory and its
  content is preserved exactly (it is not overwritten or silently repaired).
- A quarantine manifest (`recovery_audit_quarantine_manifest.json`) is written
  recording the original recovery audit path, the quarantine recovery audit path,
  the known-good recovery audit path, the detected error types, a quarantine
  timestamp, `dry_run=true`, `local_only=true`, `silently_repaired=false`,
  `live_memory_written=false`, `operator_required=true`, and all safety metadata
  fields.
- The corrupt recovery audit log is never trusted for recovery audit validation.
- Recovery audit state is re-resolved from the known-good copy only.
- The recovered recovery audit event sequence matches the known-good
  pre-corruption state.

Why it is safe:

- Uses local fixtures and temporary workspaces only; corrupt logs, quarantine
  copies, and manifests are written only inside the temp workspace.
- Reuses the local-only `audit_recovery_log` checker from the recovery audit
  tamper-evidence smoke and the existing recovery audit-trail smoke; no server,
  API, or core file was modified. It performs no network, model, embedding,
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
- `dry_run: true`
- `local_only: true`
- `silently_repaired: false`
- `operator_required: true`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_recovery_smoke.py --json --base-dir .\tmp\memory-review-recovery-audit-tamper-recovery
```

The JSON report includes artifact paths under the supplied base directory so an
operator can inspect the known-good recovery audit log, the restored recovery
audit log, the quarantined corrupt recovery audit log, and the quarantine
manifest.

## Recovery Inspection Bundle

Operator inspection bundle coverage is available separately by:

```powershell
python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json
```

That smoke runs the tamper-recovery flow and writes a
`recovery_inspection_bundle/` directory with an inspection summary (paths,
recovered event sequence, SHA-256 hashes, and safety metadata). It uses local
fixtures and temporary workspaces only and does not use live accounts, models,
embeddings, live runtime memory, vector DB writes, UI actions, browser calls,
POST forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md`](MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md).

## Recovery Audit Tamper Evidence

Recovery audit log tamper detection is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json
```

That smoke proves a local-only audit checker detects corrupted
`recovery_audit.jsonl` logs (malformed JSON, missing required fields,
non-chronological timestamps, unsupported recovery event types, unsafe metadata),
returning `verdict=FAIL` with specific error messages while a clean log still
passes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md).

## Recovery Audit Trail

Recovery action audit-trail coverage is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_trail_smoke.py --json
```

That smoke appends every quarantine/recovery step to `recovery_audit.jsonl` and
verifies the recovery audit log is valid JSONL with required fields and
chronological events. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md).
