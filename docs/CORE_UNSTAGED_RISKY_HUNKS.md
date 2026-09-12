# Unstaged risky hunks — `project_guardian/core.py`

**Date:** 2026-05-25  
**Purpose:** Quarantine local `core.py` work so it is not accidentally mixed into autonomy Phase 1 or safe-stack commits.  
**Related:** [`DRY_RUN_AUTONOMY_PHASE1_PLAN.md`](DRY_RUN_AUTONOMY_PHASE1_PLAN.md), [`AUTONOMY_ENTRYPOINT_AUDIT.md`](AUTONOMY_ENTRYPOINT_AUDIT.md), [`SERVER_UNSTAGED_RISKY_HUNKS.md`](SERVER_UNSTAGED_RISKY_HUNKS.md)

---

## A. Latest commit hash (Phase 1b.1 baseline)

| Item | Value |
|------|--------|
| **HEAD** | `5f2b8f6` — `fix(autonomy): keep phase one dry-run non-overridable` |
| **Prior autonomy guard** | `65bc31d` — `feat(autonomy): add dry-run guard wrappers` |
| **Phase 1 dry-run contract tests** | `c67ce61` — `test(autonomy): define dry-run autonomy safety contract` |

Committed Phase 1 behavior on `HEAD`:

- `config/autonomy.json` defaults to **`enabled: false`** (`14a5fbe`)
- Enabled autonomy cycles route through `run_autonomous_phase1_dry_run` only
- `autonomy_dry_run_only()` is **non-overridable** in Phase 1 (`dry_run_only: false` ignored)
- Legacy executor in `run_autonomous_cycle` is unreachable when `enabled: true`

---

## B. Current `core.py` unstaged diff stat

| Item | Value |
|------|--------|
| **File** | `project_guardian/core.py` |
| **Status** | Modified in working tree; **not** in index |
| **Diff vs HEAD (`5f2b8f6`)** | **189 lines changed** — **180 insertions**, **9 deletions** |
| **Index** | Empty — nothing staged |

```powershell
git diff --name-only -- project_guardian/core.py
# project_guardian/core.py

git diff --stat -- project_guardian/core.py
# 1 file changed, 180 insertions(+), 9 deletions(-)
```

**Important:** Local pytest/smoke runs may execute against this **dirty** working tree. CI and clean-checkout verification use **committed** `HEAD` only unless otherwise noted.

---

## C. Classification of remaining hunks

| # | Region / symbols | Lines (approx.) | Classification | Notes |
|---|------------------|-----------------|----------------|-------|
| 1 | `_autonomy_decision_trace_enabled`, `_autonomy_trace_*`, `_build_autonomy_decision_trace` | ~143 insertions | **Autonomy decision trace** | New logging/format helpers for candidate selection visibility |
| 2 | `_get_next_action_impl` wiring: `decision_trace`, `logger.info`, `out["decision_trace"]` | ~18 insertions | **Autonomy decision trace** | Emits trace on every next-action pick when enabled |
| 3 | `_maybe_collect_chatlog_guidance` — guard `memory.remember` on `items_used > 0` | ~7 lines changed | **Unrelated runtime change** | Reduces memory writes when chatlog guidance is empty |
| 4 | Self-task candidate path — `arch_select_factor`, `archetype_selection_factor` metadata | ~12 insertions | **Autonomy planner / candidate scoring** | Adjusts self-task priority from queue archetype multipliers |
| 5 | `run_autonomous_cycle` `harvest_income_report` — `action_meaningful_success` init/fix | ~3 insertions | **Legacy executor behavior** (dead path on HEAD when enabled) | Touches legacy branch below Phase 1 dry-run return; not active while Phase 1 guard holds |

### Summary buckets

| Bucket | Included? | Risk if staged accidentally |
|--------|-----------|------------------------------|
| **Autonomy decision trace** | Yes (majority) | Expands autonomy observability without Phase 1 guard review; mixes with safe-stack commits |
| **Unrelated runtime changes** | Yes (chatlog, harvest) | Behavior changes outside Phase 1b.1 scope |
| **Safe-stack adjacent** | No | No ConversationStore / brain pipeline / operator chat changes |
| **Risky / do-not-stage** | Partial | Trace + scoring changes affect autonomy selection paths; not fail-closed guard work |
| **Unknown** | No | All hunks identified |

