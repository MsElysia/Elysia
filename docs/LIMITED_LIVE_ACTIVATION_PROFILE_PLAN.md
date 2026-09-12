# Limited Live Activation Profile Plan

**Activation profile name:** `limited_live_harmless_smoke_activation_v1`  
**Date:** 2026-05-30  
**Status:** Plan only — **not implemented; readiness remains BLOCKED**

**Related docs:** [`LIMITED_LIVE_RC_CHECKPOINT.md`](LIMITED_LIVE_RC_CHECKPOINT.md), [`LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md`](LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md), [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md), [`LIMITED_LIVE_SMOKE_COMMAND.md`](LIMITED_LIVE_SMOKE_COMMAND.md), [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md)

---

## 1. Current verified baseline

| Property | Value |
|----------|-------|
| Checkpoint commit | `236f0b5 docs(autonomy): checkpoint limited live rc` |
| Local tag | `limited_live_rc_1` → `236f0b5` (not pushed) |
| Full pytest baseline | **459 passed, 12 skipped, 0 failed** |
| Full collection | **471** tests collected |
| Readiness status | `BLOCKED` |
| `ready_for_limited_live_mode` | `false` |
| `config/autonomy.json` | `"enabled": false` |
| Autonomy enabled | **No** |
| Production live execution by default | **No** |

This plan documents a **future** activation profile design. It does not change runtime behavior, enable autonomy, or remove readiness blockers.

---

## 2. Purpose

Define a **future activation-profile design** for limited-live harmless smoke only.

| Principle | Detail |
|-----------|--------|
| Plan, not implementation | No code, scripts, routes, executors, or config changes in this milestone |
| Narrow scope | Activation profile must not be broad autonomy |
| Fail closed | Default remains blocked; activation is operator-only and temporary |
| Evidence driven | Future activation requires verified RC baseline and passing regressions |

The activation profile is an **operator wrapper concept** that may later coordinate env gates, preflight checks, and smoke command invocation. It is **not** a substitute for triple gates or manual operator confirmation.

---

## 3. Activation profile name

**`limited_live_harmless_smoke_activation_v1`**

This name identifies a future operator-only activation wrapper. It does **not** exist in code today and is **not** enabled by default.

---

## 4. Relationship to existing limited-live profile

| Profile | Role |
|---------|------|
| `operator_approved_harmless_smoke_v1` | **Existing verified limited-live profile** — defines the only allowed action, path, content, gates, and workspace rules |
| `limited_live_harmless_smoke_activation_v1` | **Future activation wrapper** — may only activate the path defined by `operator_approved_harmless_smoke_v1` |

**Binding rule:** The activation profile may **only** activate `operator_approved_harmless_smoke_v1`. No other actions, profiles, paths, or content variants are permitted.

If the activation profile cannot be bound exclusively to `operator_approved_harmless_smoke_v1`, the implementation must be rejected.

---

## 5. Required future gates

All three execution gates must be explicitly truthy before any smoke write:

| # | Flag | Purpose |
|---|------|---------|
| 1 | `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED=true` | Approval route handlers reachable |
| 2 | `ELYSIA_LIVE_EXECUTOR_ENABLED=true` | Executor may write when called |
| 3 | `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE=true` | Route may invoke executor on APPROVE |

**Optional future activation flag** (not implemented; disabled by default):

| Flag | Value |
|------|-------|
| `ELYSIA_LIMITED_LIVE_PROFILE` | `operator_approved_harmless_smoke_v1` |

If present, this flag must match the verified profile exactly. Any other value must fail closed with no writes.

---

## 6. Required future preconditions

Before any future activation attempt, **all** must pass:

| # | Precondition |
|---|--------------|
| 1 | Repo at or after verified RC baseline (`limited_live_rc_1` / `236f0b5` or later explicit milestone) |
| 2 | `config/autonomy.json` → `"enabled": false` (unchanged) |
| 3 | Full pytest clean, or operator explicitly accepts current documented clean baseline |
| 4 | Safe Observer reports SAFE with `any_executed: false` |
| 5 | Limited-live smoke command passes in isolated temp workspace |
| 6 | Unsafe workspace rejection tests pass |
| 7 | Operator manually confirms intent (explicit flag or confirmation step) |
| 8 | Temp-only workspace — no repo root, user home, cwd, or external paths |
| 9 | No unexpected dirty staged files |
| 10 | root `test.py` absent, untracked, unstaged |

**Stop** if any precondition fails. Do not enable gates or run smoke.

---

## 7. Allowed action (only)

| Property | Value |
|----------|-------|
| Relative path | `live_smoke_workspace/approved_smoke.txt` |
| Exact content | `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF) |
| Workspace | Isolated system temp directory only |
| Write count | One file per approved invocation |
| Rollback | Required — verify target removed after smoke |

Operator command (current verified path):

```bash
python scripts/run_limited_live_smoke.py \
  --profile operator_approved_harmless_smoke_v1 \
  --confirm-limited-live-smoke \
  --json
