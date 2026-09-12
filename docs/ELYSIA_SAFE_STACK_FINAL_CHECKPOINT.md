# Elysia safe-stack final checkpoint

**Related plan:** `docs/ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md` - planning-only one-entry operator interface simplification.

**Date:** 2026-05-24 (post-commit audit)  
**Status:** **Source of truth** for the safe-stack slice after UI marker restoration and governance visibility  
**Scope:** Documentation only — no production behavior changed by this report.

**Post-commit audit (milestone complete):** [`SAFE_STACK_POST_COMMIT_AUDIT.md`](SAFE_STACK_POST_COMMIT_AUDIT.md) — 10-commit chain, final smoke **386 passed**, index clean, unstaged server hunks excluded.

**Related (historical / slice-specific):**

- `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md` — runtime vs UI host parity
- `docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md` — live-execution governance slice
- `docs/CONTROL_PANEL_CONVERSATION_MEMORY.md` — conversation memory and legacy import
- `docs/SELF_IMPROVEMENT_PROPOSAL_QUEUE.md` — proposal queue and export
- `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md` — short architecture index (links here)

---

## Executive summary

The **safe stack** is the operator-facing, fail-closed slice of Elysia / Project Guardian: durable conversation memory, read-only diagnostics (brain trace, memory ranking, prompt contracts, self-improvement proposals), shared HTTP response builders, shared operator-chat orchestration, and **live-execution governance** (guard + confirmation store + read-only visibility). Runtime API (`elysia/api/server.py`, default `:8123`) and UI control panel (`project_guardian/ui_control_panel.py`, default `:5000`) mirror the same safe-stack routes via `project_guardian/safe_stack/`.

**Included today:**

- Canonical `ConversationStore` for chat/history/conversations
- `run_operator_chat_turn` shared operator-chat helper (hosts supply LLM/brain callbacks)
- BrainPipeline / Think–Decide–Act **dry-run** trace persistence and sanitized trace API
- Prompt contract validation **visibility** (config-gated; defaults off)
- Memory ranking **read-only** summary API
- Self-improvement proposal queue (list/get/status/export only)
- Operator confirmation store + validation-only guard integration + **read-only** governance diagnostics API
- Control panel dashboard panels and helper copy (Brain Trace, proposals, export, ranking, contracts, system safety card)

**Intentionally disabled / unwired:**

- **Live execution** — `config/brain_pipeline.json`: `enabled: false`, `dry_run: true`, `operator_chat_live_execution: false`
- **Autonomy** — not wired through safe-stack routes; `entrypoints.autonomy: false`
- **Confirmation creation/consumption** — no create API; `mark_operator_confirmation_used` not called from runtime/API visibility
- **Self-improvement implement/apply** — no execute routes in safe stack
- **Memory ranking mutations** — `memory_ranking.enabled: false`, `allow_delete_proposals: false`
- **Real LLM / external API calls** — smoke tests use mocks/offline paths only

**Smoke (verified 2026-05-24, post-commit audit):**

```text
python scripts/run_safe_stack_smoke_tests.py
-> 386 passed, 3 warnings
```

See [`SAFE_STACK_POST_COMMIT_AUDIT.md`](SAFE_STACK_POST_COMMIT_AUDIT.md) for full commit chain (`1ada6e8` … `ec458c5`) and worktree exclusions.

---

## Systems completed

