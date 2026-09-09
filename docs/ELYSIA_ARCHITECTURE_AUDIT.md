# Elysia Architecture Audit

Date: 2026-05-16

Scope: BrainPipeline, Think-Decide-Act, Brain/TDA adapter, conversation store, memory ranking, prompt contracts, self-improvement proposal queue, brain trace visibility, control panel trace/proposal UI, and config defaults.

## Executive Summary

Overall status: PASS WITH WARNINGS.

The recent architecture additions are mostly safe by default and covered by focused tests. The canonical data-path work is in good shape for conversation storage, memory ranking, prompt contracts, trace visibility, and self-improvement proposals. The main risks are architectural drift in naming and route/UI duplication, plus one likely control-panel JavaScript syntax defect found by inspection that the current tests do not catch.

## Area Results

| Area | Status | Notes |
| --- | --- | --- |
| Conversation store | PASS | Canonical implementation is `project_guardian/conversation_store.py`. `elysia/api/conversation_store.py` is shim-only. Runtime API imports canonical store. |
| Memory ranking | PASS | Canonical implementation is `project_guardian/memory_ranking`. `project_guardian/brain/memory_ranking.py` is a compatibility shim. No `project_guardian/memory/` package shadowing found; `project_guardian/memory.py` remains the memory module. |
| Self-improvement proposal queue | PASS | Canonical implementation is `project_guardian/self_improvement/proposal_queue.py`. Endpoints and BrainPipeline adapter delegate to that queue. |
| Prompt contracts | PASS | Canonical registry is `project_guardian/prompt_contracts/registry.py`; default contracts are in `project_guardian/prompt_contracts/default_contracts.py`. `project_guardian/module_prompt_registry.py` is an adjacent legacy prompt registry, not the prompt-contract registry. |
| Think-Decide-Act | PASS | TDA has typed stage dataclasses and returns `ThinkDecideActTrace`. It does not execute blocked actions. |
| Brain/TDA adapter | PASS | Adapter delegates validation/execution/review/remember stages through TDA when enabled. Concept map tests exist. |
| TDA trace field names | WARN | BrainPipeline stores both `think_decide_act_trace` and `tda_trace`, while persisted summaries use `think_decide_act_trace_present` and UI summaries use `tda_used`. Tests cover this, but the canonical field name should be documented or aliased intentionally. |
| Brain trace visibility | PASS | Endpoints use sanitized summaries. Raw nested TDA traces are not exposed. Endpoint is read-only. |
| Control panel trace/proposal UI | WARN | UI is review/status-only and tests cover unsafe labels, but manual inspection found a duplicated `window.openTabAndFocus = function(...) {` fragment that may break later JavaScript parsing. Add a JS parse/static lint test. |
| Config defaults | PASS | `brain_pipeline.enabled=false`, `dry_run=true`, `operator_chat=false`, `operator_chat_live_execution=false`, `autonomy=false`. Memory ranking defaults are `enabled=false`, `dry_run=true`, and delete proposals disabled. |

## Safety Defaults

Verified safe defaults:

- `config/brain_pipeline.json`
  - `enabled: false`
  - `dry_run: true`
  - `entrypoints.operator_chat: false`
  - `entrypoints.operator_chat_live_execution: false`
  - `entrypoints.autonomy: false`
- `project_guardian/brain/config.py`
  - Missing or malformed config returns safe defaults.
- `config/memory_ranking.json`
  - `enabled: false`
  - `dry_run: true`
  - `allow_delete_proposals: false`
- `project_guardian/memory_ranking/ranking.py`
  - Defaults match safe config behavior.
- Self-improvement endpoints:
  - `GET /api/self-improvement/proposals`
  - `GET /api/self-improvement/proposals/<proposal_id>`
  - `POST /api/self-improvement/proposals/<proposal_id>/status`
  - No apply, patch, shell, command, or autonomy execution route found in the self-improvement endpoint set.
- Brain trace endpoint:
  - `GET /api/brain/trace/latest`
  - Read-only; returns sanitized summary.

Important nuance:

- Direct `BrainPipeline.run(...)` defaults `dry_run` to false when called without context. The production wrapper/config path is safe/off by default, but direct internal callers can still run the pipeline's allowed execution path. This should be documented as an internal API contract or changed in a later compatibility-aware step.

## Canonical Paths

