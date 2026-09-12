# API Host Final Consolidation Audit

**Date:** 2026-05-18  
**Status:** Pass for safe-stack consolidation (companion to checkpoint)  
**Scope:** RuntimeAPIServer, UIControlPanel, shared safe-stack response helpers, shared operator-chat helper

**Source of truth (summary):** [`API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`](API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md) — use the checkpoint for operator guidance and next steps; this audit adds verification detail.

This audit records the final state after both HTTP hosts were wired through shared helpers for safe-stack visibility routes and general operator chat. It does not propose or enable autonomy, live execution, real LLM calls, or external API calls.

---

## 1. Shared Helper Inventory

### `project_guardian/safe_stack/responses.py`

Both `elysia/api/server.py` and `project_guardian/ui_control_panel.py` call the same framework-neutral builders for mirrored safe-stack routes:

| Helper | Route behavior |
|--------|----------------|
| `build_chat_history_response` | GET `/api/chat/history` |
| `build_chat_history_clear_response` | DELETE `/api/chat/history` |
| `build_conversations_list_response` | GET `/api/conversations` |
| `build_conversation_create_response` | POST `/api/conversations` |
| `build_conversation_detail_response` | GET `/api/conversations/<conversation_id>` |
| `build_conversation_delete_response` | DELETE `/api/conversations/<conversation_id>` |
| `build_brain_trace_latest_response` | GET `/api/brain/trace/latest` |
| `build_memory_ranking_summary_response` | GET `/api/memory/ranking/summary` |
| `build_prompt_contracts_status_response` | GET `/api/prompt-contracts/status` |
| `build_self_improvement_proposals_list_response` | GET `/api/self-improvement/proposals` |
| `build_self_improvement_proposal_detail_response` | GET `/api/self-improvement/proposals/<proposal_id>` |
| `build_self_improvement_proposal_status_update_response` | POST `/api/self-improvement/proposals/<proposal_id>/status` |
| `build_self_improvement_prompt_export_response` | GET `/api/self-improvement/proposals/<proposal_id>/export_prompt` |

These helpers keep response shapes, redaction, read-only summaries, and self-improvement prompt export envelopes aligned across both hosts.

### `project_guardian/safe_stack/operator_chat.py`

Both general chat paths call `run_operator_chat_turn`:

- RuntimeAPIServer: `elysia/api/server.py` uses `_handle_runtime_general_chat`.
- UIControlPanel: `project_guardian/ui_control_panel.py` uses `_handle_control_panel_operator_chat`.

The helper owns:

- conversation id normalization
- bounded history loading
- prompt context assembly
- optional fail-open BrainPipeline trace callback
- callback-based responder invocation
- user and assistant persistence
- compact brain metadata merging
- secret and raw trace metadata filtering
- optional host `after_persist_callback`

The helper does not import Flask, call LLM providers, call shell/subprocess, apply patches, trigger autonomy, or implement proposals.

### Canonical state helpers

| Concern | Canonical implementation |
|---------|--------------------------|
| Conversation history | `project_guardian/conversation_store.py` |
| Self-improvement proposals | `project_guardian/self_improvement/proposal_queue.py` |
| Proposal prompt export | `project_guardian/self_improvement/prompt_export.py` |
| Brain trace visibility | `project_guardian/brain/trace_visibility.py` |
| Memory ranking visibility | `project_guardian/memory_ranking/visibility.py` |
| Prompt-contract status | `project_guardian/prompt_contracts/status.py`, backed by `controls.py` |

---

## 2. Runtime vs UI Chat Comparison

