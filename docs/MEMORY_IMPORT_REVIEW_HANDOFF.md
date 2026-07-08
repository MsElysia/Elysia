# Memory Import Review Handoff Smoke

This dry-run/local smoke proves that Project Guardian Memory imports can hand off
local fixture data into the review/search workflow without live execution.

Run:

```powershell
python scripts/run_memory_import_review_handoff_smoke.py --json
```

The command defaults to all currently supported local fixture source types:

- `transcription`
- `chatgpt_export`
- `email_export`

It creates temporary workspaces, runs the existing local preview/apply staging
logic, verifies review queue artifacts, approves local fixture candidates,
prepares the approved-memory export/store/search path, emits JSON, and removes
the temporary workspace unless `--keep-temp` or `--base-dir` is used.

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
python scripts/run_memory_import_review_handoff_smoke.py --json --base-dir .\tmp\memory-handoff-smoke
```

The JSON report includes per-source artifact paths under the supplied base
directory.

## Review Decision Branches

Approve/reject/edit branch coverage is available through:

```powershell
python scripts/run_memory_review_decision_branches_smoke.py --json
```

That smoke uses local fixtures and temporary workspaces only. It proves one
candidate can be approved, one can be rejected, and one can be edited before
approval. Rejected candidates are excluded from approved output and search, and
edited candidates preserve the edited text in approved output.

The branch smoke does not use live accounts, models, embeddings, runtime memory,
vector DB writes, UI actions, browser calls, POST forms, or routes.

## Review Decision Idempotency

Repeated-decision safety is available through:

```powershell
python scripts/run_memory_review_decision_idempotency_smoke.py --json
```

That smoke applies the same approve/reject/edit decisions twice and re-runs the
export/store/search steps each time. It proves repeated decisions keep stable
counts and identifiers, repeated export/store steps do not duplicate approved or
local memory store records, rejected candidates stay excluded from approved
output and search, and edited text stays preserved. It uses local fixtures and
temporary workspaces only and does not use live accounts, models, embeddings,
live runtime memory, vector DB writes, UI actions, browser calls, POST forms, or
routes. See
[`MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`](MEMORY_REVIEW_DECISION_IDEMPOTENCY.md).

## Review Decision Audit Trail

Audit-log trustworthiness is available through:

```powershell
python scripts/run_memory_review_decision_audit_trail_smoke.py --json
```

That smoke applies approve/reject/edit decisions twice and audits the append-only
`review_decisions.jsonl` log: every entry is valid JSON with the required audit
fields, records candidate identity and previous/new status, represents all three
transitions, keeps chronological timestamps, and still resolves to the correct
latest decision per candidate. Rejected candidates stay excluded and edited text
stays preserved. It uses local fixtures and temporary workspaces only and does
not use live accounts, models, embeddings, live runtime memory, vector DB writes,
UI actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`](MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md).

## Review Decision Tamper Evidence

Audit-log tamper detection is available through:

```powershell
python scripts/run_memory_review_decision_tamper_evidence_smoke.py --json
```

That smoke proves a local-only audit checker detects corrupted
`review_decisions.jsonl` logs (malformed JSON, missing required fields,
non-chronological timestamps, unknown candidates, unsupported transitions),
returning `verdict=FAIL` with specific error messages while a clean log still
passes. It uses local fixtures and temporary workspaces only and does not use
live accounts, models, embeddings, live runtime memory, vector DB writes, UI
actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md).

## Review Decision Tamper Recovery

Safe recovery/quarantine after a corrupted log is detected is available through:

```powershell
python scripts/run_memory_review_decision_tamper_recovery_smoke.py --json
```

That smoke builds a clean log and a known-good copy, corrupts the working log,
detects the corruption, quarantines the corrupt log (preserved, not repaired)
with a manifest, and re-resolves the latest decisions from the known-good copy
only. It proves the corrupt log is never trusted, rejected candidates stay
excluded, and edited text stays preserved. It uses local fixtures and temporary
workspaces only and does not use live accounts, models, embeddings, live runtime
memory, vector DB writes, UI actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md`](MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md).

## Review Recovery Audit Trail

Recovery action audit-trail coverage is available through:

```powershell
python scripts/run_memory_review_recovery_audit_trail_smoke.py --json
```

That smoke appends every quarantine/recovery step to `recovery_audit.jsonl`,
verifies the recovery audit log is valid JSONL with required fields and
chronological events, and proves recovery still uses known-good data only with
rejected candidates excluded and edited text preserved. It uses local fixtures
and temporary workspaces only and does not use live accounts, models,
embeddings, live runtime memory, vector DB writes, UI actions, browser calls,
POST forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md).

## Recovery Audit Tamper Evidence

Recovery audit log tamper detection is available through:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json
```

That smoke proves a local-only audit checker detects corrupted
`recovery_audit.jsonl` logs (malformed JSON, missing required fields,
non-chronological timestamps, unsupported recovery event types, unsafe metadata),
returning `verdict=FAIL` with specific error messages while a clean log still
passes. It uses local fixtures and temporary workspaces only and does not use
live accounts, models, embeddings, live runtime memory, vector DB writes, UI
actions, browser calls, POST forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md).

## Recovery Audit Tamper Recovery

Safe recovery/quarantine after a corrupted recovery audit log is detected is
available through:

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

## Recovery Inspection Bundle

Operator inspection bundle coverage is available through:

```powershell
python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json
```

That smoke runs the tamper-recovery flow and writes a
`recovery_inspection_bundle/` directory with an inspection summary (paths,
recovered event sequence, detected error types from the quarantine manifest,
SHA-256 hashes, and safety metadata). Re-running against the same kept
`--base-dir` may detect a stale workspace; use `--reset-workspace` to remove
only known generated dry-run artifacts under that base directory before rerunning.
It uses local
fixtures and temporary workspaces only and does not use live accounts, models,
embeddings, live runtime memory, vector DB writes, UI actions, browser calls,
POST forms, or routes. See
[`MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md`](MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md).

## Approved Promotion Bundle

Operator approved-promotion bundle coverage is available through:

```powershell
python scripts/run_memory_review_approved_promotion_bundle_smoke.py --json
```

That smoke stages local fixture candidates, runs approve/edit/reject review
decisions, and writes an `approved_promotion_bundle/` directory with a promotion
manifest listing approved and edited candidates ready for future promotion.
Rejected candidates are excluded. Edited candidates preserve both original and
edited text with review decision links and SHA-256 hashes. It uses local
fixtures and temporary workspaces only and does not use live accounts, models,
embeddings, live runtime memory, vector DB writes, UI actions, browser calls,
POST forms, or routes. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_BUNDLE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_BUNDLE.md).

## Approved Promotion Tamper Evidence

Approved-promotion manifest tamper detection is available through:

```powershell
python scripts/run_memory_review_approved_promotion_tamper_evidence_smoke.py --json
```

That smoke builds a clean approved-promotion bundle, verifies the clean
`promotion_manifest.json`, then writes tampered manifest copies for malformed
JSON, missing manifest fields, missing promotion item fields, promoted/candidate
hash mismatches, rejected candidate inclusion, count mismatch, unsafe metadata,
and manifest hash mismatch. Each tampered copy must return `verdict=FAIL` with
a specific error token while the clean manifest continues to pass. It uses local
fixtures and temporary workspaces only and does not use live accounts, models,
embeddings, live runtime memory, vector DB writes, UI actions, browser calls,
POST forms, or routes. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_TAMPER_EVIDENCE.md).
