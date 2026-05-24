# Live execution governance plan

**Status:** Planning only — **do not enable live execution from this document.**  
**Date:** 2026-05-18  
**Scope:** BrainPipeline, Think–Decide–Act (TDA), operator chat, capabilities/tools, change-proposal implementation, autonomy, and control-panel surfaces.

This plan defines what must be true **before** any non–dry-run execution path is allowed. Implementation work should add **tests and guards first**, not flip production flags.

**Governance invariants (summary):** dry-run-before-live (persist a **dry-run artifact** before any live attempt); blocked and **high risk** actions **cannot execute** live; **no raw LLM text to executable commands** (reject free-form user text as shell/code); **autonomy remains excluded** from operator-chat live paths unless a separate autonomy checklist is completed.

---

## 1. Current baseline (intentionally safe)

| Control | Default / current behavior |
|--------|---------------------------|
| `brain_pipeline.enabled` | **off** (`config/brain_pipeline.json`) |
| `brain_pipeline.dry_run` | **on** |
| `entrypoints.operator_chat` | **off** |
| `entrypoints.operator_chat_live_execution` | **off** — operator chat Brain hook stays dry-run even if pipeline runs |
| `entrypoints.tool_execution` | **off** |
| `entrypoints.autonomy` | **off** |
| `prompt_contract_validation.enabled` | **off** |
| Safe-stack dashboard panels | Read-only / review-only (trace, proposals export, memory ranking, prompt contracts) |
| Self-improvement JSONL API | List / detail / status / **export text only** — no patch apply |
| `run_operator_chat_turn` | Does not call LLMs, tools, shell, or autonomy; host supplies responder |

**Operator-chat live execution gate (already in code):**  
`project_guardian/brain/runtime.py` forces `dry_run=True` for `source_entrypoint=="operator_chat"` unless `entrypoints.operator_chat_live_execution` is true.

**Risk skip (already in code):**  
`project_guardian/brain/pipeline.py` skips execution when `risk.level` is `BLOCKED` or `HIGH`.

**TDA execute stage (already in code):**  
`project_guardian/orchestration/think_decide_act.py` returns skipped execution when `dry_run=True` or validation not approved; blocks raw LLM/shell execution in proposer prompts.

---

## 2. Execution surfaces inventory

Document every path that can cause real side effects. Live-execution governance must cover **all** of these (not only BrainPipeline).

### 2.1 BrainPipeline and TDA

| Surface | Location | Side effects when live |
|---------|----------|-------------------------|
| **BrainPipeline.run** | `project_guardian/brain/pipeline.py` | Planner → routers → risk → TDA or **CapabilityExecutionFacade** |
| **CapabilityExecutionFacade.execute** | `project_guardian/brain/execution_module.py` | Calls `capability_execution.execute_capability` |
| **TDA `execute()`** | `project_guardian/orchestration/think_decide_act.py` | `_execute_approved_action` when not dry-run and validation approved |
| **Operator Brain entry** | `project_guardian/brain/runtime.py` | `run_brain_pipeline_for_operator_event` — dry-run forced for operator chat unless live flag |
| **Runtime API Brain hook** | `elysia/api/server.py` | Same runtime entry on `/api/chat` when pipeline + `operator_chat` enabled |
| **Control panel Brain hook** | `project_guardian/ui_control_panel.py` | `_maybe_run_brain_operator_chat_trace` on panel chat |

**Config flags:** `enabled`, `dry_run`, `entrypoints.operator_chat`, `entrypoints.operator_chat_live_execution`, `entrypoints.tool_execution`, `entrypoints.autonomy`, `entrypoints.diagnostic`, `use_think_decide_act`, `prompt_contract_validation.*`.

### 2.2 Capabilities and tools

| Surface | Location | Notes |
|---------|----------|--------|
| **execute_capability / execute_capability_kind** | `project_guardian/capability_execution.py` | Includes gated `elysia_builtin_exec` (explicit operator approval required in code comments) |
| **Chat tool-first execute** | `project_guardian/unified_llm_route.py` | `try_chat_capability_execute` may run capabilities before LLM |
| **tool_executor** | `project_guardian/tool_executor.py` | Task execution delegation / queue |
| **orchestration bridge** | `project_guardian/orchestration/tools/bridge.py` | `execute_action_intent` |
| **ModuleRegistry.route_task** | Control panel `submitTask` API | Custom code / task routing |

