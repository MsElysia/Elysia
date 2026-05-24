# Safe-stack release readiness audit

**Date:** 2026-05-21  
**Scope:** Worktree hygiene and commit planning for the safe-stack milestone — **no production behavior changes** from this audit.  
**Authoritative milestone doc:** [`ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md`](ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md)  
**Staging plan:** [`SAFE_STACK_COMMIT_STAGING_PLAN.md`](SAFE_STACK_COMMIT_STAGING_PLAN.md)

---

## Executive summary

| Check | Result |
|-------|--------|
| Safe-stack smoke | **385 passed, 3 warnings** (`python scripts/run_safe_stack_smoke_tests.py`) |
| Live execution / autonomy | Disabled defaults; not enabled by smoke |
| Safe-stack code readiness | **Ready** — smoke green; canonical modules present |
| Git release readiness | **Not ready as a single commit** — large mixed worktree; split commits and exclude runtime/generated paths |

The repository worktree mixes **new safe-stack files (mostly untracked)** with **~158 tracked files already modified before/during the milestone**, including substantial unrelated edits (`project_guardian/core.py`, `unified_llm_route.py`, launchers, OpenClaw config, `deployments/`, etc.). Treat safe-stack as a **focused add-on slice** when staging commits.

---

## Smoke / test state

```bash
python scripts/run_safe_stack_smoke_tests.py
```

**Result (verified 2026-05-21):** `385 passed, 3 warnings` in ~6–12s.

- Includes real UI marker tests (`test_control_panel_ui_clarity.py`, `test_control_panel_brain_visibility.py`, …), not one-shot repair scripts.
- Includes `test_one_shot_ui_scripts_quarantined.py` (quarantine guard only).
- Does **not** invoke `scripts/maintenance/one_shot/*` repair scripts.

Full-repo pytest was **not** run (out of scope; worktree has broad unrelated deltas).

---

## Git worktree snapshot

| Metric | Count |
|--------|------:|
| Tracked files with working-tree changes (`git status --short`, non-`??`) | **158** |
| Untracked paths (`git ls-files --others --exclude-standard`) | **743** |
| Tracked diff names (`git diff --name-only`) | **158** (same set as modified tracked) |
| Diff stat (tracked) | **158 files, +22,691 / −2,644 lines** (dominated by `ui_control_panel.py`) |

**Interpretation:** Most safe-stack **modules are new (untracked)**. Only two safe-stack production files are **tracked modifications**: `elysia/api/server.py`, `project_guardian/ui_control_panel.py` (large template/route diff).

---

## Changed file categories

### A. Core safe-stack production code (commit)

**Tracked modifications (2):**

- `elysia/api/server.py` — mirrored safe-stack + governance routes
- `project_guardian/ui_control_panel.py` — `CONTROL_PANEL_TEMPLATE`, routes, operator chat wiring (**largest diff in repo**)

**Untracked new modules (representative — 47 paths in `prod_safe_stack` bucket):**

| Area | Paths |
|------|--------|
| Conversation | `project_guardian/conversation_store.py` |
| Safe-stack helpers | `project_guardian/safe_stack/` (`operator_chat.py`, `responses.py`) |
| Brain / TDA | `project_guardian/brain/` (`config.py`, `pipeline.py`, `runtime.py`, `trace_visibility.py`, `think_decide_act_adapter.py`, `tda_trace_fields.py`, `live_execution_runtime.py`, …) |
| Governance | `project_guardian/governance/` (guard, audit, confirmation store, visibility) |
| Memory ranking | `project_guardian/memory_ranking/` |
| Prompt contracts | `project_guardian/prompt_contracts/` |
| Self-improvement | `project_guardian/self_improvement/` (`proposal_queue.py`, `prompt_export.py`) |

### B. Tests (commit with production)

**Untracked (~26 modules):** conversation store, control panel UI/brain/JS/clarity, API host parity, operator-chat helper integrations, brain/TDA trace, prompt contracts, memory ranking, self-improvement queue/export/legacy retirement, live-execution guard + governance docs, operator confirmation store/guard/visibility, `test_one_shot_ui_scripts_quarantined.py`, safe-stack smoke/CI config tests, etc.

**Tracked test deltas (~23 files):** mostly **unrelated** pre-existing test edits (bounded browser, social intelligence, routing, …) — review before bundling with safe-stack.

### C. Docs (commit)

**Untracked safe-stack docs (~12):**