---

## D. Part of Phase 1b.1?

**No.**

Phase 1b.1 (`5f2b8f6`) committed only:

- `autonomy_dry_run_only()` always returns `True` (ignore `dry_run_only: false`)
- `run_autonomous_cycle` unconditional dry-run return after `enabled` gate (+4/−3 lines on `HEAD` `core.py`)

None of the unstaged hunks above were in that commit. They pre-existed in the local worktree and were **explicitly excluded** when staging `core.py` from `HEAD` for `65bc31d` / `5f2b8f6`.

---

## E. Why they must not be staged accidentally

| Reason | Detail |
|--------|--------|
| **Mixed-commit hazard** | `git add project_guardian/core.py` without `-p` pulls ~180 lines of trace/scoring work into autonomy or safe-stack PRs |
| **False test confidence** | Smoke/contract tests passing locally do **not** prove these hunks are reviewed or committed |
| **Scope creep** | Decision trace is **Phase 1c+ / autonomy observability**, not Phase 1b dry-run guard |
| **Legacy path edits** | Harvest meaningful-success tweak modifies legacy executor code that Phase 1 intentionally bypasses |
| **No config/guard pairing** | Trace helpers do not add BrainPipeline, `live_execution_guard`, or audit JSONL required by Phase 1 plan |

---

## F. How to verify they remain unstaged

Before any autonomy or safe-stack commit:

```powershell
git diff --cached --name-only
# expect empty (or no project_guardian/core.py)

git diff --name-only -- project_guardian/core.py
# expect: project_guardian/core.py  (until quarantined or committed separately)

git diff --stat -- project_guardian/core.py
# expect: ~180 insertions vs 5f2b8f6 until resolved
```

Clean-checkout verification (committed Phase 1 only):

```powershell
git stash push -m "core trace quarantine" -- project_guardian/core.py
python -m pytest project_guardian/tests/test_dry_run_autonomy_phase1_contract.py -q
python scripts/run_safe_stack_smoke_tests.py
git stash pop
```

---

## G. Recommended future track

| Track | Suggested scope | Separate from |
|-------|-----------------|---------------|
| **Autonomy decision trace design** | Review trace format, env gate (`ELYSIA_AUTONOMY_DECISION_TRACE`), PII/log volume; wire to Phase 1 audit JSONL or brain trace | Safe-stack milestone |
| **Self-task archetype scoring** | Unit tests for `arch_select_factor`; document interaction with antiloop / planner_readiness | Phase 1b guard commits |
| **Chatlog guidance memory gate** | Small behavior PR with explicit test | Autonomy guard |
| **Harvest meaningful-success** | Only relevant if legacy executor re-enabled post-Phase 4; otherwise defer | Phase 1 dry-run |

Do **not** bundle these with Phase 1c UI label work or safe-stack doc/test commits.

---

## H. Safety note

| Statement | Status |
|-----------|--------|
| Committed Phase 1 dry-run non-overridable behavior | **In HEAD (`5f2b8f6`)** |
| Remaining dirty hunks required for committed contract tests | **No** — tests pass on clean `HEAD` + guard module |
| Autonomy enabled by default | **No** — `config/autonomy.json` `enabled: false` unchanged |
| Live execution enabled | **No** |
| Dirty hunks enable legacy executor when autonomy re-enabled | **No** — Phase 1 return still runs first on `HEAD`; dirty hunks only add logging/scoring inside `get_next_action` and dead legacy branches |

**Verifier takeaway:** Treat this worktree as **HEAD + local experiment**. For release/sign-off, re-run contract + smoke from a clean checkout or after stashing `core.py`.

---

## Verification (audit pass)

```text
git log -1 --oneline
→ 5f2b8f6 fix(autonomy): keep phase one dry-run non-overridable

git diff --stat -- project_guardian/core.py
→ 1 file changed, 180 insertions(+), 9 deletions(-)
```

**Production code changed by this audit pass:** **No** — documentation only.
