# API Host State Consolidation Audit

Date: 2026-05-17

> **Superseded audit note (2026-05-18):** This file is retained as the
> pre-consolidation state audit. The current source of truth is
> `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md` and
> `docs/API_HOST_FINAL_CONSOLIDATION_AUDIT.md`.
>
> Current state: shared response helpers are in use on both hosts, prompt export
> response shape is normalized through `project_guardian/safe_stack/responses.py`,
> both general chat routes use `project_guardian/safe_stack/operator_chat.py`, and
> UI chat supports config-gated BrainPipeline dry-run metadata. Sections below that
> describe helper extraction, parity tests, or prompt export normalization as future
> work are historical.

Scope: duplicated API host behavior across `elysia.api.server.RuntimeAPIServer` and
`project_guardian.ui_control_panel.UIControlPanel`, focused on the current safe-stack
features. This audit is read-only and does not change runtime behavior.

## Summary

Status: **historical pass with consolidation risks; superseded by final audit**

Both API hosts reuse the canonical implementation modules for the safe-stack state
objects. The main risk is not duplicate core storage code; it is duplicated route
handling across two Flask hosts with slightly different dependency injection and
response-shaping behavior.

No unsafe default was found in the audited config:

- `brain_pipeline.enabled`: `false`
- `brain_pipeline.dry_run`: `true`
- `entrypoints.operator_chat`: `false`
- `entrypoints.operator_chat_live_execution`: `false`
- `entrypoints.autonomy`: `false`
- `prompt_contract_validation.enabled`: `false`
- `prompt_contract_validation.operator_chat`: `false`

## Hosts Found

### Runtime API Host

File: `elysia/api/server.py`

Class: `RuntimeAPIServer`

Default bind: `127.0.0.1:8123`

Purpose: runtime-facing JSON API for chat, conversations, status, safe-stack
visibility, proposals, and related runtime features.

State injection:

- Accepts an injected `conversation_store`.
- Accepts an injected `self_improvement_queue`.
- Falls back to canonical default helpers when no injection is provided.

### Control Panel Host

File: `project_guardian/ui_control_panel.py`

Class: `UIControlPanel`

Default bind: `127.0.0.1:5000`

Purpose: operator dashboard and browser control panel, including chat UI,
safe-stack visibility panels, and operator review controls.

State construction:

- Constructs a canonical `ConversationStore` in `__init__`.
- Can derive the conversation directory from `orchestrator.conversation_store_dir`.
- Uses the default self-improvement proposal queue helper directly.
- Imports legacy JSON chat history into the canonical conversation store once.

## Route Inventory By Host

### Runtime API Host

| Route | Method | Feature | State/helper used |
| --- | --- | --- | --- |
| `/api/chat` | POST | Operator chat | `_runtime_conversation_store()`, optional brain dry-run trace |
| `/api/chat/history` | GET | Chat history | `_runtime_conversation_store().list_messages()` |
| `/api/chat/history` | DELETE | Clear chat history | `_runtime_conversation_store().delete_conversation()` |
| `/api/conversations` | GET | Conversation list | `_runtime_conversation_store().list_conversations()` |
| `/api/conversations` | POST | Conversation id creation | `_runtime_conversation_store().new_conversation_id()` |
| `/api/conversations/<conversation_id>` | GET | Conversation messages | `_runtime_conversation_store().list_messages()` |
| `/api/conversations/<conversation_id>` | DELETE | Delete conversation | `_runtime_conversation_store().delete_conversation()` |
| `/api/conversations/<conversation_id>/messages` | POST | Append message | `_runtime_conversation_store().append_message()` |
| `/api/brain/trace/latest` | GET | Brain trace summary | `load_latest_brain_trace_summary(get_brain_pipeline_config())` |
| `/api/self-improvement/proposals` | GET | Proposal list | `_self_improvement_queue_impl().list_latest()`, `sanitize_proposal()` |
| `/api/self-improvement/proposals/<proposal_id>` | GET | Proposal detail | `_self_improvement_queue_impl().get()`, `sanitize_proposal()` |
| `/api/self-improvement/proposals/<proposal_id>/status` | POST | Review status update | `_self_improvement_queue_impl().update_status()` |
| `/api/self-improvement/proposals/<proposal_id>/export_prompt` | GET | Copyable prompt export | `normalize_target()`, `proposal_prompt_to_dict()` |
| `/api/memory/ranking/summary` | GET | Read-only memory ranking summary | `load_memory_ranking_visibility(conversation_store=...)` |
| `/api/prompt-contracts/status` | GET | Prompt-contract status | `build_prompt_contract_status()` |

