# API host final consolidation checkpoint

**Date:** 2026-05-18  
**Status:** **Source of truth** for API host / safe-stack consolidation (post operator-chat wiring)  
**Related:** `docs/API_HOST_FINAL_CONSOLIDATION_AUDIT.md`, `docs/API_HOST_STATE_CONSOLIDATION_PLAN.md` (historical), `docs/OPERATOR_CHAT_HELPER_PLAN.md` (historical), `scripts/run_safe_stack_smoke_tests.py`

> Use this document first for current host behavior, shared helpers, parity status, and ranked next steps. Older planning/audit docs below are preserved for context and may describe pre-helper state.

---

## A. Executive summary

RuntimeAPIServer (`elysia/api/server.py`, default `:8123`) and UIControlPanel (`project_guardian/ui_control_panel.py`, default `:5000`) now share the same **safe-stack libraries** for mirrored REST routes and for general operator chat orchestration.

| Question | Answer |
|----------|--------|
| **What is shared?** | `project_guardian/safe_stack/responses.py` (read/status routes), `project_guardian/safe_stack/operator_chat.py` (chat turn orchestration), `ConversationStore`, default proposal queue, brain trace summary loader, memory-ranking visibility, prompt-contract status builder. |
| **What remains host-specific?** | HTTP ports, UI HTML, chat **response envelopes**, session transport (cookie vs body/localStorage), LLM backends (Architect vs unified/ask_ai), runtime **proposal:** chat branch, event bus, `memory.remember`, prompt/history limits, thin Flask route wrappers, runtime-only `/api/proposals/*`. |
| **Duplication risk reduced?** | **Yes** for business logic (persistence, history assembly, brain metadata sanitization, proposal list/export/status). **Residual** duplication is mostly one-line Flask registrations and two copies of `_maybe_run_brain_operator_chat_trace` (runtime vs panel). |
| **Blueprint extraction still necessary?** | **No — not now.** Optional later if a third host appears or route registration drift returns. Current pattern (shared helpers + thin host adapters) is the intended end state for the safe stack. |

---

## B. Shared components

### `project_guardian/safe_stack/responses.py`

Framework-neutral builders used by **both** hosts for mirrored read/write-safe routes:

| Builder | Purpose |
|---------|---------|
| `build_chat_history_response` | GET `/api/chat/history` |
| `build_chat_history_clear_response` | DELETE `/api/chat/history` |
| `build_conversations_list_response` | GET `/api/conversations` |
| `build_conversation_create_response` | POST `/api/conversations` |
| `build_conversation_detail_response` | GET `/api/conversations/<id>` |
| `build_conversation_delete_response` | DELETE `/api/conversations/<id>` |
| `build_brain_trace_latest_response` | GET `/api/brain/trace/latest` |
| `build_memory_ranking_summary_response` | GET `/api/memory/ranking/summary` |
| `build_prompt_contracts_status_response` | GET `/api/prompt-contracts/status` |
| `build_self_improvement_proposals_list_response` | GET `/api/self-improvement/proposals` |
| `build_self_improvement_proposal_detail_response` | GET `/api/self-improvement/proposals/<id>` |
| `build_self_improvement_proposal_status_update_response` | POST `.../status` |
| `build_self_improvement_prompt_export_response` | GET `.../export_prompt` |

Hosts call these and `return jsonify(body), code` — no duplicated serialization logic.

### `project_guardian/safe_stack/operator_chat.py`

Framework-neutral **operator chat turn** orchestration (no Flask, no LLM calls):

- `run_operator_chat_turn` — history → optional user persist → brain trace callback → responder → assistant persist → optional `after_persist_callback`
- `build_operator_history_context`, `merge_brain_trace_metadata`, `sanitize_operator_chat_metadata`
- `OperatorChatResponderError` for host-shaped failures without persisting assistant rows

Both hosts supply **responder** and **brain_trace_callback**; hosts own HTTP envelopes.

### Canonical `ConversationStore`

