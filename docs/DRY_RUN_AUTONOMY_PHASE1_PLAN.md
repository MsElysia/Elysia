# Phase 1: Dry-Run Autonomy Guard Plan

**Date:** 2026-05-25  
**Role:** Committer-side planner/auditor (documentation only — no production wiring in this pass)  
**Prerequisites:** Safe-stack milestone committed; autonomy audit `893ebd8`; Phase 0 config `14a5fbe` (`config/autonomy.json` **`enabled: false`**)  
**Smoke baseline:** 386 passed (`python scripts/run_safe_stack_smoke_tests.py`)  
**Related:** [`AUTONOMY_ENTRYPOINT_AUDIT.md`](AUTONOMY_ENTRYPOINT_AUDIT.md), [`LIVE_EXECUTION_GOVERNANCE_PLAN.md`](LIVE_EXECUTION_GOVERNANCE_PLAN.md)

---

## A. Objective

Introduce **dry-run-only autonomy** with **no side effects**: every autonomy invocation produces a **bounded, auditable trace** (proposed action + BrainPipeline/TDA metadata + live-execution guard decision) and **stops after one cycle** without executing tools, capabilities, mutations, proposal implementation, subprocess/shell, or unattended loops.

Phase 1 is **guard design + tests-first**; runtime wiring lands in Phase 1b–1c only after tests pass. Operators may later set `config/autonomy.json` `enabled: true` for experiments, but Phase 1 code must **still force dry-run** and deny live execution via `live_execution_guard`.

---

## B. Non-goals

| Non-goal | Rationale |
|----------|-----------|
| Live execution | Autonomy context is permanently denied by guard until a later phased rollout |
| Tool / capability execution | No `execute_capability_kind`, `tool_executor.execute_action`, or dynamic `use_capability/*` in Phase 1 |
| File / repo mutation | No `consider_mutation`, Implementer, or mutation publisher paths from autonomy |
| Proposal implementation | No `ImplementerAgent.run_for_proposal`, auto-implement on approval, or architect implementation apply |
| Real autonomy loops | Heartbeat and UI must not chain cycles; one bounded dry-run per explicit trigger |
| Subprocess / shell | No `subprocess.run`, PowerShell acceptance, or pytest from autonomy paths |
| Config enablement by default | Repo ships `enabled: false` (Phase 0); Phase 1 must not flip defaults |
| Wiring `entrypoints.autonomy: true` for live Brain runs | Entrypoint may be enabled only for **trace-only** dry-run after tests |
| Real LLM / external API calls in Phase 1 tests | Tests use mocks/stubs; no network in CI for this slice |

---

## C. Required design

### C.1 Gate order (fail-closed, first line of every autonomy path)

Every guarded entrypoint must evaluate **in this order** before `get_next_action` or any executor:

1. **Kill switch** — env `ELYSIA_AUTONOMY_KILL=1` and/or repo-local flag file (e.g. `data/runtime/autonomy_kill.switch`); return `{ executed: false, dry_run: true, reason: "kill_switch" }`.
2. **`config/autonomy.json` → `enabled`** — if `false`, return immediately (current `run_autonomous_cycle` behavior; preserve).
3. **Phase 1 dry-run flag** — `config/autonomy.json` → `dry_run_only: true` (new key, default `true` in Phase 1b) **or** hard-coded Phase 1 mode when `ELYSIA_AUTONOMY_PHASE1_DRY_RUN=1`; never honor `executed: true` in Phase 1.
4. **Loop budget** — `max_actions_per_hour`, antiloop factors (`autonomy_antiloop.py`), per-request cycle cap (`max_cycles_per_request: 1`).
5. **Brain + guard** — then propose action only.

### C.2 BrainPipeline / TDA trace

Add a dedicated wrapper (name TBD in implementation):

```text
run_brain_pipeline_for_autonomy_event(next_action_snapshot, *, guardian, context)
  → run_brain_pipeline_for_operator_event(..., source_entrypoint="autonomy", context={...})
```