Adjacent routes outside the safe-stack visibility surface also exist in this host,
including general proposal implementation-preview routes. Those are separate from
the self-improvement proposal queue reviewed here.

### Control Panel Host

| Route | Method | Feature | State/helper used |
| --- | --- | --- | --- |
| `/api/chat` | POST | Operator chat | `run_operator_chat_turn` via `_handle_control_panel_operator_chat`; `safe_stack/operator_chat` *(was inline append/prompt — obsolete)* |
| `/api/chat/history` | GET | Chat history | `self._chat_history_for_response()` |
| `/api/chat/history` | DELETE | Clear chat history | `self._clear_chat_history()` |
| `/api/conversations` | GET | Conversation list | `self._conversation_store.list_conversations()` |
| `/api/conversations` | POST | Conversation id creation | `self._conversation_store.new_conversation_id()` |
| `/api/conversations/<conversation_id>` | GET | Conversation messages | `self._conversation_store.list_messages()` |
| `/api/conversations/<conversation_id>` | DELETE | Delete conversation | `self._conversation_store.delete_conversation()` |
| `/api/conversations/<conversation_id>/messages` | POST | Append message | `self._conversation_store.append_message()` |
| `/api/brain/trace/latest` | GET | Brain trace summary | `load_latest_brain_trace_summary(get_brain_pipeline_config())` |
| `/api/self-improvement/proposals` | GET | Proposal list | `get_default_proposal_queue().list_latest()`, `sanitize_proposal()` |
| `/api/self-improvement/proposals/<proposal_id>` | GET | Proposal detail | `get_default_proposal_queue().get()`, `sanitize_proposal()` |
| `/api/self-improvement/proposals/<proposal_id>/status` | POST | Review status update | `get_default_proposal_queue().update_status()` |
| `/api/self-improvement/proposals/<proposal_id>/export_prompt` | GET | Copyable prompt export | `normalize_target()`, `proposal_prompt_to_dict()` |
| `/api/memory/ranking/summary` | GET | Read-only memory ranking summary | `load_memory_ranking_visibility(conversation_store=self._conversation_store)` |
| `/api/prompt-contracts/status` | GET | Prompt-contract status | `build_prompt_contract_status()` |

The control panel host also exposes autonomy, control, memory maintenance,
research, diagnostics, and learning routes. Those routes are not part of this
safe-stack state consolidation audit.

## State Paths Used By Each Route

| State | Canonical path | Runtime API host | Control panel host |
| --- | --- | --- | --- |
| Conversation JSONL | `data/runtime/conversations/` | Injected store or `get_default_conversation_store()` | `ConversationStore(...)`, defaulting to canonical dir or `orchestrator.conversation_store_dir` |
| Legacy control-panel chat import | `data/runtime/control_panel_chat_history.json` | Not used | Imported once into canonical conversation store |
| Brain pipeline trace | `data/runtime/brain_last_pipeline.json` from `config/brain_pipeline.json` | Shared helper | Shared helper |
| Self-improvement queue | `data/runtime/self_improvement_proposals.jsonl` | Injected queue or `get_default_proposal_queue()` | `get_default_proposal_queue()` |
| Legacy brain self-improvement queue | `data/runtime/brain_self_improvement_queue.jsonl` | Canonical queue can import/adapt legacy records | Canonical queue can import/adapt legacy records |
| Memory ranking config | `config/memory_ranking.json` | Visibility helper | Visibility helper |
| Prompt-contract config/status | `config/brain_pipeline.json` and latest brain trace | Controls helper | Controls helper |

## Canonical Helpers Used

### Conversation History

