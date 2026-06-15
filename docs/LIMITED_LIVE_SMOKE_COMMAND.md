# Limited Live Smoke Command

**Script:** `scripts/run_limited_live_smoke.py`  
**Profile:** `operator_approved_harmless_smoke_v1`  
**Date:** 2026-05-30  
**Status:** Operator manual command — **does not enable broad autonomy**

**Related docs:** [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md), [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md), [`LIVE_READINESS_AFTER_LIMITED_LIVE_PROFILE.md`](LIVE_READINESS_AFTER_LIMITED_LIVE_PROFILE.md)

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
| `--workspace <dir>` | Parent directory for isolated workspace (tests/dev only) |

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
| `safe` | `true` only when full cycle passes |
| `errors` | Failure reasons when `safe=false` |

Exit code `0` only when all checks pass.

---

## Safety statement

- No shell, subprocess, network, browser, API, or mutation paths
- No writes outside isolated temp workspace
- No repo-root smoke file creation
- `config/autonomy.json` is read-only; never modified
- Readiness blockers remain unchanged after successful run
