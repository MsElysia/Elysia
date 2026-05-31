# Phase 2 Passive Safety Stack Baseline

**Milestone:** Documentation baseline — passive Phase 2 stack recorded  
**Date:** 2026-05-31  
**Status:** **Live mode remains blocked**

**Related docs:** [`PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`](PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md), [`DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md), [`STARTUP_STORAGE_FALLBACK_BASELINE.md`](STARTUP_STORAGE_FALLBACK_BASELINE.md)

---

## 1. Current checkpoint

| Item | Value |
|------|-------|
| **HEAD** | `9a5e93b` — feat(autonomy): add passive live-mode readiness gate |
| **`config/autonomy.json`** | **`enabled: false`** (unchanged by design) |
| **Safe Observer** | Verified runtime mode |
| **Limited live mode** | **Not ready** — readiness gate reports `NOT_READY_FOR_LIVE_MODE` / `BLOCKED` by default |
| **Live execution** | **Not enabled** |
| **Full autonomy** | **Not enabled** |

This document records what the **passive** Phase 2 safety stack can do today. It does **not** authorize live execution, autonomy enablement, or runtime wiring.

---

## 2. Components completed

The following passive safety components are implemented, tested, and verified on the commit chain below:

| Component | Module / artifact | Role |
|-----------|-------------------|------|
| Safe Observer dry-run reporting | `scripts/run_elysia_dry_run_report.py` | Dry-run cycles with zero execution |
| Dry-run observability envelope | `project_guardian/autonomy_dry_run_guard.py` | Safety verdict, decision traces, observability warnings |
| Phase 2 allowlist design | `docs/PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md` | Mode ladder, risk categories, policy design |
| Passive live-action gate | `project_guardian/live_action_gate.py` | Risk classification and allowlist validation |
| Passive audit scaffolding | `project_guardian/live_action_audit.py` | Audit record schema; explicit JSONL writer only |
| Passive rollback metadata | `project_guardian/live_action_rollback.py` | Rollback plan schema and completeness validation |
| Passive approval packet | `project_guardian/live_action_approval_packet.py` | Combines gate, rollback, and audit metadata |
| Passive operator decision | `project_guardian/live_action_operator_decision.py` | Approve/deny decision schema and validation |
| Passive live-mode readiness gate | `project_guardian/live_action_readiness.py` | Evaluates readiness for limited live mode |

Supporting verified baselines (pre-Phase 2 scaffolding):

- Startup storage fallback — `project_guardian/startup_health.py`, documented in `docs/STARTUP_STORAGE_FALLBACK_BASELINE.md`
- Dirty risky hunks quarantine — `docs/DIRTY_RISKY_HUNKS_TRIAGE.md` (`project_guardian/core.py`, `elysia/api/server.py` unstaged)

---

## 3. Commit chain

Phase 2 passive scaffolding commits (oldest → newest):

| Commit | Message |
|--------|---------|
| `cb018fa` | docs(autonomy): design phase2 live-action allowlist |
| `c968cdf` | feat(autonomy): add passive live-action gate scaffolding |
| `0c81da3` | feat(autonomy): add passive live-action audit scaffolding |
| `ea6d822` | feat(autonomy): add passive live-action rollback scaffolding |
| `c6e9944` | feat(autonomy): add passive live-action approval packets |
| `37296a5` | feat(autonomy): add passive operator decision scaffolding |
| `9a5e93b` | feat(autonomy): add passive live-mode readiness gate |

Prior Safe Observer observability (feeds the stack):

| Commit | Message |
|--------|---------|
| `f7b21f0` | feat(observer): improve dry-run safety observability |

---

## 4. What the passive stack can do

The passive stack supports **classification, validation, and recording only**:

- Classify proposed actions by risk category (`ActionRiskCategory`)
- Apply Phase 2 allowlist policy (`ALLOW_LOGGED`, `REQUIRE_APPROVAL`, `BLOCKED`)
- Block dangerous categories (API, browser/WebScout, network, autonomy config, proposal implementation, etc.)
- Build structured approval packets combining request, validation, rollback, and audit metadata
- Validate rollback plan schema and completeness (no file touches)
- Shape audit records and optionally append JSONL when explicitly called with a path
- Record operator approve/deny/request-changes decisions passively (`execution_permitted` always `False` in this milestone)
- Evaluate readiness for limited live mode and list blockers
- Explain why limited live mode remains blocked

All of the above runs **without** enabling autonomy, live execution, or runtime wiring.

---

## 5. What the passive stack cannot do

The passive stack explicitly does **not**:

- Execute actions
- Execute rollback
- Enable autonomy
- Modify `config/autonomy.json`
- Run tools or capabilities
- Call browser or WebScout
- Call external APIs
- Add or trigger server/API routes
- Perform proposal implementation
- Make code changes automatically
- Write audit files by default (Safe Observer does not append live-action audit JSONL)
- Grant `execution_permitted=True` via operator decision or readiness evaluation in current milestones

Safe Observer Mode remains the **only verified runtime mode**.

---

## 6. Current readiness result

Default evaluation via `evaluate_live_mode_readiness()` (no overrides):

| Field | Default value |
|-------|---------------|
| **Status** | `BLOCKED` / `NOT_READY` |
| **`ready_for_limited_live_mode`** | `false` |
| **`safety_verdict`** | `NOT_READY_FOR_LIVE_MODE` |

### Blockers (required checks not satisfied)

| Blocker | Evidence |
|---------|----------|
| Dirty `project_guardian/core.py` | Quarantined unstaged hunks — not cleaned or safely committed |
| Dirty `elysia/api/server.py` | Quarantined unstaged hunks — not cleaned or safely committed |
| Missing live executor | No approval-gated live executor implementation |
| Missing UI/API approval route | No operator approval UI or API route wired |
| Missing harmless live-action smoke verification | No verified harmless live-action smoke test run |
| Full runtime tests not classified | `FULL_RUNTIME_TESTS_CLASSIFIED` remains false |

Checks that **pass** in default evidence (scaffolding present, Safe Observer verified, autonomy config disabled by design):

- `SAFE_OBSERVER_VERIFIED`
- `STARTUP_STABLE`
- `ALLOWLIST_IMPLEMENTED`
- `APPROVAL_PACKET_IMPLEMENTED`
- `OPERATOR_DECISION_IMPLEMENTED`
- `AUDIT_IMPLEMENTED`
- `ROLLBACK_METADATA_IMPLEMENTED`
- `AUTONOMY_CONFIG_DEFAULT_DISABLED`

---

## 7. Safety guarantees verified

At checkpoint `9a5e93b`, the following guarantees hold:

| Guarantee | Status |
|-----------|--------|
| `config/autonomy.json` remained `enabled=false` | Verified |
| No autonomy or live execution enabled | Verified |
| Passive modules avoid execution/tool/browser/API imports | Verified by tests |
| No server/API routes added for Phase 2 scaffolding | Verified |
| Safe Observer dry-run passes | `python scripts/run_elysia_dry_run_report.py --mode real-planning` → exit 0, SAFE, zero execution |
| Safe-stack smoke tests pass | `python scripts/run_safe_stack_smoke_tests.py` → 454 passed |
| Quarantined dirty files not staged | `project_guardian/core.py`, `elysia/api/server.py` remain unstaged |

Targeted Phase 2 passive test slice (gate, audit, rollback, packet, operator decision, readiness): **91 passed**.

---

## 8. Recommended next branches

Work should proceed in isolated branches. **None of these branches enable live mode by default.**

| Branch | Scope | Type |
|--------|-------|------|
| **A** | Permanently clean or reject dirty `project_guardian/core.py` and `elysia/api/server.py` hunks | Hygiene / quarantine resolution |
| **B** | Full runtime pytest failure classification | Analysis / test taxonomy |
| **C** | Limited executor design only | Design — no implementation |
| **D** | UI/API approval route design only | Design — no routes wired |
| **E** | Harmless live-action smoke plan | Design — no live run |

---

## 9. Explicit next recommendation

**Recommend Branch A before any executor or route work:**

Permanently clean or reject the quarantined dirty hunks in `project_guardian/core.py` and `elysia/api/server.py`. Those files contain mixed autonomy trace, auto-implement-on-approve, and WebScout expansion hunks that must not be adopted as-is. Until they are resolved, the readiness gate correctly reports **not ready for limited live mode**.

Do **not** proceed to live executor implementation, UI/API approval routes, or harmless live-action smoke execution until Branch A is complete and re-verified.

---

## 10. Summary

The Phase 2 **passive** safety stack is complete through the readiness gate. Elysia can classify, packetize, validate rollback metadata, shape audit records, validate operator decisions, and explain blockers — all without executing anything.

**Limited live mode and live execution remain blocked.** Safe Observer Mode remains the verified runtime path.

**This document does not enable live execution or autonomy.**
