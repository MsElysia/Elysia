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
