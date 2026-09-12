# Operator chat helper — audit and implementation plan

**Date:** 2026-05-16  
**Status:** Phases 1–3 complete — historical plan  
**Related:** `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`, `project_guardian/safe_stack/operator_chat.py`

> **Superseded / current status:** Preserved for migration history. **Source of truth:** [`API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`](API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md) and [`API_HOST_FINAL_CONSOLIDATION_AUDIT.md`](API_HOST_FINAL_CONSOLIDATION_AUDIT.md). Both hosts use `run_operator_chat_turn`. Sections §3–4 and older checklist items in §9 describe **pre-wiring** behavior and are obsolete unless repeated in the final checkpoint/audit.

---

## Executive summary

`POST /api/chat` was the last major safe-stack divergence between hosts; it is now unified via **`project_guardian/safe_stack/operator_chat.py`** (Phases 2–3 complete). Non-chat routes share `project_guardian/safe_stack/responses.py`.

This document plans a **framework-neutral** helper at:

**`project_guardian/safe_stack/operator_chat.py`**

The helper will own **persistence, history assembly, optional BrainPipeline dry-run trace metadata, and response assembly** — but **not** the LLM/architect backend. Hosts pass a **`responder` callback** and optional host-specific hooks (cookies, memory side effects, proposal branches).

**Implementation complete (Phases 1–3).** See `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md` for the consolidated host matrix.

---

## 1. Inspection notes

| File | Role |
|------|------|
| `elysia/api/server.py` | Runtime `POST /api/chat`, `_maybe_run_brain_operator_chat_trace`, `_architect_chat`, cookie, proposal branch |
| `project_guardian/ui_control_panel.py` | Panel `POST /api/chat`, unified `chat_with_llm` / `ask_ai`, `_remember_chat_exchange`, localStorage-oriented defaults |
| `project_guardian/conversation_store.py` | Canonical JSONL store, `sanitize_conversation_id`, `build_recent_transcript`, redaction |
| `project_guardian/brain/runtime.py` | `run_brain_pipeline_for_operator_event` — operator_chat forces `dry_run` unless `operator_chat_live_execution` |
| `config/brain_pipeline.json` | Defaults: `enabled: false`, `operator_chat: false`, `operator_chat_live_execution: false` |
| `project_guardian/tests/test_brain_operator_chat_hook.py` | Runtime brain hook gating, dry-run, fail-open, metadata size |
| `project_guardian/tests/test_control_panel_chat_memory.py` | Panel transcript in prompt, persistence, redaction, `memory.remember` |
| `project_guardian/tests/test_api_host_route_parity.py` | Both hosts call brain hook when config enables `operator_chat` |
| `project_guardian/tests/test_runtime_api_conversations.py` | **Not present** in repo; runtime chat coverage lives in `test_brain_operator_chat_hook.py` and parity tests |

---

## 2. Current behavior — RuntimeAPIServer (`POST /api/chat`)