- `docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md` (source of truth)
- `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md`
- `docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md`, `docs/LIVE_EXECUTION_GOVERNANCE_PLAN.md`
- `docs/OPERATOR_CONFIRMATION_CONTEXT_PLAN.md`
- `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`, `docs/API_HOST_FINAL_CONSOLIDATION_AUDIT.md`
- `docs/CONTROL_PANEL_CONVERSATION_MEMORY.md`, `docs/SELF_IMPROVEMENT_PROPOSAL_QUEUE.md`
- `docs/ELYSIA_SAFE_STACK_AUDIT.md`, `docs/ELYSIA_ARCHITECTURE_AUDIT.md`
- This file: `docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md`

**Tracked doc deltas (unrelated):** `docs/HEALTH_CHECKS.md`, `docs/OPENCLAW_INTEGRATION.md`

### D. Scripts / CI (commit)

| Path | Role |
|------|------|
| `scripts/run_safe_stack_smoke_tests.py` | Smoke driver (untracked) |
| `scripts/maintenance/one_shot/` | Quarantined historical UI repair scripts + README |
| `.github/workflows/safe-stack-smoke.yml` | CI smoke (untracked) |

**Not in smoke/CI:** `scripts/maintenance/one_shot/_*.py` (documented one-shot only).

**Optional local helper (do not commit unless desired):** `scripts/_audit_release_readiness.py` — audit-only; not part of runtime.

### E. Config (commit — safe-stack only)

**Untracked (safe-stack defaults):**

- `config/brain_pipeline.json` — `enabled: false`, `dry_run: true`, live/autonomy entrypoints off
- `config/memory_ranking.json` — `enabled: false`, `allow_delete_proposals: false`

**Tracked config deltas (review — likely unrelated):** `config/autonomy.json`, `config/mission_autonomy.json`, `config/auto_learning.json`, `config/llm_router.yaml`, `config/social_intelligence.json`, OpenClaw/MCP example configs, etc.

### F. Runtime / generated data — **do not commit**

| Pattern | Untracked count (approx.) | Notes |
|---------|---------------------------|--------|
| `data/runtime/` | Many under **429** `runtime_data` paths | Conversations, audits, confirmations, traces |
| `deployments/*/` | Large tree | Slave runtime artifacts |
| `data/context_pipeline/`, `data/prompt_registry/` | Present | Local/generated |
| `REPORTS/review_queue.jsonl` | **Tracked modified** | Should likely stay local |

Examples that must **not** ship:

- `data/runtime/operator_confirmations.jsonl`
- `data/runtime/live_execution_guard_audit.jsonl`
- `data/runtime/conversations/*.jsonl`
- `data/runtime/brain_last_pipeline.json` (if present under `data/runtime/`)
- `deployments/**/slave_runtime.py`, `slave_config.json`, …

### G. Unrelated / pre-existing dirty work (separate commits or defer)

**~101 tracked production files** outside safe-stack prefixes, including:

- `project_guardian/core.py`, `elysia_loop_core.py`, `unified_llm_route.py`, `tool_executor.py`
- Bounded browser, trust registry, self-task portfolio, OpenClaw integration
- `core_modules/elysia_core_comprehensive/*`
- `run_elysia_unified.py`, `elysia/runtime.py`, launchers (`.bat`, `.cmd`, `.ps1`)
- `config/autonomy.json`, `config/mission_autonomy.json`, …

**~64 untracked** non-safe-stack paths (OpenClaw stubs, MCP examples, prompt evolution, etc.).

### H. Risky files needing human review

| Risk | Files / areas |
|------|----------------|
| **Huge UI diff** | `project_guardian/ui_control_panel.py` — verify safe-stack panels only; avoid accidental unrelated dashboard edits |
| **Autonomy config touched** | `config/autonomy.json`, `config/mission_autonomy.json` (modified tracked) — confirm defaults still safe |
| **Implement / execute paths** | `elysia/agents/implementer.py`, `project_guardian/implementer/` (modified) — out of safe-stack; do not mix without review |
| **Tracked runtime report** | `REPORTS/review_queue.jsonl` — local queue data |
| **Secrets** | Ensure no `data/secrets/`, API key files, or `*.encrypted` staged (`.gitignore` covers most) |
| **Accidental LLM enablement** | Review any `config/llm_router.yaml` / `auto_learning.json` diffs separately |

---

## Ignore hygiene

**Status:** Updated. Runtime/generated safe-stack data should **not** be committed.

`.gitignore` uses **directory rules** (no duplicate per-file lines where the tree rule suffices):

