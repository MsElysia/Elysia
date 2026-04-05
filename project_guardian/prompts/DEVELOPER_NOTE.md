# Elysia prompt stack (Project Guardian)

## Invariant

New LLM call sites should assemble prompts with `project_guardian.llm.prompted_call` helpers (`prepare_prompted_bundle`, `prepare_prompted_system`, `prepare_prompted_messages`) or, for low-level use, `build_prompt()` / `build_prompt_bundle()` from `project_guardian.prompts` (import the helpers from **`project_guardian.llm`**, not `project_guardian.prompts`, to avoid circular imports).

Public LLM entry points require **keyword-only** `module_name` and optional `agent_name`. Use **`require_prompt_profile()`** (from `project_guardian.llm.prompted_call`) at entry boundaries; it validates the profile and supports `allow_legacy=True` only for documented escape hatches.

## Central helpers (`project_guardian.llm.prompted_call`)

| Helper | Purpose |
|--------|---------|
| `require_prompt_profile(module_name, agent_name, *, allow_legacy=False, caller=None)` | Validate or mark legacy; returns `(mod, ag, legacy_prompt_path)`. |
| `prepare_prompted_bundle(...)` | Validate + `build_prompt_bundle`; returns `prompt_text`, `meta`, `logging_fields`, `module_name`, `agent_name`. |
| `prepare_prompted_system(...)` | Same as bundle; adds `system_text` alias for system-string APIs. |
| `prepare_prompted_messages(messages, ...)` | Prepends stack as system message(s); returns `messages`, `meta`, `logging_fields`. |
| `log_prompted_call(...)` | **Canonical** audit log line (see required fields below). |
| `flatten_bundle_meta(meta)` | Nested `meta` → flat keys for tests/custom logs. |

`prompt_builder.log_llm_prompt_usage` delegates to `log_prompted_call` (backward compatible).

## Elysia cloud fallback (`project_guardian.elysia_llm_fallback`)

When `unified_chat_llm_router` is disabled in config, or `unified_chat_completion` raises, **`elysia.py`** uses **`elysia_cloud_fallback_completion`**: same `planner` + `orchestrator` stack and `UNIFIED_CHAT_PROMPT_TASK_TEXT` as `unified_llm_route` / `MistralEngine.complete_chat`, then `cloud_preferred` (OpenAI → OpenRouter) unchanged.

## Architectural boundary (prompt vs transport)

| Layer | Role |
|-------|------|
| **Prompt assembly** | `unified_llm_route`, `elysia_llm_fallback`, `MistralEngine`, `mutation`, `auto_learning.compress_with_llm`, orchestration **pipelines** (system strings via `build_prompt`). |
| **Transport** | `elysia._llm_completion_cloud_openai` / `_openrouter`, orchestration **adapters** (`OpenAIAdapter`, `OllamaAdapter`): HTTP only; **no** Guardian prompt registry; callers pass final `messages`. |

Orchestration adapters log **`log_legacy_llm_call(..., reason=orchestration_*_adapter_transport)`** once per call — intentional; they are not chat fallbacks.

## Required logging fields (canonical `[PromptStack]` line)

Emitted by `log_prompted_call` (no full prompt bodies):

- `module_name`, `agent_name`, `task_type`, `provider`, `model`
- `prompt_core_name`, `prompt_core_version`
- `prompt_module_name`, `prompt_module_version`
- `prompt_agent_name`, `prompt_agent_version`
- `prompt_length`
- `legacy_prompt_path` (`True` only if explicitly logged as legacy path)

## Legacy paths (intentionally unmigrated)

| Path | Impact | Notes |
|------|--------|--------|
| **Orchestration adapters** (`OpenAIAdapter`, `OllamaAdapter`) | Transport | **Prompt-agnostic** by design; `log_legacy_llm_call` with stable `reason=orchestration_*_adapter_transport`. |
| **WebScout** (`research_with_llm`) | Medium | Inline research prompts; `reason=inline_prompt_webscout_research`. |
| **Implementer codegen** (`CodegenClient.generate_code`) | Medium | Inline codegen prompts; `reason=inline_prompt_implementer_codegen`. |
| **Memory condense** (`elysia.condense_memory_with_ai`) | High local | Structured JSON task; not migrated in this pass. |

**Legacy observability:** `log_legacy_llm_call(detail, caller="Module.fn", reason="...")` — stable `reason` strings; `detail` optional. No duplicate `log_prompted_call` on the same invocation for these paths.

## Migration status summary

- **Unified chat** (`unified_chat_completion`): all backends + prompt stack + `log_prompted_call`.
- **Elysia fallback** (`_chat_with_llm_cloud_only`, `_llm_completion` when unified off or on exception): **`elysia_cloud_fallback_completion`** — migrated.
- **Adapters / WebScout / codegen**: legacy markers only; boundary above.

## Preferred migration pattern for a new LLM call site

1. Register module/agent prompts if new names are needed (`prompt_registry.py`).
2. At the entrypoint: `mod, ag, legacy = require_prompt_profile(..., caller="YourClass.method")`.
3. Build: `prepare_prompted_bundle` or `prepare_prompted_messages`.
4. Log: `log_prompted_call(..., bundle_meta=prep["meta"], prompt_length=len(...), legacy_prompt_path=False)`.
5. If you cannot use the stack yet: `log_legacy_llm_call(...)` and plan a follow-up.

See also: `REGISTRY_IDENTITY.md` (prompt registry vs orchestration capability registry vs AskAI-local engines).

## Add a new module prompt

1. Create `project_guardian/prompts/modules/<name>.py` with `MODULE_META` (`name`, `version`, `description`) and `MODULE_TEXT`.
2. Export in `modules/__init__.py`.
3. Register in `prompt_registry.py` `MODULES` dict.

## Add a new agent prompt

1. Create `project_guardian/prompts/agents/<name>.py` with `AGENT_META` and `AGENT_TEXT`.
2. Export in `agents/__init__.py`.
3. Register in `prompt_registry.py` `AGENTS` dict.

Unknown module or agent names raise `KeyError` with the list of known keys.