- Module: `project_guardian/conversation_store.py`
- Default dir: `data/runtime/conversations/*.jsonl`
- Used by both chat paths and ranking visibility
- Redaction, `sanitize_conversation_id`, `build_recent_transcript`

### Canonical self-improvement proposal queue

- Module: `project_guardian/self_improvement/proposal_queue.py`
- Default: `data/runtime/self_improvement_proposals.jsonl`
- API: list / get / status update / export_prompt only (no execute in safe stack)

### Canonical trace / status / ranking helpers

| Concern | Module / entry |
|---------|----------------|
| Brain trace read | `trace_visibility.load_latest_brain_trace_summary` + `get_brain_pipeline_config()` |
| Brain trace write (chat) | `brain.runtime.run_brain_pipeline_for_operator_event` via host `_maybe_run_brain_operator_chat_trace` |
| Prompt contracts | `prompt_contracts.controls.build_prompt_contract_status` |
| Memory ranking | `memory_ranking.visibility.load_memory_ranking_visibility` |

---

## C. Runtime vs UI behavior table

### `POST /api/chat`

| Dimension | RuntimeAPIServer | UIControlPanel |
|-----------|------------------|----------------|
| **Shared helper** | `run_operator_chat_turn` via `_handle_runtime_general_chat` | `run_operator_chat_turn` via `_handle_control_panel_operator_chat` |
| **Request fields** | `message` (required), `context` (default `general`), optional `conversation_id`; cookie `elysia_conversation_id` | `message` (required), optional `conversation_id` or `session_id` |
| **Response envelope** | Architect/echo dict + `response`, `reply`, `conversation_id`; optional `context`/`source`; additive `brain_*` | `success`, `reply`, `error`, `conversation_id`, `history`; additive `brain_*` |
| **conversation_id** | Body → cookie → new UUID; `sanitize_conversation_id` | Body/session → default `control_panel`; `sanitize_conversation_id` |
| **Cookie / localStorage** | Sets `elysia_conversation_id` (1y, Lax, `/`) | No Set-Cookie; client `localStorage` `elysia_control_panel_conversation_id` |
| **History in prompt** | 20 messages / 8000 chars | 10 messages / 6000 chars (`CONTROL_PANEL_CHAT_PROMPT_*`) |
| **History in POST response** | No | Yes (`history`, up to 20 rows via `_chat_history_for_response`) |
| **BrainPipeline trace** | Config-gated; `brain_trace_callback` → `_maybe_run_brain_operator_chat_trace`; dry-run unless `operator_chat_live_execution`; fail-open | Same rules; duplicate host method (same logic as runtime) |
| **LLM backend** | `_architect_chat(composed_prompt, context)` or echo fallback | `chat_with_llm(composed_prompt)` then `ask_ai(composed_prompt)` |
| **Memory side effect** | None | `after_persist` → `_remember_chat_exchange` → `orchestrator.memory.remember` (category `conversation`) |
| **Proposal branch** | `context: proposal:<id>` — **not** using helper; no store/brain | N/A |
| **User persist on LLM error** | Default helper: user row may persist before responder | `persist_user_before_responder=False` — no rows on responder failure; `history: []` |
| **Event bus** | Emits `api`/`chat` after successful turn | None |
| **Store unavailable** | `_handle_runtime_general_chat_no_store` (architect/echo, no persist) | Requires store (panel always has `_conversation_store`) |

### Other mirrored routes

| Route | Shared helper? | Host-specific notes |
|-------|----------------|---------------------|
| GET/DELETE `/api/chat/history` | Yes (`build_chat_history_*`) | Default session id differs (`control_panel` vs cookie) |
| GET/POST `/api/conversations` | Yes | Thin wrappers only |
| GET/DELETE `/api/conversations/<id>` | Yes | Thin wrappers only |
| POST `/api/conversations/<id>/messages` | **No** — inline `append_message` on both hosts | Duplicate handlers; same store |
| GET `/api/brain/trace/latest` | Yes | Same trace file when same cwd/config |
| GET `/api/memory/ranking/summary` | Yes | Panel passes `conversation_store=` |
| GET `/api/prompt-contracts/status` | Yes | Read-only |
| GET/POST self-improvement proposal routes | Yes (export/status/list/detail) | No implement/execute |