| Dimension | Behavior |
|-----------|----------|
| **Request input** | JSON: `message` (required), `context` (default `"general"`), optional `conversation_id`. Cookie: `elysia_conversation_id`. |
| **Response output** | Architect path: spread architect dict + `conversation_id`, `reply` (duplicate of `response`). Echo fallback: `response`, `status`, `conversation_id`, `reply`. Errors: `{"error": "..."}` with 400/404/503/500. |
| **conversation_id** | Body → cookie → new `uuid4()`; then `sanitize_conversation_id`. Returned in JSON; **Set-Cookie** `elysia_conversation_id` (1 year, Lax, `/`). |
| **History loading** | Before persist: `store.get_recent_context(cid, limit=20)` (fail-open log on error). |
| **History context** | `build_recent_transcript(hist, max_messages=20, max_chars=8000)` + `"\n\nCurrent user message:\n" + message` → `composed` passed to architect. |
| **Assistant generation** | 1) `context.startswith("proposal:")` → proposal_system lookup (no store, no brain). 2) `_architect_chat(composed, context)`. 3) Echo fallback. |
| **BrainPipeline trace** | `_maybe_run_brain_operator_chat_trace(message, context)` **before** store/LLM when `enabled` + `entrypoints.operator_chat`. Calls `run_brain_pipeline_for_operator_event(..., source_entrypoint="operator_chat", guardian=self._guardian)`. Fail-open: `brain_trace_error` only. Merges small `brain_*` keys into HTTP response; assistant row metadata via `_brain_meta_for_storage`. |
| **Metadata returned** | When trace runs: `brain_trace_enabled`, `brain_trace_id`, `brain_trace_path`, `brain_dry_run`, `brain_risk_level`, `brain_tda_used`, `brain_execution_success`, `brain_transition_count`, `brain_last_transition`, or `brain_trace_error`. Never raw trace blobs. |
| **Error handling** | Missing message → 400. Proposal not found → 404. Proposal system down → 503. Store/history failures → log, continue. Architect exception → 500. Brain trace exception → warning, chat continues. |
| **Persistence** | After reply: `append_message(user)`, `append_message(assistant, metadata=brain_meta subset)`. Redaction via store. |
| **Memory side effects** | None on runtime chat path. |
| **Proposal branch** | `context` like `proposal:<id>` — early return, **no** ConversationStore, **no** brain hook. |
| **Cookie / localStorage** | Sets HTTP cookie only; no localStorage. |
| **Event bus** | Emits `"api"/"chat"` with message, context, response, brain_meta. |

---

## 3. Current behavior — UIControlPanel (`POST /api/chat`)

| Dimension | Behavior |
|-----------|----------|
| **Request input** | JSON: `message` (required), optional `conversation_id` or `session_id`. No server cookie read on chat POST. |
| **Response output** | Success: `{ success: true, reply, error: null, conversation_id, history }`. LLM error: `{ success: false, error, reply: null, conversation_id, history }` with **HTTP 200**. Hard errors: `{ error }` 400/500. No `response` key; no `brain_*` keys today. |
| **conversation_id** | `_control_panel_chat_session_id(body id \|\| session_id \|\| "control_panel")`. Frontend uses `localStorage` key `elysia_control_panel_conversation_id` (`getApiChatConversationId` / `setApiChatConversationId`). |
| **History loading** | For **prompt**: `get_messages(cid, limit=CONTROL_PANEL_CHAT_PROMPT_MESSAGES)` (10) **before** current turn appended. For **response**: `_chat_history_for_response` (20 rows, shaped subset). |
| **History context** | `_build_chat_prompt_with_history` → same transcript pattern as runtime (6000 char cap, 10 messages). |
| **Assistant generation** | 1) `_get_unified_system().chat_with_llm(prompt_message)` → `(reply, err)`. 2) Fallback `orchestrator.ask_ai(prompt_message)`. 3) 400 if neither. **No Architect-Core, no proposal branch.** |
| **BrainPipeline trace** | **Now:** config-gated via `brain_trace_callback` (same as runtime). *Was “not called” pre–Phase 3.* |
| **Metadata returned** | Additive compact `brain_*` when trace runs; `history` on success/partial-success paths. |
| **Error handling** | Missing message → 400. LLM `err` string → 200 with `success: false`. Exceptions → 500. |
| **Persistence** | **After** LLM: `_append_chat_history` → `ConversationStore.append_message` (redacted). Order: build prompt from prior messages → call LLM → persist user+assistant. |
| **Memory side effects** | `_remember_chat_exchange` → `orchestrator.memory.remember(..., category="conversation")` after successful reply (both unified and ask_ai paths). |
| **Proposal branch** | None. |
| **Cookie / localStorage** | Client-only session id; server does not set cookies on chat response. |
| **Event bus** | None. |

---

## 4. Side-by-side differences (summary)