| Dimension | RuntimeAPIServer | UIControlPanel |
|-----------|------------------|----------------|
| Shared helper | `run_operator_chat_turn` | `run_operator_chat_turn` |
| Route file | `elysia/api/server.py` | `project_guardian/ui_control_panel.py` |
| Request fields | `message`, `context`, optional `conversation_id`; may use `elysia_conversation_id` cookie | `message`, optional `conversation_id` or `session_id` |
| Default conversation id | New sanitized UUID when body/cookie missing | Sanitized `control_panel` when body/session missing |
| Session transport | Response sets `elysia_conversation_id` cookie | Frontend localStorage sends conversation id in body |
| Responder | `_architect_chat(composed_prompt, context)` or echo fallback | `chat_with_llm(composed_prompt)` then `ask_ai(composed_prompt)` |
| Response envelope | `response`, `reply`, `conversation_id`, extra architect fields, optional compact `brain_*` | `success`, `reply`, `error`, `conversation_id`, `history`, optional compact `brain_*` |
| Prompt history limit | 20 messages / 8000 chars | 10 messages / 6000 chars |
| POST response history | Not included | Included and capped |
| Brain trace | Config-gated callback, fail-open, compact metadata only | Same config-gated callback, fail-open, compact metadata only |
| Memory side effect | Runtime event bus only | `after_persist_callback` preserves `orchestrator.memory.remember` |
| Proposal chat branch | `context: proposal:<id>` remains outside helper | Not present |
| Store-unavailable behavior | Has no-store fallback | Panel constructs a local ConversationStore |

The remaining differences are intentional host adapters, not duplicated orchestration logic.

---

## 3. Route Parity Status

**Pass.** Mirrored safe-stack routes are registered on both hosts and use shared response helpers for stateful read/status behavior.

| Route family | RuntimeAPIServer | UIControlPanel | Shared logic |
|--------------|------------------|----------------|--------------|
| Conversation list/create/detail/delete | Yes | Yes | `safe_stack.responses` + `ConversationStore` |
| Chat history get/clear | Yes | Yes | `safe_stack.responses` + `ConversationStore` |
| Brain trace latest | Yes | Yes | `safe_stack.responses` + brain trace visibility |
| Memory ranking summary | Yes | Yes | `safe_stack.responses` + memory ranking visibility |
| Prompt-contract status | Yes | Yes | `safe_stack.responses` + prompt-contract status |
| Self-improvement list/detail/status/export | Yes | Yes | `safe_stack.responses` + proposal queue/export |
| General `POST /api/chat` | Yes | Yes | `safe_stack.operator_chat`, host envelope adapters |

Intentional exclusions:

- Runtime-only `/api/proposals/*` routes remain outside the safe stack.
- Runtime `context: proposal:<id>` chat branch remains outside `run_operator_chat_turn`.
- `POST /api/conversations/<conversation_id>/messages` is still implemented inline in both hosts, though both write through `ConversationStore`.

---

## 4. Remaining Host-Specific Behavior

| Behavior | Reason / impact |
|----------|-----------------|
| Different ports: UI default `:5000`, runtime default `:8123` | Operators can still perceive two surfaces. Shared disk state reduces data drift, but UX remains split by host. |
| Runtime cookie vs UI localStorage | Same store can be used when the same conversation id is supplied, but default sessions differ. |
| Different chat response envelopes | Preserves existing runtime clients and dashboard JS. |
| Different responders | Runtime remains Architect-Core oriented; UI remains unified/ask_ai oriented. |
| UI memory write side effect | Preserved through `after_persist_callback`; runtime does not write Guardian memory from chat. |
| Runtime event bus emission | Preserved as runtime-specific behavior. |
| Runtime proposal chat branch | Kept outside safe stack to avoid mixing implementation/proposal flows with operator chat persistence. |
| Duplicate `_maybe_run_brain_operator_chat_trace` methods | Same behavior exists in two host classes. This is low-risk but still a cleanup candidate. |
| Thin Flask route wrappers | The real logic is shared, but route registration remains duplicated. A blueprint is optional later. |
| Older docs may still contain pre-helper notes | `API_HOST_STATE_CONSOLIDATION_PLAN.md` includes historical phase notes; this audit and the final checkpoint are the current sources of truth. |

---

## 5. Safety Boundaries

**Safe defaults verified from config:**