| System | Role | Canonical module(s) |
|--------|------|---------------------|
| **ConversationStore & chat memory** | Append-only JSONL per conversation; redaction; legacy control-panel JSON import-once | `project_guardian/conversation_store.py` |
| **Shared operator-chat helper** | History → optional persist → brain callback → responder → assistant persist | `project_guardian/safe_stack/operator_chat.py` |
| **Shared safe-stack responses** | Framework-neutral JSON builders for mirrored GET/POST routes | `project_guardian/safe_stack/responses.py` |
| **BrainPipeline / TDA dry-run trace** | Config-gated pipeline; compact trace file; fail-open on chat | `project_guardian/brain/pipeline.py`, `runtime.py`, `think_decide_act_adapter.py`, `tda_trace_fields.py` |
| **Brain trace visibility** | Sanitized latest-trace summary for API/UI | `project_guardian/brain/trace_visibility.py` |
| **Prompt contracts & controls** | Registry, validation, status builder (defaults off) | `project_guardian/prompt_contracts/` (`controls.py`, `validation.py`, …) |
| **Memory ranking visibility** | Read-only ranking summary from recent memories | `project_guardian/memory_ranking/visibility.py`, `ranking.py` |
| **Self-improvement queue & export** | Canonical JSONL queue; status updates; Cursor/Codex prompt export | `project_guardian/self_improvement/proposal_queue.py`, `prompt_export.py` |
| **Operator confirmation store** | Append-only confirmations JSONL | `project_guardian/governance/operator_confirmation_store.py` |
| **Live-execution guard (fail-closed)** | Denies live paths; forces dry-run metadata on denied attempts | `project_guardian/governance/live_execution_guard.py` |
| **Guard audit** | Append-only audit JSONL for guard decisions | `project_guardian/governance/live_execution_audit.py` |
| **Confirmation validation (runtime)** | Loads confirmation by ID; does **not** mark used | `project_guardian/brain/live_execution_runtime.py` |
| **Operator confirmation visibility** | Read-only list/detail diagnostics | `project_guardian/governance/operator_confirmation_visibility.py` |
| **Control panel visibility** | HTML/JS markers + mirrored routes; review-only panels | `project_guardian/ui_control_panel.py` (`CONTROL_PANEL_TEMPLATE`) |

**Recent fixes (no new features):**

- Safe-stack dashboard UI markers restored (`brain-visibility-panel`, proposal export, memory ranking, prompt contracts, JS refresh helpers).
- Operator confirmation governance endpoints exposed on both hosts (API-only in UI — no dedicated panel markup).

---

## Canonical paths

### Data (runtime)

| Artifact | Path |
|----------|------|
| Conversations | `data/runtime/conversations/<conversation_id>.jsonl` |
| Legacy control-panel chat (import-only) | `data/runtime/control_panel_chat_history.json` |
| Import marker | `data/runtime/conversations/.legacy_control_panel_chat_history_imported` |
| Brain last trace | `data/runtime/brain_last_pipeline.json` (config: `brain_pipeline.trace_path`) |
| Self-improvement proposals | `data/runtime/self_improvement_proposals.jsonl` |
| Legacy SI queue (opt-in dual-write) | `data/runtime/brain_self_improvement_queue.jsonl` |
| Operator confirmations | `data/runtime/operator_confirmations.jsonl` |
| Live-execution guard audit | `data/runtime/live_execution_guard_audit.jsonl` |

### Config (defaults unchanged)

| File | Safe-stack relevance |
|------|----------------------|
| `config/brain_pipeline.json` | Pipeline off, dry-run on, live/autonomy entrypoints off |
| `config/memory_ranking.json` | Ranking off, delete proposals disallowed |

### Modules

| Concern | Path |
|---------|------|
| ConversationStore | `project_guardian/conversation_store.py` |
| Safe-stack responses | `project_guardian/safe_stack/responses.py` |
| Safe-stack operator chat | `project_guardian/safe_stack/operator_chat.py` |
| Brain config | `project_guardian/brain/config.py` |
| Brain pipeline / runtime / TDA | `project_guardian/brain/pipeline.py`, `runtime.py`, `think_decide_act_adapter.py`, `tda_trace_fields.py` |
| Trace visibility | `project_guardian/brain/trace_visibility.py` |
| Live-execution runtime adapter | `project_guardian/brain/live_execution_runtime.py` |
| Memory ranking | `project_guardian/memory_ranking/ranking.py`, `visibility.py` |
| Prompt contracts | `project_guardian/prompt_contracts/controls.py` (and package siblings) |
| SI proposal queue | `project_guardian/self_improvement/proposal_queue.py` |
| SI prompt export | `project_guardian/self_improvement/prompt_export.py` |
| Live-execution guard | `project_guardian/governance/live_execution_guard.py` |
| Live-execution audit | `project_guardian/governance/live_execution_audit.py` |
| Operator confirmation store | `project_guardian/governance/operator_confirmation_store.py` |
| Operator confirmation visibility | `project_guardian/governance/operator_confirmation_visibility.py` |
| HTTP hosts | `elysia/api/server.py`, `project_guardian/ui_control_panel.py` |