### 2.3 Change proposals (separate from self-improvement queue)

| Surface | Location | Notes |
|---------|----------|--------|
| **POST `/api/proposals/<id>/implement`** | `elysia/api/server.py` | `ImplementerAgent.run_for_proposal`; supports `dry_run` query/body |
| **Implementation preview** | `elysia/api/server.py` | `dry_run=True` preview route |
| **Approval auto-implement** | `elysia/api/server.py` | `_approval_should_implement` / `_run_implementation` on approve |
| **Implementer task runner** | `project_guardian/implementer/task_runner.py` | `apply_patch`, file writes when not dry-run |
| **proposal_api** | `project_guardian/proposal_api.py` | Architect metadata (plans, todos) — distinct from runtime implement route |

**Isolation requirement:** Self-improvement queue (`/api/self-improvement/proposals/*`) must **never** auto-wire to implementer apply paths without a separate governance workflow.

### 2.4 Self-improvement and mutation

| Surface | Location | Notes |
|---------|----------|--------|
| **Self-improvement API** | `ui_control_panel.py`, `safe_stack/responses.py` | GET list/detail, POST status, GET export_prompt — **no execute/apply route** |
| **Brain enqueue** | `project_guardian/brain/self_improvement_module.py` | Proposals only |
| **Mutation engine / sandbox** | `project_guardian/tests/test_integration_mutation_workflow.py` | Separate mutation workflow |
| **Prompt evolution / harvest / research buttons** | Control panel Control tab | Operator-triggered subsystem calls |

### 2.5 Autonomy and loop execution

| Surface | Location | Notes |
|---------|----------|--------|
| **POST `/api/autonomy/execute-cycle`** | `ui_control_panel.py` | `orchestrator.run_autonomous_cycle()` |
| **Autonomy config POST/GET** | `/api/autonomy` | Enables/configures autonomy — separate from Brain `entrypoints.autonomy` |
| **Elysia loop / global task queue** | `elysia_loop_core.py`, `global_task_queue.py` | Background task execution |
| **Mission / next-action UI** | `suggestNextAction`, `executeNextAction` | May call execute-cycle or dream cycle |
| **Planner readiness / antiloop** | `planner_readiness.py`, autonomy tests | Scoring and guards — not a substitute for live-exec governance |

### 2.6 UI controls (operator-triggered)

| Control | Risk class |
|---------|------------|
| **Submit Task** (`submitTask`) | Code execution via ModuleRegistry |
| **Trigger Dream Cycle** | Memory / internal state mutation |
| **Execute next action / execute-cycle** | Autonomy cycle |
| **Start Learning** | External fetch / learning pipeline |
| **Harvest / research / prompt evolution** | External or heavy subsystem |
| **Pause/Resume loop, memory snapshot** | Runtime control |
| **Self-improvement status “Implemented”** | Status label only today — must not imply code apply |
| **Safe-stack refresh buttons** | Read-only APIs only |

### 2.7 Shell / subprocess / file mutation

| Surface | Notes |
|---------|--------|
| `elysia_builtin_exec` capability | Gated in `capability_execution.py` |
| Implementer `apply_patch` | File writes |
| Learning headless / Playwright | Browser subprocess when enabled |
| Deployment / slave scripts | Out of operator-chat path but in repo |

---

## 3. Live-execution gate requirements (must all pass)

These are **preconditions** for enabling any non–dry-run path (starting with `operator_chat_live_execution`, then `tool_execution`, then broader autonomy).

### 3.1 Config and policy gates

