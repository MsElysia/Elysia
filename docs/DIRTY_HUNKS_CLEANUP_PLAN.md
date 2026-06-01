# Dirty Hunks Cleanup Plan — Branch A

**Milestone:** Branch A — permanent cleanup/rejection plan (documentation only)  
**Current verified checkpoint:** `2f5621a` — docs(autonomy): record phase2 passive safety stack baseline  
**Date:** 2026-05-31  
**Scope:** Planning only. **Does not modify, stage, reset, stash, or discard** quarantined files.

**Related docs:** [`DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md), [`PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md`](PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md), [`PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`](PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md)

---

## 1. Purpose

This plan **permanently decides** how to handle dirty risky hunks in `project_guardian/core.py` and `elysia/api/server.py` **before** any limited live executor, UI/API approval route, or harmless live-action smoke work begins.

The passive Phase 2 safety stack (gate, audit, rollback, approval packets, operator decisions, readiness gate) is complete on committed HEAD. The quarantined dirty files are **not** part of that stack and must not be adopted as-is.

**This milestone does not enable autonomy or live execution.**

---

## 2. Files covered

| File | Status (at plan time) | Diff size |
|------|----------------------|-----------|
| `project_guardian/core.py` | Modified, **unstaged**, quarantined | +180 / −9 lines |
| `elysia/api/server.py` | Modified, **unstaged**, quarantined | +108 / −20 lines |

Inspection method (read-only):

```powershell
git diff -- project_guardian/core.py
git diff -- elysia/api/server.py
```

---

## 3. Classification legend

| Label | Meaning |
|-------|---------|
| **ALREADY_EXTRACTED_CLEANLY** | Useful intent already landed in committed passive/safe code; dirty hunk is redundant |
| **REWRITE_FROM_SCRATCH** | Idea may be valid later; must be reimplemented on clean branch using passive safety stack / governance |
| **REJECT** | Do not adopt; discard with dirty file restore after human approval |
| **KEEP_UNSTAGED_UNTIL_MANUAL_DISCARD** | Remains quarantined until human approves discard; no staging |
| **NEEDS_HUMAN_REVIEW** | Low/medium risk isolated change; human decides extract vs discard |

---

## 4. `project_guardian/core.py` — hunk classification

**Overall decision:** **REJECT** all groups as a batch after human approval. Do **not** stage or commit dirty `core.py`. Safe observability needs are already met on HEAD without these hunks.

| # | Hunk group | Symbols / region | Classification | Rationale |
|---|------------|------------------|----------------|-----------|
| **C1** | Autonomy decision trace helpers | `_autonomy_decision_trace_enabled`, `_autonomy_trace_identity`, `_autonomy_trace_action_label`, `_autonomy_trace_markers`, `_format_autonomy_candidate_trace`, `_build_autonomy_decision_trace` (~143 lines) | **ALREADY_EXTRACTED_CLEANLY** + **REJECT** (live placement) | Safe Observer observability is committed in `project_guardian/autonomy_dry_run_guard.py` (`f7b21f0`) and `scripts/run_elysia_dry_run_report.py`. These core-local trace formatters duplicate intent and would wire into live autonomy selection context if adopted. |
| **C2** | Live selection path trace emission | `_get_next_action_impl` — builds `decision_trace`, `logger.info`, adds `out["decision_trace"]` (~18 lines) | **REJECT** | Touches live candidate-selection return path. Risky autonomy behavior; conflicts with fail-closed Safe Observer baseline. |
| **C3** | Chatlog guidance memory guard | `_maybe_collect_chatlog_guidance` — only `memory.remember` when `items_used > 0` (~7 lines changed) | **NEEDS_HUMAN_REVIEW** → default **KEEP_UNSTAGED_UNTIL_MANUAL_DISCARD** | Unrelated maintenance; not required for Phase 2 passive stack. If ever wanted, rewrite in isolated PR with test — not from dirty hunk. |
| **C4** | Self-task archetype scoring | `arch_select_factor`, `archetype_selection_factor`, `queue.archetype_multiplier` / `archetype_suppression_factor` priority scaling (~12 lines) | **REJECT** | Changes autonomy **selection/scoring**. Must not be adopted as-is; no committed safe replacement needed for limited live mode prep. |
| **C5** | Legacy harvest executor branch | `run_autonomous_cycle` — `harvest_income_report` / `action_meaningful_success` init (~3 lines) | **REJECT** | Legacy executor path; risky if legacy paths re-enabled. Phase 1 dry-run guard blocks while `enabled=false`; hunk still must not land. |

### Required decisions (`core.py`)

| Requirement | Decision |
|-------------|----------|
| Safe observability from `core.py` useful for Safe Observer | **Already extracted cleanly** into committed `autonomy_dry_run_guard.py` + dry-run report script |
| Risky autonomy scoring / archetype / legacy behavior | **REJECT** — groups C2, C4, C5 |
| Unrelated maintenance (C3) | **KEEP_UNSTAGED_UNTIL_MANUAL_DISCARD** — discard with batch restore unless human opens separate clean PR |

---

## 5. `elysia/api/server.py` — hunk classification

**Overall decision:** **REJECT** all groups as a batch after human approval. Future approval/UI/API routes must be **designed from scratch** using the passive safety stack (`live_action_*` modules), not copied from dirty `server.py`.

| # | Hunk group | Symbols / route | Classification | Rationale |
|---|------------|-----------------|----------------|-----------|
| **S1** | Auto-implement constructor flag | `RuntimeAPIServer.__init__` — `auto_implement_on_approval` | **REJECT** | Global opt-in for chained implementation on approval; no live-execution guard integration. |
| **S2** | Implementation helpers | `_approval_should_implement`, `_run_implementation` | **REJECT** | HTTP-triggered proposal implementation machinery; must be **REWRITE_FROM_SCRATCH** behind passive packet + operator decision + readiness gate if ever built. |
| **S3** | Approve chains implementation | `POST /api/proposals/<id>/approve` — `response["implementation"]` | **REJECT** | Approval becomes implicit implement trigger; conflicts with Phase 2 approval-gated design. |
| **S4** | Status transition chains implementation | `POST /api/proposals/<id>/status` — on `approved`, chain implementation | **REJECT** | Same as S3. |
| **S5** | Implement route refactor | `POST /api/proposals/<id>/implement` → `_run_implementation` | **REWRITE_FROM_SCRATCH** | Centralization concept only; dirty implementation must not be adopted. |
| **S6** | New preview route | `GET|POST /api/proposals/<id>/implementation/preview` | **REJECT** | New API surface for proposal implementation; outside safe-stack scope; preview still invokes implementer machinery. |
| **S7** | WebScout research expansion | `POST /api/webscout/research` — `research_options` (`tags`, `check_duplicates`, `implementation_plan`, `max_sources`, `auto_generate_implementation_plan`) | **REJECT** | WebScout / external research API expansion; fail-closed posture forbids adopting from dirty hunk. |

### Required decisions (`server.py`)

| Requirement | Decision |
|-------------|----------|
| Risky proposal implementation / auto-implement on approve | **REJECT** — groups S1–S4, S6 |
| WebScout / API surface expansion | **REJECT** — group S7 |
| Future approval/UI/API routes | **REWRITE_FROM_SCRATCH** using passive stack; **never copy** dirty `server.py` hunks |

---

## 6. Existing safe replacements (committed HEAD)

The following committed work **supersedes** any need to adopt dirty hunks for safe autonomy preparation:

| Need | Committed replacement | Commit / artifact |
|------|----------------------|-------------------|
| Safe Observer dry-run | `scripts/run_elysia_dry_run_report.py` | Phase 1d checkpoints |
| Dry-run observability envelope | `project_guardian/autonomy_dry_run_guard.py` | `f7b21f0` |
| Startup stability | `project_guardian/startup_health.py` | `c8cd3d4` / `e0e6e09` |
| Phase 2 allowlist / gate | `project_guardian/live_action_gate.py` | `c968cdf` |
| Audit scaffolding | `project_guardian/live_action_audit.py` | `0c81da3` |
| Rollback metadata | `project_guardian/live_action_rollback.py` | `ea6d822` |
| Approval packets | `project_guardian/live_action_approval_packet.py` | `c6e9944` |
| Operator decisions | `project_guardian/live_action_operator_decision.py` | `37296a5` |
| Readiness gate | `project_guardian/live_action_readiness.py` | `9a5e93b` |
| Baseline summary | `docs/PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md` | `2f5621a` |

**Conclusion:** Step 1 of cleanup — confirm HEAD contains all safe replacements — **passes**. No dirty hunk is required for current verified behavior.

---

## 7. Recommended cleanup sequence

| Step | Action | Owner |
|------|--------|-------|
| **1** | Confirm committed HEAD contains all safe replacements (table above) | ✅ Done at `2f5621a` |
| **2** | Save human-readable quarantine reference if needed | This doc + [`DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md) |
| **3** | **Human approves** discard/revert of dirty `core.py` and `server.py` | Operator |
| **4** | Discard **only** those two files with explicit command (see §8) | Operator |
| **5** | Verify Safe Observer and safe-stack smoke still pass on clean tree | Operator / CI |
| **6** | Commit documentation noting dirty risky hunks were permanently rejected | Future doc commit |
| **7** | Only **after** Steps 3–6: consider limited executor design (Branch C) or UI/API approval route design (Branch D) | Design-only branches |

