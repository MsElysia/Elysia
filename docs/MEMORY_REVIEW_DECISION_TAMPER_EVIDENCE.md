# Memory Review Decision Tamper Evidence Smoke

This dry-run/local smoke proves the review decision audit checker detects and
reports corrupted `review_decisions.jsonl` logs. The prior checkpoint proved the
normal audit trail is valid and trustworthy; this checkpoint proves the audit
trail fails safely when corrupted.

Run:

```powershell
python scripts/run_memory_review_decision_tamper_evidence_smoke.py --json
```

The command creates a temporary transcription fixture workspace with three
candidates (approve, reject, and edit branches), applies the approve/reject/edit
decisions to build a valid append-only `review_decisions.jsonl`, then writes
tampered copies of that log inside the temp workspace and runs a self-contained,
local-only audit checker (`audit_decision_log`) against each. The temporary
workspace is removed unless `--keep-temp` or `--base-dir` is used.

Tamper-evidence coverage:

- The clean audit log returns `verdict=PASS`.
- A malformed JSON line fails with a specific error containing
  `malformed_json`.
- An entry missing a required field fails with a specific error containing
  `missing_required_field`.
- A non-chronological (out-of-order) timestamp fails with a specific error
  containing `non_chronological`.
- An unknown/unrecognized candidate id fails with a specific error containing
  `unknown_candidate` (optional case, implemented).
- An unsupported status transition fails with a specific error containing
  `unsupported_transition` (optional case, implemented).
- Every tampered variant returns `verdict=FAIL`.
- The clean log still returns `verdict=PASS` after the tamper cases are checked.

All five tamper cases are implemented and exercised; none are faked. If a case
were not practical it would be reported as `not_applicable` with a reason.

Why it is safe:

- Uses local fixtures and temporary workspaces only.
- Tampered logs are written only inside the temp test workspace.
- Composes the existing local ingestion/review helpers to build the clean log.
  The audit checker itself is a small, self-contained, local-only helper inside
  the smoke script; no server, API, or core file was modified. It performs no
  network, model, embedding, live-account, runtime-memory, or vector-DB access.
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
python scripts/run_memory_review_decision_tamper_evidence_smoke.py --json --base-dir .\tmp\memory-review-tamper-evidence
```

The JSON report includes the workspace path, the clean-log verdict, the per-case
detection flags (`malformed_json_detected`, `missing_field_detected`,
`non_chronological_detected`, `unknown_candidate_detected`,
`unsupported_transition_detected`), `specific_errors_present`,
`clean_log_still_passes`, and a `cases` array with each tampered variant's
verdict and specific error messages so an operator can confirm tamper detection.

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
