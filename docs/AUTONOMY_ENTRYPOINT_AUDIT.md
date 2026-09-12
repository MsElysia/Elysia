# Autonomy Entrypoint & Execution-Capable Path Audit

**Date:** 2026-05-25 (updated after Phase 0 config + Phase 1 plan)  
**Role:** Committer-side auditor (read-only; no config/code changes in this pass)  
**Safe-stack baseline:** `aea5f8b` (`docs(safe-stack): add final post-commit audit`) — smoke **386 passed**  
**Phase 0 config:** `14a5fbe` — `config/autonomy.json` defaults to **`"enabled": false`**  
**Phase 1 plan:** [`DRY_RUN_AUTONOMY_PHASE1_PLAN.md`](DRY_RUN_AUTONOMY_PHASE1_PLAN.md) — dry-run guard design (tests-first; no wiring in plan pass)  
**Verdict:** **Do not run autonomy mode yet.**  
Safe dry-run autonomy must **not** be attempted until Phase 1 tests pass **and** all autonomy/execution entrypoints route through **BrainPipeline/TDA + `live_execution_guard`**.

---

## A. Executive summary

### Is autonomy safe to run now?

**No — not yet.**

The safe-stack milestone (`1ada6e8` … `aea5f8b`) governs **operator-facing dry-run surfaces**: ConversationStore chat, read-only diagnostics, fail-closed `live_execution_guard` on **BrainPipeline** entrypoints (`operator_chat`, etc.), and governance GET APIs. It does **not** wrap the legacy **Guardian autonomy loop** (`run_autonomous_cycle`, heartbeat scheduling, control-panel execute-cycle).

**Critical separation:**

| Layer | Governed by safe-stack? | Default posture |
|-------|-------------------------|-----------------|
| `config/brain_pipeline.json` | **Yes** (committed) | `enabled: false`, `dry_run: true`, `entrypoints.autonomy: false` |
| `config/autonomy.json` | **No** (pre-existing) | Repo history shows `"enabled": true` since initial commit |
| `GuardianCore.run_autonomous_cycle` | **No** | Executes when `autonomy.json` enabled + heartbeat/UI trigger |
| `live_execution_guard` on autonomy actions | **No** | Guard denies `is_autonomy_context` if called — **autonomy path does not call guard today** |

If an operator re-enables autonomy via UI (`POST /api/autonomy`) while legacy guards are unwired, **`run_autonomous_cycle`** can still run learning, mutation, capabilities, self-tasks, OpenClaw delegation, and related side effects **without** BrainPipeline trace or live-execution guard integration. Committed default is **`enabled: false`** (`14a5fbe`).

**Verification addendum (2026-05-24):** Five additional execution-capable surfaces were missing from the first draft and are inventoried below — alternate API host task enqueue, FastAPI acceptance runner, Architect proposal API, Implementer agent subprocess/pytest, and legacy autonomy config defaults.

**Unstaged note:** `elysia/api/server.py` still has documented proposal-implementation/WebScout hunks outside this audit’s scope — see [`SERVER_UNSTAGED_RISKY_HUNKS.md`](SERVER_UNSTAGED_RISKY_HUNKS.md).

---

## B. Entry point inventory

Risk levels: **Critical** (unattended mutate/execute/LLM), **High** (loop + side effects), **Medium** (config/visibility), **Low** (read-only).