### Runtime-only (outside safe stack)

| Route | Notes |
|-------|--------|
| `/api/proposals/*` | Elysia change proposals; approve/implement |
| `/api/status`, `/api/events` | Runtime lifecycle |

---

## D. API route parity status

Routes in `SAFE_STACK_ROUTE_SPECS` (`test_api_host_route_parity.py`) — both hosts register the same methods.

| Route fragment | Methods | Shared response/helper | Chat/operator helper |
|----------------|---------|------------------------|----------------------|
| `/api/chat/history` | GET, DELETE | `safe_stack.responses` | N/A |
| `/api/conversations` | GET, POST | `safe_stack.responses` | N/A |
| `/api/conversations/<id>` | GET, DELETE | `safe_stack.responses` | N/A |
| `/api/brain/trace/latest` | GET | `safe_stack.responses` | N/A |
| `/api/memory/ranking/summary` | GET | `safe_stack.responses` | N/A |
| `/api/prompt-contracts/status` | GET | `safe_stack.responses` | N/A |
| `/api/self-improvement/proposals` | GET | `safe_stack.responses` | N/A |
| `/api/self-improvement/proposals/<id>` | GET | `safe_stack.responses` | N/A |
| `.../status` | POST | `safe_stack.responses` | N/A |
| `.../export_prompt` | GET | `safe_stack.responses` | N/A |

**Not in parity spec (by design):**

- `POST /api/chat` — behavior parity via integration tests; envelopes intentionally differ
- `POST /api/conversations/<id>/messages` — mirrored but not in `SAFE_STACK_ROUTE_SPECS`; still duplicate inline handlers
- `/api/proposals/*` — runtime only

---

## E. Remaining differences

| Difference | Impact | Mitigation |
|------------|--------|------------|
| **Runtime `proposal:<id>` chat** | No ConversationStore/brain/helper | Keep early-exit in `api_chat`; document for API clients |
| **Runtime cookie vs UI localStorage** | Two session transports on different ports | Operators use one host per workflow; same store if same `conversation_id` |
| **Response envelopes** | Dashboard JS vs runtime API clients | Optional Phase 5 convergence (`OPERATOR_CHAT_HELPER_PLAN.md`) |
| **`memory.remember` (UI only)** | Panel writes Guardian memory; runtime does not | `after_persist_callback` by design |
| **Duplicate `_maybe_run_brain_operator_chat_trace`** | ~45 lines × 2 hosts | Optional extract to `safe_stack` or `brain` helper later |
| **Thin Flask route wrappers** | ~10 routes × 2 files | Optional blueprint; low priority |
| **POST `.../messages` inline** | Small duplicate validation | Could add `build_conversation_append_response` later |
| **Legacy chat import** | UI init: `import_legacy_control_panel_json` from `control_panel_chat_history.json` once | Marker: `.legacy_control_panel_chat_history_imported`; canonical read path is JSONL store |
| **Legacy SI queue** | `brain_self_improvement_queue.jsonl` is historical/opt-in only via `ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE=1` | API reads canonical `self_improvement_proposals.jsonl` only |
| **Dual ports (5000 vs 8123)** | Operator confusion if mixing hosts | Document in runbooks; attach mode uses separate status URL (`:8888`) |

---

## F. Safety status

| Guard | Status |
|-------|--------|
| **Autonomy** | Not wired through safe-stack routes; smoke does not enable `config/autonomy.json` execution |
| **Live execution** | `operator_chat_live_execution: false` default; brain `dry_run: true` default in `config/brain_pipeline.json` |
| **Brain trace on chat** | Config-gated (`enabled` + `entrypoints.operator_chat`); compact `brain_*` only; fail-open; no raw trace blobs in JSON |
| **Self-improvement API** | List / get / status / export_prompt only — no implement in safe stack |
| **Memory ranking** | Read-only summary endpoint |
| **Prompt contracts** | `prompt_contract_validation.enabled: false` by default |
| **Safe-stack smoke** | `python scripts/run_safe_stack_smoke_tests.py` — mocks/offline; no real LLM/API calls |