| Topic | Runtime | UI panel |
|-------|---------|----------|
| Response envelope | `response` + `reply` + optional `context`/`source` | `success` + `reply` + `history` |
| Default conversation id | New UUID if absent | `control_panel` |
| Session transport | Cookie | Body + localStorage |
| LLM backend | Architect-Core `chat()` | Unified `chat_with_llm` / `ask_ai` |
| Brain trace on chat | Yes (config-gated) | Yes (config-gated; additive `brain_*`) |
| Proposal chat context | Yes (`proposal:<id>`) | No |
| History in POST response | No | Yes (`history` array) |
| Prompt message limits | 20 msgs / 8000 chars | 10 msgs / 6000 chars |
| Memory.remember | No | Yes |
| Persist timing | After reply | After reply (same) |
| Chat history GET | Shared `build_chat_history_response` | Same (limit 20) |

---

## 5. What can be shared safely

### 5.1 Proposed module

**`project_guardian/safe_stack/operator_chat.py`**

Pure Python; no Flask imports. Complements `safe_stack/responses.py` (read routes) without replacing them.

### 5.2 Shared responsibilities

| Responsibility | Notes |
|----------------|-------|
| Normalize `conversation_id` | `sanitize_conversation_id`; host supplies default/id source |
| Validate `message` | Strip; empty → structured error |
| Load bounded history | `store.get_recent_context` / `get_messages` with configurable limits |
| Build composed prompt | `build_recent_transcript` + current user line (shared limits as params) |
| Optional brain trace | Wrapper around `run_brain_pipeline_for_operator_event` + metadata extraction (move logic from `RuntimeAPIServer._maybe_run_brain_operator_chat_trace`) |
| Invoke responder callback | Host provides LLM/architect implementation |
| Persist user + assistant | `append_message` with redaction; assistant `metadata` from sanitized brain keys only |
| Sanitize brain metadata | Reuse allowlist from `_brain_meta_for_storage` |
| Build core result dict | `conversation_id`, `reply`/`response` text, `brain_*` subset — host adapts envelope |

### 5.3 Callback interface (draft)

```python
@dataclass(frozen=True)
class OperatorChatInput:
    message: str
    conversation_id: str          # already sanitized
    context: str                  # e.g. "general" or "proposal:..."
    composed_prompt: str          # transcript + current user message
    history_rows: list[dict]      # recent store rows used for prompt

@dataclass(frozen=True)
class OperatorChatResponderResult:
    reply_text: str
    extra_fields: dict[str, Any] = field(default_factory=dict)  # source, context, etc.

Responder = Callable[[OperatorChatInput], OperatorChatResponderResult]

def run_operator_chat_turn(
    *,
    message: str,
    conversation_id: str | None,
    context: str = "general",
    store: ConversationStore | None,
    responder: Responder,
    default_conversation_id: str = "control_panel",
    brain_trace_fn: Callable[[str, str], dict[str, Any]] | None = None,
    guardian: Any = None,
    history_limit: int = 20,
    prompt_max_messages: int = 20,
    prompt_max_chars: int = 8000,
    after_persist: Callable[[str, str, str, dict], None] | None = None,
) -> tuple[dict[str, Any], int]:
    """
    Returns (body, status_code). Does not set cookies or call real LLMs itself.
    """
```

**`brain_trace_fn`** default implementation: `maybe_run_operator_chat_brain_trace(message, http_context, guardian=...)` extracted from runtime server — config-gated, fail-open, never calls tools/executors directly.

**`after_persist`**: optional hook for UI `memory.remember` (host passes closure).

### 5.4 Host adapters (thin wrappers)

| Host | Adapter duties |
|------|----------------|
| **Runtime** | Map proposal branch before helper; pass architect responder; attach brain fn; map result → architect JSON + cookie; emit event bus |
| **Panel** | Pass unified/ask_ai responder; pass `after_persist=_remember_chat_exchange`; map result → `{success, reply, error, history}`; use panel prompt limits |

Response-shape adapters stay in hosts so existing JS and API clients do not break in phase 1.

---

## 6. What should NOT be shared yet

