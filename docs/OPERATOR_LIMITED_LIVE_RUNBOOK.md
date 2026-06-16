# Operator Limited Live Runbook

**Profile:** `operator_approved_harmless_smoke_v1`  
**Date:** 2026-05-30  
**Status:** Published — **documentation only; does not enable autonomy**

**Starting checkpoint:** `5683990 fix(autonomy): update readiness after approval route wiring`

**Related docs:** [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md), [`LIMITED_LIVE_SMOKE_COMMAND.md`](LIMITED_LIVE_SMOKE_COMMAND.md), [`LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md`](LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md), [`LIVE_READINESS_AFTER_APPROVAL_ROUTE_WIRING.md`](LIVE_READINESS_AFTER_APPROVAL_ROUTE_WIRING.md), [`APPROVAL_ROUTE_EXECUTOR_WIRING_IMPLEMENTATION.md`](APPROVAL_ROUTE_EXECUTOR_WIRING_IMPLEMENTATION.md)

---

## 1. Purpose

Step-by-step operator procedure for the **first safe limited-live run**: one harmless smoke file write in an isolated temp workspace, behind triple gates, with explicit rollback verification.

This runbook does **not** enable autonomy or broad live execution.

---

## 2. Preconditions

Before any limited-live attempt:

| # | Precondition |
|---|--------------|
| 1 | HEAD at verified safe-autonomy checkpoint |
| 2 | `config/autonomy.json` → `"enabled": false` (unchanged) |
| 3 | Passive Phase 2 tests pass |
| 4 | Safe Observer reports SAFE with `any_executed: false` in default mode |
| 5 | Operator has read [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md) |
| 6 | Isolated temp workspace path chosen (not repo root, not user data) |
| 7 | No unrelated dirty files staged or used as proof |

---

## 3. Required repo state checks

Run before enabling any gate:

```powershell
cd "c:\Users\mrnat\Project guardian"
git status --short
git log -5 --oneline
```

Confirm:

| Check | Expected |
|-------|----------|
| HEAD | Known safe-autonomy checkpoint (e.g. `5683990` or later docs commit) |
| `config/autonomy.json` | `"enabled": false`, file not modified for this run |
| Index | No unintended staged files |
| root `test.py` | Absent |

Inspect autonomy config:

```powershell
Select-String -Path config\autonomy.json -Pattern '"enabled"'
```

Expected: `"enabled": false`

**Stop** if `config/autonomy.json` was modified or autonomy appears enabled.

---

## 4. Required test checks before any limited run

Run **all** before setting execution flags:

```powershell
python -m pytest project_guardian/tests/test_live_action_readiness.py -q
python -m pytest project_guardian/tests/test_live_action_approval_route_executor_wiring.py -q
python -m pytest project_guardian/tests/test_live_action_executor.py -q
python -m pytest project_guardian/tests/test_live_action_gate.py project_guardian/tests/test_live_action_audit.py project_guardian/tests/test_live_action_rollback.py project_guardian/tests/test_live_action_approval_packet.py project_guardian/tests/test_live_action_operator_decision.py project_guardian/tests/test_live_action_readiness.py project_guardian/tests/test_live_action_approval_route.py project_guardian/tests/test_live_action_smoke_packet.py project_guardian/tests/test_live_action_passive_smoke_approval_flow.py project_guardian/tests/test_live_action_executor.py project_guardian/tests/test_live_action_approval_route_executor_wiring.py -q
python scripts/run_elysia_dry_run_report.py --mode real-planning
python scripts/run_elysia_dry_run_report.py --mode real-planning --json
python scripts/run_safe_stack_smoke_tests.py
```

All must pass. Safe Observer must report `SAFE` and `any_executed: false` in default (ungated) mode.

---

## 5. Required environment flags (limited smoke path only)

Set **only** for the bounded smoke run; unset immediately after:

| Flag | Value |
|------|-------|
| `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED` | `true` |
| `ELYSIA_LIVE_EXECUTOR_ENABLED` | `true` |
| `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` | `true` |

PowerShell example (session only):

```powershell
$env:ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED = "true"
$env:ELYSIA_LIVE_EXECUTOR_ENABLED = "true"
$env:ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE = "true"
```

**Never** persist these flags in startup scripts, `.env`, or `config/autonomy.json`.

---

## 6. Operator steps

### Step 1 — Create isolated temp workspace

```powershell
$SmokeRoot = Join-Path $env:TEMP "elysia_limited_live_smoke_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $SmokeRoot -Force
```

Confirm path is under `%TEMP%`, not repo root.

