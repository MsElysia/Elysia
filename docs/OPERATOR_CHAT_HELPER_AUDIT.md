# Operator Chat Helper Audit

**Date:** 2026-05-17
**Status:** Historical audit; implementation is now complete.
**Scope:** `POST /api/chat` behavior in `RuntimeAPIServer` and `UIControlPanel`.

> **Superseded audit note (2026-05-18):** This file is retained as the original
> design audit for the operator-chat helper. The current source of truth is
> `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md` and
> `docs/API_HOST_FINAL_CONSOLIDATION_AUDIT.md`.
>
> Current state: `project_guardian/safe_stack/operator_chat.py` exists, both
> RuntimeAPIServer and UIControlPanel general `POST /api/chat` routes use it,
> response envelopes remain host-specific by design, and UI chat can receive
> config-gated BrainPipeline dry-run metadata. Sections below that say the helper
> should still be implemented, runtime/UI routes are not migrated, or UI has no
> BrainPipeline hook are historical.

## Summary

`POST /api/chat` was the most important safe-stack behavior split between the runtime API host and the control-panel host when this audit was written.

Both hosts use the canonical `project_guardian.conversation_store.ConversationStore` for durable chat history, redaction, and bounded transcript assembly. They differ in response envelopes, session identity, backend callbacks, BrainPipeline tracing, proposal handling, and memory side effects.

The implemented framework-neutral helper is at:

`project_guardian/safe_stack/operator_chat.py`

The helper owns shared mechanics only: message validation, conversation id normalization, history loading, prompt composition, optional dry-run BrainPipeline metadata, persistence, and compact result assembly. Hosts keep their Flask routes, response shapes, cookie/localStorage behavior, and backend selection.

## Hosts Compared

| Host | File | Current role |
|------|------|--------------|
| RuntimeAPIServer | `elysia/api/server.py` | API-only host, Architect-Core chat, config-gated BrainPipeline dry-run hook, cookie conversation id |
| UIControlPanel | `project_guardian/ui_control_panel.py` | Dashboard host, same-origin chat for UI, unified LLM / `ask_ai` fallback, localStorage conversation id |

## Behavior Comparison

| Dimension | RuntimeAPIServer `POST /api/chat` | UIControlPanel `POST /api/chat` |
|-----------|-----------------------------------|----------------------------------|
| Request fields | JSON `message` required, `context` default `"general"`, optional `conversation_id`; cookie fallback `elysia_conversation_id` | JSON `message` required, optional `conversation_id` or `session_id`; no `context` field used |
| JSON parsing | `request.get_json(force=True, silent=True) or {}` | `request.get_json() or {}` |
| Empty message | `400 {"error": "message is required"}` | `400 {"error": "message is required"}` |
| Response fields | Architect path returns backend dict plus `conversation_id` and `reply`; echo fallback returns `response`, `status`, `conversation_id`, `reply`; optional compact `brain_*` metadata | Success returns `success`, `reply`, `error`, `conversation_id`, `history`; LLM backend errors return HTTP 200 with `success: false` |
| Default conversation id | Body id, then cookie, then new UUID | Body id, then `session_id`, then `"control_panel"` |
| Session transport | Sets `elysia_conversation_id` cookie for one year | Frontend stores id in localStorage key `elysia_control_panel_conversation_id` |
| History persistence | Persists user and assistant rows after architect or echo reply | Persists user and assistant rows after successful unified LLM or `ask_ai` reply |
| History context passed to backend | `build_recent_transcript(..., max_messages=20, max_chars=8000)` plus current message | `build_recent_transcript(..., max_messages=10, max_chars=6000)` plus current message |
| Backend callback | `_architect_chat(composed, context)` or echo fallback | `_get_unified_system().chat_with_llm(prompt)` or `orchestrator.ask_ai(prompt)` |
| BrainPipeline dry-run hook | Yes, when `brain_pipeline.enabled` and `entrypoints.operator_chat` are true | Superseded: UIControlPanel now has the same config-gated, fail-open dry-run hook through the shared helper |
| Brain trace persistence | Assistant metadata gets allowlisted scalar `brain_*` keys only | Superseded: UI chat now also supports config-gated compact `brain_*` metadata through the shared helper |
| Brain trace failure | Warning, chat continues with compact `brain_trace_error` | Not applicable |
| Proposal branch | `context.startswith("proposal:")` returns proposal status and skips store/brain/backend | No proposal branch |
| Memory side effects | No `memory.remember` call | Calls `orchestrator.memory.remember(..., category="conversation")` after successful reply if available |
| Event side effects | Emits EventBus `"api"/"chat"` event | No EventBus emission in chat handler |
| Store failure behavior | History/persist failures log warning and chat continues | Exceptions in route become 500; memory writes are debug-skipped |