- `brain_pipeline.enabled`: `false`
- `brain_pipeline.dry_run`: `true`
- `brain_pipeline.entrypoints.operator_chat`: `false`
- `brain_pipeline.entrypoints.operator_chat_live_execution`: `false`
- `brain_pipeline.entrypoints.autonomy`: `false`
- `brain_pipeline.prompt_contract_validation.enabled`: `false`
- `memory_ranking.enabled`: `false`
- `memory_ranking.dry_run`: `true`
- `memory_ranking.allow_delete_proposals`: `false`

**Boundary checks:**

- Operator chat helper is callback-based and does not call real LLM providers itself.
- Brain trace callbacks are config-gated and fail open.
- Chat trace metadata is compact `brain_*` only; raw `think_decide_act_trace`, `tda_trace`, `raw_trace`, and nested trace blobs are stripped from storage metadata.
- ConversationStore handles text redaction before persistence.
- Memory ranking endpoint is read-only and returns advisory summaries only.
- Self-improvement safe-stack routes list, view, update status, and export prompts only. They do not apply patches, run commands, or execute proposals.
- Prompt-contract status route is read-only and does not expose raw prompts or model outputs.
- Runtime-only proposal implementation routes remain outside the safe-stack route parity set.

---

## 6. Tests and Smoke Result

Command run:

```bash
python scripts/run_safe_stack_smoke_tests.py
```

Result:

```text
247 passed, 3 warnings in 4.39s
```

The smoke script includes the current consolidation coverage:

- `test_operator_chat_helper.py`
- `test_runtime_operator_chat_helper_integration.py`
- `test_control_panel_operator_chat_helper_integration.py`
- `test_api_host_route_parity.py`
- `test_safe_stack_response_helpers.py`
- conversation store and control-panel chat memory tests
- brain trace and Brain/TDA integration tests
- self-improvement proposal queue and prompt export tests
- prompt contracts, prompt contract integration, and prompt contract controls tests
- memory ranking, memory ranking visibility, and memory ranking import tests
- TDA trace field tests

No real LLM/API calls, autonomy, live execution, service startup, proposal implementation, shell execution from app code, or memory mutation/compression/deletion is enabled by this smoke slice.

---

## 7. Is A Shared Blueprint Still Needed?

**No, not for the current safe-stack goal.**

The important business logic is already consolidated:

- response builders for mirrored safe-stack routes
- operator chat orchestration
- conversation storage
- proposal queue and prompt export
- trace, memory ranking, and prompt-contract visibility helpers

A shared Flask blueprint would still reduce thin route-registration duplication, but it is optional. It becomes worthwhile if:

- a third API host is added,
- route registration drift returns,
- a single plug-in route pack becomes easier to maintain than the current host adapters.

For now, the helper-based design keeps the hosts flexible while centralizing the risky state and response behavior.

---

## 8. Recommended Next Cleanup

1. **Refresh older consolidation docs.** Mark historical sections in `API_HOST_STATE_CONSOLIDATION_PLAN.md` as superseded by this audit and `API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`.

2. **Extract shared brain trace callback logic.** Move the duplicate `_maybe_run_brain_operator_chat_trace` logic into a small helper while preserving host-specific guardian lookup.

3. **Add a shared `build_conversation_append_response`.** This would remove the last small duplicated conversation route body for `POST /api/conversations/<conversation_id>/messages`.

4. **Keep response envelopes intentionally host-specific unless a client needs parity.** Converging `POST /api/chat` envelopes would be a product/API contract change, not a safety cleanup.

5. **Defer blueprint extraction.** Keep it as an optional later simplification, not a required safety fix.

---

## 9. Final Audit Summary

| Area | Status |
|------|--------|
| Shared response helpers | Pass |
| Shared operator chat helper | Pass |
| Runtime general chat wired | Pass |
| UI general chat wired | Pass |
| Safe-stack route parity | Pass |
| Chat safety defaults | Pass |
| Memory ranking read-only visibility | Pass |
| Self-improvement prompt export safety | Pass |
| Prompt-contract status safety | Pass |
| Autonomy/live execution defaults | Pass |
| Remaining risks | Low to medium, mostly docs/route-wrapper cleanup |