| File | Symbol / route | Trigger | Can loop? | Tools | File mutate | LLM/API | BrainPipeline/TDA | live_execution_guard | Risk |
|------|----------------|---------|-----------|-------|-------------|---------|-------------------|----------------------|------|
| `project_guardian/core.py` | `run_autonomous_cycle()` | Heartbeat (`monitoring.py`), `POST /api/autonomy/execute-cycle`, tests | **Yes** (periodic + manual) | **Yes** (`use_capability/*`, tools) | **Yes** (mutation, self-task, etc.) | **Yes** (learning, mutation OpenAI, Mistral decider) | **No** | **No** | **Critical** |
| `project_guardian/core.py` | `get_next_action()` / `_get_next_action_impl()` | UI `GET /api/next-action`, internal cycle | No (single shot) | Indirect | No direct | **Yes** (Mistral/LLM routing in selector) | **No** | **No** | **High** |
| `project_guardian/monitoring.py` | Heartbeat `_beat` | Background thread when monitor running | **Yes** | Via cycle | Via cycle | Via cycle | **No** | **No** | **Critical** |
| `project_guardian/ui_control_panel.py` | `POST /api/autonomy/execute-cycle` | Dashboard “Execute” / JS | One shot per POST | Via orchestrator | Via cycle | Via cycle | **No** | **No** | **Critical** |
| `project_guardian/ui_control_panel.py` | `POST /api/autonomy` | Toggle `config/autonomy.json` `enabled` | Enables loop | — | — | — | **No** | **No** | **High** |
| `project_guardian/ui_control_panel.py` | `GET /api/autonomy` | Dashboard status | No | No | No | No | **No** | **No** | **Low** |
| `project_guardian/ui_control_panel.py` | `GET /api/next-action` | `suggestNextAction()` JS | No | Indirect | No | **Yes** | **No** | **No** | **Medium** |
| `project_guardian/ui_control_panel.py` | `suggestNextAction` / `executeNextAction` | Mission UI buttons | Can chain POSTs | dream-cycle, execute-cycle | dream/mutation paths | **Yes** | **No** | **No** | **High** |
| `project_guardian/ui_control_panel.py` | `POST /api/control/dream-cycle` | JS after suggest / manual | No | No | No (memory) | **Possible** (dreams component) | **No** | **No** | **Medium** |
| `project_guardian/ui_control_panel.py` | `POST /api/control/pause` / `resume` | Control panel | No | No | No | No | **No** | **No** | **Medium** |
| `config/autonomy.json` | `enabled`, `allowed_actions`, … | File edit via UI POST or manual; **committed default: `enabled: false`** (`14a5fbe`) | Enables heartbeat when toggled on | Defines actions | — | — | **No** | **No** | **High** (operator can re-enable via UI) |
| `config/brain_pipeline.json` | `entrypoints.autonomy` | Brain config loader | N/A | N/A | N/A | N/A | Gate only if wired | If wired | **Low** (off) |
| `project_guardian/elysia_loop_core.py` | `ElysiaLoopCore.start()` / task queue | `system_orchestrator`, singleton | **Yes** | Task funcs vary | Varies | Varies | **No** | **No** | **High** |
| `project_guardian/system_orchestrator.py` | Wires `elysia_loop`, `runtime_loop` | Startup | **Yes** | Yes | Yes | Yes | **No** | **No** | **High** |
| `project_guardian/mission_autonomy.py` | `MissionAutonomyStore` | `get_next_action` candidate governance | No | No | No | No | **No** | **No** | **Medium** |
| `project_guardian/tool_executor.py` | `execute_action()` | Mistral decision tools (allowlist) | No | **Yes** (bounded set) | Indirect | Indirect | **No** | **No** | **High** |
| `project_guardian/capability_execution.py` | `execute_capability()` | Autonomy `use_capability/*`, APIs | No | **Yes** | **Yes** (modules) | **Yes** (builtin LLM caps) | **No** | **No** | **Critical** |
| `project_guardian/mutation.py` / `mutation_engine.py` | Mutation apply paths | `consider_mutation` in cycle | No | No | **Yes** | **Yes** | **No** | **No** | **Critical** |
| `elysia/api/server.py` (committed `da8d0ae`) | `POST /api/proposals/.../implement` | API clients | No | No | **Yes** | Via Implementer | **No** | **No** | **High** |
| `elysia/api/server.py` (committed) | `POST /api/webscout/research` | API | No | Web | No | **Yes** | **No** | **No** | **Medium** |
| `elysia/api/server.py` (unstaged) | `_run_implementation`, preview route | Not committed | No | No | **Yes** | **Yes** | **No** | **No** | **High** (excluded) |
| `project_guardian/api_server.py` | `POST /api/tasks` → `submit_task()` | HTTP clients to alternate PG API host | No (queues work) | **Yes** (resolved callables on orchestrator roots) | **Yes** (via enqueued funcs) | **Yes** (module-dependent) | **No** | **No** | **Critical** |
| `project_guardian/api_server.py` | `_resolve_task_callable` / `_task_resolution_roots` | Used by `POST /api/tasks` | No | **Yes** | **Yes** | **Yes** | **No** | **No** | **Critical** |
| `project_guardian/api_server.py` | `GET /api/mutations` | Legacy/alternate API host | No | No | Read | No | **No** | **No** | **Low** |
| `project_guardian/ui/app.py` | `POST /control/run-acceptance` | FastAPI dashboard UI | No | No | No (script side effects) | No | **No** | **No** | **Critical** |
| `project_guardian/proposal_api.py` | `POST /api/proposals`, `.../approve`, `.../reject`, `.../implementation` | Architect-hosted Flask app (alternate host) | No | Indirect (architect) | Plan/metadata | **Possible** (architect LLM) | **No** | **No** | **High** |
| `elysia/agents/implementer.py` | `ImplementerAgent.run_for_proposal()` | `elysia/api/server.py` implement route, autonomy-adjacent tooling | No | No | **Yes** (applies plan steps) | **Possible** | **No** | **No** | **Critical** |
| `elysia/agents/implementer.py` | `_run_pytest_step` → `subprocess.run(["pytest", ...])` | During `run_for_proposal` when plan includes tests | No | **Yes** (pytest) | No direct | No | **No** | **No** | **Critical** |
| `project_guardian/brain/runtime.py` | `run_brain_pipeline_for_operator_event` | Operator chat only (if entrypoint on) | No | Dry-run modules | No | Config-gated | **Yes** | **Yes** | **Low** (off) |
| `project_guardian/governance/live_execution_guard.py` | `evaluate_live_execution_request` | Brain runtime / tests | No | Deny raw shell | Policy only | N/A | N/A | **Yes** | **Low** (policy) |
| `project_guardian/autonomy_antiloop.py` | `apply_autonomy_antiloop_factors` | `get_next_action` | No | No | No | No | **No** | **No** | **Medium** |
| `scripts/autonomy_loop_health.py` | Health script | Manual ops | No | No | No | No | **No** | **No** | **Medium** |
| `scripts/harness_upstream_routing_task_type_emitters.py` | Calls `run_autonomous_cycle` | Dev harness | Yes | Yes | Yes | Yes | **No** | **No** | **High** (dev only) |
| `Elysia_Control_Panel_Standalone.html` | `/api/autonomy` fetch | External HTML | Same as UI | Same | Same | Same | **No** | **No** | **High** |

