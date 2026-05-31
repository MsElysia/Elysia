# Dirty risky hunks quarantine — Branch A

**Milestone:** Branch A — dirty risky file cleanup/quarantine  
**Current verified checkpoint:** `e0e6e09` — docs(startup): record storage fallback baseline  
**Date recorded:** 2026-05-30  
**Scope:** Documentation/triage only. Inspected dirty hunks; **not staged**, **not committed**, **not modified**.

Prior detail docs (still valid references): [`CORE_UNSTAGED_RISKY_HUNKS.md`](CORE_UNSTAGED_RISKY_HUNKS.md), [`SERVER_UNSTAGED_RISKY_HUNKS.md`](SERVER_UNSTAGED_RISKY_HUNKS.md), [`DIRTY_HUNK_TRIAGE_PHASE1D_A.md`](DIRTY_HUNK_TRIAGE_PHASE1D_A.md).

---

## Explicit decision (this milestone)

| Decision | Status |
|----------|--------|
| Stage `project_guardian/core.py` | **No** |
| Commit `project_guardian/core.py` | **No** |
| Stage `elysia/api/server.py` | **No** |
| Commit `elysia/api/server.py` | **No** |
| Commit only this quarantine document | **Yes** |

Dirty worktree hunks are **not** proof of committed safety. Verified gates use **clean HEAD** (`e0e6e09`) plus Safe Observer / safe-stack smoke.

---

## Files under quarantine

| File | Git status vs `e0e6e09` | Diff stat |
|------|-------------------------|-----------|
| `project_guardian/core.py` | Modified, **unstaged** | +180 / −9 (~189 lines touched) |
| `elysia/api/server.py` | Modified, **unstaged** | +108 / −20 (~128 lines touched) |

```powershell
git diff --cached --name-only
# expect: empty (no core.py / server.py)

git diff --stat -- project_guardian/core.py elysia/api/server.py
# project_guardian/core.py  | 189 ++++++++++++++++---
# elysia/api/server.py      | 128 +++++++++++++++++---
```

---

## Safety classification legend

| Label | Meaning |
|-------|---------|
| **SAFE_DOC_ONLY** | Documentation-only; no runtime effect |
| **SAFE_OBSERVABILITY** | Read-only logging/trace intent; still needs dry-run-only wiring review before commit |
| **NEEDS_REVIEW** | Possibly useful maintenance; isolate and test on clean branch |
| **RISKY_AUTONOMY** | Touches autonomy selection, scoring, or legacy executor paths |
| **RISKY_API_SURFACE** | Expands HTTP API toward implement / WebScout / chained side effects |
| **REJECT_OR_REWRITE** | Do not adopt as-is; rewrite behind explicit governance or discard after human approval |

---

## `project_guardian/core.py`

**Dirty status:** Modified, unstaged, **quarantined**  
**Overall recommendation:** **Keep unstaged.** Never adopt as-is. Extract safe observability later on a clean branch; rewrite scoring/legacy hunks; discard only after explicit human approval.

### Hunk groups

| # | Region / symbols | Approx. lines | Classification | Recommendation |
|---|------------------|---------------|----------------|----------------|
| 1 | `_autonomy_decision_trace_enabled`, `_autonomy_trace_identity`, `_autonomy_trace_action_label`, `_autonomy_trace_markers`, `_format_autonomy_candidate_trace`, `_build_autonomy_decision_trace` | ~143 insert | **SAFE_OBSERVABILITY** (intent) / **NEEDS_REVIEW** (placement) | **Extract safe observability later** — rewrite to dry-run-only / audit surfaces per Phase 1d-B design; do not wire into live `_get_next_action_impl` on dirty tree |
| 2 | `_get_next_action_impl` — builds `decision_trace`, `logger.info`, adds `out["decision_trace"]` | ~18 insert | **RISKY_AUTONOMY** | **Rewrite behind explicit dry-run only** — touches live candidate-selection return path; pair with committed `autonomy_dry_run_guard.py` patterns, not wholesale core hunk |
| 3 | `_maybe_collect_chatlog_guidance` — guard `memory.remember` when `items_used > 0` | ~7 changed | **NEEDS_REVIEW** | **Keep unstaged** — unrelated maintenance; isolate PR with test if ever adopted |
| 4 | Self-task candidate path — `arch_select_factor`, `archetype_selection_factor` in metadata, priority scaling via `queue.archetype_multiplier` / `archetype_suppression_factor` | ~12 insert | **RISKY_AUTONOMY** | **Never adopt as-is** — changes autonomy **selection/scoring**; requires unit tests, antiloop/planner review, and explicit allowlist |
| 5 | `run_autonomous_cycle` legacy branch — `harvest_income_report` / `action_meaningful_success` init and assignment | ~3 insert | **RISKY_AUTONOMY** | **Discard later only after human approval** — legacy executor path bypassed by Phase 1 dry-run guard while `enabled=false`; risky if legacy re-enabled |

### Summary