**Do not run Step 4 in this milestone.**

---

## 8. Future discard commands (NOT RUN in this milestone)

After explicit human approval, restore both files to last committed version:

```powershell
git checkout -- project_guardian/core.py elysia/api/server.py
```

Safer modern equivalent:

```powershell
git restore project_guardian/core.py elysia/api/server.py
```

Verify discard:

```powershell
git diff -- project_guardian/core.py elysia/api/server.py
# expect: no output

git status --short -- project_guardian/core.py elysia/api/server.py
# expect: not listed as modified
```

---

## 9. Safety warning

**The discard commands in §8 are destructive to local dirty hunks.**

- They permanently remove uncommitted changes in `project_guardian/core.py` and `elysia/api/server.py`.
- They must **only** be run after human review of this plan and quarantine references.
- They must **not** be run with `git add -A`, `git reset --hard`, or broad clean commands that would affect other worktree files.
- Other modified files in the worktree are **out of scope** for Branch A Step 4; discard only the two named files.

---

## 10. Readiness gate alignment

Default `evaluate_live_mode_readiness()` blockers that this plan addresses:

| Readiness check | Before cleanup | After human-approved discard (Step 4–6) |
|-----------------|----------------|----------------------------------------|
| `DIRTY_CORE_CLEANED` | **false** | **true** (if only these hunks were the blocker) |
| `DIRTY_SERVER_CLEANED` | **false** | **true** (if only these hunks were the blocker) |

Discarding dirty files does **not** by itself enable limited live mode. Remaining blockers (live executor, approval route, harmless smoke, test classification) stay in place.

---

## 11. Explicit next recommendation

1. **Human review** this plan and [`DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md).
2. **Approve discard** of both quarantined files (§8).
3. **Verify** Safe Observer + smoke on clean tree.
4. **Document rejection** in a follow-up commit.
5. **Then** proceed to Branch B (pytest classification) or design-only Branches C/D/E — **not** before Step 3.

**Do not enable autonomy. Do not adopt dirty hunks. Do not wire dirty server routes.**

---

## 12. Verifier checklist (this plan commit)

After committing **only** `docs/DIRTY_HUNKS_CLEANUP_PLAN.md`:

| Check | Expected |
|-------|----------|
| `project_guardian/core.py` staged? | **No** |
| `elysia/api/server.py` staged? | **No** |
| `project_guardian/core.py` still dirty/unstaged? | **Yes** |
| `elysia/api/server.py` still dirty/unstaged? | **Yes** |
| `config/autonomy.json` unchanged (`enabled=false`)? | **Yes** |
| Safe Observer passes? | **Yes** |
| Safe-stack smoke passes? | **Yes** |

**This document does not enable live execution or autonomy.**