### Representative `allowed_actions` (from `config/autonomy.json` on branch)

Committed file (`14a5fbe`): `"enabled": false`, `"interval_seconds": 45`, `"max_actions_per_hour": 40`, `"require_approval_for": []`. Worktree copies may differ if locally edited.

Includes: `consider_learning`, `consider_dream_cycle`, `consider_prompt_evolution`, `consider_adversarial_learning`, `consider_mutation`, `execute_self_task`, `delegate_openclaw`, `use_capability/*` (dynamic), `execute_task`, `process_queue`, `continue_mission`, income/harvest pulses, etc.

### `POST /api/tasks` resolution roots (alternate API host)

`_task_resolution_roots()` exposes orchestrator components including **`tool_executor`**, **`mutation_router`**, **`implementer_core`**, **`mutation_engine`**, **`income_executor`**, **`task_queue`**, **`runtime_loop`**, and others. A client supplying `function` + optional `module` can enqueue arbitrary **public** callables onto `orchestrator.submit_task()` — bypassing safe-stack routes entirely.

### `proposal_api.py` vs safe-stack proposal routes

| Route | Host | Execution character |
|-------|------|---------------------|
| Safe-stack SI queue | `elysia/api/server.py`, `ui_control_panel.py` | Review/status/export only |
| Architect `proposal_api.py` | Separate Flask app | Create/research/design/**implementation plan**/approve/reject — **not** the same as safe-stack SI; can advance proposal workflow and architect-side implementation metadata |
| Runtime implement | `elysia/api/server.py` `POST .../implement` | **`ImplementerAgent.run_for_proposal`** — file changes + pytest |

