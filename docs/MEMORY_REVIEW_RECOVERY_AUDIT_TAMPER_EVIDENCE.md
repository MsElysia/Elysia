# Memory Review Recovery Audit Tamper Evidence Smoke

This dry-run/local smoke proves the recovery audit checker detects and reports
corrupted `recovery_audit.jsonl` logs. The prior checkpoint proved every
quarantine/recovery action is appended to a well-formed, chronological,
operator-safe recovery audit log; this checkpoint proves the recovery audit log
itself fails safely when corrupted.

Run:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json
```

The command creates a temporary workspace, runs the existing recovery audit-trail
flow to build a valid `recovery_audit.jsonl`, then writes tampered copies inside
the temp workspace (malformed JSON line, missing required field,
non-chronological timestamp, unsupported recovery event type, and unsafe metadata)
and runs a self-contained, local-only audit checker (`audit_recovery_log`)
against each. The temporary workspace is removed unless `--keep-temp` or
`--base-dir` is used.

Recovery audit tamper-evidence coverage:

- The clean recovery audit log returns `verdict=PASS`.
- A malformed JSON line fails with a specific error containing `malformed_json`.
- An entry missing a required field fails with a specific error containing
  `missing_required_field`.
- A non-chronological (out-of-order) timestamp fails with a specific error
  containing `non_chronological`.
- An unsupported recovery event type fails with a specific error containing
  `unsupported_event` (implemented).
- Unsafe metadata (for example `dry_run=false`) fails with a specific error
  containing `unsafe_metadata` (implemented).
- Every tampered variant returns `verdict=FAIL`.
- The clean log still returns `verdict=PASS` after the tamper cases are checked.

All five tamper cases are implemented and exercised; none are faked.

Why it is safe:

- Uses local fixtures and temporary workspaces only.
- Tampered recovery audit logs are written only inside the temp test workspace.
- Reuses the existing recovery audit-trail smoke to build the clean log and
  imports recovery audit constants from that script. The audit checker itself
  is a small, self-contained, local-only helper inside this smoke script; no
  server, API, or core file was modified.
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
python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json --base-dir .\tmp\memory-review-recovery-audit-tamper
```

The JSON report includes the workspace path, the clean-log verdict, per-case
detection flags, `specific_errors_present`, `clean_log_still_passes`, and a
`cases` array with each tampered variant's verdict and specific error messages.
