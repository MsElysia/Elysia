# Harmless Live-Action Smoke Design

**Milestone:** Design/specification only — **no implementation**  
**Date:** 2026-06-14  
**Status:** Designed — **not implemented, not verified, not run**

**Related docs:** [`PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`](PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md), [`PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md`](PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md), [`LIVE_MODE_READINESS_POST_REPAIR_UPDATE.md`](LIVE_MODE_READINESS_POST_REPAIR_UPDATE.md), [`LIVE_EXECUTOR_INTERFACE_DESIGN.md`](LIVE_EXECUTOR_INTERFACE_DESIGN.md), [`UI_API_APPROVAL_ROUTE_DESIGN.md`](UI_API_APPROVAL_ROUTE_DESIGN.md)

**Starting checkpoint:** `623ce00 fix(tests): repair remaining noncritical failures`

---

## 1. Purpose

Define the **future** harmless live-action smoke test that will eventually prove the approval-gated limited live-mode path works end-to-end **without** touching user data, network, shell, browser, APIs, mutation, or runtime memory.

The smoke is a **single reversible file write** inside an isolated temporary workspace — the smallest action that can validate:

- allowlist classification
- approval packet completeness
- operator decision recording
- audit append (explicit path only)
- executor invocation (future)
- rollback metadata and execution (future)

This document does **not** authorize running the smoke, implementing an executor, or enabling autonomy.

---

## 2. Why this is required before limited live mode

Limited live mode (`Approval-Gated Live` in Phase 2 ladder) requires proof that:

| Proof | Why smoke provides it |
|-------|----------------------|
| Approval path is wired | Smoke only runs after explicit operator approval packet + decision |
| Executor is bounded | Smoke action is fixed, allowlisted, single-file |
| Audit is complete | Smoke mandates audit record with path, hash, approval id |
| Rollback works | Smoke requires delete-or-restore rollback of one file |
| Fail-closed defaults hold | Denied/unapproved smoke must produce **zero** workspace writes |

Without a harmless smoke, limited live mode would lack a **minimal real execution proof** separate from full runtime tests (which remain dry/passive).

**Current readiness:** `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED=false` — design exists; implementation and verified run are future milestones.

---

## 3. Non-goals

This milestone and the future smoke **do not**:

- Enable autonomy or modify `config/autonomy.json`
- Implement a live executor
- Add UI/API approval routes
- Run or simulate real live actions now
- Prove full autonomy, bounded autonomy, or multi-action batches
- Replace Safe Observer dry-run verification
- Write to repo root, `CONTROL.md`, `MUTATIONS/`, `REPORTS/` (except explicit opt-in audit path), or user data paths
- Touch `project_guardian/core.py` or `elysia/api/server.py`

---

## 4. Prohibited actions (smoke and executor must deny)

The harmless smoke contract **forbids** these action classes entirely:

| Prohibited | Examples |
|------------|----------|
| **Network** | HTTP, WebSocket, DNS, outbound API |
| **Shell / subprocess** | PowerShell, bash, `SubprocessRunner`, background jobs |
| **Browser / WebScout** | Bounded browser, page fetch, CAPTCHA flows |
| **API calls** | OpenAI, Stripe, implementer, proposal `/implement` |
| **Mutation / proposal implementation** | `APPLY_MUTATION`, implementer agent, repo patches |
| **Runtime memory cleanup** | `MemoryCore` trim, vector reindex, configured memory purge |
| **Config changes** | Any JSON/YAML including `config/autonomy.json` |
| **User data paths** | Home dir, Documents, external drives, cloud sync folders |
| **Repo-root writes** | Any path under project root outside isolated smoke workspace |
| **External storage** | Paths resolved via `external_storage.json` |

If classification is ambiguous → **deny** (fail-closed).

---

## 5. Allowed future smoke action

### Action summary

| Property | Value |
|----------|-------|
| **Category** | `LOCAL_FILE_WRITE` (restricted) or dedicated `HARMLESS_LIVE_SMOKE` allowlist entry |
| **Risk** | Lowest tier — requires approval but no elevated trust |
| **Scope** | Isolated temp workspace only |