---

## C. Execution-capable paths

Paths that can **execute tools**, **mutate files**, **run subprocess/shell**, **call external APIs**, or **continue unattended loops**:

| Path | Mechanism | Guarded today? |
|------|-----------|----------------|
| **Autonomy loop** | `monitoring` → `run_autonomous_cycle` when `autonomy.json` `enabled` | Partial (config allowlist, `max_actions_per_hour`, `can_auto_execute`, antiloop) — **not** live_execution_guard / Brain |
| **Manual execute-cycle** | `POST /api/autonomy/execute-cycle` | Same as loop |
| **use_capability/** | `execute_capability()` → modules/tools (LLM, web, exec builtins) | Trust/capability registry; **no** operator confirmation |
| **consider_mutation** | OpenAI/mutation engine apply to repo files | Trust + protected-target skips; **no** rollback guard at autonomy layer |
| **execute_self_task** | `_run_self_generated_task` | Self-task gates; can invoke capabilities |
| **delegate_openclaw** | `delegate_to_openclaw` | External worker — **high risk** if enabled |
| **consider_learning** | Auto-learning with optional `make_learning_llm_callback` | LLM when callback wired |
| **Subprocess** | `SubprocessRunner` / acceptance scripts in `core.py` | Gateway exists; autonomy paths must route through it |
| **Implementer** | `elysia/api/server.py` `POST .../implement` | Separate from autonomy; **file mutation** |
| **ElysiaLoopCore** | Async task queue processing | Independent loop; not smoke-gated |
| **Dream cycle** | `POST /api/control/dream-cycle` | Memory consolidation; side effects on memory stores |
| **Tool executor** | Mistral `execute_action` allowlist | Blocks unknown tools only |
| **`POST /api/tasks`** | `api_server.submit_task` → `_resolve_task_callable` → `orchestrator.submit_task` | Name filter only (`_` prefix blocked); **no** guard/brain |
| **`POST /control/run-acceptance`** | `ui/app.py` → `subprocess.run(powershell -File scripts/acceptance.ps1)` | Path suffix check only; **raw shell** |
| **Implementer agent** | `run_for_proposal` applies steps; **pytest via `subprocess.run`** | `dry_run` flag exists but not safe-stack governed |
| **Architect proposal API** | `proposal_api.py` approve/reject/implementation POSTs | Parallel proposal workflow outside safe-stack SI |

**Unattended loop sources:** `monitoring.py` interval + `autonomy.json` `interval_seconds`; `elysia_loop` task queue; `POST /api/tasks` backlog; optional OpenClaw/MCP workers (separate configs).

### Highest-risk paths (prioritized)

1. **Unguarded `run_autonomous_cycle` when operator sets `enabled: true`** — heartbeat can auto-run cycles on `interval_seconds` with `max_actions_per_hour`.  
2. **`run_autonomous_cycle` + `POST /api/autonomy/execute-cycle`** — full legacy autonomy executor.  
3. **`POST /api/tasks`** — programmatic enqueue of mutation/tool/implementer callables without governance.  
4. **`elysia/agents/implementer.py`** — repo file mutation + **`subprocess.run(pytest)`**.  
5. **`POST /control/run-acceptance`** — PowerShell execution from FastAPI UI.  
6. **`execute_capability` / `consider_mutation`** — direct module and file mutation from autonomy allowlist.

---

## D. Current safe-stack coverage (what is already guarded)

| Surface | Coverage |
|---------|----------|
| Operator chat BrainPipeline trace | `run_brain_pipeline_for_operator_event` + `apply_live_execution_guard_to_context`; entrypoints off in `config/brain_pipeline.json` |
| Live execution | Fail-closed guard + audit JSONL; `operator_chat_live_execution: false` |
| Self-improvement (safe-stack API) | List/detail/status/export only — no implement |
| Memory ranking | Read-only summary API |
| Prompt contracts | Visibility/validation config off by default |
| Operator confirmation | Store + validation-only in guard path; **read-only** list/detail APIs |
| Autonomy loop | **Not covered** — `entrypoints.autonomy: false` only affects BrainPipeline if wired |
| `config/autonomy.json` | **Not modified** by safe-stack commits |
| `api_server.py` `POST /api/tasks` | **Not covered** |
| `ui/app.py` run-acceptance | **Not covered** |
| `proposal_api.py` | **Not covered** (separate host) |
| `elysia/agents/implementer.py` | **Not covered** |

Smoke gate (`386` tests) validates safe-stack modules and **forbids** tokens like `run_autonomous_cycle` in **safe-stack** route handlers — it does **not** prove autonomy is disabled at runtime or that alternate API/UI hosts are safe.

---

## E. Gaps before autonomy mode

Before any production or operator “autonomy mode”:

| Requirement | Current state |
|-------------|---------------|
| All autonomy entrypoints default **dry-run** | **Gap** — `enabled: false` default done; dry-run wrapper + guard not wired |
| All action proposals through **BrainPipeline/TDA trace** | **Gap** — `core.py` has zero `run_brain_pipeline` / guard calls |
| Any execution calls **live_execution_guard** | **Gap** — guard has `AUTONOMY_CONTEXT_DENIED` but autonomy doesn’t invoke guard |
| Tool/capability **allowlist** | Partial — dynamic `use_capability/*`; needs central registry + deny-by-default |
| Mutation **rollback metadata** | Partial in guard policy; not enforced on autonomy mutation path |
| Operator confirmation for medium/high or mutating | **Gap** — confirmations not required for autonomy cycle |
| Loop **budget** / time / task limits | Partial — `max_actions_per_hour`, antiloop; no global kill file in cycle |
| **Audit logging** | Partial — memory + module logs; no unified autonomy audit JSONL |
| **Kill switch** | **Gap** — UI can enable autonomy; no hard repo-wide kill enforced in `run_autonomous_cycle` first line |
| Brain `entrypoints.autonomy` | **false** in config — wiring not implemented |
| Proposal implement from autonomy | Not directly wired; **Implementer** + `POST /api/tasks` remain open |
| **`POST /api/tasks` allowlist** | **Gap** — dotted public methods on sensitive roots allowed |
| **Acceptance subprocess UI** | **Gap** — `run-acceptance` not behind guard or brain trace |
| **Alternate proposal API** | **Gap** — `proposal_api.py` not aligned with safe-stack SI governance |
| **Implementer pytest subprocess** | **Gap** — raw `subprocess.run` in implementer path |

---

## F. Recommended phased plan

| Phase | Goal | Run in production? |
|-------|------|--------------------|
| **0** | **`enabled: false` default** — **Done** (`14a5fbe`); do not call `execute-cycle` or `POST /api/tasks` for mutation/implementer targets | **No execution** |
| **1** | **Dry-run autonomy trace only** — see [`DRY_RUN_AUTONOMY_PHASE1_PLAN.md`](DRY_RUN_AUTONOMY_PHASE1_PLAN.md): BrainPipeline/TDA + `live_execution_guard` with `autonomy_context=True`; bounded cycle; audit JSONL; tests before wiring | Logs only |
| **2** | Guarded **recommendations** — return proposed actions; no tool/file execution | Advisory UI |
| **3** | **Single** allowlisted low-risk action (e.g. `continue_monitoring` or read-only diagnostic) with guard + confirmation in non-production | Controlled experiment |
| **4** | Broader autonomy only after full governance test suite + operator runbooks | Staged rollout |

**Do not** conflate enabling `operator_chat_live_execution` in brain config with autonomy — separate checklists ([`LIVE_EXECUTION_GOVERNANCE_PLAN.md`](LIVE_EXECUTION_GOVERNANCE_PLAN.md)).

---

## G. Tests needed (proposed)

| Test | Intent |
|------|--------|
| `test_autonomy_config_defaults_disabled` | Shipped default or CI fixture: `autonomy.json` `enabled: false` for safe profiles |
| `test_run_autonomous_cycle_noop_when_disabled` | Cycle returns immediately without side effects |
| `test_execute_cycle_denied_without_guard` | When guard wired, autonomy context denied |
| `test_autonomy_no_subprocess_without_runner` | No raw `subprocess` in cycle path |
| `test_autonomy_no_mutation_without_rollback` | Mutation requires rollback metadata when guard on |
| `test_proposal_implement_not_invoked_from_autonomy` | No `run_for_proposal` from cycle |
| `test_loop_budget_enforced` | `max_actions_per_hour` + antiloop |
| `test_operator_confirmation_required_medium_high` | Confirmation store integration |
| `test_autonomy_audit_jsonl_append` | Structured audit per cycle |
| `test_kill_switch_blocks_cycle` | Env/file flag stops heartbeat + execute-cycle |
| `test_brain_entrypoint_autonomy_trace_only` | Phase 1: trace persisted, `executed: false` |
| `test_api_tasks_denies_mutation_implementer_without_guard` | `POST /api/tasks` cannot enqueue `mutation_router` / `implementer_core` without governance (Phase 1+) |
| `test_run_acceptance_requires_explicit_operator_gate` | `POST /control/run-acceptance` blocked or dry-run only until confirmation |
| `test_implementer_subprocess_gated` | `subprocess.run(pytest)` only after guard + allowlist |
| `test_proposal_api_not_exposed_in_production_profile` | Document/deploy separation of `proposal_api.py` vs safe-stack hosts |
| `test_autonomy_json_enabled_false_in_repo_default` | CI asserts shipped `config/autonomy.json` has `enabled: false` after Phase 0 config fix |

Existing: `test_autonomy_loop_guards.py`, `test_autonomy_safe_fallback.py`, smoke token bans in route tests.

---

## H. Verdict

### Is autonomy safe to run now?

**No.**

### Phase 0 (configuration) — resolved

**`config/autonomy.json` defaults to `"enabled": false`** (`14a5fbe`). Heartbeat and startup threads in `monitoring.py` still **call** `run_autonomous_cycle` when an operator re-enables autonomy via UI or config edit — those paths remain **unguarded** and can execute real side effects until Phase 1 wiring lands.

**Required before running autonomy:** complete Phase 1 per [`DRY_RUN_AUTONOMY_PHASE1_PLAN.md`](DRY_RUN_AUTONOMY_PHASE1_PLAN.md).

### Safe dry-run autonomy

**Do not attempt** safe dry-run autonomy until **all** of the following:

1. **Phase 0:** `config/autonomy.json` **`enabled: false`** — **done** (`14a5fbe`). UI can still re-enable; Phase 1 must force dry-run when enabled.
2. **Phase 1 wiring:** `run_autonomous_cycle`, `get_next_action`, and any future autonomy entrypoints call **BrainPipeline/TDA** (trace persisted, dry-run default).
3. **Guard:** any non-dry execution path calls **`apply_live_execution_guard`** (including blocking `is_autonomy_context` until a dedicated autonomy governance design exists).
4. **Surfaces:** `POST /api/tasks`, `proposal_api.py`, `ImplementerAgent`, and `run-acceptance` inventoried and either disabled, gated, or excluded from production profiles.
5. Proposed tests in §G passing in CI.
6. Control panel execute-cycle hidden or hard-disabled until Phase 3 sign-off.

**Safe-stack milestone remains valid** for operator chat and read-only panels — it is **not** a certificate of autonomy safety or of alternate API/UI host safety.

---

## Verification (audit run)

```text
python scripts/run_safe_stack_smoke_tests.py
→ 386 passed, 3 warnings (2026-05-24)
```

**Production code changed by this audit:** **No** — documentation only.
