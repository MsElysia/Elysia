# Limited Live Activation Wrapper

**Script:** `scripts/run_limited_live_activation.py`  
**Activation profile:** `limited_live_harmless_smoke_activation_v1`  
**Limited-live profile:** `operator_approved_harmless_smoke_v1`  
**Branch:** `codex/limited-live-activation-wrapper`  
**RC tag:** `limited_live_rc_1` → `236f0b5`  
**Date:** 2026-05-30  
**Status:** Operator-only wrapper — **readiness remains BLOCKED**

**Related docs:** [`LIMITED_LIVE_ACTIVATION_PROFILE_PLAN.md`](LIMITED_LIVE_ACTIVATION_PROFILE_PLAN.md), [`LIMITED_LIVE_SMOKE_COMMAND.md`](LIMITED_LIVE_SMOKE_COMMAND.md), [`LIMITED_LIVE_RC_CHECKPOINT.md`](LIMITED_LIVE_RC_CHECKPOINT.md), [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md)

---

## Purpose

Operator-only wrapper that activates **only** the already verified harmless smoke limited-live path. It adds preflight checks (RC tag, branch, config disabled, index clean, `test.py` absent) before delegating to `scripts/run_limited_live_smoke.py`.

This is **not** full autonomy. It does **not** enable production live execution by default. It does **not** modify `config/autonomy.json`. It does **not** remove readiness blockers.

---

## Usage

```bash
python scripts/run_limited_live_activation.py \
  --activation-profile limited_live_harmless_smoke_activation_v1 \
  --profile operator_approved_harmless_smoke_v1 \
  --confirm-limited-live-activation \
  --json
```

### Required flags

| Flag | Purpose |
|------|---------|
| `--activation-profile limited_live_harmless_smoke_activation_v1` | Future activation profile binding |
| `--profile operator_approved_harmless_smoke_v1` | Verified limited-live profile |
| `--confirm-limited-live-activation` | Explicit operator confirmation |

### Optional flags

| Flag | Purpose |
|------|---------|
| `--json` | Print JSON summary to stdout |
| `--workspace <dir>` | Optional parent inside OS system temp only (same rules as smoke command) |

---

## Preflight checks

Before invoking smoke logic, the wrapper verifies:

| Check | Requirement |
|-------|-------------|
| RC tag | `limited_live_rc_1` exists and points to `236f0b5` |
| Branch | Current branch is `codex/limited-live-activation-wrapper` |
| Config | `config/autonomy.json` → `"enabled": false` |
| Readiness | `ready_for_limited_live_mode` remains `false` |
| `test.py` | Root `test.py` absent, untracked, unstaged |
| Index | No staged files |
| Workspace | Temp-only if `--workspace` provided |

Test override: set `ELYSIA_LIMITED_LIVE_ACTIVATION_SKIP_BRANCH_CHECK=true` to skip branch check (tests only).

---

## Allowed action (only)

| Property | Value |
|----------|-------|
| Path | `live_smoke_workspace/approved_smoke.txt` |
| Content | `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF) |
| Workspace | System temp only |
| Rollback | Required and verified |

---

## JSON summary fields

| Field | Meaning |
|-------|---------|
| `activation_profile` | Activation profile name |
| `profile` | Limited-live profile name |
| `rc_tag_verified` | RC tag check passed |
| `rc_tag_target` | Resolved RC tag commit |
| `branch_verified` | Branch check passed |
| `config_autonomy_enabled` | Config autonomy flag (must be false) |
| `readiness_blocked` | Readiness remains blocked |
| `smoke_command_invoked` | Smoke logic was called |
| `executed` | Harmless smoke executed |
| `exact_content_verified` | Content hash verified |
| `rollback_verified` | Rollback cleanup verified |
| `workspace_temp_only` | Workspace under system temp |
| `unsafe_workspace_rejected` | Unsafe workspace rejected |
| `safe` | All checks passed |
| `errors` | Failure reasons |

Exit `0` only when `safe=true`. Nonzero on any failure.

---

## Explicitly forbidden

- Full autonomy or background loops
- Tool/capability execution beyond harmless smoke
- WebScout, browser, network, API calls
- Shell/subprocess for smoke execution (git read-only checks only)
- Mutation or proposal implementation
- Repo-root, user/home, or external writes
- Changing `config/autonomy.json`
- Marking readiness ready
- Removing `AUTONOMY_CONFIG_DISABLED` or `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT`

---

## Safety statement

- **Readiness remains BLOCKED** after wrapper run
- **`config/autonomy.json` stays `enabled=false`**
- **Triple gates** are applied only inside smoke command lifecycle
- **Operator confirmation required** — no silent activation
