# Dirty hunk triage — Phase 1d Branch A

**Date:** 2026-05-28  
**Current verified HEAD:** `9804f2c` — `docs(autonomy): record phase one checkpoint`  
**Scope:** Documentation/triage only. `project_guardian/core.py` and `elysia/api/server.py` were **inspected but not staged**.

**Safety note:** No autonomy was enabled, no live execution was run, and no real autonomy mode was exercised during this triage.

---

## Inspection summary

| File | Diff vs HEAD | Status |
|------|--------------|--------|
| `project_guardian/core.py` | 189 lines changed (+180 / −9) | Dirty, unstaged |
| `elysia/api/server.py` | 128 lines changed (+108 / −20) | Dirty, unstaged |

Prior quarantine docs: [`CORE_UNSTAGED_RISKY_HUNKS.md`](CORE_UNSTAGED_RISKY_HUNKS.md), [`SERVER_UNSTAGED_RISKY_HUNKS.md`](SERVER_UNSTAGED_RISKY_HUNKS.md).

---

## Hunk group summary table

| # | File | Section / symbols | Appears to do | Category | Risk | Why | Recommended action |
|---|------|-------------------|---------------|----------|------|-----|------------------|
| 1 | `project_guardian/core.py` | `_autonomy_decision_trace_enabled`, `_autonomy_trace_*`, `_build_autonomy_decision_trace` (~L2054–2197) | Adds env/config-gated autonomy candidate decision trace formatting (winner, runner, top-N, mistral/planner fields) | **B** | **medium** | Observability-only intent, but lives on `GuardianCore` selection path and expands log/output surface without Phase 1 audit JSONL review | **Rewrite as dry-run-only** on a clean branch; wire to Phase 1 audit/report surfaces (Branch B); do not stage wholesale |
| 2 | `project_guardian/core.py` | `_get_next_action_impl` — `decision_trace`, `logger.info`, `out["decision_trace"]` (~L3475–3564) | Emits trace on every next-action pick when enabled; attaches trace string to returned dict | **B** | **medium** | Touches live candidate-selection return path; local smoke may pass against dirty tree while committed HEAD does not include this | **Keep for later split** after separate verification; pair with dry-run audit only |
| 3 | `project_guardian/core.py` | `_maybe_collect_chatlog_guidance` — guard `memory.remember` on `items_used > 0` (~L3998–4007) | Skips memory write when chatlog guidance used zero items | **D** | **low** | Unrelated autonomy maintenance; reduces empty guidance memory noise | **Investigate** on isolated PR with explicit test; safe to defer |
| 4 | `project_guardian/core.py` | Self-task candidate path — `arch_select_factor`, `archetype_selection_factor` metadata (~L5701–5726) | Applies queue archetype multiplier/suppression to self-task priority; records factor in metadata | **C** | **high** | Changes autonomy **selection/scoring** behavior, not observability; affects which action wins | **Quarantine**; rewrite with unit tests and antiloop/planner review before any commit |
| 5 | `project_guardian/core.py` | `run_autonomous_cycle` legacy branch — `harvest_income_report` / `action_meaningful_success` (~L6481–6506) | Initializes and sets meaningful-success flag for harvest income report in **legacy executor** | **C** | **high** | Modifies legacy executor path below Phase 1 dry-run return; irrelevant while Phase 1 guard holds, risky if legacy re-enabled | **Quarantine**; defer until post-Phase 4 legacy policy is explicit |
| 6 | `elysia/api/server.py` | `RuntimeAPIServer.__init__` — `auto_implement_on_approval` (~L49–61) | Server-level flag to auto-chain implementation after approval | **C** | **high** | Expands proposal **implementation** surface; conflicts with fail-closed safe-stack posture | **Quarantine**; do not stage |
| 7 | `elysia/api/server.py` | `_approval_should_implement`, `_run_implementation` (~L82–128) | Request/server-gated implementer invocation; emits `implementation_triggered` event | **C** | **high** | Direct **proposal implementation** execution path via HTTP layer | **Quarantine**; requires governance review before any merge |
| 8 | `elysia/api/server.py` | `POST .../approve`, `POST .../status` — attach `response["implementation"]` (~L642–686) | Chains implementer run on approval or approved status transition | **C** | **high** | Approval becomes implicit implement trigger | **Quarantine**; separate from safe-stack |
| 9 | `elysia/api/server.py` | `POST .../implement` refactor + new `.../implementation/preview` (~L746–757) | Centralizes implement route; adds preview endpoint (`dry_run=True`) | **C** | **high** | Expands implement/preview API; preview is dry-run but still proposal-implementation machinery | **Quarantine**; design-only review first (Branch D) |
| 10 | `elysia/api/server.py` | `POST /api/webscout/research` — `research_options` expansion (~L700–733) | Passes tags, duplicates check, implementation_plan, max_sources, auto_generate_implementation_plan to WebScout | **C** | **high** | **WebScout** / external research behavior change outside safe-stack scope | **Quarantine**; do not mix with autonomy work |

### Category legend

| Cat | Meaning |
|-----|---------|
| **A** | Potentially safe observability only |
| **B** | Potentially useful but needs rewrite before commit |
| **C** | Risky autonomy / live execution / proposal implementation / WebScout / browser / mutation |
| **D** | Legacy cleanup or unrelated maintenance |
| **E** | Unknown / needs deeper review |

**Counts:** A=0 committed-as-is, B=2, C=7, D=1, E=0 (all hunks identified).

---

## Explicit warnings

- **Do not stage `project_guardian/core.py` or `elysia/api/server.py` casually** — use `git add -p` only after per-hunk re-review, or split onto dedicated branches.
- **Do not use `git add -A`** — broader dirty worktree may contain unrelated files.
- Local safe-stack smoke passing does **not** certify these hunks; committed HEAD (`9804f2c`) is the sign-off baseline.

---

## Recommended next step

1. **Prefer Branch A continuation or Branch B (dry-run observability)** before any repeated dry-run autonomy cycle.
2. **Split safe observability hunks** (core groups 1–2) onto a clean branch only after:
   - separate contract/smoke verification on clean checkout
   - explicit dry-run-only wiring to audit JSONL / report surfaces
   - no mixing with groups 4–5 or server groups 6–10
3. **Keep groups 4–5 and all server hunks quarantined** until governance and test plans exist.

---

## Current gates (unchanged by this doc)

| Gate | Status |
|------|--------|
| Safe-stack smoke | 408 passed, 3 warnings |
| Full pytest collection | Succeeds (see `docs/PHASE1C2_COLLECTION_REPAIR_BASELINE.md`) |
| Full runtime pytest | Not passing; out of scope |
| `config/autonomy.json` | `enabled=false` |
| Phase 1 autonomy | Dry-run only; `dry_run_only:false` ignored/blocked |
| Live execution | Not enabled; not run |
| Real autonomy | Not run |

---

## Verifier takeaway

| Check | Result |
|-------|--------|
| Production code changed by this triage | **No** — documentation only |
| `core.py` staged | **No** |
| `server.py` staged | **No** |
| Autonomy enabled | **No** |
| Live execution run | **No** |