| Bucket | Count | Notes |
|--------|-------|-------|
| Observability (groups 1–2) | 2 | Useful ideas already partially superseded by committed `project_guardian/autonomy_dry_run_guard.py` + Safe Observer command |
| Scoring / legacy (groups 4–5) | 2 | High risk; must not mix with safe-stack or startup commits |
| Unrelated maintenance (group 3) | 1 | Low risk but out of scope |

**Why not stage:** ~180 lines mix observability with scoring and legacy executor edits. Local pytest/smoke against dirty tree does **not** certify these hunks. Committed Phase 1 dry-run guards on HEAD do not include this work.

---

## `elysia/api/server.py`

**Dirty status:** Modified, unstaged, **quarantined**  
**Overall recommendation:** **Keep unstaged.** **Never adopt as-is.** Design API/approval surfaces from scratch with governance; do not merge dirty hunks into safe-stack or startup tracks.

### Hunk groups

| # | Region / route | Classification | Recommendation |
|---|----------------|----------------|----------------|
| 6 | `RuntimeAPIServer.__init__` — `auto_implement_on_approval` flag | **RISKY_API_SURFACE** | **Keep unstaged** — global opt-in for chained implementation on approval |
| 7 | `_approval_should_implement`, `_run_implementation` | **RISKY_API_SURFACE** / **REJECT_OR_REWRITE** | **Never adopt as-is** — HTTP-triggered proposal implementation; needs live-execution guard, config gate, tests |
| 8 | `POST /api/proposals/<id>/approve` — attach `response["implementation"]` | **RISKY_API_SURFACE** | **Quarantine** — approval becomes implicit implement trigger |
| 9 | `POST /api/proposals/<id>/status` — on `approved`, chain implementation | **RISKY_API_SURFACE** | **Quarantine** — same as above |
| 10 | `POST /api/proposals/<id>/implement` refactor to `_run_implementation` | **RISKY_API_SURFACE** | **Rewrite behind explicit dry-run only** — centralization OK in principle; needs governance track |
| 11 | **New** `GET|POST /api/proposals/<id>/implementation/preview` | **RISKY_API_SURFACE** | **Quarantine** — preview is dry-run but still proposal-implementation machinery outside safe-stack scope |
| 12 | `POST /api/webscout/research` — `research_options` (`tags`, `check_duplicates`, `implementation_plan`, `max_sources`, `auto_generate_implementation_plan`) | **RISKY_API_SURFACE** | **Never adopt as-is** — WebScout / external research expansion; conflicts with fail-closed posture |

### Summary

| Bucket | Count | Notes |
|--------|-------|-------|
| Proposal auto-implement / chaining | 5 | Conflicts with live-execution governance and safe-stack fail-closed defaults |
| WebScout expansion | 1 | External research surface change |
| Refactor-only (implement route) | 1 | Still part of implementation track |

**Why not stage:** Committed safe-stack server wiring on HEAD excludes these hunks intentionally. Safe-stack smoke does not validate implement/preview/WebScout option matrices.

---

## Safety boundaries (unchanged)

This triage milestone does **not**:

- Enable autonomy (`config/autonomy.json` remains `enabled=false`)
- Enable live execution
- Run real autonomy mode
- Run tools, capabilities, mutation, proposal implementation, WebScout, or browser activity
- Expand API surface
- Use dirty hunks as verification proof

Verified committed behavior remains:

- Safe Observer: `python scripts/run_elysia_dry_run_report.py --mode real-planning`
- Startup storage fallback: `c8cd3d4` / baseline `docs/STARTUP_STORAGE_FALLBACK_BASELINE.md`
- Phase 1 dry-run guards on HEAD when autonomy were enabled (it is not)

---

## Recommended next actions

### After this document

1. **Clean patch plan for `core.py` (optional):** Extract groups 1–2 observability only onto a **clean branch**, wired exclusively through:
   - `project_guardian/autonomy_dry_run_guard.py`
   - Safe Observer / dry-run audit JSONL (opt-in `--write-audit`)
   - **Not** through live `_get_next_action_impl` without explicit dry-run gate

2. **API/server track (separate):** Design proposal approval + implementation governance **from scratch**:
   - Default `dry_run=True`
   - Explicit config + operator confirmation
   - Live-execution guard integration
   - Dedicated pytest; do not adopt dirty `server.py` hunks wholesale

3. **Do not discard dirty files** in this milestone — quarantine only. Reset/stash/discard requires explicit human approval.

### Branch pointers (from startup baseline)

| Branch | Focus |
|--------|-------|
| **A** (continued) | Per-hunk extraction or human-approved discard of quarantined files |
| **B** | Safe Observer user guide |
| **C** | Full runtime pytest failure classification |
| **D** | Phase 2 live-action allowlist design only |

---

## Verification commands (clean HEAD baseline)

```powershell
# Index must not contain quarantined files
git diff --cached --name-only

# Safe Observer (no live execution)
python scripts/run_elysia_dry_run_report.py --mode real-planning

# Safe-stack smoke (does not certify dirty hunks)
python scripts/run_safe_stack_smoke_tests.py
```

---

## Related commits (verified stack)

```
e0e6e09 docs(startup): record storage fallback baseline
c8cd3d4 fix(startup): allow storage fallback during health check
64ff8da docs(autonomy): checkpoint safe observer mode
```
