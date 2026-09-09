# Elysia Safe-Stack Audit

Date: 2026-05-17

Scope: current safe-stack after self-improvement prompt export, memory ranking visibility, and prompt-contract controls/status were added.

This audit is documentation only. It does not change runtime behavior, wire autonomy, enable live execution, call LLMs, or apply mutations.

## Pass/Fail Summary

| Area | Result | Notes |
| --- | --- | --- |
| Safe-stack smoke script | PASS | `python scripts/run_safe_stack_smoke_tests.py` passed with 167 tests. |
| Required smoke coverage | PASS | Script includes conversation store, control-panel chat memory, brain visibility, brain trace visibility, Brain/TDA integration, TDA trace fields, self-improvement queue/export, prompt contracts/integration/controls, memory ranking/visibility/imports. |
| Safe defaults | PASS | Brain pipeline off, operator chat off, live execution off, autonomy off, prompt-contract validation off, memory ranking off, memory ranking dry-run on, deletion disabled. |
| Read-only visibility endpoints | PASS | Brain trace, memory ranking, and prompt-contract status endpoints are read-only summaries. |
| Self-improvement prompt export | PASS | Export endpoint returns copyable text only; it does not apply patches or run commands. |
| Dashboard visibility | PASS | Control panel exposes Brain Trace, Self-Improvement Proposals, Memory Ranking, and Prompt Contracts panels. |
| Duplication risk | WATCH | Runtime API and control panel mirror several routes; self-improvement and general proposal systems remain distinct but similarly named. |
| Unsafe default risk | WATCH | Separate legacy/control-panel routes for autonomy, memory cleanup, and proposal implementation still exist outside this safe-stack slice. They are not enabled by the new safe-stack additions but should stay clearly separated. |

## Smoke Result

Command:

```text
python scripts/run_safe_stack_smoke_tests.py
```

Result:

```text
167 passed, 3 warnings
```

Resolved test files:

```text
project_guardian/tests/test_conversation_store.py
project_guardian/tests/test_control_panel_chat_memory.py
project_guardian/tests/test_control_panel_brain_visibility.py
project_guardian/tests/test_control_panel_js_smoke.py
project_guardian/tests/test_brain_trace_visibility.py
project_guardian/tests/test_brain_tda_integration.py
project_guardian/tests/test_self_improvement_proposal_queue.py
project_guardian/tests/test_self_improvement_prompt_export.py
project_guardian/tests/test_prompt_contracts.py
project_guardian/tests/test_prompt_contract_integration.py
project_guardian/tests/test_memory_ranking.py
project_guardian/tests/test_memory_ranking_visibility.py
project_guardian/tests/test_prompt_contract_controls.py
project_guardian/tests/test_tda_trace_fields.py
project_guardian/tests/test_memory_ranking_imports.py
```

No required safe-stack test files were missing.

## Endpoint Inventory

Safe-stack endpoints in `elysia/api/server.py`:

| Endpoint | Method | Purpose | Safety posture |
| --- | --- | --- | --- |
| `/api/chat` | POST | Operator chat with optional BrainPipeline trace metadata | Brain trace is config-gated; operator chat dry-run is forced unless live flag is explicitly enabled. |
| `/api/chat/history` | GET | Bounded chat history | Read-only. |
| `/api/chat/history` | DELETE | Clear current conversation history | Conversation-store mutation only. |
| `/api/conversations` | GET | List conversation metadata | Read-only summary. |
| `/api/conversations` | POST | Create conversation id | Store metadata only. |
| `/api/conversations/<conversation_id>` | GET | Load sanitized messages | Read-only. |
| `/api/conversations/<conversation_id>/messages` | POST | Append sanitized message | Store write only. |
| `/api/conversations/<conversation_id>` | DELETE | Remove conversation | Store delete only. |
| `/api/brain/trace/latest` | GET | Sanitized latest BrainPipeline trace summary | Read-only; no raw TDA trace. |
| `/api/self-improvement/proposals` | GET | List sanitized proposals | Read-only. |
| `/api/self-improvement/proposals/<proposal_id>` | GET | Load proposal detail | Read-only. |
| `/api/self-improvement/proposals/<proposal_id>/status` | POST | Update review status/note | Status mutation only; no code apply. |
| `/api/self-improvement/proposals/<proposal_id>/export_prompt` | GET | Export Cursor/Codex prompt text | Read-only text export; no execution. |
| `/api/memory/ranking/summary` | GET | Advisory ranking summary from safe sources | Read-only; no memory mutation/compression/delete. |
| `/api/prompt-contracts/status` | GET | Prompt-contract config/catalog/latest validation summary | Read-only; no raw prompts or outputs. |

Mirrored safe-stack routes in `project_guardian/ui_control_panel.py`:

- `/api/brain/trace/latest`
- `/api/self-improvement/proposals`
- `/api/self-improvement/proposals/<proposal_id>`
- `/api/self-improvement/proposals/<proposal_id>/status`
- `/api/self-improvement/proposals/<proposal_id>/export_prompt`
- `/api/memory/ranking/summary`
- `/api/prompt-contracts/status`
- `/api/chat`, `/api/chat/history`, `/api/conversations*`

Important adjacent routes outside this safe stack:

- `elysia/api/server.py` has general proposal routes such as `/api/proposals/<proposal_id>/implement`.
- `project_guardian/ui_control_panel.py` has autonomy/control routes such as `/api/autonomy`, `/api/autonomy/execute-cycle`, and memory maintenance routes such as `/api/memory/cleanup`.
- These were not added by the recent safe-stack visibility work and are not exercised by the smoke script.

## Dashboard Panel Inventory

Control panel safe-stack visibility:

| Panel/section | Data source | Actions shown |
| --- | --- | --- |
| Conversation chat | `/api/chat`, `/api/chat/history`, `/api/conversations` | Send message, load/create/clear conversation history. |
| Brain Trace | `/api/brain/trace/latest` | Refresh trace summary only. |
| Self-Improvement Proposals | `/api/self-improvement/proposals*` | Refresh proposals, inspect detail, update review status, export Cursor/Codex prompt. No apply/run button in this panel. |
| Memory Ranking | `/api/memory/ranking/summary` | Refresh ranking summary only. |
| Prompt Contracts | `/api/prompt-contracts/status` | Refresh validation status only. |

## Safe Defaults

Source: `config/brain_pipeline.json`, `config/memory_ranking.json`, and matching dataclass defaults.

Brain pipeline:

```text
brain_pipeline.enabled = false
brain_pipeline.dry_run = true
brain_pipeline.use_think_decide_act = true
brain_pipeline.entrypoints.operator_chat = false
brain_pipeline.entrypoints.operator_chat_live_execution = false
brain_pipeline.entrypoints.tool_execution = false
brain_pipeline.entrypoints.autonomy = false
brain_pipeline.entrypoints.diagnostic = false
```

Prompt-contract validation:

```text
brain_pipeline.prompt_contract_validation.enabled = false
brain_pipeline.prompt_contract_validation.mode = warn
brain_pipeline.prompt_contract_validation.operator_chat = false
```

Runtime rule:

```text
run_brain_pipeline_for_operator_event(...) bypasses when brain_pipeline.enabled is false or the entrypoint is disabled.
operator_chat dry_run is forced true unless entrypoints.operator_chat_live_execution is true.
strict prompt-contract mode is downgraded to warn when dry_run is not true.
```

Memory ranking:

```text
memory_ranking.enabled = false
memory_ranking.dry_run = true
memory_ranking.allow_delete_proposals = false
```

Visibility helpers:

```text
/api/brain/trace/latest does not expose raw TDA trace.
/api/memory/ranking/summary does not mutate, compress, archive, or delete memory.
/api/prompt-contracts/status does not expose raw prompts, raw model outputs, scratchpads, or hidden reasoning.
/api/self-improvement/proposals/<id>/export_prompt returns copyable prompt text only.
```

## Duplication Risks

| Risk | Status | Recommended cleanup |
| --- | --- | --- |
| Runtime API vs control panel mirrored routes | Present | Keep mirrored route tests. Longer term, route both hosts through small shared helper functions for trace/proposal/ranking/prompt-contract responses. |
| Self-improvement proposals vs general proposals | Present | Keep naming explicit in docs/UI: `/api/self-improvement/proposals` is review-only; `/api/proposals` can include implementation flows. |
| Conversation history paths | Present | Canonical store is `project_guardian/conversation_store.py`; legacy control-panel history helpers still exist. Continue consolidating callers to the canonical store. |
| Memory ranking brain shim | Controlled | `project_guardian/brain/memory_ranking.py` should remain shim-only; new imports should use `project_guardian.memory_ranking`. |
| Prompt-contract status helpers | Controlled | `project_guardian.prompt_contracts.controls` owns config/context/status behavior; `project_guardian.prompt_contracts.status` is a compatibility facade. Avoid adding another status implementation. |
| TDA trace field naming | Controlled | Canonical field is `think_decide_act_trace`; compact visibility uses `tda_used`. Alias tests cover drift. |

## Unsafe Default Risks

No unsafe defaults were found in the newly audited safe-stack additions.

Residual risks outside the safe-stack additions:

- `project_guardian/ui_control_panel.py` includes existing autonomy and control routes; keep them out of safe-stack smoke and clearly label them separately.
- `elysia/api/server.py` includes general proposal implementation routes; do not confuse these with the self-improvement proposal queue.
- Memory maintenance endpoints such as cleanup/rebuild are separate from read-only memory ranking visibility.
- If `operator_chat_live_execution` is enabled in the future, strict prompt-contract blocking and explicit operator authorization need a separate live-execution test slice.

## Recommended Next Fixes

1. Add a route/helper consolidation pass for shared read-only status surfaces so Runtime API and Control Panel do not drift.
2. Rename or visually separate general `/api/proposals` implementation routes from review-only `/api/self-improvement/proposals` in docs and UI copy.
3. Finish conversation history consolidation by reducing reliance on legacy `control_panel_chat_history.json` helpers.
4. Add a negative smoke assertion that safe-stack UI panels do not expose apply/run/delete/autonomy controls in their local panel blocks.
5. Add a future live-execution governance test plan, but keep it out of the current safe-stack runner until live execution is intentionally designed.

## Files Inspected

- `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md`
- `scripts/run_safe_stack_smoke_tests.py`
- `elysia/api/server.py`
- `project_guardian/ui_control_panel.py`
- `project_guardian/self_improvement/`
- `project_guardian/memory_ranking/`
- `project_guardian/prompt_contracts/`
- `project_guardian/brain/`
- `config/brain_pipeline.json`
- `config/memory_ranking.json`