**Context requirements:**

| Field | Value |
|-------|--------|
| `source_entrypoint` | `"autonomy"` |
| `dry_run` | `true` (forced; cannot be overridden) |
| `autonomy_context` / `is_autonomy_context` | `true` |
| `persist_trace` | per `config/brain_pipeline.json` |
| `cycle_id` | UUID per bounded cycle |

**Config interaction:**

- `config/brain_pipeline.json`: `entrypoints.autonomy` remains **`false`** until Phase 1c sign-off; when enabled for trace-only, pairing with `dry_run: true` globally.
- Even if operator sets `config/autonomy.json` `enabled: true`, Phase 1 wrapper **forces** dry-run and does not call legacy executors.

### C.3 Live execution guard

Call `apply_live_execution_guard_to_context` (via brain runtime) with:

- `source_entrypoint="autonomy"`
- `is_autonomy_context=True` / `autonomy_context=True`

**Expected:** `AUTONOMY_CONTEXT_DENIED` in guard reasons; `dry_run` forced `true` (see `test_autonomy_context_cannot_enable_live_execution` in `test_live_execution_guard_runtime_integration.py`).

No path may set `live_execution_requested: true` or `dry_run: false` from autonomy.

### C.4 Audit trace object

Each bounded cycle appends one JSON object (JSONL recommended: `data/runtime/autonomy_dry_run_audit.jsonl`):

```json
{
  "cycle_id": "...",
  "timestamp": "ISO-8601",
  "source": "heartbeat|execute-cycle|manual",
  "config_enabled": false,
  "dry_run_only": true,
  "proposed_action": "...",
  "can_auto_execute": false,
  "executed": false,
  "brain_trace_id": "...",
  "live_execution_guard": { "allowed": false, "reasons": ["autonomy_context_denied", "..."] },
  "budget": { "max_actions_per_hour": 40, "actions_this_hour": 0 },
  "kill_switch_active": false
}
```

### C.5 Return contract (Phase 1)

`run_autonomous_cycle` / `POST /api/autonomy/execute-cycle` return shape:

```json
{
  "success": true,
  "dry_run": true,
  "executed": false,
  "action": "<proposed>",
  "reason": "dry_run_only",
  "trace_id": "...",
  "guard_reasons": ["autonomy_context_denied"]
}
```

**Stop after one bounded cycle** — no internal re-entry, no queue drain, no second `get_next_action` execution pass.

### C.6 Proposed action only

`get_next_action` may still run for **selection/logging** in Phase 1b under mock, but Phase 1c **`run_autonomous_cycle` must not branch** into:

- `execute_capability_kind` / `use_capability/*`
- `_run_self_generated_task`
- `delegate_to_openclaw`
- `consider_mutation` / learning / dream side-effect handlers
- `tool_executor.execute_action`

Existing code paths (today) perform real execution when `enabled: true` and `can_auto_execute` — Phase 1 wrapper **short-circuits before** those branches.

---

## D. Entry points to guard in Phase 1

Exact surfaces from audit + verification (2026-05-25):