| Concept | Canonical path | Compatibility path |
| --- | --- | --- |
| Conversation store | `project_guardian/conversation_store.py` | `elysia/api/conversation_store.py` shim |
| Memory ranking | `project_guardian/memory_ranking/` | `project_guardian/brain/memory_ranking.py` shim |
| Self-improvement proposals | `project_guardian/self_improvement/proposal_queue.py` | None required |
| Prompt contracts | `project_guardian/prompt_contracts/registry.py` | None required |
| Think-Decide-Act | `project_guardian/orchestration/think_decide_act.py` | `project_guardian/brain/think_decide_act_adapter.py` adapter |
| Brain trace visibility | `project_guardian/brain/trace_visibility.py` | Used by both API/control-panel route surfaces |

## Test Coverage Map

| Feature | Test files |
| --- | --- |
| Conversation persistence and redaction | `project_guardian/tests/test_conversation_store.py` |
| Conversation canonical/shim behavior | `project_guardian/tests/test_conversation_store_consolidation.py` |
| Runtime API conversations | `project_guardian/tests/test_runtime_api_conversations.py` |
| Control panel history reload | `project_guardian/tests/test_control_panel_chat_memory.py` |
| Brain trace API/sanitization | `project_guardian/tests/test_brain_trace_visibility.py` |
| Operator chat trace hook | `project_guardian/tests/test_brain_operator_chat_hook.py` |
| Memory ranking behavior | `project_guardian/tests/test_memory_ranking.py` |
| Memory ranking import consolidation | `project_guardian/tests/test_memory_ranking_imports.py`, `project_guardian/tests/test_memory_ranking_consolidation.py` |
| Prompt contracts | `project_guardian/tests/test_prompt_contracts.py` |
| Prompt contract integration | `project_guardian/tests/test_prompt_contract_integration.py` |
| Self-improvement proposal queue/API | `project_guardian/tests/test_self_improvement_proposal_queue.py` |
| Control panel trace/proposal visibility | `project_guardian/tests/test_control_panel_brain_visibility.py` |

## Risks Found

1. WARN: TDA trace naming drift.
   - `BrainPipelineTrace` has both `tda_trace` and `think_decide_act_trace`.
   - Persisted trace uses `think_decide_act_trace_present`.
   - UI/API summaries use `tda_used`.
   - Risk: future integrations may read the wrong field or duplicate trace data.

2. WARN: Duplicate endpoint surfaces for trace/proposal visibility.
   - `elysia/api/server.py` and `project_guardian/ui_control_panel.py` both expose brain trace and self-improvement proposal routes.
   - Both appear to delegate to canonical helpers, but route logic can drift.

3. WARN: Control panel JavaScript should be parsed by tests.
   - Manual inspection found a duplicated `window.openTabAndFocus = function(tabName, elementId) {` fragment in the embedded template.
   - Current tests are string-based and do not parse JavaScript.

4. WARN: Direct BrainPipeline invocation is not dry-run by default.
   - Config/runtime wrapper defaults are safe.
   - Direct `BrainPipeline.run` defaults `dry_run` to false unless context sets it.

5. LOW: Prompt contract registry boundary should be documented.
   - `project_guardian/prompt_contracts/registry.py` is canonical for prompt contracts.
   - `project_guardian/module_prompt_registry.py` is separate legacy/adjacent prompt infrastructure.

## Recommended Fixes

1. Fix the duplicated `window.openTabAndFocus` fragment in `project_guardian/ui_control_panel.py` and add a lightweight control-panel JavaScript parse/static sanity test.
2. Document `think_decide_act_trace` as the canonical BrainPipeline field and keep `tda_trace` as a compatibility alias, or migrate callers to one name.
3. Extract shared read-only route helpers for brain trace and self-improvement proposals so `elysia/api/server.py` and `project_guardian/ui_control_panel.py` cannot drift.
4. Decide whether direct `BrainPipeline.run` should default to dry-run or whether direct execution is an explicitly internal API. Add a test documenting the decision.
5. Add one import-boundary test documenting that `project_guardian/module_prompt_registry.py` is separate from `project_guardian.prompt_contracts`.

## Tests Run

Command:

```powershell
python -m pytest project_guardian/tests/test_conversation_store.py project_guardian/tests/test_control_panel_chat_memory.py project_guardian/tests/test_control_panel_brain_visibility.py project_guardian/tests/test_brain_trace_visibility.py project_guardian/tests/test_self_improvement_proposal_queue.py project_guardian/tests/test_prompt_contract_integration.py project_guardian/tests/test_memory_ranking.py -q
```

Result:

```text
79 passed, 3 warnings
```

## Final Assessment

The architecture is safe enough to keep iterating behind defaults. No autonomy/live-execution enablement was found in the new trace/proposal visibility paths. The next highest-value fix is the control-panel JavaScript cleanup plus a parse/static test, because current UI tests verify strings and endpoints but do not prove the embedded script remains syntactically valid.
