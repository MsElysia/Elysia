# Memory Review Recovery Inspection Bundle Smoke

This dry-run/local smoke produces an operator inspection bundle after
recovery-audit tamper-recovery. The prior checkpoint proved a corrupted
`recovery_audit.jsonl` can be detected, quarantined, preserved byte-for-byte,
and bypassed while state is re-resolved from a known-good copy; this checkpoint
makes that recovery evidence easy for an operator to inspect.

Run:

```powershell
python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json
```

The command creates a temporary workspace, runs the existing recovery-audit
tamper-recovery flow, then writes a `recovery_inspection_bundle/` directory
with an operator-readable inspection summary and optional Markdown README. The
temporary workspace is removed unless `--keep-temp` or `--base-dir` is used.

## Stale workspace rerun

Re-running against the same kept `--base-dir` can fail when prior dry-run review
state remains in the workspace. The smoke detects this stale state and returns a
clear operator message instead of deleting anything automatically:

```powershell
python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json --base-dir .\tmp\recovery-inspection-rerun --keep-temp
```

To rerun safely on the same base directory, pass an explicit reset flag. Reset
removes only the known generated dry-run artifacts under the supplied base
directory (`source/`, `dest/`, `known_good/`, `quarantine/`,
`recovery_inspection_bundle/`, and `recovery_audit.jsonl`). It never deletes
arbitrary files, repo source files, live memory paths, vector DB paths, or
account data:

```powershell
python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json --base-dir .\tmp\recovery-inspection-rerun --keep-temp --reset-workspace
```

`--reset-workspace` requires `--base-dir` and refuses unsafe paths such as the
repository root, home directory, drive root, or empty path.

Reset JSON fields:

- `stale_workspace_detected`
- `workspace_reset_performed`
- `workspace_reset_paths`
- `workspace_reset_safe`

Recovery inspection bundle coverage:

- Runs the existing recovery-audit tamper-recovery flow in a temp workspace.
- Creates `recovery_inspection_bundle/inspection_summary.json` with paths to the
  quarantine manifest, quarantined corrupt log, known-good recovery audit copy,
  recovered event sequence, and detected error types copied from the quarantine
  manifest (`detected_error_types`, `detected_error_type_count`,
  `detected_error_types_match_manifest`).
- Includes SHA-256 hashes for the corrupt log, known-good copy, and quarantine
  manifest; hashes are verified against the artifact files.
- Surfaces quarantine manifest `detected_error_types` directly in the summary so
  operators can triage corruption without opening the manifest file.
- Confirms the corrupt log was preserved and known-good resolution was used.
- Confirms recovered event sequence matches the known-good pre-corruption state.
- Confirms `dry_run=true`, `local_only=true`, `silently_repaired=false`, and
  `operator_required=true`.
- All bundle paths stay inside the temp workspace.

Why it is safe:

- Uses local fixtures and temporary workspaces only; inspection bundle files
  are written only inside the temp workspace.
- Reuses the existing recovery-audit tamper-recovery smoke; no server, API, or
  core file was modified. It performs no network, model, embedding,
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
python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json --base-dir .\tmp\memory-review-recovery-inspection-bundle
```

The JSON report includes artifact paths under the supplied base directory so an
operator can inspect the inspection summary, README, quarantine manifest,
quarantined corrupt log, known-good recovery audit copy, and restored recovery
audit log.

## Recovery Audit Tamper Recovery

The underlying tamper-recovery flow is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_recovery_smoke.py --json
```

That smoke builds a clean `recovery_audit.jsonl` and a known-good copy, corrupts
the working log, detects the corruption, quarantines the corrupt log (preserved,
not repaired) with a manifest, and re-resolves recovery audit state from the
known-good copy only. See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_RECOVERY.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_RECOVERY.md).

## Recovery Audit Tamper Evidence

Recovery audit log tamper detection is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json
```

See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md).

## Recovery Audit Trail

Recovery action audit-trail coverage is covered separately by:

```powershell
python scripts/run_memory_review_recovery_audit_trail_smoke.py --json
```

See
[`MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`](MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md).
