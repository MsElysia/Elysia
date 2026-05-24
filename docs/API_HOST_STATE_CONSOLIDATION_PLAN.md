# API host & state consolidation plan

**Date:** 2026-05-16  
**Status:** Historical plan — implementation complete  
**Related:** `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`, `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md`, `scripts/run_safe_stack_smoke_tests.py`

> **Superseded / current status:** Preserved for historical planning context.
> **Source of truth:** [`API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`](API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md)
> and [`API_HOST_FINAL_CONSOLIDATION_AUDIT.md`](API_HOST_FINAL_CONSOLIDATION_AUDIT.md).
> RuntimeAPIServer and UIControlPanel now share
> `project_guardian/safe_stack/responses.py` and
> `project_guardian/safe_stack/operator_chat.py`. Do not treat sections below that
> say UI chat has no brain hook, parity tests are future work, or blueprint
> extraction is the immediate next step as current unless repeated in the final
> checkpoint/audit.

---

## Executive summary

Project Guardian exposes **two Flask HTTP hosts** that mirror most **safe-stack** REST routes:

| Host | Module | Typical URL | Primary role |
|------|--------|-------------|--------------|
| **UIControlPanel** | `project_guardian/ui_control_panel.py` | `http://127.0.0.1:5000` | Serves **HTML dashboard** + **same-origin** `/api/*` for embedded JS |
| **RuntimeAPIServer** | `elysia/api/server.py` | `http://127.0.0.1:8123` (Elysia runtime default) | **API-only** surface when `ElysiaRuntime` has `enable_api` |

A third status surface (`http://127.0.0.1:8888` / `elysia_config.get_status_url()`) is used by `elysia_interface.py` attach mode and is **not** the safe-stack mirror; it is called out for confusion avoidance only.

**Recommended strategy: C — Hybrid transition** (see §6) — **largely completed** for safe-stack read routes and operator chat via shared helpers. Residual risks: **dual ports**, thin duplicate Flask registrations, and **split client session identity** (localStorage vs cookie). UI and runtime chat both support **config-gated** BrainPipeline dry-run metadata when `operator_chat` is enabled (see final checkpoint).

---

## 1. Host map

### 1.1 UIControlPanel

| Item | Detail |
|------|--------|
| **Startup** | `GuardianCore.start_ui_panel()` → `UIControlPanel(orchestrator, host, port)` → `panel.start()` (`project_guardian/core.py`) |
| **Also** | `start_ui_panel.py`, `elysia_sub_guardian.py` (config port, often **5000**) |
| **Default bind** | `127.0.0.1:5000` |
| **Serves UI?** | **Yes** — `CONTROL_PANEL_TEMPLATE` via `render_template_string` on `/` |
| **Route registration** | `UIControlPanel._setup_routes()` — large inline `@self.app.route(...)` block |
| **Conversation store** | `ConversationStore(Path(raw_conv_dir))` where `raw_conv_dir` = `orchestrator.conversation_store_dir` or `DEFAULT_CONVERSATIONS_DIR` (`data/runtime/conversations/`) |
| **Legacy chat** | Imports `control_panel_chat_history.json` once at init; `_chat_history_for_response` reads **ConversationStore** (not legacy file directly) |
| **Proposal queue** | `get_default_proposal_queue()` → `data/runtime/self_improvement_proposals.jsonl` |
| **Brain trace read** | `load_latest_brain_trace_summary(get_brain_pipeline_config())` → `config/brain_pipeline.json` `trace_path` (default `data/runtime/brain_last_pipeline.json`) |
| **Brain trace write** | **Now:** config-gated via `run_operator_chat_turn` + `_maybe_run_brain_operator_chat_trace` (same rules as runtime). *Historical note below may say “not on UI” — obsolete.* |
| **Elysia change proposals** | **No** `/api/proposals` routes on this host |
| **Frontend API calls** | **Same origin** — `fetch('/api/...')` relative to control panel port (e.g. `:5000`), **not** `:8123` |

### 1.2 RuntimeAPIServer