Forbidden tokens checked in parity tests: `run_autonomous_cycle`, `apply_patch`, `subprocess`, `operator_chat_live_execution`, `implementer.run_for_proposal` in safe-route handlers.

---

## G. Test coverage

### Core helper (unit, no HTTP/LLM)

| File | Role |
|------|------|
| `project_guardian/tests/test_operator_chat_helper.py` | `run_operator_chat_turn`, history caps, brain fail-open, metadata sanitization, wiring on both hosts |

### Host integration (Flask test clients, mocked backends)

| File | Role |
|------|------|
| `project_guardian/tests/test_runtime_operator_chat_helper_integration.py` | Runtime `/api/chat`: cookie, persist, proposal branch bypasses helper, brain metadata, architect/echo |
| `project_guardian/tests/test_control_panel_operator_chat_helper_integration.py` | Panel envelope, memory.remember, brain when config on, `persist_user_before_responder=False` on LLM error |

### Parity and helpers

| File | Role |
|------|------|
| `project_guardian/tests/test_api_host_route_parity.py` | Route registration parity; shared handler safety; **both** hosts call brain hook when config enabled |
| `project_guardian/tests/test_safe_stack_response_helpers.py` | Response builder contracts |

### Related smoke slice (not operator-chat-specific)

| File | Role |
|------|------|
| `test_conversation_store.py` | Store/redaction |
| `test_control_panel_chat_memory.py` | Panel transcript + persistence + remember |
| `test_brain_trace_visibility.py`, `test_brain_tda_integration.py` | Trace read/TDA naming |
| `test_self_improvement_*.py`, `test_prompt_contracts*.py`, `test_memory_ranking*.py` | SI + contracts + ranking |

### Safe-stack smoke command

```bash
python scripts/run_safe_stack_smoke_tests.py
```

**Last verified:** 247 passed, exit 0 (2026-05-18).

---

## H. Recommended next steps (ranked)

1. **Optional shared Flask blueprint** — Only if route-handler duplication becomes painful (e.g. third HTTP host). **Not recommended immediately**; helpers already centralize logic.

2. **Optional envelope convergence** — Only if a single client must consume both `:5000` and `:8123` chat responses without adapters. Dashboard and runtime clients today expect different shapes.

3. **Monitor legacy self-improvement queue retirement** — Default writes now go only to `self_improvement_proposals.jsonl`; keep `ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE=1` as temporary compatibility only.

4. **Finish legacy `control_panel_chat_history.json` cleanup** — After confirming all deployments imported to JSONL; remove import path and file references when unused.

5. **Live-execution governance test plan** — Before enabling `operator_chat_live_execution` or any non-dry-run brain path: explicit approval workflow, audit tests, and operator runbook (out of scope for safe stack).

### Lower priority

- Extract shared `_maybe_run_brain_operator_chat_trace` to one module (reduce duplicate host methods).
- Add `build_conversation_append_response` for POST `.../messages` parity.
- Update `docs/API_HOST_STATE_CONSOLIDATION_PLAN.md` §2 route table (still describes pre-helper chat split).

---

## Checkpoint sign-off

| Milestone | Done |
|-----------|------|
| `safe_stack/responses.py` on mirrored read routes | Yes |
| `safe_stack/operator_chat.py` library + unit tests | Yes |
| Runtime general `POST /api/chat` wired | Yes |
| UI `POST /api/chat` wired | Yes |
| Brain trace on both hosts (config-gated) | Yes |
| Safe-stack smoke 227 tests | Yes |
| Blueprint extraction | Deferred (optional) |

**No further safe-stack host wiring is required** for operator chat unless product requests envelope unification or a new HTTP surface.