| Item | Reason |
|------|--------|
| Runtime `proposal:<id>` branch | Different product surface; keep early-exit in runtime route only |
| UI `orchestrator.memory.remember()` | Side effect; optional `after_persist` hook only — not default in helper |
| HTTP cookie / Set-Cookie | Runtime-only transport |
| Frontend localStorage | Client-only |
| Event bus emission | Runtime-only |
| Unified vs Architect vs ask_ai selection | Host `responder` factory |
| `/api/proposals/*` implement paths | Out of safe stack |
| POST response `history` array | Panel adapter adds via `_chat_history_for_response` |
| Different prompt limits (10 vs 20) | Parameters per host, not one global constant |
| Enabling `operator_chat_live_execution` | Remains config-off; helper must not bypass `brain/runtime.py` dry_run rules |

---

## 7. Safety rules (helper contract)

1. **Never** call `implementer`, `subprocess`, `apply_patch`, or autonomy entrypoints from the helper.
2. **Never** invoke LLM APIs inside the helper — only the host `responder`.
3. Brain trace: only when `brain_pipeline.enabled` and `entrypoints.operator_chat` (same as today).
4. Operator chat trace must respect `run_brain_pipeline_for_operator_event` dry_run forcing (see `test_brain_operator_chat_hook.py`).
5. Brain failures are **fail-open** (chat continues; `brain_trace_error` only).
6. Persisted metadata: allowlisted scalar `brain_*` keys only; no raw traces (store `_safe_metadata` + server allowlist).
7. All stored text through `ConversationStore.append_message` (redaction).
8. No new routes, no autonomy wiring, no live execution flags enabled by helper defaults.

---

## 8. Migration phases

### Phase 0 — Plan and test design (this document)

- [x] Audit both hosts
- [ ] Review and sign off on callback API

### Phase 1 — Pure helper + unit tests (done)

- [x] `project_guardian/safe_stack/operator_chat.py` — dataclasses, `run_operator_chat_turn`, history/brain/metadata helpers
- [x] `project_guardian/tests/test_operator_chat_helper.py` — mocked store/responder/brain (no HTTP, no LLM)
- **Route integration:** helper library only (hosts wired in Phases 2–3)

### Phase 2 — Runtime host wiring (done)

- [x] `elysia/api/server.py` — general `POST /api/chat` uses `run_operator_chat_turn` via `_handle_runtime_general_chat`
- [x] Proposal branch (`context: proposal:<id>`) unchanged; does not call helper
- [x] `_maybe_run_brain_operator_chat_trace` passed as `brain_trace_callback` (config-gated, fail-open)
- [x] Architect responder + echo fallback preserved; cookie + event bus preserved
- [x] `project_guardian/tests/test_runtime_operator_chat_helper_integration.py`
- [x] Smoke script includes runtime integration tests
### Phase 3 — UIControlPanel host wiring (done)

- [x] `project_guardian/ui_control_panel.py` — `POST /api/chat` uses `run_operator_chat_turn` via `_handle_control_panel_operator_chat`
- [x] Panel responder: `chat_with_llm` → `ask_ai` (unchanged selection order)
- [x] Response envelope preserved: `success`, `reply`, `error`, `history`, `conversation_id`
- [x] `after_persist_callback` → `_remember_chat_exchange` (fail-open debug log on memory errors)
- [x] History limits: 10 messages / 6000 chars (`CONTROL_PANEL_CHAT_PROMPT_*`)
- [x] **Brain trace:** config-gated via `_maybe_run_brain_operator_chat_trace` (same rules as runtime); compact `brain_*` fields merged **additively** into JSON when trace runs; fail-open on errors
- [x] `project_guardian/tests/test_control_panel_operator_chat_helper_integration.py`
- [x] Parity test updated: both hosts call brain hook when `operator_chat` entrypoint enabled

**Preserved panel-only behavior**

| Item | Notes |
|------|--------|
| Default `conversation_id` | `control_panel` when body/cookie absent |
| Client session | localStorage `elysia_control_panel_conversation_id` (unchanged; server reads body only) |
| LLM error shape | HTTP 200, `success: false`, `reply: null` |
| No HTTP cookie on chat | Runtime still sets `elysia_conversation_id` cookie; panel does not |