| Item | Detail |
|------|--------|
| **Startup** | `ElysiaRuntime._init_api_server()` when `RuntimeConfig.enable_api` (`elysia/runtime.py`) |
| **Default bind** | `127.0.0.1:8123` (`elysia/config.py`, `ELYSIA_API_PORT`) |
| **Serves UI?** | **No** — JSON API + CORS |
| **Route registration** | `RuntimeAPIServer._setup_routes()` in `elysia/api/server.py` |
| **Conversation store** | Injected optional `conversation_store`; else `get_default_conversation_store()` singleton → same `DEFAULT_CONVERSATIONS_DIR` |
| **Proposal queue** | Injected optional `self_improvement_queue`; else `get_default_proposal_queue()` |
| **Brain trace read** | Same `load_latest_brain_trace_summary` + `get_brain_pipeline_config()` |
| **Brain trace write** | `POST /api/chat` → `_maybe_run_brain_operator_chat_trace` when `brain_pipeline.enabled` + `entrypoints.operator_chat` |
| **Elysia change proposals** | **Yes** — `/api/proposals/*` including **implement** (outside safe stack) |
| **Optional injection** | `guardian`, `architect`, `proposal_system`, `implementer` wired from runtime |

### 1.3 Unified launcher / attach (context only)

| Item | Detail |
|------|--------|
| **`run_elysia_unified.py`** | Delegates to `elysia.py` full backend (`ELYSIA_FORCE_FULL_BACKEND=1`) |
| **`elysia_interface.py`** | Attach mode polls `STATUS_URL` (default **8888**), not 5000/8123 |
| **Risk** | Operators may think “one Elysia URL” while safe-stack data lives under 5000 vs 8123 |

---

## 2. Route comparison table

Legend: **Safe** = in safe-stack smoke slice. **Canon** = shared library function.

| Route | RuntimeAPIServer | UIControlPanel | Canonical helper | State path | Safe? | Risk / notes |
|-------|------------------|----------------|------------------|------------|-------|----------------|
| `POST /api/chat` | `run_operator_chat_turn` + architect/echo responder; proposal branch outside helper | `run_operator_chat_turn` + `chat_with_llm` / `ask_ai` | `safe_stack.operator_chat` + host responders | `data/runtime/conversations/<id>.jsonl` | Safe | **Envelopes differ** (`response`/`reply`/cookie vs `success`/`history`); **brain_* additive on both** when config enables `operator_chat`. |
| `GET /api/chat/history` | `store.list_messages` / recent | `_chat_history_for_response` → store | `ConversationStore` | Same dir | Safe | UI default session id `control_panel`; runtime uses cookie `elysia_conversation_id` or body |
| `GET /api/conversations` | `store.list_conversations()` | `store.list_conversations()` | `ConversationStore` | Same dir | Safe | Duplicate handlers |
| `POST /api/conversations` | `new_conversation_id()` | `new_conversation_id()` | `ConversationStore` | Same dir | Safe | Duplicate handlers |
| `GET /api/conversations/<id>` | `list_messages` | `list_messages` | `ConversationStore` | Same dir | Safe | UI returns `messages`; runtime may differ key naming — verify clients |
| `POST /api/conversations/<id>/messages` | **Yes** | **Yes** | `ConversationStore` | Same dir | Safe | Duplicate handlers |
| `DELETE /api/conversations/<id>` | `delete_conversation` | `delete_conversation` | `ConversationStore` | Same dir | Safe | Duplicate handlers |
| `DELETE /api/chat/history` | Clears via store | `_clear_chat_history` | `ConversationStore` | Same dir | Safe | Duplicate handlers |
| `GET /api/brain/trace/latest` | `load_latest_brain_trace_summary` | Same | `trace_visibility.load_latest_brain_trace_summary` | `brain_last_pipeline.json` | Safe | Same file if same config cwd |
| `GET /api/memory/ranking/summary` | `load_memory_ranking_visibility(store=...)` | Same with `self._conversation_store` | `memory_ranking.visibility` | Reads conversations + trace fallback | Safe | Same store path if defaults used |
| `GET /api/prompt-contracts/status` | `build_prompt_contract_status()` | Same | `prompt_contracts.controls` | Config + trace file | Safe | No host-specific state |
| `GET /api/self-improvement/proposals` | `sanitize_proposal` + queue | Same pattern | `proposal_queue` + `sanitize_proposal` | `self_improvement_proposals.jsonl` | Safe | Duplicate handlers; same default queue singleton |
| `GET /api/self-improvement/proposals/<id>` | queue `.get` | queue `.get` | Same | Same JSONL | Safe | Duplicate handlers |
| `POST .../status` | queue `.update_status` | queue `.update_status` | Same | Same JSONL | Safe | Status-only, no execute |
| `GET .../export_prompt` | `build_self_improvement_prompt_export_response` | Same helper | `safe_stack_responses` + `prompt_export` | N/A (derived) | Safe | Normalized envelope (`success: true` + export fields) |
| `GET /api/proposals` | Elysia `proposal_system` | **Absent** | N/A | Proposal system store | **No** | Implement/approve only on runtime |
| `POST /api/proposals/<id>/implement` | **Yes** (unsafe) | **Absent** | Implementer agent | Varies | **No** | Must stay out of safe stack |