```

A future activation wrapper may orchestrate this command but must not broaden scope.

---

## 8. Explicitly forbidden

The activation profile and any future wrapper must **never** permit:

| Category | Forbidden |
|----------|-----------|
| Autonomy | Full autonomy, background autonomy loops, self-directed runtime |
| Execution | Tool/capability execution beyond harmless smoke |
| Network | WebScout, browser, network, API calls |
| Process | Shell/subprocess invocation for live actions |
| Mutation | Mutation or proposal implementation |
| Memory | Memory cleanup or condensation |
| Writes | Repo-root, user/home, or external-storage writes |
| Config | Config changes; changing `config/autonomy.json` |
| Git | Pushing tags or commits automatically |
| Readiness | Marking `ready_for_limited_live_mode=true` without separate explicit milestone |
| Blockers | Removing `AUTONOMY_CONFIG_DISABLED` or `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` |

---

## 9. Activation sequence (future implementation)

When a separate approved milestone implements an activation wrapper, operators should follow this sequence:

| Step | Action |
|------|--------|
| 1 | Verify RC tag: `git rev-parse limited_live_rc_1^{commit}` → `236f0b5` or later approved baseline |
| 2 | Verify clean index: `git diff --cached --name-only` empty |
| 3 | Verify config disabled: `config/autonomy.json` → `"enabled": false` |
| 4 | Run limited-live critical regressions (readiness, script, route wiring, executor) |
| 5 | Run Safe Observer (text and JSON) — expect SAFE, `any_executed=false` |
| 6 | Run safe-stack smoke |
| 7 | Set triple gates (and optional `ELYSIA_LIMITED_LIVE_PROFILE` if implemented) |
| 8 | Run limited-live smoke command with `--confirm-limited-live-smoke --json` |
| 9 | Inspect JSON result — verify `safe=true`, correct path/content, rollback success |
| 10 | Verify rollback — smoke target must not remain |
| 11 | Unset all env gates immediately |
| 12 | Record evidence (operator log, JSON output, git status) |
| 13 | Leave readiness **BLOCKED** unless a separate explicit milestone changes it |

---

## 10. Deactivation / emergency stop

If anything unexpected occurs, or after smoke completes:

| Step | Action |
|------|--------|
| 1 | Unset all env gates: `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED`, `ELYSIA_LIVE_EXECUTOR_ENABLED`, `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE`, `ELYSIA_LIMITED_LIVE_PROFILE` |
| 2 | Stop any running Elysia/Guardian process involved in the attempt |
| 3 | Verify no smoke target remains in workspace |
| 4 | Verify no repo/user/external writes occurred |
| 5 | Run `git status --short` — do not clean unrelated pre-existing dirty files |
| 6 | Do not modify `config/autonomy.json` |
| 7 | Record incident evidence if smoke did not complete cleanly |

**Do not** use emergency stop as an excuse to `git clean`, `git reset`, `git stash`, or discard unrelated worktree changes.

---

## 11. Future implementation boundaries

Any code milestone implementing this plan must obey:

| Boundary | Requirement |
|----------|-------------|
| Separate milestone | Must not be bundled with unrelated autonomy work |
| Tests first | Tests for activation wrapper behavior before production code |
| Config | Must not change `config/autonomy.json` |
| Production default | Must not enable production live execution by default |
| Blockers | Must not remove `AUTONOMY_CONFIG_DISABLED` blocker |
| Scope | May only add evidence checks or operator-only activation wrapper after separate approval |
| Profile binding | Wrapper must bind exclusively to `operator_approved_harmless_smoke_v1` |
| Readiness | Must not mark readiness ready without explicit separate milestone |

---

## 12. Acceptance criteria for this docs-only plan

| Criterion | Expected |
|-----------|----------|
| Plan exists | `docs/LIMITED_LIVE_ACTIVATION_PROFILE_PLAN.md` |
| No code changed | Yes |
| No behavior changed | Yes |
| Readiness remains BLOCKED | Yes |
| `config/autonomy.json` remains disabled | Yes |
| Tests still pass | Readiness, script, critical regression, Phase 2, Safe Observer, safe-stack |

---

## 13. Recommended next milestone

After Codex verifies this plan:

1. **Codex verification of the plan** — confirm gates, preconditions, forbidden actions, and implementation boundaries are complete
2. **Decision point** — either:
   - Implement an operator-only activation wrapper (separate milestone, tests first), or
   - Stop and preserve the RC baseline (`limited_live_rc_1` at `236f0b5`) without further activation machinery

Neither path should enable autonomy by default or modify `config/autonomy.json` without explicit operator opt-in.

---

## Safety statement

- **This document is a plan only** — no activation profile is enabled
- **Readiness remains BLOCKED** — `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` and `AUTONOMY_CONFIG_DISABLED` remain
- **`config/autonomy.json` stays `enabled=false`**
- **No production live execution by default**
- **Tag `limited_live_rc_1` is a local checkpoint marker** — not pushed automatically