---

## Endpoint inventory

### Safe-stack (mirrored on Runtime API + UI control panel)

| Method | Path | Shared builder / notes |
|--------|------|------------------------|
| `GET`, `DELETE` | `/api/chat/history` | `build_chat_history_*` |
| `GET`, `POST` | `/api/conversations` | `build_conversations_list_response`, `build_conversation_create_response` |
| `GET`, `DELETE` | `/api/conversations/<conversation_id>` | `build_conversation_detail_response`, `build_conversation_delete_response` |
| `POST` | `/api/chat` | `run_operator_chat_turn` (host-specific envelope; not in parity spec) |
| `POST` | `/api/conversations/<conversation_id>/messages` | Inline append (both hosts; duplicate thin handlers) |
| `GET` | `/api/brain/trace/latest` | `build_brain_trace_latest_response` |
| `GET` | `/api/memory/ranking/summary` | `build_memory_ranking_summary_response` |
| `GET` | `/api/prompt-contracts/status` | `build_prompt_contracts_status_response` |
| `GET` | `/api/self-improvement/proposals` | `build_self_improvement_proposals_list_response` |
| `GET` | `/api/self-improvement/proposals/<proposal_id>` | `build_self_improvement_proposal_detail_response` |
| `POST` | `/api/self-improvement/proposals/<proposal_id>/status` | Status field only — no implement |
| `GET` | `/api/self-improvement/proposals/<proposal_id>/export_prompt` | `build_self_improvement_prompt_export_response` |
| `GET` | `/api/governance/operator-confirmations` | `build_operator_confirmations_list_response` — read-only |
| `GET` | `/api/governance/operator-confirmations/<operator_confirmation_id>` | `build_operator_confirmation_detail_response` — read-only |

**Governance list query params:** `limit` (default 25, max 50), optional `conversation_id`, optional `status`.

### Explicitly outside safe stack