**Note:** `project_guardian/prompt_contracts/status.py` does **not** exist; status is implemented in `prompt_contracts/controls.py`.

---

## 3. State paths (canonical on-disk)

| State | Default path | Writers | Readers (both hosts) |
|-------|--------------|---------|----------------------|
| Conversations | `data/runtime/conversations/*.jsonl` | Both chat paths via `ConversationStore` | Both |
| Legacy chat import marker | `data/runtime/conversations/.legacy_control_panel_chat_history_imported` | UI init import | — |
| Legacy chat file | `data/runtime/control_panel_chat_history.json` | Historical | UI import only |
| Self-improvement proposals | `data/runtime/self_improvement_proposals.jsonl` | Brain enqueue, queue API | Both list/get/status/export |
| Legacy SI queue | `data/runtime/brain_self_improvement_queue.jsonl` | Brain dual-write | Not API-exposed |
| Brain trace | `data/runtime/brain_last_pipeline.json` | BrainPipeline persist | trace + prompt-contract status |
| Brain config | `config/brain_pipeline.json` | Manual edit | `get_brain_pipeline_config()` |

---

## 4. State split risks

### 4.1 Low risk when defaults apply (same repo cwd)

- **Conversation files:** Both hosts use `ConversationStore` rooted at `DEFAULT_CONVERSATIONS_DIR` unless `orchestrator.conversation_store_dir` overrides UI only.
- **Proposals:** Both use `get_default_proposal_queue()` → same JSONL.
- **Brain trace / prompt contracts:** Same config loader and trace path.

### 4.2 Material risks

| Risk | Severity | Description |
|------|----------|-------------|
| **Different ports** | High (UX) | Dashboard at `:5000` never calls `:8123`; operator may run only one host and miss routes/features on the other. |
| **Brain hook only on runtime chat** | ~~Medium~~ **Mitigated** | *Historical.* Both hosts call the operator-chat brain trace callback when config enables `entrypoints.operator_chat` (dry-run by default). |
| **Session identity** | Medium | UI: `localStorage` + default `control_panel` conversation id. Runtime: cookie `elysia_conversation_id`. Same store, different ids → “split history” perception. |
| **Duplicate route logic** | Medium | Handlers are copy-pasted; future fixes can diverge (e.g. export_prompt JSON shape, error payloads). |
| **Separate ConversationStore instances** | Low–Medium | UI constructs its own `ConversationStore`; runtime uses singleton. Same files, but two objects — no shared in-process lock beyond file-level JSONL append. |
| **`/api/proposals` only on runtime** | High if misused | Implement path is **not** safe-stack; easier to discover on 8123 than on 5000. |
| **8888 status vs 5000/8123** | Low | Attach tooling does not substitute for safe-stack APIs. |
| **cwd / path overrides** | Medium | If runtime starts with different working directory, `get_brain_pipeline_config()` trace_path resolution could differ from UI. |

### 4.3 UI calls its own Flask routes

Embedded JS uses **relative** URLs (`fetch('/api/brain/trace/latest')`, etc.). It does **not** proxy to RuntimeAPIServer. Confirmed: no hardcoded `:8123` in safe-stack dashboard fetches.

---

## 5. Strategy options

### A. Single API owner (UI proxies runtime)

- UI serves static/template only; all `/api/*` safe-stack traffic proxied to `127.0.0.1:8123`.
- **Pros:** One handler set, one chat+brain behavior, clearest operator model.
- **Cons:** Large change; requires runtime always up; Socket.IO and 100+ control-panel-only routes still need UI host.

### B. Shared canonical helpers only (current near-state)

- Keep two hosts; extract duplicated routes into a Flask **Blueprint** or shared functions module used by both registrars.
- **Pros:** Minimal operational change; fixes drift; matches today’s disk layout.
- **Cons:** Still two ports; brain hook gap on UI chat remains unless unified in shared chat helper.

### C. Hybrid transition (recommended at plan time — **mostly done**)

1. [x] **Document** mirrors and ports → [`API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`](API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md).
2. [x] **Shared helpers** — `safe_stack/responses.py` + `safe_stack/operator_chat.py` (blueprint optional; not required now).
3. [x] **Unify** `POST /api/chat` via `run_operator_chat_turn` on both hosts (config-gated brain callback).
4. [x] **Regression tests** — `test_api_host_route_parity.py`, runtime/panel operator-chat integration tests; smoke **227 passed**.
5. **Later:** optional UI proxy for operators who only start Guardian (phase A).

