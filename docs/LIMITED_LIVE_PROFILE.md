# Limited Live Profile

**Profile name:** `operator_approved_harmless_smoke_v1`  
**Date:** 2026-05-30  
**Status:** Declared — **not full autonomy; readiness remains BLOCKED**

**Starting checkpoint:** `5683990 fix(autonomy): update readiness after approval route wiring`

**Related docs:** [`OPERATOR_LIMITED_LIVE_RUNBOOK.md`](OPERATOR_LIMITED_LIVE_RUNBOOK.md), [`APPROVAL_ROUTE_EXECUTOR_WIRING_IMPLEMENTATION.md`](APPROVAL_ROUTE_EXECUTOR_WIRING_IMPLEMENTATION.md), [`HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md`](HARMLESS_SMOKE_EXECUTOR_IMPLEMENTATION.md)

---

## 1. Purpose

First limited-live profile for verifying **one** operator-approved harmless action: a single smoke file write inside an isolated temporary workspace.

This profile is for controlled verification only. It does **not** authorize broad autonomy, tool use, or runtime self-direction.

---

## 2. Allowed action (only)

| Property | Value |
|----------|-------|
| Action ID | `harmless_live_smoke_v1` |
| Action kind | `harmless_live_smoke` |
| Relative target | `live_smoke_workspace/approved_smoke.txt` |
| Exact content | `ELYSIA_APPROVED_LIVE_SMOKE\n` (UTF-8, LF) |
| Write count | **One file only** per approved invocation |

No other action categories, paths, or content variants are permitted under this profile.

---

## 3. Allowed location

- **Only** inside an isolated operator-chosen temporary workspace
- Workspace must not be repo root
- Workspace must not resolve to user data paths (Documents, Downloads, Desktop, etc.)
- Workspace must not resolve to external storage paths
- Path validation enforced via `validate_harmless_smoke_paths()`

---

## 4. Required gates (triple)

All three environment flags must be explicitly truthy (`1`, `true`, `yes`, `on`):

| # | Flag | Purpose |
|---|------|---------|
| 1 | `ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED` | Approval route handlers reachable |
| 2 | `ELYSIA_LIVE_EXECUTOR_ENABLED` | Executor may write when called |
| 3 | `ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE` | Route may invoke executor on APPROVE |

If **any** gate is off, APPROVE is decision-only and writes nothing.

---

## 5. Required approval

Before execution may occur, **all** must pass:

| # | Requirement |
|---|-------------|
| 1 | Valid approval packet exists |
| 2 | Packet not expired (`expires_at` in future) |
| 3 | `packet_content_hash` matches canonical server hash |
| 4 | Operator decision is `APPROVE` |
| 5 | `action_id` is `harmless_live_smoke_v1` |
| 6 | `action_category` is `harmless_live_smoke` |
| 7 | `target_path` is `live_smoke_workspace/approved_smoke.txt` |
| 8 | `expected_content_hash` matches `compute_harmless_smoke_content_hash()` |
| 9 | Rollback metadata present |
| 10 | Audit preview present |

`DENY`, `REQUEST_CHANGES`, `CANCEL`, and `EXPIRE` never invoke the executor.

---

## 6. Prohibited actions

Under this profile, the following are **explicitly prohibited**:

| Category | Prohibited |
|----------|------------|
| Broad autonomy | Autonomy loop, self-task advancement, mission autonomy |
| WebScout / browser | Any browser or web navigation |
| Network / API | HTTP, shell, subprocess, external API calls |
| Mutation / proposals | `apply_mutation`, proposal implementation |
| Memory cleanup | Runtime memory condense/cleanup |
| Config changes | Any `config/*.json` modification |
| Repo-root writes | Any write under repository root |
| User data writes | Documents, Downloads, Desktop, etc. |
| External storage writes | Configured external data paths |

---

## 7. Required rollback

Rollback is **explicit** (not automatic after success):

| Strategy | When |
|----------|------|
| Delete created file | File did not exist before execution |
| Restore prior content | File existed; `prior_content` bytes supplied |

Rollback target: `live_smoke_workspace/approved_smoke.txt` inside validated workspace only.

---

## 8. Required audits

| Audit type | When | Content |
|------------|------|---------|
| Decision audit | Always on APPROVE/DENY/etc. | Operator id, decision, packet hash binding |
| Execution audit | When executor called | `approval_packet_id`, `operator_decision_id`, execution result |
| Rollback audit | When rollback run | Before/after hash, strategy, target path |

Decision and execution audits are separate append-only records.

---

## 9. Exit criteria

A limited-live run under this profile is **successful** when:

| # | Criterion |
|---|-----------|
| 1 | Exact file created: `live_smoke_workspace/approved_smoke.txt` |
| 2 | Exact content verified: `ELYSIA_APPROVED_LIVE_SMOKE\n` |
| 3 | Rollback verified (delete or restore) |
| 4 | No unrelated files created in workspace or repo |
| 5 | All execution gates unset after run |
| 6 | Readiness still **not** broad-autonomy ready (`ready_for_limited_live_mode=false`) |

---

## 10. Safety statement

| Constraint | Status |
|------------|--------|
| Full autonomy | **Not authorized** |
| Broad tool use | **Not authorized** |
| `config/autonomy.json` | **Must remain** `enabled=false` |
| Default production behavior | Decision-only; triple gates off |
| This profile enables autonomy | **No** |

This profile declares operator intent for a **single bounded smoke verification**. It does not change runtime code, readiness evidence, or autonomy configuration.