| Route | Host | Notes |
|-------|------|--------|
| `/api/proposals/*` | Runtime API only | Elysia change proposals; approve/**implement** — not part of safe stack |
| `/api/status`, `/api/events` | Runtime API | Lifecycle / event bus |

Parity enforced by `project_guardian/tests/test_api_host_route_parity.py` (`SAFE_STACK_ROUTE_SPECS`).

---

## Dashboard/control panel inventory

Template: `CONTROL_PANEL_TEMPLATE` in `project_guardian/ui_control_panel.py`.

| Panel / area | Markers | Behavior |
|--------------|---------|----------|
| **System Safety Status** | `system-safety-status-card` | Plain-language autonomy/live-exec/memory/SI/chat notes |
| **Conversation Chat** | `getApiChatConversationId`, `refreshApiChatHistory`, `/api/chat/history` | Canonical store; localStorage session id |
| **Brain Trace** | `brain-visibility-panel`, `brain-trace-summary`, `refreshBrainTrace` | `GET /api/brain/trace/latest`; dry-run copy |
| **Self-Improvement Proposals** | `self-improvement-proposals-list`, `refreshSelfImprovementProposals` | List + status buttons (review states only) |
| **Proposal Export** | `exportSelfImprovementProposalPrompt`, export pre block | Cursor/Codex export — no apply |
| **Memory Ranking** | `memory-ranking-panel`, `refreshMemoryRankingSummary` | `GET /api/memory/ranking/summary` |
| **Prompt Contracts** | `prompt-contract-panel`, `refreshPromptContractStatus` | `GET /api/prompt-contracts/status` |
| **Operator confirmations** | *API only* | Routes registered; **no dedicated dashboard panel** — use REST diagnostics |
| **Review-only markers** | `brain-visibility-review-only-start/end` | “Does not apply code” warnings |

Secondary tabs include operator helper copy (Learning, Task Queue, Workbench, Security, Introspection, observability).

---

## Safety boundaries

| Boundary | Status |
|----------|--------|
| **Autonomy** | Not wired through safe-stack routes; smoke does not enable autonomy execution |
| **Live execution** | Disabled by default; guard fail-closed; denied attempts recorded with dry-run forced |
| **Apply / run / execute** | Safe-stack panels and parity tests forbid `apply_patch`, `run_command`, implement routes in mirrored handlers |
| **Confirmations** | Validation-only in `live_execution_runtime`; visibility and API do **not** create or mark used |
| **Memory ranking** | Read-only summary; config disallows delete proposals by default |
| **Self-improvement** | Review, status update, and export only — no queue-driven implement |
| **Prompt / trace leakage** | Sanitized API payloads; forbidden keys checked in governance visibility tests |
| **Legacy files** | Not auto-deleted: `control_panel_chat_history.json`, `brain_self_improvement_queue.jsonl` (opt-in dual-write via `ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE=1`) |

Default `config/brain_pipeline.json` (unchanged):

- `enabled: false`, `dry_run: true`
- `operator_chat: false`, `operator_chat_live_execution: false`, `autonomy: false`

---

## Smoke/test inventory

**Command:** `python scripts/run_safe_stack_smoke_tests.py`  
**Result:** **386 passed, 3 warnings** (2026-05-24, post-commit audit)

**Script:** `scripts/run_safe_stack_smoke_tests.py` — 28 required modules + 2 optional alternates (TDA naming, memory-ranking imports).

| Group | Test module(s) |
|-------|----------------|
| Conversation store | `test_conversation_store.py` |
| Control panel chat / legacy retirement | `test_control_panel_chat_memory.py`, `test_control_panel_legacy_history_retirement.py` |
| Control panel UI / brain / JS | `test_control_panel_brain_visibility.py`, `test_control_panel_js_smoke.py`, `test_control_panel_ui_clarity.py` |
| Brain trace / TDA | `test_brain_trace_visibility.py`, `test_brain_tda_integration.py`, `test_tda_trace_fields.py` (optional alt) |
| Self-improvement queue / export / legacy | `test_self_improvement_proposal_queue.py`, `test_self_improvement_prompt_export.py`, `test_self_improvement_legacy_queue_retirement.py` |
| Prompt contracts | `test_prompt_contracts.py`, `test_prompt_contract_integration.py`, `test_prompt_contract_controls.py` |
| Memory ranking | `test_memory_ranking.py`, `test_memory_ranking_visibility.py`, `test_memory_ranking_imports.py` (optional alt) |
| API host parity / response helpers | `test_api_host_route_parity.py`, `test_safe_stack_response_helpers.py` |
| Operator chat helper | `test_operator_chat_helper.py`, `test_runtime_operator_chat_helper_integration.py`, `test_control_panel_operator_chat_helper_integration.py` |
| Live-execution governance | `test_live_execution_governance_docs.py`, `test_live_execution_guard.py`, `test_live_execution_guard_runtime_integration.py` |
| Operator confirmations | `test_operator_confirmation_context_plan.py`, `test_operator_confirmation_store.py`, `test_operator_confirmation_guard_integration.py`, `test_operator_confirmation_visibility.py` |
| One-shot script quarantine | `test_one_shot_ui_scripts_quarantined.py` |
| Gitignore / runtime hygiene | `test_safe_stack_gitignore.py` |

---

## Ignore hygiene (generated runtime)

- **Updated:** `.gitignore` excludes `data/runtime/`, `data/context_pipeline/`, `data/prompt_registry/`, `deployments/`, temp outputs, `REPORTS/*.json(l)`, and tool caches.
- **Policy:** Runtime and generated safe-stack artifacts must not be committed; use directory rules rather than duplicating every JSONL filename.
- **Guard:** `test_safe_stack_gitignore.py` in the smoke slice.

---

## H. Known cleanup risks

**One-shot UI repair scripts (quarantined):** `scripts/maintenance/one_shot/` — `_restore_safe_stack_control_panel_ui.py`, `_apply_control_panel_ui_clarity.py`, `_apply_control_panel_secondary_clarity.py`, `_patch_prompt_contract_ui.py`, plus `README.md`. Not runtime/CI/smoke; guard `test_one_shot_ui_scripts_quarantined.py`. Source of truth: `project_guardian/ui_control_panel.py` + UI marker pytest modules.

1. **Dual response envelopes** — `POST /api/chat` intentionally differs (runtime Architect/echo vs UI `success`/`reply`/`history`). Clients must not assume one shape across ports.
3. **Historical docs** — `docs/API_HOST_STATE_CONSOLIDATION_PLAN.md`, `docs/OPERATOR_CHAT_HELPER_PLAN.md`, and older audits may describe pre-helper state; use **this file** and `docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md` first.
4. **Optional Flask blueprint** — Not required unless a third host appears or route registration drifts; current thin wrappers + shared helpers are the intended pattern.
5. **Lingering legacy artifacts** — `control_panel_chat_history.json`, `brain_self_improvement_queue.jsonl`, duplicate `_maybe_run_brain_operator_chat_trace` in two hosts (~45 lines each).
6. **Governance UI gap** — Operator confirmations are API-visible only; operators need curl/browser or a future read-only panel.

---

## Product simplification (planned)

**One-entry operator UI:** [`docs/ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md`](ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md) — “Ask Elysia anything” as the primary dashboard entry; safe-stack panels move to collapsible read-only details. Planning only; no implementation in that doc’s scope.

## Recommended next steps

1. ~~**Clean / quarantine one-shot UI restore/apply scripts**~~ — **Done:** `scripts/maintenance/one_shot/` + README + quarantine tests.
2. **Phase 1 one-entry UI** — See [`ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md`](ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md) (labels, safety strip, collapse advanced panels).
3. **Read-only governance panel in UI (optional)** — Fold into Phase 2 of one-entry plan (collapsible governance diagnostics).
3. **Executor allowlist registry tests** — Expand governance tests for tool/capability allowlists referenced by confirmations.
4. **Rollback metadata planner tests** — Cover rollback fields in confirmation/guard context without enabling execution.
5. **Staged live execution (non-production only)** — Only after all governance gates, explicit config, UI confirmation flows, and operator runbooks; never flip defaults in `config/brain_pipeline.json` as part of safe-stack work.

---

## Release readiness (git / commit hygiene)

**Milestone status (2026-05-24):** All 10 safe-stack commit groups landed; smoke **386 passed**. Worktree still mixed — see post-commit audit before push.

- [`SAFE_STACK_POST_COMMIT_AUDIT.md`](SAFE_STACK_POST_COMMIT_AUDIT.md) — **final** commit chain, smoke, dirty-file exclusions  
- [`SERVER_UNSTAGED_RISKY_HUNKS.md`](SERVER_UNSTAGED_RISKY_HUNKS.md) — do not stage remaining `elysia/api/server.py` hunks  
- [`SAFE_STACK_RELEASE_READINESS_AUDIT.md`](SAFE_STACK_RELEASE_READINESS_AUDIT.md) — worktree categories and files to exclude  
- [`SAFE_STACK_COMMIT_STAGING_PLAN.md`](SAFE_STACK_COMMIT_STAGING_PLAN.md) — **manual `git add` per group** (do not `git add -A`)

## Verification

```bash
python scripts/run_safe_stack_smoke_tests.py
python -m pytest project_guardian/tests/test_control_panel_ui_clarity.py -q
python -m pytest project_guardian/tests/test_operator_confirmation_visibility.py -q
```

**Production code changed by this checkpoint:** **No** — documentation update only.