| # | File | Symbol / route | Phase 1 guard action |
|---|------|----------------|----------------------|
| 1 | `project_guardian/core.py` | `GuardianCore.run_autonomous_cycle()` | Top-of-function kill switch + dry-run wrapper; skip all executors; emit audit; single cycle |
| 2 | `project_guardian/core.py` | `GuardianCore.get_next_action()` / `_get_next_action_impl()` | Optional: trace-only mode flag; **no** auto-execute side effects when called from dry-run wrapper |
| 3 | `project_guardian/monitoring.py` | Heartbeat `_beat` (lines ~375–387) | If `cfg.enabled`, call **dry-run wrapper only** (Phase 1c); Phase 1a–b: treat as no-op when `dry_run_only` |
| 4 | `project_guardian/monitoring.py` | `_run_first_autonomy()` startup thread (~604–615) | Same as heartbeat — must not run real cycle in Phase 1 |
| 5 | `project_guardian/ui_control_panel.py` | `POST /api/autonomy/execute-cycle` → `execute_autonomy_cycle()` | Route through dry-run wrapper; response `executed: false`, `dry_run: true` |
| 6 | `project_guardian/ui_control_panel.py` | `POST /api/autonomy` → `set_autonomy()` | Document: enabling config does **not** enable execution in Phase 1; require explicit Phase 4 sign-off for live |
| 7 | `project_guardian/ui_control_panel.py` | `GET /api/autonomy` | Read-only; surface `dry_run_only` + last audit summary |
| 8 | `project_guardian/ui_control_panel.py` | `GET /api/next-action` → `get_next_action()` | Phase 1: label responses `dry_run_hint: true`; block execute button wiring to real executors |
| 9 | `project_guardian/ui_control_panel.py` | JS `executeNextAction()` / `suggestNextAction()` | Phase 1d: only call dry-run execute-cycle; disable learning/dream direct POST branches when Phase 1 flag on |
| 10 | `project_guardian/api_server.py` | `POST /api/tasks` → `submit_task()` | Deny enqueue when `function` resolves to mutation/implementer/tool roots without guard (allowlist Phase 1+) |
| 11 | `project_guardian/api_server.py` | `_resolve_task_callable` / `_task_resolution_roots` | Static denylist: `mutation_router`, `mutation_engine`, `implementer_core`, `tool_executor`, `run_autonomous_cycle` |
| 12 | `elysia/api/server.py` | `POST /api/proposals/<id>/implement` | Out of autonomy loop but **inventory**: must not be reachable from autonomy context |
| 13 | `elysia/api/server.py` | `_run_implementation` / approval auto-implement | Same — blocked from autonomy trace callbacks |
| 14 | `project_guardian/proposal_api.py` | `POST .../implementation`, `.../approve` | Alternate host — production profile should not expose alongside autonomy |
| 15 | `elysia/agents/implementer.py` | `ImplementerAgent.run_for_proposal()` | Deny from autonomy; subprocess pytest path gated separately |
| 16 | `project_guardian/ui/app.py` | `POST /control/run-acceptance` | Not autonomy but **execution-adjacent**: block or require operator gate before Phase 4 |
| 17 | `elysia.py` | `_autonomy_llm_completion`, `require_autonomy_safe_reasoning` | Phase 1 dry-run should **mock** LLM in tests; runtime wrapper avoids new LLM calls in dry-run cycle |
| 18 | `project_guardian/brain/runtime.py` | `run_brain_pipeline_for_operator_event` | Extend or sibling `..._autonomy_event` with `source_entrypoint="autonomy"` |
| 19 | `project_guardian/brain/live_execution_runtime.py` | `apply_live_execution_guard_to_context` | Already supports autonomy context denial — **must be called** from new autonomy wrapper |
| 20 | `project_guardian/governance/live_execution_guard.py` | `evaluate_live_execution_request` | Policy reference; `AUTONOMY_CONTEXT_DENIED` |

**Out of scope for Phase 1 wiring (document + test only):** `scripts/harness_upstream_routing_task_type_emitters.py`, `diagnostics/upstream_routing_live_probe.py`, `Elysia_Control_Panel_Standalone.html`.

---

## E. Required tests before implementation

Tests are listed in implementation order; Phase 1a lands these as **xfail or skip** until Phase 1b wiring exists.