1. **Explicit config flag** — e.g. `entrypoints.operator_chat_live_execution: true` (and later `tool_execution` / documented autonomy flags). No implicit opt-in via missing keys.
2. **Master switch** — `brain_pipeline.enabled` must be true for Brain-mediated live execution.
3. **Global dry_run** — `brain_pipeline.dry_run` may only be false when live entrypoint flag is true; document combined semantics in `runtime.py`.
4. **Separate autonomy governance** — `entrypoints.autonomy` and `/api/autonomy/execute-cycle` require their own checklist; Brain live flag does **not** authorize autonomy loops.
5. **Prompt contracts** — When live execution is enabled for an entrypoint, `prompt_contract_validation` policy must be defined: pass vs warn vs block per mode; strict must not silently downgrade without audit.

### 3.2 Operator confirmation and disclosure

6. **Operator confirmation required** — Two-step UI or API: preview intended action → confirm with stable action id (not raw model text).
7. **Exact tool/action shown** — Display capability ref, TDA `action_type`, target module, risk level, and args summary before confirm.
8. **No raw LLM text → executable command** — Parser must produce structured `StructuredCommand` / `ActionProposal`; reject freeform shell/code from model output.
9. **Identity context** — Record `conversation_id`, `source_entrypoint`, operator/session id if available, timestamp, config snapshot hash.

**Operator confirmation context plan:** [`docs/OPERATOR_CONFIRMATION_CONTEXT_PLAN.md`](OPERATOR_CONFIRMATION_CONTEXT_PLAN.md) defines the future `operator_confirmation_id` / `dry_run_trace_id` envelope, confirmation expiry, single-use rules, trace/action matching, API shape, and exclusions. **Planning only** — it does not enable live execution, autonomy, or operator-chat confirmation UI.

### 3.3 Dry-run and trace prerequisites

10. **Dry-run trace must exist first** — For the same observation/command id, a successful dry-run Brain/TDA trace (or explicit “dry-run unavailable” waiver with reason) must be persisted before live attempt.
11. **Trace inspectable** — Operator can view sanitized trace (`/api/brain/trace/latest`, dashboard Brain Trace) matching the pending live action id.
12. **Fail closed on missing trace** — If dry-run trace missing or stale (TTL), live execution rejected.

### 3.4 Risk and validation

13. **Risk level rules** — **LOW** may auto-execute only with all other gates; **MEDIUM** requires explicit operator approval; **HIGH** and **BLOCKED** must **never** execute (pipeline already skips HIGH/BLOCKED — enforce in TDA and capability layer too).
14. **Validation approved** — TDA `validation.approved` must be true; blocked validation notes → no execute.
15. **Prompt-contract validation** — Per config: failures must block or warn per mode; live execution must not proceed on **block** mode failures.
16. **Allowlist** — Only whitelisted capability refs / action types / tools; deny by default for `elysia_builtin_exec` and subprocess unless separate whitelist entry + confirmation.

### 3.5 Audit, rollback, and recovery

17. **Audit log required** — Append-only record: who/when/what/config hash/trace id/outcome/error (no secrets; redact like ConversationStore).
18. **Rollback or undo strategy** — Where file/patch execution applies: preview diff, backup path, or implementer dry-run proof; document non-reversible actions (external API calls).
19. **Post-execution logging** — Success/failure, duration, capability result keys, link to trace id and audit id.
20. **Operator-visible result** — Control panel / API returns human-readable outcome and audit id, not only internal logs.

### 3.6 Isolation rules

21. **No self-modifying code without separate approval** — Self-improvement export ≠ implement; change proposals use `/api/proposals/.../implement` workflow only.
22. **No autonomy loop execution without separate governance** — Enabling Brain live exec must not enable `run_autonomous_cycle`.
23. **No shell/subprocess unless whitelisted** — Central registry of allowed execution kinds; default deny.
24. **Dual API hosts** — RuntimeAPIServer and UIControlPanel must enforce the same gates (parity tests).

---

## 4. Governance checklist

Use this at enablement time and per live-execution request.

### Preconditions (before enabling flags)

- [ ] All tests in §5 “Future test suite” planned or implemented for the target entrypoint.
- [ ] Security review of allowlisted capabilities and implementer paths.
- [ ] Operators trained on Brain Trace, risk labels, and confirmation UI.
- [ ] Rollback runbook documented for patch-based changes.
- [ ] `config/brain_pipeline.json` change reviewed in version control (no ad-hoc local edits on production).
- [ ] Autonomy remains off unless separate autonomy checklist completed.