| Rule | Covers |
|------|--------|
| `data/runtime/` | Entire runtime tree: `conversations/`, `*.jsonl`, audits, confirmations, `brain_last_pipeline.json`, etc. |
| `data/context_pipeline/`, `data/prompt_registry/` | Pipeline/registry artifacts |
| `deployments/` | Slave deployment output |
| `tmp_*.out`, `tmp_*.err` | Local temp captures |
| `REPORTS/*.json`, `REPORTS/*.jsonl` | Generated report queues |
| `.mypy_cache/`, `.ruff_cache/` | Tool caches |

**Regression:** `project_guardian/tests/test_safe_stack_gitignore.py` (in smoke slice) — static rules plus `git check-ignore` on representative paths.

Verify locally:

```bash
git check-ignore -v data/runtime/operator_confirmations.jsonl
git check-ignore -v data/runtime/conversations/panel.jsonl
git check-ignore -v deployments/some-id/slave_config.json
python -m pytest project_guardian/tests/test_safe_stack_gitignore.py -q
```

---

## Recommended commit grouping

Stage **only** safe-stack paths; leave unrelated 101+ modified files unstaged.

### Commit 1 — `feat(safe-stack): core modules and API hosts`

- `project_guardian/conversation_store.py`
- `project_guardian/safe_stack/**`
- `project_guardian/governance/**`
- `project_guardian/brain/**` (safe-stack subset)
- `project_guardian/memory_ranking/**`
- `project_guardian/prompt_contracts/**`
- `project_guardian/self_improvement/**`
- `elysia/api/server.py`
- `project_guardian/ui_control_panel.py`
- `config/brain_pipeline.json`, `config/memory_ranking.json`

### Commit 2 — `test(safe-stack): smoke slice and guards`

- All `project_guardian/tests/test_*` files listed in smoke script (`scripts/run_safe_stack_smoke_tests.py`)
- Exclude unrelated **tracked** test edits unless intentionally included

### Commit 3 — `docs(safe-stack): checkpoints and operator guides`

- `docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md` and related safe-stack docs
- `docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md`

### Commit 4 — `chore(safe-stack): smoke script, CI, quarantined UI repairs`

- `scripts/run_safe_stack_smoke_tests.py`
- `.github/workflows/safe-stack-smoke.yml`
- `scripts/maintenance/one_shot/**` (README + historical scripts)

### Defer or separate PRs

- Unrelated `project_guardian/core.py`, LLM routing, bounded browser, OpenClaw, launchers
- `.gitignore` (commit with chore/docs if not already on branch)
- Any `config/autonomy.json` changes unless explicitly reviewed

---

## Files to exclude from any safe-stack release commit

- `data/**` (runtime JSONL, conversations, audits, confirmations, traces)
- `deployments/**`
- `REPORTS/*.jsonl` (especially modified `REPORTS/review_queue.jsonl`)
- `.audit_*.txt` or other local audit scratch files
- `scripts/_audit_release_readiness.py` (optional; audit-only)
- `__pycache__/`, `.pytest_cache/`, local logs, `*.log`
- Secrets paths per `.gitignore`

---

## Risks before commit / release

1. **Mixed worktree** — easy to `git add -A` and ship 158 unrelated tracked files + 429 runtime paths.
2. **Accidental `git add -A`** — `.gitignore` hides new runtime/deployments files; still avoid staging tracked `REPORTS/review_queue.jsonl` or unrelated deltas.
3. **`ui_control_panel.py` size** — review diff for safe-stack-only intent.
4. **New files untracked** — safe-stack will **not** exist on remote until explicitly `git add`’d.
5. **Config drift** — only commit `brain_pipeline.json` / `memory_ranking.json` for safe-stack; isolate other config changes.

---

## Recommended next action

1. ~~Extend `.gitignore` for `data/runtime/**` and `deployments/`~~ — **Done** (see `.gitignore`).
2. Stage **Commit 1–4** paths explicitly (`git add` path list from sections above).
3. Re-run `python scripts/run_safe_stack_smoke_tests.py` before push (expect **385 passed**).
4. Open PR titled **Safe-stack milestone** with link to `ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md`; note live execution remains off.
5. Leave unrelated 101 modified tracked files for separate PRs or `git stash` / branch split.

---

## Production code changed by this audit?

**No.** Only documentation (`docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md`) and optional local audit helper under `scripts/_audit_release_readiness.py`.

---

## References

- Final checkpoint: [`docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md`](ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md)
- One-shot scripts: [`scripts/maintenance/one_shot/README.md`](../scripts/maintenance/one_shot/README.md)
- Smoke driver: [`scripts/run_safe_stack_smoke_tests.py`](../scripts/run_safe_stack_smoke_tests.py)