| Test (proposed name) | Intent | Phase |
|----------------------|--------|-------|
| `test_autonomy_config_defaults_disabled` | Committed `config/autonomy.json` has `enabled: false` | 1a |
| `test_autonomy_config_dry_run_only_default_true` | New key defaults true when added | 1b |
| `test_execute_cycle_returns_dry_run_proposal_only` | `POST /api/autonomy/execute-cycle` → `executed: false`, `dry_run: true`, proposed `action` set | 1c |
| `test_run_autonomous_cycle_cannot_call_execute_capability` | Patch/spy `execute_capability_kind` — not called in dry-run mode | 1c |
| `test_run_autonomous_cycle_denies_mutation_path` | `consider_mutation` branch not entered | 1c |
| `test_proposal_implement_denied_from_autonomy` | No `run_for_proposal` from cycle or autonomy context | 1c |
| `test_autonomy_subprocess_shell_denied` | No `subprocess` from guarded cycle | 1c |
| `test_live_execution_guard_called_with_autonomy_context_true` | Guard metadata present; `autonomy_context_denied` | 1b |
| `test_autonomy_audit_record_written` | JSONL append per cycle | 1c |
| `test_loop_budget_enforced` | `max_actions_per_hour` + single cycle cap | 1c |
| `test_kill_switch_prevents_cycle` | Env/file kill → immediate noop | 1b |
| `test_heartbeat_skips_real_cycle_when_dry_run_only` | Monitoring calls wrapper only | 1c |
| `test_api_tasks_denies_mutation_implementer_roots` | `POST /api/tasks` reject sensitive callables | 1b+ |
| `test_run_acceptance_requires_operator_gate` | FastAPI acceptance blocked or dry-run (adjacent) | 2+ |
| `test_safe_stack_smoke_still_passes` | Full smoke gate unchanged | every phase |

**Existing tests to extend:** `test_autonomy_loop_guards.py`, `test_autonomy_safe_fallback.py`, `test_live_execution_guard.py`, `test_live_execution_guard_runtime_integration.py` (`test_autonomy_context_cannot_enable_live_execution`).

---

## F. Implementation phases

| Phase | Deliverable | Autonomy runs? | Side effects? |
|-------|-------------|----------------|---------------|
| **1a** | This plan + audit link + **tests/documentation only** (xfail/skipped tests describing contract) | No | No |
| **1b** | Guard wrappers in `core.py` / monitoring: kill switch, dry-run short-circuit, brain+guard call, audit writer — **`enabled` stays false** | No (noop if disabled) | No |
| **1c** | `POST /api/autonomy/execute-cycle` returns dry-run trace; heartbeat uses wrapper; **still `dry_run_only: true`** | Trace only | No |
| **1d** | UI copy: **“Dry-run autonomy preview”**; hide/disable Execute for live paths; show last audit snippet | Preview only | No |

**Phase 2+ (not Phase 1):** guarded recommendations, single allowlisted low-risk action, operator confirmation — see audit §F.

---

## G. Rollback plan

1. Revert Phase 1 commits in reverse order (1d → 1a).
2. Confirm `config/autonomy.json` remains `"enabled": false` (Phase 0 commit `14a5fbe` unchanged).
3. Remove `data/runtime/autonomy_dry_run_audit.jsonl` if created (runtime artifact, gitignored).
4. Run `python scripts/run_safe_stack_smoke_tests.py` — expect 386 passed.
5. No DB migrations or state mutation expected from dry-run-only paths.

---

## H. Verdict

**Do not run autonomy until Phase 1 tests pass.**

| Check | Status (2026-05-25) |
|-------|---------------------|
| Phase 0: `enabled: false` default | **Done** (`14a5fbe`) |
| Legacy entrypoints route through Brain + guard | **Not done** |
| Dry-run-only cycle contract | **Planned** (this doc) |
| Phase 1 tests in CI | **Not done** |
| Safe to run autonomy mode? | **No** |

Safe-stack operator chat / read-only panels remain valid; they do **not** certify autonomy safety.

---

## Verification (planning pass)

```text
python scripts/run_safe_stack_smoke_tests.py
→ run after doc updates (2026-05-25)
```

**Production code changed by this planning pass:** **No** — documentation only.