### Runtime checks (each live execution)

- [ ] `brain_pipeline.enabled` and target `entrypoints.*` true.
- [ ] `operator_chat_live_execution` (or relevant flag) true **only** if operator chat path.
- [ ] Matching dry-run trace present and fresh.
- [ ] Risk is LOW, or MEDIUM with recorded operator approval id.
- [ ] Risk is not HIGH or BLOCKED.
- [ ] Prompt-contract validation outcome acceptable for configured mode.
- [ ] Action/capability on allowlist; not raw LLM/shell text.
- [ ] Operator confirmation token/id recorded.
- [ ] `conversation_id` / entrypoint / operator identity attached to audit record.

### Post-execution

- [ ] Audit log written with outcome.
- [ ] Trace updated or linked with live execution result.
- [ ] Operator UI/API shows result summary.
- [ ] Secrets redacted in stored artifacts.

### Rollback checks (when applicable)

- [ ] Patch backup or VCS revert path identified before live patch.
- [ ] Failed execution does not leave partial writes without detection.
- [ ] Implementer dry-run preview matches approved plan hash.

---

## 5. Future test plan (proposed — not implemented here)

Add pytest modules incrementally; all tests use mocks/offline fixtures — **no real LLM or external API calls.**

| Category | Proposed module / focus | Assertions |
|----------|-------------------------|------------|
| **Config gate** | `test_live_execution_config_gates.py` | Live exec impossible when `operator_chat_live_execution` false; operator_chat forces dry_run in `runtime.py` |
| **Dry-run before live** | `test_live_execution_dry_run_prerequisite.py` | Live rejected without prior dry-run trace id |
| **Risk blocking** | `test_live_execution_risk_blocking.py` | HIGH/BLOCKED never call `CapabilityExecutionFacade.execute` or TDA live execute |
| **Medium approval** | `test_live_execution_medium_risk_approval.py` | MEDIUM requires approval context flag |
| **Prompt contracts** | extend `test_prompt_contract_*` | Block/warn behavior when live flag on |
| **Executor allowlist** | `test_live_execution_capability_allowlist.py` | Unknown refs denied; `elysia_builtin_exec` denied without approval |
| **Audit logging** | `test_live_execution_audit_log.py` | Audit row created with conversation_id, trace id, no secrets |
| **Rollback requirement** | `test_live_execution_rollback_metadata.py` | Implement route requires backup/preview metadata |
| **UI confirmation** | `test_live_execution_ui_confirmation.py` | Template/API requires confirm step; no one-click live from safe-stack panels |
| **Proposal isolation** | `test_live_execution_proposal_isolation.py` | Self-improvement routes cannot call implementer |
| **Autonomy off** | `test_live_execution_autonomy_isolation.py` | Brain live flag does not enable `run_autonomous_cycle` |
| **Fail closed** | `test_live_execution_fail_closed.py` | Missing config/trace/validation → bypass or error, never silent live |
| **Secret redaction** | extend conversation/audit tests | Audit/trace exclude raw secrets |
| **Operator confirmation context plan** | `test_operator_confirmation_context_plan.py` | Static plan covers future context schema, expiry, single-use confirmation, trace/action matching, and non-enablement |
| **Operator confirmation store** | `test_operator_confirmation_store.py` | JSONL store: create, expiry, single-use, trace/action binding, policy denials, redaction, guard context mapping |
| **Confirmation guard integration** | `test_operator_confirmation_guard_integration.py` | Validation-only runtime wiring; no consumption; config still denies live |

**Existing tests to extend (reference only):**

- `test_brain_trace_visibility.py`, `test_brain_tda_integration.py`, `test_control_panel_brain_visibility.py`
- `test_operator_chat_helper.py`, `test_control_panel_operator_chat_helper_integration.py`
- `test_self_improvement_prompt_export.py`, `test_implementer_task_runner.py`
- `test_tool_executor.py`, `test_capability_builtin_llm.py` (`test_execute_capability_builtin_exec_is_gated`)
- `test_autonomy_loop_guards.py`, `test_eai_safety_framework.py` (dry-run patterns)