## Current Shared Pieces

| Shared concept | Current canonical implementation |
|----------------|-----------------------------------|
| Conversation store | `project_guardian.conversation_store.ConversationStore` |
| Conversation id sanitization | `sanitize_conversation_id` |
| Secret redaction before persistence | `redact_chat_text` inside `ConversationStore.append_message` |
| Transcript formatting | `build_recent_transcript` / `format_transcript_for_prompt` |
| Raw trace protection | Conversation metadata drops nested/raw trace fields; runtime also allowlists `brain_*` metadata |

## Risks

| Risk | Severity | Why it matters |
|------|----------|----------------|
| Split response envelopes | Medium | Runtime clients read `response`/`reply`; control-panel JS reads `success`/`reply`/`history`. A helper must not normalize this by accident. |
| Split session identity | Medium | Runtime defaults to UUID/cookie, while control panel defaults to `control_panel`/localStorage. Operators can see different histories depending on host. |
| Brain hook only on runtime | ~~Medium~~ **Mitigated** | *Historical.* Both hosts use the same config-gated dry-run callback when `operator_chat` is enabled. |
| Different prompt history limits | Low-Medium | Same conversation can produce different backend prompts across hosts. |
| UI memory side effect only | Medium | Control-panel chat writes an additional memory record when `orchestrator.memory.remember` exists; runtime does not. |
| Runtime proposal branch bypasses chat persistence | Low-Medium | `proposal:<id>` chat returns status only and does not create conversation history or cookies. Preserve this until explicitly redesigned. |
| Backend abstraction drift | Medium | Runtime uses Architect-Core, panel uses unified LLM / `ask_ai`. The helper must accept callbacks rather than import or call providers directly. |
| Error semantics drift | Medium | UI returns HTTP 200 for backend LLM errors; runtime uses 500 for architect exceptions and echo fallback when no architect exists. |

## Shared Helper Design

Suggested module:

`project_guardian/safe_stack/operator_chat.py`

The helper should be pure Python and framework-neutral. It should not import Flask, start services, call LLM APIs directly, invoke tools, execute shell commands, or touch autonomy.

### Proposed Data Types

```python
@dataclass(frozen=True)
class OperatorChatPolicy:
    host_name: str
    default_context: str = "general"
    default_conversation_id: str | None = None
    use_cookie_conversation_id: bool = False
    prompt_history_limit: int = 20
    prompt_max_chars: int = 8000
    response_history_limit: int = 20
    allow_brain_trace: bool = False
    allow_proposal_branch: bool = False

@dataclass(frozen=True)
class OperatorChatRequest:
    message: str
    context: str
    conversation_id: str | None = None
    session_id: str | None = None
    cookie_conversation_id: str | None = None

@dataclass(frozen=True)
class OperatorChatBackendInput:
    message: str
    context: str
    conversation_id: str
    composed_prompt: str
    history_rows: list[dict]
    brain_metadata: dict

@dataclass(frozen=True)
class OperatorChatBackendResult:
    reply: str | None
    extra_fields: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
```

### Proposed Function Shape

```python
def run_operator_chat_turn(
    request: OperatorChatRequest,
    *,
    policy: OperatorChatPolicy,
    store: ConversationStore | None,
    responder: Callable[[OperatorChatBackendInput], OperatorChatBackendResult],
    brain_trace_callback: Callable[[str, str], dict[str, Any]] | None = None,
    proposal_callback: Callable[[str, str], tuple[dict[str, Any], int] | None] | None = None,
    after_persist_callback: Callable[[str, str, str, dict[str, Any]], None] | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> OperatorChatTurnResult:
    ...
```

The returned result should include a status code, compact body fields, sanitized conversation id, optional response history, optional cookie instruction, and warnings. Flask route handlers would then adapt it to their current HTTP shapes.

### Helper Responsibilities

- Validate and strip `message`.
- Resolve and sanitize `conversation_id` according to host policy.
- Load bounded history from `ConversationStore`.
- Build `composed_prompt` with `build_recent_transcript`.
- Optionally call a supplied BrainPipeline trace callback and keep only compact scalar metadata.
- Call the supplied responder callback.
- Persist user and assistant messages through `ConversationStore.append_message`.
- Invoke optional host callbacks after persistence.
- Return structured success/error data without raising for normal invalid input.