Canonical module: `project_guardian.conversation_store`

Used by both hosts.

Runtime API:

- Uses `_runtime_conversation_store()`.
- Supports constructor injection.
- Falls back to `get_default_conversation_store()`.

Control panel:

- Uses canonical `ConversationStore`.
- Constructs its own store instance in `UIControlPanel.__init__`.
- Supports an orchestrator-provided conversation directory.

Assessment: **shared canonical implementation, but host-level store selection can split state.**

### Brain Trace Summary

Canonical module: `project_guardian.brain.trace_visibility`

Function: `load_latest_brain_trace_summary()`

Used by both hosts with `get_brain_pipeline_config()`.

Assessment: **shared canonical helper.**

### Self-Improvement Proposals

Canonical module: `project_guardian.self_improvement.proposal_queue`

Used by both hosts.

Runtime API:

- Uses injected queue or default queue.

Control panel:

- Uses default queue directly.

Assessment: **shared canonical implementation, but injection behavior is asymmetric.**

### Proposal Prompt Export

Canonical module: `project_guardian.self_improvement.prompt_export`

Functions:

- `normalize_target()`
- `proposal_prompt_to_dict()`

Used by both hosts.

Assessment: **shared canonical prompt builder, but response shape differs.**

Runtime API returns the prompt payload directly. Control panel returns the prompt
payload with an additional `success: true` wrapper.

### Memory Ranking Summary

Canonical module: `project_guardian.memory_ranking.visibility`

Function: `load_memory_ranking_visibility()`

Used by both hosts.

Runtime API passes the runtime conversation store. Control panel passes its own
conversation store instance.

Assessment: **shared canonical helper, but summaries can diverge when host stores differ.**

### Prompt-Contract Status

Canonical modules:

- `project_guardian.prompt_contracts.controls`
- `project_guardian.prompt_contracts.status`

Both hosts currently call `controls.build_prompt_contract_status()` directly.
`status.py` is a read-only facade around the controls helper.

Assessment: **shared implementation, but hosts bypass the status facade.**

## Duplication Risks

1. **Two Flask hosts duplicate safe-stack route handlers.**
   The core modules are canonical, but route parsing, error handling, limit handling,
   and response shaping are duplicated.

2. **Conversation store selection can diverge.**
   Runtime API accepts an injected store. Control panel constructs its own store.
   If one host is given a custom directory or injected test store, conversation
   history and memory-ranking visibility can disagree.

3. **Self-improvement queue injection is asymmetric.**
   Runtime API supports an injected queue. Control panel uses the default queue
   directly. Tests or future deployments that inject runtime state will not
   automatically affect the control panel.

4. **Prompt export response shape differs by host.**
   Runtime API returns the exported prompt dictionary directly. Control panel adds
   `success: true`. The prompt content is shared, but clients may need host-specific
   parsing.

5. **Prompt-contract status facade is not consistently used.**
   `project_guardian.prompt_contracts.status` exists, but both hosts import from
   `controls` directly. This is a small drift risk if status behavior later moves
   behind the facade.

6. **UI chat has additional memory side effects.**
   Control panel chat can call `orchestrator.memory.remember()` after storing the
   conversation exchange. Runtime API chat stores the conversation but does not
   mirror that optional memory write path.

7. **Legacy chat state remains present.**
   The control panel still has a legacy JSON history import path. It appears to be
   a compatibility path, but it should stay covered by tests so it does not become
   a second active history store.

8. **Adjacent non-safe routes can be confused with safe-stack routes.**
   General proposal implementation routes and control-panel autonomy routes exist.
   They are not part of the read-only safe-stack visibility surface and should be
   named and tested distinctly.

## Unsafe Default Risks

No unsafe safe-stack default was found in the audited configuration.

Confirmed defaults in `config/brain_pipeline.json`:

- BrainPipeline disabled by default.
- Dry run enabled by default.
- Operator chat hook disabled by default.
- Operator chat live execution disabled by default.
- Autonomy entrypoint disabled by default.
- Prompt-contract validation disabled by default.
- Prompt-contract operator-chat validation disabled by default.

