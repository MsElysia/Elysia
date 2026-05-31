# Phase 2 — live-action allowlist and approval-gate design

**Milestone:** Phase 2 design only (no implementation)  
**Date:** 2026-05-31  
**Status:** Design document — **not approved for live execution**

**Related docs:** [`DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md), [`STARTUP_STORAGE_FALLBACK_BASELINE.md`](STARTUP_STORAGE_FALLBACK_BASELINE.md), [`PHASE1D_G_SAFE_OBSERVER_MODE_CHECKPOINT.md`](PHASE1D_G_SAFE_OBSERVER_MODE_CHECKPOINT.md) (if present), [`CORE_UNSTAGED_RISKY_HUNKS.md`](CORE_UNSTAGED_RISKY_HUNKS.md), [`SERVER_UNSTAGED_RISKY_HUNKS.md`](SERVER_UNSTAGED_RISKY_HUNKS.md)

---

## 1. Current verified checkpoint

| Item | Status |
|------|--------|
| **HEAD** | `f7b21f0` — feat(observer): improve dry-run safety observability |
| **Safe Observer** | Verified — `python scripts/run_elysia_dry_run_report.py --mode real-planning` exits 0, SAFE, dry-run only |
| **Startup** | Stable — storage fallback baseline documented (`c8cd3d4` / `e0e6e09`) |
| **Dirty hunks** | Quarantined — `project_guardian/core.py`, `elysia/api/server.py` remain unstaged |
| **`config/autonomy.json`** | **`enabled: false`** (unchanged) |
| **Live execution** | **Not enabled** |
| **Full autonomy** | **Not enabled** |

This document describes a **future** path. It does **not** authorize implementation or enablement.

---

## 2. Purpose

Phase 2 is **not** “turn on full autonomy.”

Phase 2 defines the **first controlled path from Safe Observer Mode toward real Elysia action**:

- **Approval-gated** — operator must explicitly approve each live action (early Phase 2).
- **Allowlisted** — only pre-defined action categories and targets may execute.
- **Audited** — every proposal, approval, denial, and execution is logged with rollback metadata.
- **Fail-closed** — unknown actions, unlisted categories, and blocked paths are denied by default.

Safe Observer Mode remains the **only verified runtime mode** until separate implementation milestones pass and an operator manually opts into a higher mode.

---

## 3. Mode ladder

Modes are **strictly ordered**. Higher modes inherit lower-mode constraints unless explicitly relaxed in config **and** verified by tests.

```
Safe Observer → Assisted Action → Approval-Gated Live → Bounded Autonomy → Full Autonomy (blocked)
```

### Safe Observer Mode *(current verified mode)*

| Property | Value |
|----------|-------|
| Execution | **None** — dry-run only |
| Command | `python scripts/run_elysia_dry_run_report.py [--mode real-planning]` |
| Autonomy config | `enabled=false` |
| Tools / capabilities / mutation / WebScout / browser | **Not run** |
| File writes (audit) | **Off by default** (`--write-audit` opt-in) |
| Purpose | Observe planning, traces, safety verdicts without side effects |

### Assisted Action Mode *(Phase 2 design target — not implemented)*

| Property | Value |
|----------|-------|
| Execution | **Human performs** or manually approves outside automated executor |
| Elysia role | Proposes actions with full approval packet; may prepare drafts/reports in restricted folders only after explicit policy |
| Automated executor | **Off** |
| Purpose | Operator-in-the-loop workflow before any machine execution |

### Approval-Gated Live Mode *(Phase 2 end-state — not implemented)*

| Property | Value |
|----------|-------|
| Execution | Elysia **may execute** only **allowlisted** actions **after** structured operator approval |
| Default | Fail-closed; deny if not on allowlist or approval missing/expired |
| Autonomy loop | Still **not** “full autonomy”; single-action or bounded batch with hard caps |
| `config/autonomy.json` | Remains **`enabled=false`** until a later milestone explicitly revisits autonomy enablement |

### Bounded Autonomy Mode *(future — design placeholder only)*

| Property | Value |
|----------|-------|
| Execution | Low-risk **READ_ONLY** / **WRITE_REPORT** (restricted paths) may run without per-action approval |
| Dangerous categories | Still require approval (file modify, config, code, network, etc.) |
| Prerequisites | Approval-Gated Live Mode stable for extended trial period |

### Full Autonomy *(not approved)*

| Property | Value |
|----------|-------|
| Status | **Blocked** until many additional safety milestones pass |
| Includes | Unrestricted loops, self-modification, automatic code change, WebScout/browser autonomy, proposal implementation without gate |
| Policy | Out of scope for Phase 2 design |

---

## 4. Action risk categories

Every proposed action must be classified into **exactly one primary category** (secondary tags optional). Classification drives allowlist and approval rules.

| Category | Description |
|----------|-------------|
| **READ_ONLY** | Read files, status, logs, memory queries; no writes |
| **WRITE_REPORT** | Write operator-visible reports/artifacts to designated output folders |
| **LOCAL_FILE_WRITE** | Create new files outside report folders |
| **LOCAL_FILE_MODIFY** | Edit or delete existing local files |
| **SHELL_COMMAND** | Run subprocess/shell commands |
| **NETWORK_REQUEST** | Generic outbound HTTP/TCP (non-API-classified) |
| **API_CALL** | Call configured external APIs (OpenAI, Stripe, etc.) |
| **BROWSER_OR_WEBSCOUT** | Browser automation, WebScout research, bounded browser |
| **CODE_CHANGE** | Modify project source code (implementer, patches) |
| **PROPOSAL_IMPLEMENTATION** | Apply proposal/implementer pipeline to repo |
| **MEMORY_WRITE** | Persist to guardian memory / vector / timeline |
| **CONFIG_CHANGE** | Modify runtime config JSON/YAML (except autonomy — see below) |
| **AUTONOMY_CONFIG_CHANGE** | Change autonomy mode, allowlist, or `config/autonomy.json` |

**Default rule:** If classification is ambiguous or missing → treat as **highest applicable risk** and **deny**.

---

## 5. Initial allowlist proposal (Phase 2 early policy)

**Phase 2 early** = Approval-Gated Live Mode with a **minimal** allowlist. “Allowed in Phase 2?” means allowed **only after** implementation milestones (Section 9) and operator opt-in — not today.

| Action category | Allowed in Phase 2? | Requires approval? | Reversible? | Notes |
|-----------------|---------------------|--------------------|-------------|-------|
| **READ_ONLY** | Yes (with logging) | No *(observe-only)* | N/A | Status, logs, read-only memory queries; no side effects |
| **WRITE_REPORT** | Yes | Yes *(or restricted folder only)* | Mostly | Default output: `REPORTS/`, `data/runtime/operator_artifacts/`; no overwrite without approval |
| **MEMORY_WRITE** | Conditional | **Yes** | Partial | Operator-curated memories only; no autonomous self-task memory flooding |
| **LOCAL_FILE_WRITE** | Conditional | **Yes** | Mostly | Restricted to safe output folders; never project source tree in early Phase 2 |
| **LOCAL_FILE_MODIFY** | Conditional | **Yes** | Partial | Explicit path allowlist; backup before write |
| **SHELL_COMMAND** | **Blocked** | Yes if ever allowlisted | Varies | Only explicit approved safe commands (e.g. read-only diagnostics); no arbitrary shell |
| **NETWORK_REQUEST** | **Blocked** at first | Yes if opened later | N/A | Fail-closed until network policy module exists |
| **API_CALL** | **Blocked** at first | Yes if opened later | N/A | Billing/safety; separate API budget gate |
| **BROWSER_OR_WEBSCOUT** | **Blocked** at first | Yes if opened later | N/A | Quarantined dirty `server.py` WebScout hunks must not be adopted as-is |
| **CODE_CHANGE** | Conditional | **Yes — never automatic** | Partial | Dry-run diff preview mandatory; no auto-merge |
| **PROPOSAL_IMPLEMENTATION** | **Blocked** at first | Yes if opened later | Partial | Dirty `server.py` implement-on-approve hunks rejected for Phase 2 |
| **CONFIG_CHANGE** | Conditional | **Yes** | Partial | Never includes autonomy config in automated path |
| **AUTONOMY_CONFIG_CHANGE** | **Blocked** | Manual operator only | N/A | Direct file edit by operator; never Elysia-initiated in Phase 2 |

---

## 6. Approval gate requirements

Every **live action request** (whether initiated by operator chat or internal proposal) must produce a structured **approval packet** before execution. The UI/API surface for displaying this packet is **designed separately**; Phase 2 does not adopt dirty `elysia/api/server.py` approval/implementation routes.

### Required fields in approval packet

| Field | Description |
|-------|-------------|
| **proposed_action** | Canonical action string (e.g. `write_report:weekly_summary`) |
| **reason** | Why Elysia proposes this action |
| **target** | Exact file path, tool name, API endpoint, command, or resource ID |
| **expected_result** | What success looks like (file created, report path, status change) |
| **risk_category** | One of Section 4 categories |
| **rollback_plan** | How to undo or recover (backup path, delete artifact, revert memory entry) |
| **touches_autonomy_or_live_execution** | Boolean — must be **false** for early Phase 2 allowlist actions |
| **writes_files** | Boolean + list of paths |
| **touches_network_api_browser** | Boolean + details if true |
| **allowlist_decision** | `allowed` / `denied` / `requires_approval` with rule ID |
| **operator_result** | `pending` / `approved` / `denied` + operator ID + timestamp |

### Gate behavior

1. Classify action → check allowlist → if blocked, **deny** with audit entry.
2. If allowed but approval required → status **pending** until operator approves.
3. Approval expires after configurable TTL (default: single use, short window).
4. Execution runs only through a **single executor entrypoint** that re-validates allowlist + approval + live-execution guard.
5. Deny on any missing field, malformed packet, or guard failure.

---

## 7. Audit requirements

All proposals, approvals, denials, and executions append to an **append-only audit log** (JSONL). Default path proposal: `data/runtime/live_action_audit.jsonl`. **No audit writes in Safe Observer Mode by default** (same policy as dry-run command).

### Required audit record fields

| Field | Description |
|-------|-------------|
| **timestamp** | ISO-8601 UTC |
| **mode** | e.g. `safe_observer`, `assisted_action`, `approval_gated_live` |
| **action_id** | Unique UUID for this action instance |
| **proposed_action** | Action string |
| **risk_category** | Primary category |
| **approval_status** | `not_required` / `pending` / `approved` / `denied` / `expired` |
| **executor** | Component that would run or ran the action (empty if dry-run) |
| **target** | File/tool/API/command affected |
| **result** | `dry_run` / `success` / `failure` / `blocked` + message |
| **rollback_info** | Backup paths, revert commands, or `none` |
| **safety_verdict** | `SAFE` / `UNSAFE` / `BLOCKED` aligned with observer vocabulary |

Optional correlation fields: `batch_id`, `cycle_id`, `operator_id`, `allowlist_rule_id`, `live_execution_guard_reasons[]`.

---

## 8. Hard blocks (early Phase 2)

These remain **blocked** regardless of mode until explicit later milestones and operator policy change:

| Block | Rationale |
|-------|-----------|
| Enabling `config/autonomy.json` (`enabled=true`) via automated path | Full autonomy loop; separate milestone |
| **Proposal implementation** (implementer apply) | Quarantined `server.py` hunks; governance track required |
| **WebScout / browser autonomy** | External research + browser surface; high risk |
| **Arbitrary shell commands** | RCE class; allowlist-only if ever opened |
| **Arbitrary API calls** | Cost, data exfil, side effects |
| **Automatic code changes** | No commit/apply without approval + dry-run preview |
| **Self-modifying behavior** | Mutation engine, self-task code apply |
| **Mutation execution** | Out of Phase 2 scope |
| **External posting / messaging / email** | Without explicit per-action operator approval |
| **AUTONOMY_CONFIG_CHANGE** by Elysia | Operator manual edit only |
| Adopting dirty **`core.py`** scoring/trace/legacy hunks | Use clean dry-run guard path only |
| Adopting dirty **`server.py`** implement/WebScout hunks | Design from scratch with gates |

---

## 9. Required implementation milestones before any live action

**No live execution** until **all** items below are implemented, tested, and verified on **clean HEAD** (not dirty worktree).

| # | Milestone | Deliverable |
|---|-----------|-------------|
| 1 | **Mode config schema** | `config/live_action_mode.json` (or equivalent) — default `safe_observer`; explicit operator opt-in for higher modes |
| 2 | **Allowlist validator** | Pure function + config: category → allowed / denied / approval_required |
| 3 | **Approval request object** | Structured packet (Section 6) + persistence (store) |
| 4 | **Audit writer** | Append-only JSONL with Section 7 fields; off by default in observer mode |
| 5 | **Rollback metadata** | Pre-write backups for file actions; documented revert for memory writes |
| 6 | **Executor entrypoint** | Single fail-closed gate: allowlist → approval → live_execution_guard → execute |
| 7 | **Tests: denied actions** | Blocked categories return `BLOCKED` without side effects |
| 8 | **Tests: approved harmless actions** | READ_ONLY / WRITE_REPORT to safe paths succeed with audit |
| 9 | **Tests: blocked categories stay blocked** | Regression suite for Section 8 hard blocks |
| 10 | **UI/API approval route design** | Reviewed separately; **do not** adopt quarantined `server.py` hunks |
| 11 | **Safe-stack smoke + observer command** | Still pass after each increment |
| 12 | **Documentation baseline** | Checkpoint doc per mode enablement |

**Explicit non-goals for first implementation slice:**

- No new HTTP routes in Phase 2 first code slice without separate design review.
- No change to `config/autonomy.json` defaults.
- No background autonomy loop.

---

## 10. Definition of “ready to enable limited live mode”

**Limited live mode** = **Approval-Gated Live Mode** with minimal allowlist (READ_ONLY logging + WRITE_REPORT with approval + restricted folders).

### Readiness checklist (all required)

| # | Criterion |
|---|-----------|
| 1 | Dirty **`project_guardian/core.py`** hunks **cleaned, extracted safely, or permanently rejected** — not staged as-is |
| 2 | Dirty **`elysia/api/server.py`** hunks **cleaned, redesigned, or permanently rejected** — not staged as-is |
| 3 | **Allowlist validator** implemented and tested |
| 4 | **Approval gate** implemented and tested |
| 5 | **Audit logging** implemented (append-only, fields per Section 7) |
| 6 | **Rollback metadata** implemented for file-writing actions |
| 7 | **Denied-action tests** pass — blocked categories never execute |
| 8 | **Approved harmless-action tests** pass — READ_ONLY / restricted WRITE_REPORT |
| 9 | **Safe Observer command** still exits SAFE with `config/autonomy.json` disabled |
| 10 | **Safe-stack smoke** passes |
| 11 | **`config/autonomy.json`** still defaults to **`enabled: false`** |
| 12 | **Operator manually opts in** — env var or config flag, not automatic on startup |
| 13 | **Written checkpoint doc** recorded with commit hash and verification results |

Until this checklist is complete, the only verified operator command for safety verification remains:

```bash
python scripts/run_elysia_dry_run_report.py --mode real-planning
```

---

## Appendix A — Suggested config sketch (design only, not committed)

```json
{
  "mode": "safe_observer",
  "approval_gated_live": {
    "enabled": false,
    "approval_ttl_seconds": 300,
    "allowed_categories": ["READ_ONLY", "WRITE_REPORT"],
    "write_report_roots": ["REPORTS/", "data/runtime/operator_artifacts/"]
  }
}
```

**Note:** This schema is illustrative. Do not add this file in the design-only milestone.

---

## Appendix B — Relationship to existing guards

| Existing component | Phase 2 relationship |
|--------------------|----------------------|
| `project_guardian/autonomy_dry_run_guard.py` | Safe Observer / dry-run trace source; remains dry-run |
| `project_guardian/governance/live_execution_guard.py` | Must wrap any future executor entrypoint |
| `scripts/run_elysia_dry_run_report.py` | Verified Safe Observer command; unchanged by this design |
| Quarantined `core.py` / `server.py` | **Not** inputs to Phase 2 implementation |

---

## Document control

| Version | Commit | Notes |
|---------|--------|-------|
| 1.0 | `cb018fa` | Phase 2 design only — no implementation |
| 1.1 | feat(autonomy): add passive live-action gate scaffolding | Passive scaffolding in `project_guardian/live_action_gate.py`; validation only; **live execution remains disabled**; not wired to runtime |
| 1.2 | feat(autonomy): add passive live-action audit scaffolding | Passive audit schema/writer in `project_guardian/live_action_audit.py`; **disabled by default**; explicit path only; not wired to execution or Safe Observer |
| 1.3 | feat(autonomy): add passive live-action rollback scaffolding | Passive rollback schema/validation in `project_guardian/live_action_rollback.py`; **does not execute rollback**; not wired to runtime |

**This document does not enable live execution or autonomy.**