### Workspace

```
{tmp_path}/live_smoke_workspace/
```

- `tmp_path` = pytest temp dir, operator-designated smoke dir, or executor-provided isolated root
- **Must not** be project repo root
- **Must not** use external storage mount
- Created by test/fixture or executor immediately before smoke

### Target file

```
{workspace}/approved_smoke.txt
```

### Content (deterministic)

```
ELYSIA_APPROVED_LIVE_SMOKE\n
```

UTF-8, LF line ending, fixed marker — no timestamps in content (timestamp belongs in audit only).

### Write semantics

- **Create** if missing; **update** if exists (idempotent content)
- Single file only — no directories beyond workspace root
- No symlinks, no `..` segments, no absolute paths outside workspace

### Success criteria (future test)

1. Pre-smoke: file absent or known baseline content snapshotted
2. Approval packet built and operator decision = approve
3. Executor runs **only** after all gates pass
4. Post-smoke: file exists with exact marker content
5. Audit line appended to explicit test audit path
6. Rollback restores pre-smoke state
7. Post-rollback: file deleted or baseline restored

### Deny-path criteria (future test)

- Without approval → no file write, audit may record `BLOCKED`/`DENIED`
- Wrong path (repo root) → executor refuses before write
- Wrong content hash in packet → refuse

---

## 6. Required approval packet fields

Built via existing `build_live_action_approval_packet()` scaffolding. Smoke-specific `LiveActionApprovalRequest` must include:

| Field | Requirement |
|-------|-------------|
| `action_id` | Stable id e.g. `harmless_live_smoke_v1` |
| `action_kind` | `harmless_live_smoke` |
| `risk_category` | `LOCAL_FILE_WRITE` or `HARMLESS_LIVE_SMOKE` |
| `target_path` | Relative: `live_smoke_workspace/approved_smoke.txt` |
| `workspace_root` | Absolute isolated tmp path (redacted in operator UI if needed) |
| `content_marker` | `ELYSIA_APPROVED_LIVE_SMOKE` |
| `content_hash` | SHA-256 of exact bytes to write |
| `touches_autonomy_or_live_execution` | `false` for smoke action itself |
| `allowlist_decision` | `REQUIRE_APPROVAL` |
| `operator_identity` | Required |
| `request_id` / `packet_id` | UUID for trace correlation |

Packet must set `execution_permitted=false` at build time (passive phase). Future executor sets true only after operator decision.

---

## 7. Required audit fields

Per `LiveActionAuditRecord` / explicit JSONL append:

| Field | Requirement |
|-------|-------------|
| `event_id` | UUID |
| `timestamp` | UTC ISO-8601 |
| `action_id` | `harmless_live_smoke_v1` |
| `action_kind` | `harmless_live_smoke` |
| `status` | `PROPOSED` → `APPROVED` → `EXECUTION_SUCCEEDED` / `EXECUTION_FAILED` / `BLOCKED` |
| `approval_packet_id` | Links to packet |
| `operator_decision` | `approve` / `deny` / `request_changes` |
| `target_path` | Workspace-relative path |
| `content_hash` | SHA-256 of planned content |
| `rollback_plan_summary` | Strategy + availability |
| `execution_permitted` | `false` until operator approves |
| `dry_run` | `false` only during verified smoke run (future) |
| `executed` | `true` only if file write occurred |
| `blocked` | `true` if any gate denied |

Audit append uses **explicit path only** (`append_live_action_audit_record(path=...)`). Safe Observer must not append smoke audit by default.

---

## 8. Required rollback plan

Per `LiveActionRollbackPlan`:

| Field | Smoke value |
|-------|-------------|
| `action_id` | Same as request |
| `strategy` | `DELETE_CREATED_FILE` if created; `FILE_RESTORE` if updated existing |
| `availability` | `AVAILABLE` |
| `target` | `live_smoke_workspace/approved_smoke.txt` |
| `backup_path` | Snapshot path if file pre-existed |
| `manual_steps` | Optional: `["delete approved_smoke.txt"]` |
| `irreversible_risks` | Empty for smoke (no external side effects) |
| `estimated_complexity` | `trivial` |