### Step 2 — Generate and register harmless smoke packet

Use pytest-proven flow or API with passive smoke registration:

- `register_harmless_smoke_packet_for_approval(store, workspace, repo_root=..., expires_at=...)`
- Packet `action_id` must be `harmless_live_smoke_v1`
- Target must be `live_smoke_workspace/approved_smoke.txt`

### Step 3 — Inspect packet details

Verify via `get_approval_packet_detail()` or API equivalent:

- `packet_content_hash` matches submitted hash
- `expires_at` is in the future
- `proposed_target_path` is `live_smoke_workspace/approved_smoke.txt`
- `execution_permitted` is `false` until APPROVE with all gates on

### Step 4 — Approve only if packet matches profile

Submit `APPROVE` with:

- `operator_id`, `reason`, `approved_scope`
- `packet_content_hash` matching server canonical hash

**Do not APPROVE** if packet differs from [`LIMITED_LIVE_PROFILE.md`](LIMITED_LIVE_PROFILE.md).

### Step 5 — Verify execution result

Response must include:

- `executor_called=true`
- `execution_permitted=true`
- `executed=true`
- `execution_result` with `status=EXECUTION_SUCCEEDED`
- `approval_packet_id` and `operator_decision_id` present

### Step 6 — Verify exact file path

Confirm only:

```
{SmokeRoot}/live_smoke_workspace/approved_smoke.txt
```

exists. No files under repo root or user data.

### Step 7 — Verify exact content

Content must be exactly (UTF-8):

```
ELYSIA_APPROVED_LIVE_SMOKE\n
```

### Step 8 — Run rollback

Explicit rollback via `rollback_harmless_smoke_write()`:

- Delete strategy if file was created
- Restore `prior_content` if file existed before

### Step 9 — Verify cleanup/restoration

- After delete: target file absent
- After restore: exact prior bytes restored

### Step 10 — Unset all flags

```powershell
Remove-Item Env:ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:ELYSIA_LIVE_EXECUTOR_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE -ErrorAction SilentlyContinue
```

---

## 7. Stop conditions

**Abort immediately** if any occur:

| # | Stop condition |
|---|----------------|
| 1 | Unexpected dirty repo files unrelated to the run |
| 2 | `config/autonomy.json` changed or `enabled=true` |
| 3 | Route executes without all three gates true |
| 4 | DENY, expired, or hash-mismatched packet triggers execution |
| 5 | Any write outside isolated temp workspace |
| 6 | Shell, network, browser, API, or mutation path appears |
| 7 | Rollback fails |
| 8 | More than one file created in workspace |
| 9 | Repo-root `approved_smoke.txt` or similar appears |

---

## 8. Required post-run evidence

Capture and retain:

| Evidence | Description |
|----------|-------------|
| Test output | All pre-run pytest and Safe Observer commands |
| Decision audit | Append-only decision record JSON |
| Execution audit | Separate execution audit JSONL line |
| File content proof | Hash or hex dump of `approved_smoke.txt` |
| Rollback proof | Before/after state showing delete or restore |
| `git status --short` | Confirms no unintended repo changes |

---

## 9. Explicit forbidden commands

**Do not run:**

| Forbidden | Reason |
|-----------|--------|
| Full autonomy loop / `run_autonomous_cycle` with live execution | Not authorized |
| Mutation apply / proposal implementation | Out of profile scope |
| Enable or modify `config/autonomy.json` | Autonomy must stay disabled |
| WebScout / browser / network tools | Out of profile scope |
| `git add -A` on unrelated dirty files | Contaminates proof |
| Persist triple-gate flags in startup scripts | Production must stay gated off |

---

## 10. Recovery steps

If run aborts or fails:

1. **Unset all flags** (see Step 10 above)
2. **Stop server/process** if a test server was started for the run
3. **Inspect `git status --short`** — do not commit unrelated changes
4. **Remove only test temp workspace** (`$SmokeRoot`) if safe to delete
5. **Do not clean** unrelated dirty worktree files
6. **Re-run** pre-run test suite before any retry
7. **Document** failure reason in operator notes; do not mark readiness ready

---

## Safety statement

| Constraint | Status |
|------------|--------|
| Autonomy enabled | **No** |
| `config/autonomy.json` modified | **No** |
| Route/executor code changed by this runbook | **No** |
| Readiness marked ready | **No** |
| Broad tool/autonomy use | **No** |

This runbook supports the first bounded operator-verified smoke run only. Readiness evidence update for profile/runbook declaration is a **separate future milestone**.