Confirmed route behavior:

- Brain trace endpoint is read-only.
- Memory ranking endpoint is read-only and advisory.
- Self-improvement prompt export endpoint returns text only.
- Self-improvement proposal status endpoint only updates review status/note.
- Prompt-contract status endpoint is read-only.

Residual safety concern: the same hosts expose other non-safe-stack routes. Keep
tests explicit about which route family is read-only and which route family is not
part of the safe-stack dashboard.

## Recommended Consolidation Approach

> **Done (2026-05-18):** Steps 1–2 and operator-chat unification are implemented via `safe_stack/responses.py` and `safe_stack/operator_chat.py`. Parity tests live in `test_api_host_route_parity.py` and operator-chat integration tests. Blueprint extraction remains **optional**.

Do not merge the two hosts first. Start by extracting response-building helpers so
both hosts remain thin wrappers around the same state and serialization behavior.

Recommended sequence:

1. Add a small shared safe-stack API helper module, for example
   `project_guardian.safe_stack_api` or `project_guardian.api_state_helpers`.

2. Move only pure response-building behavior into that helper:
   - conversation list/detail/history responses
   - brain trace latest response
   - self-improvement proposal list/detail/status responses
   - self-improvement prompt export response
   - memory ranking summary response
   - prompt-contract status response

3. Add dependency injection parity to `UIControlPanel`:
   - accept an optional `conversation_store`
   - accept an optional `self_improvement_queue`
   - default to the current canonical paths when not provided

4. Normalize prompt export response shape across both hosts.
   Decide whether the canonical API includes `success: true`, then test both hosts
   against that schema.

5. Route both hosts through the same prompt-contract status facade.
   Prefer `project_guardian.prompt_contracts.status.build_prompt_contract_status`
   or make the facade the single documented import path.

6. Keep runtime defaults unchanged.
   Consolidation should reduce duplicate route logic without enabling BrainPipeline,
   operator chat trace, live execution, autonomy, compression, deletion, or proposal
   implementation behavior.

## Tests To Add Before Changing Code

> **Status:** `project_guardian/tests/test_api_host_route_parity.py` and operator-chat integration tests **exist** and run in the smoke slice (**227** tests). The list below was the pre-implementation checklist.

Add a parity suite before production consolidation, for example
`project_guardian/tests/test_api_host_state_parity.py` *(implemented as `test_api_host_route_parity.py`)*.

Recommended tests:

1. **Conversation parity**
   With both hosts pointed at the same temp `ConversationStore`, append through one
   host and read through the other.

2. **Conversation history response parity**
   Verify `/api/chat/history`, `/api/conversations`, and
   `/api/conversations/<id>` return equivalent sanitized fields.

3. **Self-improvement proposal parity**
   With both hosts using the same temp proposal queue, compare list, detail, status
   update, and prompt export responses.

4. **Prompt export schema parity**
   Lock the canonical response shape so `success` wrapping does not drift.

5. **Brain trace parity**
   With a temp trace path/config, verify both `/api/brain/trace/latest` routes
   return the same sanitized summary and no raw TDA trace.

6. **Memory ranking parity**
   With the same temp conversation store, verify both memory-ranking endpoints return
   the same advisory counts and ranked summaries.

7. **Prompt-contract status parity**
   With the same temp brain trace/config, verify both status endpoints return compact,
   sanitized validation summaries.

8. **Error parity**
   Compare missing conversation, missing proposal, invalid status, malformed trace,
   and unsupported prompt-export target behavior.

9. **Legacy import safety**
   Confirm the control panel legacy history import does not duplicate messages when
   canonical JSONL history already exists.

10. **Safe-stack boundary**
    Assert these read-only visibility routes do not call proposal implementation,
    shell execution, autonomy triggers, compression application, deletion, or real
    LLM/external APIs.

## Smoke Test

Command requested:

```text
python scripts/run_safe_stack_smoke_tests.py
```

Result at audit time (2026-05-17):

```text
167 passed, 3 warnings
```

**Current (post operator-chat wiring):** **227 passed** — see [`API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`](API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md). The script does not enable autonomy or live execution.