Rollback execution is **future executor work**. Design requires rollback metadata validation **before** any live write.

---

## 9. Required executor guardrails (future implementation)

When an executor is implemented, it **must**:

1. Refuse if `config/autonomy.json` `enabled` is not explicitly opted-in for live mode (separate milestone)
2. Refuse if approval packet invalid or operator decision not `approve`
3. Refuse if target path escapes workspace (`..`, absolute outside root, symlink)
4. Refuse if content hash mismatch
5. Refuse prohibited categories (network, shell, browser, mutation, memory, config)
6. Write **at most one** file per smoke invocation
7. Append audit before and after execution attempt
8. Run rollback on failure or offer operator-triggered rollback
9. Never touch repo root, `test.py`, `CONTROL.md`, or configured memory stores
10. Set `execution_permitted=false` in all passive/build paths

Executor is **not implemented** in this milestone. See [`LIVE_EXECUTOR_INTERFACE_DESIGN.md`](LIVE_EXECUTOR_INTERFACE_DESIGN.md) for the future executor boundary, inputs, preconditions, and result schema.

---

## 10. Required tests before implementation

Future test modules (not created in this milestone):

| Test | Asserts |
|------|---------|
| `test_harmless_smoke_packet_schema` | Packet builds with all required fields; `execution_permitted=false` |
| `test_harmless_smoke_denied_without_approval` | No workspace write when denied |
| `test_harmless_smoke_approved_writes_isolated_file` | File created under `tmp_path/live_smoke_workspace/` only |
| `test_harmless_smoke_no_repo_root_write` | Repo root `test.py` and project files unchanged |
| `test_harmless_smoke_rollback_restores` | Post-rollback file absent or baseline restored |
| `test_harmless_smoke_audit_append` | Audit JSONL line at explicit path with required fields |
| `test_harmless_smoke_prohibited_categories_blocked` | Network/shell/browser requests denied at gate |

Pre-implementation gate: default runtime suite remains clean (439 passed / 0 failed at `623ce00`).

---

## 11. Readiness impact

| Check | Before this doc | After this doc |
|-------|-----------------|----------------|
| `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED` | `false` | **`false`** (unchanged) |
| Blocker wording | "not verified" / undefined design | **"designed but not implemented/verified"** |
| `ready_for_limited_live_mode` | `false` | **`false`** |
| `status` | `BLOCKED` | **`BLOCKED`** |
| Live executor blocker | active | **active** |
| UI/API approval route blocker | active | **active** |

Readiness blocker transitions from implicit "no harmless smoke defined" to explicit **"harmless live-action smoke not implemented/verified"** per [`docs/HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md`](HARMLESS_LIVE_ACTION_SMOKE_DESIGN.md).

Setting `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED=true` requires a **future milestone** that implements and runs the smoke under approval — not this document alone.

---

## 12. Safety statement

- **No live execution implemented**
- **No live action run**
- **No executor added**
- **No API/server route added**
- **No autonomy enabled** — `config/autonomy.json` → `"enabled": false`
- **No real repo mutation performed**
- **No tools/capabilities/browser/WebScout activity**
- **Limited live mode remains BLOCKED**

---

## Appendix: Example future flow (design only)

```
1. Build LiveActionApprovalRequest (harmless_live_smoke_v1)
2. validate_live_action_request() → requires_approval
3. build_live_action_rollback_plan() → DELETE_CREATED_FILE
4. build_live_action_approval_packet() → execution_permitted=false
5. Operator decision → approve (future UI/API route)
6. Executor (future) writes tmp_path/live_smoke_workspace/approved_smoke.txt
7. append_live_action_audit_record(explicit_path) → EXECUTION_SUCCEEDED
8. Rollback (future) deletes file
9. Readiness evidence HARMLESS_LIVE_ACTION_SMOKE_VERIFIED=true (future only)
```

Steps 5–9 are **out of scope** for this milestone.