---

## 6. Fail-closed guard and runtime wiring (live execution still off by default)

| Item | Location |
|------|----------|
| **Module** | `project_guardian/governance/live_execution_guard.py` |
| **API** | `evaluate_live_execution_request(request, config=None, brain_config=None)` |
| **Types** | `LiveExecutionRequest`, `LiveExecutionDecision`, `LiveExecutionGuardConfig` |
| **Tests** | `project_guardian/tests/test_live_execution_guard.py` |
| **Default** | `LiveExecutionGuardConfig.live_execution_enabled=False` — deny unless all gates pass |

The guard answers “may this proposed action execute live?” with **default deny**. It does **not** enable live execution, call LLMs/APIs, or run shell/subprocess.

**Runtime wiring (fail-closed):** `project_guardian/brain/runtime.py` calls `apply_live_execution_guard_to_context` before `BrainPipeline.run`. Denied live attempts and audit failures force `dry_run=True`. Config defaults (`operator_chat_live_execution: false`, `dry_run: true`) remain unchanged. **Operator confirmation store** at `project_guardian/governance/operator_confirmation_store.py` is integrated **validation-only** in `live_execution_runtime.py` (load/validate/map; does not consume confirmations or enable live execution). No confirmation UI/API yet. See [`OPERATOR_CONFIRMATION_CONTEXT_PLAN.md`](OPERATOR_CONFIRMATION_CONTEXT_PLAN.md).

---

## 7. Recommended implementation order

1. **Documentation and static tests** (this file + `test_live_execution_governance_docs.py`) — done.  
2. **Fail-closed guard helper** (`live_execution_guard.py` + `test_live_execution_guard.py`) — done.  
3. **Runtime integration** — guard + audit in `runtime.py` / `live_execution_runtime.py`; config flags remain off.  
4. **Operator confirmation context plan** — `OPERATOR_CONFIRMATION_CONTEXT_PLAN.md` + `test_operator_confirmation_context_plan.py` (planning only).  
5. **Operator confirmation store** — `operator_confirmation_store.py` + `test_operator_confirmation_store.py`; JSONL at `data/runtime/operator_confirmations.jsonl`.  
6. **Confirmation guard integration (validation-only)** — `test_operator_confirmation_guard_integration.py`; runtime validates `operator_confirmation_id` without marking used.  
7. **Allowlist + risk parity** — TDA + pipeline + capability_execution aligned on HIGH/BLOCKED.  
8. **Operator confirmation API + UI** — create/list confirmations; separate from safe-stack read-only panels.  
9. **Implementer / proposal path** — rollback metadata and audit.  
10. **Autonomy** — last; separate flag and checklist.  

**Do not** set `operator_chat_live_execution: true` in production until steps 7–8 have passing tests. **Next step remains guards/tests**, not enabling live execution.

---

## 8. Explicit non-goals (this phase)

- Enabling live execution in any environment.  
- Wiring autonomy or new execute/apply buttons in safe-stack panels.  
- Calling real LLMs or external APIs from new governance tests.  
- Changing `run_operator_chat_turn` responder behavior.  

---

## 9. References

| Artifact | Path |
|----------|------|
| Brain config | `config/brain_pipeline.json` |
| Runtime entry | `project_guardian/brain/runtime.py` |
| Pipeline | `project_guardian/brain/pipeline.py` |
| Execution facade | `project_guardian/brain/execution_module.py` |
| TDA | `project_guardian/orchestration/think_decide_act.py` |
| Operator chat helper | `project_guardian/safe_stack/operator_chat.py` |
| Runtime API | `elysia/api/server.py` |
| Control panel | `project_guardian/ui_control_panel.py` |
| Architecture checkpoint | `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md` |
| Safe-stack smoke | `scripts/run_safe_stack_smoke_tests.py` |
| Live-exec guard | `project_guardian/governance/live_execution_guard.py` |
| Operator confirmation context plan | `docs/OPERATOR_CONFIRMATION_CONTEXT_PLAN.md` |
| Operator confirmation store | `project_guardian/governance/operator_confirmation_store.py` |
| Governance checkpoint (snapshot) | `docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md` |