### Host Responsibilities To Preserve

| Host | Keep outside helper |
|------|---------------------|
| RuntimeAPIServer | Flask response and cookie, Architect-Core callback, proposal early branch policy, EventBus emission, existing response envelope |
| UIControlPanel | Flask response, `success` envelope, history array in response, localStorage expectations, unified LLM / `ask_ai` callback, optional memory side effect |

## Safety Contract

- No autonomy wiring.
- No live execution enabling.
- No direct LLM or external API calls from the helper.
- No shell/subprocess/code execution.
- No proposal implementation, patching, approval, or run behavior.
- Brain trace must remain config-gated through `run_brain_pipeline_for_operator_event`.
- Operator chat BrainPipeline must remain dry-run unless `operator_chat_live_execution` is explicitly enabled by config.
- Brain trace failures must fail open and not break chat.
- Stored metadata must exclude raw Brain/TDA traces and trace paths.
- Stored text must go through `ConversationStore` redaction.

## Test Plan Before Migration

Add helper-level tests before touching route bodies:

| Test area | Coverage |
|-----------|----------|
| Message validation | Empty messages return `400`-style structured error without responder call |
| Conversation ids | Runtime policy: body id, cookie id, generated id; UI policy: body id, session id, `control_panel` |
| History prompt | Correct transcript limits and current-message suffix for both host policies |
| Persistence | User and assistant rows are stored only after successful reply |
| Redaction | Secrets and raw trace metadata are not persisted |
| Brain callback | Called only when policy/config allow it; exceptions become compact warning metadata |
| Dry-run guard | Brain callback path preserves `run_brain_pipeline_for_operator_event` dry-run forcing |
| UI memory side effect | `after_persist_callback` called only after successful UI-style reply |
| Runtime event side effect | `event_callback` preserves current emitted payload shape |
| Proposal branch | Runtime proposal callback can early-return without persistence/brain/backend |
| Error semantics | UI backend errors can remain HTTP 200 `success:false`; runtime exceptions can remain runtime-shaped |
| No execution | Source/static tests confirm helper has no apply/run/patch/subprocess/autonomy behavior |

Update existing host tests during migration:

- `project_guardian/tests/test_runtime_api_conversations.py`
- `tests/test_elysia_api_approval_implementation.py`
- `project_guardian/tests/test_control_panel_chat_memory.py`
- `project_guardian/tests/test_brain_operator_chat_hook.py`
- `project_guardian/tests/test_brain_runtime_config.py`
- `project_guardian/tests/test_api_host_route_parity.py`

## Migration Phases (historical; now complete through UI migration)

### Phase 0 - Audit only

This document. No production behavior changes.

### Phase 1 - Extract pure helper tests (done)

Create `project_guardian/tests/test_operator_chat_helper.py` with fake stores and fake callbacks. Do not wire routes yet.

### Phase 2 - Implement helper internals (done)

Add `project_guardian/safe_stack/operator_chat.py` with pure functions and dataclasses. Keep it callback-only.

### Phase 3 - RuntimeAPIServer migration (done)

Move runtime `POST /api/chat` internals to the helper while preserving:

- response keys,
- cookie behavior,
- proposal branch behavior,
- BrainPipeline dry-run hook behavior,
- event bus behavior,
- echo fallback behavior.

### Phase 4 - UIControlPanel migration (done)

Move panel `POST /api/chat` internals to the helper while preserving:

- `success` response envelope,
- localStorage/client `conversation_id` expectations,
- response `history`,
- unified LLM / `ask_ai` fallback order,
- `memory.remember` side effect.

### Phase 5 - Optional normalization

Only after compatibility tests pass, consider a versioned normalized chat response or a documented single-host operator chat entrypoint. Do not change existing `POST /api/chat` shape by default.

## Non-Goals From The Original Audit

These were non-goals for the audit-only task. The helper implementation and route
wiring have since been completed in later phases.

- Do not implement the helper in this audit task. Completed later.
- Do not change either `POST /api/chat` route during the audit-only task. Completed later via the shared helper.
- Do not normalize response envelopes yet.
- Do not add a BrainPipeline hook to UIControlPanel during the audit-only task. Completed later as a config-gated dry-run callback.
- Do not alter cookie or localStorage behavior.
- Do not merge runtime proposal implementation routes into the safe stack.
- Do not enable autonomy, live execution, proposal implementation, shell commands, or real LLM calls.

## Smoke

Safe-stack smoke command to run after this documentation update:

```powershell
python scripts/run_safe_stack_smoke_tests.py
```
