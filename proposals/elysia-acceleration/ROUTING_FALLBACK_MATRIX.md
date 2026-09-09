# Routing / fallback matrix (Task 5 — starter)

Fill the “Verified” column from **your** machine (models pulled, keys present). This file is a template, not runtime truth.

## Unified operator chat (`unified_chat_completion`)

| Concern | Code / behavior | Verified (Y/N) |
|--------|------------------|----------------|
| Local-first option | `decide_chat_llm_backend` + provider order includes `ollama` | |
| Local-only structured tasks | `_LOCAL_ONLY_ROUTER_TASK_TYPES` — no cloud fallback for compression-style `task_type` | |
| Autonomy-safe cloud order | `require_autonomy_safe_reasoning=True` uses `autonomy_safe_cloud_backend_order()` | |
| Self-build RAG | Prepends when policy allows; `meta["selfbuild_rag"]` on return | |

## Orchestration (`RulesRouter` + broker)

| Task type (examples) | Default pipeline (from embedded YAML) | Parallel when |
|---------------------|----------------------------------------|----------------|
| `critique` | `parallel_compare_and_judge` | Always (YAML + rule) |
| `reasoning` / `coding` / … | `serial_plan_execute_review` | High uncertainty, governance hints, telemetry escalation |
| OpenAI down | Fanout / executor fall back to Ollama | `rules.py` `_openai_available()` branch |

## “Cloud-only” hotspots to map later

Search the repo for direct OpenAI / OpenRouter calls outside unified orchestration when you want full local coverage:

- `cloud_openai_call`, `OpenAIAdapter`, `openai.` client usage in modules you care about.

Add rows below as you discover them:

| Module / path | Cloud-only? | Local fallback? | Notes |
|---------------|-------------|-----------------|-------|
| *(add rows)* | | | |
