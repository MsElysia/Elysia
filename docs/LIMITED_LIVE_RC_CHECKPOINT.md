# Limited Live RC Checkpoint

**Baseline name:** `limited_live_rc_1`  
**Checkpoint commit:** `e70e45c docs(tests): refresh full runtime after limited live rc`  
**Date:** 2026-05-30  
**Status:** Clean limited-live release candidate checkpoint — **readiness remains BLOCKED**

**Related docs:** [`FULL_RUNTIME_TEST_REFRESH_LIMITED_LIVE_RC.md`](FULL_RUNTIME_TEST_REFRESH_LIMITED_LIVE_RC.md), [`LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md`](LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md), [`LIMITED_LIVE_SMOKE_COMMAND.md`](LIMITED_LIVE_SMOKE_COMMAND.md), [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md)

---

## 1. Checkpoint purpose

This document records `e70e45c` as the **clean limited-live release candidate baseline** (`limited_live_rc_1`). It freezes verified safety state, test evidence, and operator path for operator-approved harmless smoke only.

This checkpoint does **not** enable autonomy, production live execution, or broad tool use.

---

## 2. Checkpoint commit

| Property | Value |
|----------|-------|
| Baseline name | `limited_live_rc_1` |
| Git commit | `e70e45c docs(tests): refresh full runtime after limited live rc` |
| Parent RC baseline | `4d2b351 docs(autonomy): record limited live release candidate` |

---

## 3. Test evidence at checkpoint

| Suite | Result |
|-------|--------|
| Full collection | **471** tests collected |
| Full pytest | **459 passed, 12 skipped, 0 failed** (936.52s) |
| Limited-live critical regression | 87 passed, 1 skipped, 0 failed |
| Passive Phase 2 targeted tests | **185 passed**, 0 failed |
| Safe Observer (text) | SAFE, exit 0, `any_executed=false` |
| Safe Observer (JSON) | `"safe": true`, exit 0 |
| Safe-stack smoke | **454 passed**, 0 failed |

Full pytest details: [`FULL_RUNTIME_TEST_REFRESH_LIMITED_LIVE_RC.md`](FULL_RUNTIME_TEST_REFRESH_LIMITED_LIVE_RC.md)

---

## 4. Current safety state

| Property | Value |
|----------|-------|
| Readiness status | `BLOCKED` |
| `ready_for_limited_live_mode` | `false` |
| `config/autonomy.json` | `"enabled": false` |
| Autonomy enabled | **No** |
| Production live execution by default | **No** — triple gates off |
| root `test.py` | Absent, untracked, unstaged |

---

## 5. Verified limited-live path

| Property | Value |
|----------|-------|
| Profile | `operator_approved_harmless_smoke_v1` |
| Operator command | `python scripts/run_limited_live_smoke.py --profile operator_approved_harmless_smoke_v1 --confirm-limited-live-smoke --json` |
| Exact file | `live_smoke_workspace/approved_smoke.txt` |
| Exact content | `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF) |
| Workspace | System temp only; custom `--workspace` must be inside system temp |
| Unsafe workspaces | Rejected before execution; writes nothing |
| Rollback | Verified by command and executor tests |

---

## 6. Required triple gates

All three must be explicitly truthy for smoke execution:

| # | Flag |
|---|------|
| 1 | `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED=true` |
| 2 | `ELYSIA_LIVE_EXECUTOR_ENABLED=true` |
| 3 | `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE=true` |

If any gate is off, APPROVE is decision-only and writes nothing.

---

## 7. Remaining blockers

| Blocker | Reason |
|---------|--------|
| `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` | Triple execution gates off by default in production/runtime |
| `AUTONOMY_CONFIG_DISABLED` | `config/autonomy.json` `enabled=false` |

`evaluate_live_mode_readiness()` returns `status=BLOCKED`, `ready_for_limited_live_mode=false`.

---

## 8. Explicit non-goals

This checkpoint does **not** include:

- Full autonomy or broad tool execution
- WebScout, browser, or network activity
- Mutation or proposal implementation
- Memory cleanup or config changes
- Repo-root, user-data, or external-storage writes
- Enabling `config/autonomy.json`
- Removing production-disabled or autonomy-disabled readiness blockers
- Marking `ready_for_limited_live_mode=true`

---

## 9. Safety statement

- **No autonomy enabled** — `config/autonomy.json` remains `enabled=false`
- **No production live default** — triple gates off outside explicit operator smoke command
- **Limited-live command is operator-confirmed only** — requires `--confirm-limited-live-smoke` and correct profile
- **No non-test live execution** except manual smoke command in isolated system temp workspace
- **Readiness remains BLOCKED** — this checkpoint does not mark broad autonomy ready

---

## 10. Recommended next milestone

Choose one (still **without** enabling autonomy by default):

1. **Define a future activation-profile plan** — document additional operator gates for any future limited-live expansion; remain disabled by default
2. **Create a Git tag after Codex verifies this checkpoint** — e.g. `limited_live_rc_1` pointing at `e70e45c`

Neither milestone should enable production live execution or modify `config/autonomy.json` without explicit operator opt-in.