**Remaining host differences**

| Topic | Runtime | Panel |
|-------|---------|-------|
| Response envelope | `response` + `reply` + cookie | `success` + `history` |
| Proposal chat | `context: proposal:<id>` | N/A |
| Event bus | Yes | No |
| Memory.remember | No | Yes (`after_persist`) |
| Prompt/history limits | 20 / 8000 | 10 / 6000 |

### Phase 5 — Response shape convergence (optional, later)

- Align envelopes only if product wants single client contract
- Out of scope until explicit request

---

## 9. Test coverage (implemented; historical checklist retained)

> **Status:** Helper unit tests, both host integration tests, and updated parity brain test are **in the smoke slice (227 tests)**. Checklist below is historical.

| Test file | Purpose |
|-----------|---------|
| `test_operator_chat_helper.py` | Core helper unit tests — **done** |
| `test_runtime_operator_chat_helper_integration.py` | Runtime wiring — **done** |
| `test_control_panel_operator_chat_helper_integration.py` | Panel wiring — **done** |
| `test_api_host_route_parity.py` | Both-host brain hook when config on — **done** |
| `test_control_panel_chat_memory.py` | Panel persistence + remember — **done** |

### Required helper unit cases (historical checklist)

- [x] Persists user then assistant messages in order
- [x] Loads bounded history (respect `history_limit`)
- [x] Returns sanitized `conversation_id`
- [x] Composed prompt includes transcript + current message
- [x] Calls `brain_trace_fn` only when config enabled + `operator_chat` entrypoint
- [x] Does not call brain when disabled (default config)
- [x] Brain trace failure → fail-open; responder still runs
- [x] `brain_dry_run` true for operator_chat when live_execution false (delegate to runtime/brain tests)
- [x] No `apply_patch` / `run_command` / autonomy strings in helper module
- [x] Responder receives `composed_prompt`, not raw message only
- [x] `after_persist` called once per successful turn when provided
- [x] Store `None` → runtime no-store path; panel requires store

### Integration / parity cases

- [x] Runtime JSON still includes `response` + `reply` + cookie
- [x] Panel JSON still includes `success` + `history`
- [x] Proposal branch on runtime unchanged and **does not** call helper
- [x] No real network / LLM (mocks in tests)

**Note:** Add `test_runtime_api_conversations.py` only if dedicated runtime conversation+chat tests are desired; currently uncovered as a single file.

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| Response shape regression for dashboard JS | Keep host adapters; contract tests per host |
| Panel accidentally enables brain + changes UX | Default config off; parity test documents drift until explicit enable |
| Double-persist if helper and host both append | Single persist path inside helper only |
| Prompt built from stale history (UI order) | Helper loads store **before** append; document ordering in API |
| `memory.remember` duplication | Only via `after_persist` once |
| Circular imports (`ui_control_panel` ↔ helper) | Helper must not import Flask or UIControlPanel |
| Proposal branch regression | Keep outside helper; test unchanged |
| Enabling live execution via config | Do not change defaults; existing `brain/runtime.py` guards remain |

---

## 11. Non-goals

- Changing `POST /api/chat` request/response contracts in the implementation phase without explicit approval
- Wiring autonomy or tool execution through chat
- Enabling `operator_chat_live_execution` by default
- Unifying runtime proposal chat with panel
- Replacing Architect with unified LLM on runtime
- Proxying panel chat to port 8123
- Moving chat routes into Flask blueprint in the same PR as helper extraction (optional later)

---

## 12. References

- Shared read routes: `project_guardian/safe_stack/responses.py`
- Brain operator entry: `project_guardian/brain/runtime.py` → `run_brain_pipeline_for_operator_event`
- Config defaults: `config/brain_pipeline.json`
- Host consolidation: `docs/API_HOST_STATE_CONSOLIDATION_PLAN.md` Phase 3
