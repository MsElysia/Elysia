# Registry and component naming (avoid confusion)

## Prompt registry (`project_guardian.prompts`)

- **What it is:** Named **module** and **agent** prompt profiles (metadata + text) used by `build_prompt` / `prepare_prompted_bundle` and friends.
- **What it is not:** Not the list of Python tools, not the orchestration capability catalog, not Ollama’s model tag list.

## Orchestration capability registry (`guardian._orchestration_registry`)

- **What it is:** Runtime ranking of **tools/modules/APIs** for autonomy and chat (e.g. `get_relevant_capabilities`, `suggested_action`).
- **Variable naming:** Prefer names like `orch_registry` or `capability_registry` in new code — **not** `tool_registry` unless you truly mean a tool-only registry.

## AskAI / UI-local chat vs Guardian-wired paths

- **Unified chat** (`unified_llm_route.unified_chat_completion`, `MistralEngine.complete_chat`): uses the **prompt stack** for the local Ollama branch; cloud branches may still use raw messages until migrated.
- **Separate engines** (e.g. WebScout research, implementer codegen): often **inline prompts** today; they are marked with `log_legacy_llm_call` until migrated. They are not the same code path as `MistralEngine`.

When adding features, state explicitly whether you are touching **prompt profiles**, **capability routing**, or **provider HTTP adapters**.