**Blueprint:** Optional only if a third host appears or route registration drift returns — **not currently recommended** (see final checkpoint §A).

---

## 6. Phased implementation plan

### Phase 0 — Documentation & CI (done / in progress)

- [x] Architecture checkpoint
- [x] GitHub Actions `Safe stack smoke`
- [x] This consolidation plan

### Phase 1 — Guardrails (done)

- [x] `project_guardian/tests/test_api_host_route_parity.py` — route registration, response shapes, store path, negative checks, documented chat hook difference.
- [x] `project_guardian/tests/test_safe_stack_response_helpers.py` — helper unit tests (dict + status, export envelope, status validation).
- [ ] `test_conversation_store_path_parity.py` (optional split) — partially covered by parity tests.
- Document operator note: “Use one conversation id; chat on dashboard uses port 5000.”

#### Shared response helpers (done)

- Module: `project_guardian/safe_stack/responses.py` (framework-neutral builders; `project_guardian/api/` avoided because it shadows legacy `api.py`).
- Both `RuntimeAPIServer` and `UIControlPanel` call helpers for mirrored read/status routes.
- **`export_prompt` envelope normalized** on both hosts: `{ success, proposal_id, target, prompt, copy_safe, warnings }`.

#### Remaining intentional drift (current)

| Area | Runtime | Control panel |
|------|---------|---------------|
| `POST /api/chat` envelope | `response` + `reply` + cookie; proposal branch outside helper | `success` + `history`; `persist_user_before_responder=False` on LLM error |
| Brain trace | Config-gated on both via helper callback | Same (duplicate host `_maybe_run_brain_*` methods) |
| Session | Cookie `elysia_conversation_id` | Default `control_panel` + localStorage |
| `GET /api/conversations/<id>` message limit | 50 (helper default) | 20 (`CONTROL_PANEL_CHAT_RESPONSE_MESSAGES`) |

#### Next implementation phase (post-consolidation)

See [`API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md`](API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md) §H. Optional blueprint only if duplication hurts again.

### Phase 2 — Shared route module (optional, **not started**)

*Historical.* Mirrored read routes already use `safe_stack/responses.py` without a Flask blueprint.

### Phase 3 — Unified operator chat helper — **done**

- Module: `project_guardian/safe_stack/operator_chat.py` (not `project_guardian/api/operator_chat.py`).
- Wired: Runtime Phase 2, UI Phase 3; tests in smoke slice.

### Phase 4 — Optional single-port mode (later)

- Env `ELYSIA_SAFE_STACK_API_BASE=http://127.0.0.1:8123` for UI-only deployments that want proxy.
- Or: start RuntimeAPIServer in-process and mount blueprint once.

---

## 7. Tests needed

| Test | Purpose |
|------|---------|
| `test_api_host_route_parity.py` | Safe-stack paths exist on both hosts (import app route map) |
| `test_safe_stack_store_paths.py` | Default conversation + proposal + trace paths match |
| `test_chat_brain_hook_both_hosts_when_config_enabled` in `test_api_host_route_parity.py` | Brain hook on **both** hosts when config on — **exists** |
| `test_runtime_operator_chat_helper_integration.py` / `test_control_panel_operator_chat_helper_integration.py` | Host wiring — **exist** |
| CI: `Safe stack smoke` workflow | **227** tests on last run (see final checkpoint) |

---

## 8. Non-goals

- Enabling autonomy, live execution, or `operator_chat_live_execution` by default
- Merging `/api/proposals` implement flow into safe stack
- Removing UIControlPanel-specific routes (insights, introspection, memory cleanup, learning tests)
- Replacing `module_prompt_registry` with `prompt_contracts`
- Running real LLMs or external APIs in CI
- Deleting legacy `brain_self_improvement_queue.jsonl` dual-write (separate cleanup)

---

## 9. Operator guidance (interim)

1. Prefer **one conversation id** across refreshes (control panel localStorage / explicit id).
2. For **brain trace from chat**, enable `brain_pipeline` + `operator_chat`; either host `POST /api/chat` (**5000** or **8123**) runs the same config-gated dry-run hook when enabled.
3. Safe-stack visibility panels on dashboard (**5000**) read the same on-disk trace/proposals as **8123** when cwd and config match.
4. Do not use `/api/proposals/.../implement` for self-improvement review — use `/api/self-improvement/...` only.

---

## 10. Verification

```bash
python scripts/run_safe_stack_smoke_tests.py
make safe-smoke
```

Expected: **227 passed** (last verified 2026-05-18); confirms helpers and dual-host Flask test clients, not production co-hosting on one port.
