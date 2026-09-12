# Limited Live Smoke Command

**Script:** `scripts/run_limited_live_smoke.py`  
**Profile:** `operator_approved_harmless_smoke_v1`  
**Date:** 2026-05-30  
**Status:** Operator manual command — **does not enable broad autonomy**

**Related docs:** [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md), [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md), [`LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md`](LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md), [`LIVE_READINESS_AFTER_LIMITED_LIVE_PROFILE.md`](LIVE_READINESS_AFTER_LIMITED_LIVE_PROFILE.md)

---

## Purpose

Manual operator command to run the full limited-live harmless smoke cycle in an **isolated temporary workspace only**:

1. Preflight checks (confirmation, profile, autonomy config)
2. Register harmless smoke approval packet
3. Inspect packet detail
4. Record operator `APPROVE` through approval route
5. Execute via triple-gated route-to-executor wiring
6. Verify exact target path and content
7. Roll back and verify cleanup
8. Emit machine-readable JSON summary

This command does **not** enable broad autonomy, does **not** modify `config/autonomy.json`, and does **not** mark readiness ready.

---

## Usage

```bash
python scripts/run_limited_live_smoke.py \
  --profile operator_approved_harmless_smoke_v1 \
  --confirm-limited-live-smoke \
  --json
```

### Required flags

| Flag | Purpose |
|------|---------|
| `--profile operator_approved_harmless_smoke_v1` | Must match declared limited-live profile |
| `--confirm-limited-live-smoke` | Explicit operator confirmation |

### Optional flags

| Flag | Purpose |
|------|---------|
| `--json` | Print JSON summary to stdout |
| `--workspace <dir>` | Optional parent inside the **OS system temp directory only**; unsafe paths are rejected before execution |

When `--workspace` is omitted, the script creates an isolated workspace under `tempfile.mkdtemp()`.

---

## Workspace safety

Default operator mode uses a fresh system temp directory only.

Custom `--workspace` is allowed **only** when the resolved parent path is inside the OS system temp directory (`tempfile.gettempdir()`). The script rejects unsafe parents **before** packet registration or execution and writes nothing.

Rejected workspace parents include:

- Relative paths
- Filesystem/drive roots
- Repo root or any project path under the repo
- Current working directory
- User home directory root
- External storage paths
- Symlinks that resolve outside system temp
- Any path outside the system temp directory

Unsafe workspace rejection sets `workspace_rejected=true`, `safe=false`, and a clear error in `errors`.

---

## Preflight

The script refuses to run unless:

- `--confirm-limited-live-smoke` is present
- `--profile` is exactly `operator_approved_harmless_smoke_v1`
- `config/autonomy.json` has `"enabled": false`
- Readiness remains blocked (`ready_for_limited_live_mode=false`)

---

## Triple gates (set for process only)

The script sets these env flags for the smoke run:

| Flag | Value |
|------|-------|
| `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED` | `true` |
| `ELYSIA_LIVE_EXECUTOR_ENABLED` | `true` |
| `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` | `true` |

All three are required for APPROVE to invoke the harmless smoke executor.

---

## Verified artifact

| Property | Value |
|----------|-------|
| Relative target | `live_smoke_workspace/approved_smoke.txt` |
| Exact content | `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF) |
| Workspace | Isolated temp directory only |

Rollback deletes the created file and verifies the target no longer exists.

---

## JSON summary fields

| Field | Meaning |
|-------|---------|
| `profile` | Profile name used |
| `preflight_passed` | Confirmation, profile, config, gates OK |
| `packet_registered` | Smoke packet registered in approval store |
| `decision_recorded` | Operator APPROVE recorded |
| `executor_called` | Route invoked executor |
| `execution_permitted` | Executor permitted write |
| `executed` | Smoke file written |
| `target_path` | Relative smoke target |
| `exact_content_verified` | Bytes match expected marker |
| `rollback_executed` | Rollback completed |
| `rollback_verified` | Target removed after rollback |
| `autonomy_enabled` | Always `false` for this command |
| `config_autonomy_enabled` | Value read from committed config |
| `workspace_parent` | Custom parent when provided; empty for default temp |
| `workspace_root` | Resolved isolated smoke workspace used for the run |
| `workspace_rejected` | `true` when custom workspace failed safety validation |
| `safe` | `true` only when full cycle passes |
| `errors` | Failure reasons when `safe=false` |

Exit code `0` only when all checks pass.

---

## Safety statement

- No shell, subprocess, network, browser, API, or mutation paths
- No writes outside isolated system temp workspace
- No repo-root, user-home, external-storage, or project-path workspace parents
- Unsafe custom workspace rejection writes nothing
- `config/autonomy.json` is read-only; never modified
- Readiness blockers remain unchanged after successful run
