# Limited Live Release Candidate Baseline

**Checkpoint:** `be1c49c fix(autonomy): update readiness after limited live smoke command`  
**Date:** 2026-05-30  
**Status:** Release candidate baseline — **limited live mode remains BLOCKED**

**Related docs:** [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md), [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md), [`LIMITED_LIVE_SMOKE_COMMAND.md`](LIMITED_LIVE_SMOKE_COMMAND.md), [`LIVE_READINESS_AFTER_LIMITED_LIVE_SMOKE_COMMAND.md`](LIVE_READINESS_AFTER_LIMITED_LIVE_SMOKE_COMMAND.md)

---

## 1. Baseline purpose

This document freezes the current **limited-live release candidate** safety state for Elysia / Project Guardian.

Scope: **operator-approved harmless smoke only** — one file write in an isolated system temp workspace, behind triple gates, with explicit operator confirmation. This is **not** broad autonomy and does **not** grant production live execution by default.

---

## 2. Current checkpoint

| Property | Value |
|----------|-------|
| Git HEAD | `be1c49c fix(autonomy): update readiness after limited live smoke command` |
| Readiness status | `BLOCKED` |
| `ready_for_limited_live_mode` | `false` |
| `config/autonomy.json` | `"enabled": false` (unchanged) |

---

## 3. What is complete

| Area | Status | Evidence |
|------|--------|----------|
| Limited live profile declared | Complete | `docs/LIMITED_LIVE_PROFILE.md` — `operator_approved_harmless_smoke_v1` |
| Operator runbook declared | Complete | `docs/OPERATOR_LIMITED_LIVE_RUNBOOK.md` |
| Harmless smoke executor implemented | Complete | `project_guardian/live_action_executor.py` |
| Rollback verified | Complete | Executor + command rollback verification |
| Approval route wired (triple-gated) | Complete | `project_guardian/live_action_approval_route.py` |
| Limited-live smoke command verified | Complete | `scripts/run_limited_live_smoke.py` |
| Workspace constrained to temp only | Complete | `30a4915` workspace safety repair |
| Unsafe workspaces rejected | Complete | Rejected before execution; writes nothing |
| Safe Observer | Pass | `python scripts/run_elysia_dry_run_report.py --mode real-planning` |
| Passive Phase 2 targeted tests | Pass | 185 passed |
| Safe-stack smoke | Pass | 454 passed |
| Full collection | Pass | 471 tests collected |

---

## 4. What remains blocked

| Blocker | Reason |
|---------|--------|
| `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` | Triple execution gates remain off by default in production/runtime |
| `AUTONOMY_CONFIG_DISABLED` | `config/autonomy.json` `enabled=false` |
| Broad autonomy | Not enabled; not in scope for this release candidate |

`evaluate_live_mode_readiness()` returns `status=BLOCKED`, `ready_for_limited_live_mode=false`, `safety_verdict=NOT_READY_FOR_LIVE_MODE`.

---

## 5. Exact allowed profile and action

| Property | Value |
|----------|-------|
| Profile name | `operator_approved_harmless_smoke_v1` |
| Action ID | `harmless_live_smoke_v1` |
| Action kind | `harmless_live_smoke` |
| Relative target | `live_smoke_workspace/approved_smoke.txt` |
| Exact content | `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF) |
| Write count | One file only per approved invocation |

No other action categories, paths, or content variants are permitted.

---

## 6. Required triple gates

All three environment flags must be explicitly truthy (`1`, `true`, `yes`, `on`):

| # | Flag |
|---|------|
| 1 | `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED=true` |
| 2 | `ELYSIA_LIVE_EXECUTOR_ENABLED=true` |
| 3 | `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE=true` |

If any gate is off, APPROVE is decision-only and writes nothing.

---

## 7. Explicit non-goals

This release candidate does **not** include:

- Full autonomy or broad tool execution
- WebScout, browser, or network activity
- Mutation or proposal implementation
- Memory cleanup or config changes
- Repo-root, user-data, or external-storage writes
- Enabling `config/autonomy.json`
- Removing production-disabled or autonomy-disabled readiness blockers
- Marking `ready_for_limited_live_mode=true`

---

## 8. Required operator command

```bash
python scripts/run_limited_live_smoke.py \
  --profile operator_approved_harmless_smoke_v1 \
  --confirm-limited-live-smoke \
  --json
```

Requirements:

- `--confirm-limited-live-smoke` must be present
- `--profile` must be exactly `operator_approved_harmless_smoke_v1`
- Default workspace uses system temp only; custom `--workspace` must be inside system temp

---

## 9. Required evidence for release-candidate pass

A release-candidate verification pass requires all of the following in the manual script JSON summary:

| Field | Required value |
|-------|----------------|
| `safe` | `true` |
| `exact_content_verified` | `true` |
| `rollback_verified` | `true` |
| `config_autonomy_enabled` | `false` |
| `readiness_blocked` | `true` |
| `autonomy_enabled` | `false` |
| `workspace_rejected` | `false` (for default safe run) |
| `errors` | `[]` |

Additional operator checks:

- `config/autonomy.json` remains `"enabled": false`
- No repo-root `approved_smoke.txt` created
- Git index clean for milestone commits; unrelated dirty worktree files not used as proof

---

## 10. Current test evidence (baseline)

| Suite | Last verified result |
|-------|---------------------|
| Readiness tests | 20 passed |
| Script tests | 20 passed, 1 skipped |
| Route wiring tests | 17 passed |
| Executor tests | 30 passed |
| Passive Phase 2 targeted tests | 185 passed |
| API approval regression tests | 23 passed |
| Safe Observer (text) | SAFE, exit 0 |
| Safe Observer (JSON) | `"safe": true`, exit 0 |
| Safe-stack smoke | 454 passed |
| Full collection | 471 tests collected |
| Full runtime pytest | Not re-run; last clean: `439 passed, 0 failed, 11 skipped` |

Commands:

```bash
python -m pytest project_guardian/tests/test_live_action_readiness.py -q
python -m pytest tests/test_limited_live_smoke_script.py -q
python -m pytest project_guardian/tests/test_live_action_approval_route_executor_wiring.py -q
python -m pytest project_guardian/tests/test_live_action_executor.py -q
python scripts/run_elysia_dry_run_report.py --mode real-planning
python scripts/run_safe_stack_smoke_tests.py
python -m pytest --collect-only -q
```

---

## 11. Safety statement

- **No autonomy enabled** — `config/autonomy.json` remains `enabled=false`
- **No production live default** — triple gates off by default outside explicit operator smoke command
- **Limited-live command is operator-confirmed only** — requires `--confirm-limited-live-smoke` and correct profile
- **No non-test live execution** except manual smoke command in isolated system temp workspace
- **Readiness remains BLOCKED** — this baseline does not mark broad autonomy ready

---

## 12. Next recommended milestone

Choose one (still **without** enabling autonomy):

1. **Full runtime pytest refresh** — re-run full suite and update classification if needed
2. **Release candidate tag/doc checkpoint** — tag or document this baseline for operator handoff; autonomy remains disabled

Neither milestone should enable production live execution or modify `config/autonomy.json` without explicit operator opt-in.
