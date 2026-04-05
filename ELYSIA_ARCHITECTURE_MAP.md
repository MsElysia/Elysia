# Elysia / Project Guardian — Architecture Map

**Purpose:** Reverse-engineered map of how the unified Elysia process is assembled, how decisions run, and where subsystems connect. Based on reading `elysia.py`, `elysia_sub_*.py`, `project_guardian/core.py`, `guardian_singleton.py`, `monitoring.py`, `architect_core.py`, and related modules (not on guesswork).

**Uncertainty:** Some optional packages (`fractalmind`, `harvest_engine`, `longterm_planner`, `ai_tool_registry`) are imported by name from the Python path; exact package locations depend on `sys.path` (project root + `core_modules/elysia_core_comprehensive` + `project_guardian`). If an import fails, that module is simply absent from `UnifiedElysiaSystem.modules`.

---

## 1. Entry points and startup trace

### True entry points

| Entry | File | Role |
|-------|------|------|
| **Primary CLI** | `elysia.py` | `main()` → `UnifiedElysiaSystem` → `start()` → blocking `while True: sleep(1)` |
| **Launcher alias** | `run_elysia_unified.py` | `runpy.run_path(elysia.py)` — same as running `elysia.py` |
| **Guardian-only / tests** | `project_guardian/guardian_singleton.py` → `get_guardian_core()` | Can construct `GuardianCore` without full Elysia stack |

### Step-by-step: launch → active loop

1. **Process start:** `python elysia.py` (or unified launcher).
2. **`elysia.py:main()`** (`elysia.py` ~821+):
   - Checks `STATUS_HOST`/`STATUS_PORT` bind (single-instance heuristic).
   - `config = get_elysia_config()` from `elysia_config`.
3. **`UnifiedElysiaSystem.__init__`** (`elysia.py` ~274–359):
   - **`load_api_keys()`** — `elysia_sub_apikeys.py` (env / key files).
   - **`run_startup_health_check`** (`project_guardian/startup_health.py`) in a thread pool; on hard failure can `sys.exit(1)`.
   - **`init_guardian_core(config)`** — `elysia_sub_guardian.py` → `get_guardian_core()` → **`GuardianCore.__init__`** (singleton).
   - **`init_architect_core()`** — `elysia_sub_architect.py` → **`ArchitectCore()`** from `architect_core` (on `sys.path` under `core_modules/elysia_core_comprehensive`).
   - **`init_runtime_loop()`** — `elysia_sub_runtime_loop.py`: tries `elysia_runtime_loop.ElysiaRuntimeLoop`, else `project_guardian.runtime_loop_core.RuntimeLoop`.
   - **`init_integrated_modules(...)`** — `elysia_sub_modules.py` builds **`modules` dict** (FractalMind, Harvest, tool registry, planner, etc.).
   - **`init_income_modules(modules, PROJECT_ROOT)`** — `elysia_sub_income.py` adds income/finance/wallet + **`APIManager`** from `organized_project/launcher` when paths exist.
   - **`guardian.wire_modules(self.modules)`** — attaches Elysia modules to **`GuardianCore._modules`** and triggers **`CapabilityRegistry.refresh`** (`project_guardian/capability_registry.py`).
   - **`register_all_modules(self.architect)`** — `elysia_sub_registration.py` calls **`architect.register_new_module(...)`** for each **metadata** entry in `MODULE_REGISTRY` (descriptive registration into `ModuleArchitect`, not Python object wiring).
   - **`guardian._unified_system = self`**, startup health propagated to guardian.
4. **`UnifiedElysiaSystem.start()`** (`elysia.py` ~698+):
   - Sets `running = True`.
   - Embeddings: immediate vs deferred depending on **`guardian._defer_heavy_startup`** and dashboard readiness; may spawn **`guardian.start_deferred_initialization`** in a daemon thread.
   - **`runtime_loop.start`** in a daemon thread if present.
   - **`AutoLearningScheduler.start()`** if `config["auto_learning"]` enabled (`project_guardian/auto_learning.py`).
   - Status HTTP server thread: `_run_status_server` (GET `/status`, `/health`, POST `/chat`, OpenAI-compatible route).
5. **`main()`** after `start()`: prints status, registers signal handlers, **`while True: time.sleep(1)`** — the “main loop” is **sleep-only**; real work is **threads** (runtime loop, monitoring heartbeat, status server, auto-learning, deferred init).

### When things become available

| Concern | Becomes available |
|---------|-------------------|
| **GuardianCore** | End of `init_guardian_core` (before Architect). |
| **ArchitectCore** | After Guardian; WebScout may resolve `web_reader` via Guardian singleton if needed. |
| **`self.modules` (FractalMind, tools, planner, …)** | After `init_integrated_modules` + `init_income_modules`. |
| **`guardian._modules`** | After `wire_modules` (same boot as above). |
| **Architect `ModuleArchitect` registry** | After `register_all_modules` (names/metadata only). |
| **Consensus “agents”** | During **`GuardianCore.__init__`** → **`_register_core_agents`** (`core.py`) — these are **not** the same as `self.modules` plugins. |
| **External APIs (OpenAI, etc.)** | When keys loaded + income **`APIManager`** constructed; **`UnifiedElysiaSystem.chat_with_llm`** uses `income_generator.api_manager`. |
| **Capability discovery (orchestration)** | **`CapabilityRegistry`** exists on Guardian at init; **snapshot refresh** on `wire_modules` and on **`refresh_if_due`** during **`_get_next_action_impl`** pre-decision pass (`core.py`). |

### Initialization fragility (where later behavior breaks)

- **Startup health hard fail** → process exits before Guardian.
- **`get_guardian_core` returns `None`** → `self.guardian` is None; status/chat/autonomy paths degrade.
- **`wire_modules` never called** (non-Elysia Guardian use) → `_modules` empty; planner/tool/income autonomy actions missing from candidate pool.
- **Deferred init failure** → `operational_state` flags (`vector_degraded`, `deferred_init_failed`); memory/vector features degraded but core may still run.
- **Architect import failure** → `architect` None; `register_all_modules` no-ops; WebScout/proposals may be missing depending on failure site.

---

## 2. Core file map (high-signal)

| Path | Role | Depends on | Depended on by |
|------|------|------------|----------------|
| `elysia.py` | Process shell: config, `UnifiedElysiaSystem`, HTTP status, main sleep loop | `elysia_sub_*`, `elysia_config` | Launchers, operators |
| `elysia_sub_guardian.py` | Builds Guardian singleton config, calls `get_guardian_core` | `guardian_singleton`, `GuardianCore` | `elysia.py` |
| `elysia_sub_architect.py` | Instantiates `ArchitectCore` | `architect_core` | `elysia.py` |
| `elysia_sub_runtime_loop.py` | Runtime loop implementation selection | `elysia_runtime_loop` or `runtime_loop_core` | `elysia.py` |
| `elysia_sub_modules.py` | Dict of integrated plugins (FractalMind, Harvest, tools, planner, …) | Various top-level packages | `wire_modules`, registration |
| `elysia_sub_income.py` | Income stack + `APIManager` | `organized_project/launcher/*` | `chat_with_llm`, financial modules |
| `elysia_sub_registration.py` | Metadata registration into Architect `ModuleArchitect` | `ArchitectCore` | Boot only |
| `project_guardian/core.py` | **`GuardianCore`**: memory, tasks, trust, safety, missions, autonomy, **`get_next_action`**, **`run_autonomous_cycle`**, wiring | Many `project_guardian/*` | UI, monitoring, Elysia |
| `project_guardian/guardian_singleton.py` | Single instance + `ensure_monitoring_started` | `GuardianCore` | Elysia init |
| `project_guardian/monitoring.py` | Heartbeat thread: memory pressure, cleanup, **`run_autonomous_cycle`** on interval | `MemoryCore`, Guardian | Started from singleton guard |
| `project_guardian/mistral_engine.py` | Ollama JSON: **`decide`**, **`decide_next_action`**, **`suggest_learning_targets`** | `requests`, Ollama | `core.py`, `auto_learning.py` |
| `project_guardian/capability_registry.py` | Runtime capability snapshot, **`get_relevant_capabilities`**, usage logs/stats | Guardian, optional `multi_api_router` | `core.py` pre-decision |
| `project_guardian/multi_api_router.py` | **`select_best_api`**, **`evaluate_api_vs_local`** (heuristic, logs) | env keys, optional `CapabilityRegistry` | `capability_registry.refresh`, prompts |
| `core_modules/.../architect_core.py` | **`ArchitectCore`**: module/mutation/policy/persona architects, WebScout, proposals | `webscout_agent`, `proposal_system` | Elysia registration & APIs |
| `project_guardian/elysia_loop_core.py` | **`ElysiaLoopCore`**, timeline, module registry adapters | asyncio, sqlite timeline | `GuardianCore` |
| `project_guardian/memory.py` | **`MemoryCore`**, recall, search, optional vector | files, optional embeddings | Nearly all subsystems |
| `project_guardian/tasks.py` | **`TaskEngine`** | persistence files | Guardian, candidates |
| `project_guardian/consensus.py` | **`ConsensusEngine`** + **`register_agent`** | — | Guardian decisions |
| `project_guardian/external.py` | **`WebReader`**, **`AIInteraction`** (OpenAI legacy API) | trust, memory | Guardian |
| `project_guardian/ui_control_panel.py` | Dashboard; can call **`run_autonomous_cycle`** | Flask, Guardian | Operators |
| `project_guardian/auto_learning.py` | Scheduled learning, **`MistralEngine`** for chained targets | storage, Mistral | `UnifiedElysiaSystem.start` |

---

## 3. Subsystem map (requested names)

Implementation is **split** between **`GuardianCore` internals** and **`UnifiedElysiaSystem.modules`** (`elysia_sub_modules.py` + income). Below: **what it is / init / exposure / how Elysia uses it**.

| Subsystem | Implementation | Initialized | Exposed as | Elysia usage |
|-----------|----------------|-------------|------------|--------------|
| **memory** | `project_guardian/memory.py` (`MemoryCore`), optional `json_memory`, embeddings | `GuardianCore.__init__` | `guardian.memory` | Recall, search, remember; autonomy logs; pressure in `monitoring.py` |
| **mutation** | `project_guardian/mutation.py` | Guardian init | `guardian.mutation` | Adapters; autonomy `consider_mutation` |
| **safety** | `project_guardian/safety.py` (`DevilsAdvocate`) | Guardian init | `guardian.safety` | Adapter; mission/task context |
| **trust** | `project_guardian/trust.py` (`TrustMatrix`) | Guardian init | `guardian.trust` | Network gating via `external.WebReader` |
| **tasks** | `project_guardian/tasks.py` | Guardian init | `guardian.tasks` | **`execute_task`** candidates, queue |
| **consensus** | `project_guardian/consensus.py` | Guardian init | `guardian.consensus` | **`_register_core_agents`**; voting APIs |
| **trust_eval_action** | `project_guardian/trust_eval_action.py` | Guardian init | `guardian.trust_eval_action` | Module registry adapter |
| **trust_eval_content** | `project_guardian/trust_eval_content.py` | Guardian + often **`modules["trust_eval_content"]`** | Same or shared ref | Content policy eval |
| **feedback_loop** | `project_guardian/feedback_loop.py` | Guardian init | `guardian.feedback_loop` | Adapter |
| **webscout** | `project_guardian/webscout_agent.py` → **`ElysiaWebScout`** inside **`ArchitectCore`** | `ArchitectCore.__init__` | `architect.webscout` | Proposals / research flows via Architect API |
| **fractalmind** | Package `fractalmind` | `elysia_sub_modules.py` | `modules["fractalmind"]` | Autonomy `fractalmind_planning` |
| **harvest engine** | Package `harvest_engine` | `elysia_sub_modules.py` | `modules["harvest_engine"]` | `harvest_income_report` |
| **identity mutation verifier** | Package `identity_mutation_verifier` | `elysia_sub_modules.py` | `modules["identity_verifier"]` | Not wired into autonomy candidate list by default (available on dict) |
| **ai tool registry** | **`from ai_tool_registry import ToolRegistry, TaskRouter`** (not `project_guardian/ai_tool_registry_engine.py` in this path) | `elysia_sub_modules.py` | `modules["tool_registry"]`, `modules["task_router"]` | `tool_registry_pulse`, routing probe |
| **long term planner** | Package `longterm_planner` | `elysia_sub_modules.py` | `modules["longterm_planner"]` | `work_on_objective`, objectives in capability context |
| **income generator** | `launcher.elysia_income_generator` | `elysia_sub_income.py` | `modules["income_generator"]` | **`chat_with_llm`** API client, `income_modules_pulse` |
| **financial manager** | `launcher.elysia_financial_manager` | income init | `modules["financial_manager"]` | Status, pulse |
| **revenue creator** | `launcher.elysia_revenue_creator` | income init | `modules["revenue_creator"]` | Financial automation (if used) |
| **wallet** | `launcher.elysia_wallet` | income init | `modules["wallet"]` | Balance, pulse |
| **multi-api router** | `project_guardian/multi_api_router.py` | Pure functions + optional registry | Imported by capability layer | Hints + budget hooks; not all call sites use `reserve_slot` |
| **API manager** | `organized_project/launcher/api_manager.py` | `elysia_sub_income.py` | Held by income modules / `system.get_income_generator().api_manager` | OpenAI / OpenRouter chat in `UnifiedElysiaSystem` |

**Underused / easy to miss:** `identity_verifier` in `modules` has no mirrored autonomy action in the standard candidate builder (unless added elsewhere). `project_guardian/ai_tool_registry_engine.py` is a **separate** engine from the `ai_tool_registry` package used at Elysia boot.

---

## 4. Decision-flow map (autonomy / next action)

**Trigger:** `SystemMonitor` heartbeat (`project_guardian/monitoring.py` ~281–295) when `config/autonomy.json` has `"enabled": true`, on `interval_seconds` (min 30s enforced there).

**Flow:**

1. **Trigger** — monitoring beat fires → `guardian.run_autonomous_cycle()`.
2. **Context gathering** — `run_autonomous_cycle` → `get_next_action()` → **`_get_next_action_impl`** builds **candidate list** from missions, tasks, queue, introspection, operational flags, exploration actions, etc. (`core.py`).
3. **Pre-decision (orchestration)** — **`CapabilityRegistry.begin_decision_cycle`**, **`refresh_if_due`**, **`get_relevant_capabilities`** over task + memory hints, **`boost_candidates_for_relevance`** (`core.py` ~2005+). Stored in **`_pre_decision_context`**.
4. **Memory lookup** — `_build_capability_task_context`, `_memory_capability_hints` (`search_memories`); snapshot also uses `memory_recon_hint` in registry refresh.
5. **Planner/task selection** — candidates may include `work_on_objective`, `execute_task`, `continue_mission`, `process_queue` depending on state.
6. **Mistral (optional)** — If `mistral_primary_decider_enabled` or `use_mistral_decision_engine`, **`MistralEngine.decide_next_action(snapshot)`** (`core.py` ~2076+). Snapshot includes **`orchestration_recon`**, **`relevant_capabilities`**, **`H_api_vs_local`**, etc.
7. **Governor** — **`_apply_governor_to_mistral`** enforces confidence, cooldowns, warmup, memory pressure rules.
8. **Module/tool/API selection** — Expressed as **named autonomy actions** (`tool_registry_pulse`, `consider_learning`, …), not dynamic tool JSON at this layer.
9. **Execution** — `run_autonomous_cycle` big `if/elif` on `action` (learning, dream, prompt evolution, code analysis, …) (`core.py` ~2761+).
10. **Validation** — Partial: governor + trust on some paths; not a single unified “validator” step after every action.
11. **Logging** — **`_orchestration_log_cycle`** → `log_outcome` + **`log_capability_usage`** → `data/capability_usage_log.jsonl` + `data/capability_usage_stats.json`.
12. **Memory writeback** — Many branches call `memory.remember(...)`; not centralized.

**Missing stages (relative to an ideal orchestrator):** unified post-action validation, single pipeline for “tool call result → trust → memory,” and consistent **API slot consumption** on every external LLM call.

---

## 5. Mistral integration analysis

| Question | Answer (from code) |
|----------|-------------------|
| Only generating text? | **Also** returns structured JSON for routing (`decide_next_action`) and planning (`decide`, `suggest_learning_targets`). |
| Selecting actions? | **Yes**, when Mistral decider enabled: chooses among **discrete candidate actions** from Python-built list. |
| Routing tools? | **Indirectly** — actions like `tool_registry_pulse` / `consider_learning` map to subsystems; **not** OpenAI-style parallel tool calling in the decider. |
| Reading memory before acting? | **Partially** — snapshot includes counts, hints, recall lines, orchestration digest; Mistral does not run arbitrary `recall()` itself. |
| Aware of modules/agents? | **Via prompts**: `relevant_capabilities`, `orchestration_recon`, capability digest; **not** live object introspection inside the model. |
| APIs intentional? | **Incidental** for Mistral path (Ollama local). **Separate** cloud path: `UnifiedElysiaSystem.chat_with_llm` → **Income `api_manager`** (gpt-4o-mini / OpenRouter). `evaluate_api_vs_local` informs prompts; does not by itself call cloud APIs. |
| What blocks “true orchestrator” behavior? | (1) Action set is **fixed enumeration** from Python. (2) **No closed loop** from Mistral to arbitrary `modules[x].method()` without new actions. (3) **Cloud vs local** not unified: Ollama decider vs OpenAI chat. (4) **Architect `ModuleArchitect`** registry is **metadata**, not execution wiring to `GuardianCore`. |

**Code points for stronger orchestration:** `core.py` `_get_next_action_impl` / `_build_decider_state_snapshot` / `_apply_governor_to_mistral`; `mistral_engine.py` `decide_next_action`; any new **executor** that maps structured tool intents to `guardian._modules` or `tool_registry.call_tool`.

---

## 6. API and tool analysis

| Surface | Config / keys | Health | When used | Router / fallback |
|---------|----------------|--------|-----------|-------------------|
| **Ollama / Mistral** | `config/mistral_decider.json`, Ollama URL in `mistral_engine.py` | Implicit (request fails → fallback in decider) | Decider, `decide`, learning targets | Deterministic candidate max if Mistral fails |
| **OpenAI via Income APIManager** | `OPENAI_API_KEY`, OpenRouter key | Client null → error string | `UnifiedElysiaSystem.chat_with_llm`, `_llm_completion`, condensation | OpenRouter branch in same methods |
| **FractalMind** | `OPENAI_API_KEY` passed into constructor | Unknown without reading `fractalmind` package | When autonomy selects `fractalmind_planning` | Local/planner fallback |
| **Env flags in CapabilityRegistry** | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, Twitter token | Boolean “key present” in snapshot | Prompt hints, `multi_api_router` | `select_best_api` returns `local_mistral` if no keys |
| **multi_api_router** | Same | Cooldown + per-cycle budget **if** registry passed | `refresh()` embeds `api_routing_hints`; prompts | `evaluate_api_vs_local` heuristic only unless callers use `reserve_slot` |

**Plumbing assessment:** **Partial.** There is **intelligent hinting** and **budget/cooldown primitives** in `CapabilityRegistry` + `multi_api_router.py`, but **most cloud calls** still go through **ad hoc** paths (`chat_with_llm`, `AskAI`, FractalMind internals) without a **single** router that scores cost/quality across all LLM entry points.

---

## 7. Memory and learning analysis

| Topic | Mechanism |
|-------|-----------|
| **Storage** | `MemoryCore` memory log (JSON file path from config); optional **`TimelineMemory`** (SQLite) via loop core; snapshots in `MemorySnapshot`. |
| **Vector memory** | Lazy / deferred: `enable_embeddings()` from `start()` or deferred init; `search_semantic` in `memory.py` when index built. |
| **Fallback** | Keyword `search_memories`; truncation when LLM/vector unavailable. |
| **What gets written** | `remember()` from autonomy, learning, external, errors, condensation, etc. |
| **Action outcomes** | `_last_autonomy_result`, `capability_outcomes.jsonl`, `capability_usage_log.jsonl`, `capability_scoreboard.json`, `capability_usage_stats.json`; **Mistral outcome boosts** in `core.py`. |
| **Past tool/API choices → future** | **Light bias** via `_load_usage_stats` + `get_relevant_capabilities` match scores; **not** a full RL policy. |

**Missing layer:** unified **event-sourced** “decision record” (task, chosen capability, outcome, quality) consumed by **all** LLM entry points, not only autonomy.

---

## 8. Bottlenecks and weak spots

1. **Architecture:** Two parallel “registries” — **`ModuleArchitect`** (metadata) vs **`guardian._modules`** (live objects) — easy for humans/tools to confuse.
2. **Underused:** `identity_verifier` in `modules`; `ArchitectCore` command routing rarely used from main loop; second tool registry in `project_guardian/ai_tool_registry_engine.py` may be orphaned relative to Elysia boot.
3. **Passive:** `main()` sleep loop; no central tick beyond heartbeat + runtime loop + schedulers.
4. **Bypass capability checks:** `chat_with_llm` and other UI/API chat paths do **not** run `get_next_action` / capability registry.
5. **API underuse:** Heavy reasoning still often **local Mistral** while cloud is on a **different** code path.
6. **Performance:** Memory pressure + optional vector rebuild + auto-learning + condensation can contend; deferred init reduces boot cost but adds race windows.
7. **Init fragility:** Optional imports in `elysia_sub_modules.py` fail silently into warnings — system runs **partial**.
8. **Logging blind spots:** Not every subsystem logs structured decisions; trust/consensus outcomes not uniformly tied to autonomy log lines.

---

## 9. Recommended next edits (prioritized)

### Priority 1 — high leverage, low disruption

| Change | Files | Why | Risk |
|--------|-------|-----|------|
| Route **`chat_with_llm` / `_llm_completion`** through **`select_best_api(..., reserve_slot=True)`** + **`note_api_failure`** | `elysia.py`, `multi_api_router.py`, maybe `launcher/api_manager.py` | Unifies cloud vs local policy | Must not break existing clients expecting errors as today |
| Single **`log_capability_usage`** call site wrapper for **all** LLM completions | `elysia.py`, `mistral_engine.py`, `ask_ai.py` | Comparable learning signal | Volume of log lines |

### Priority 2 — medium leverage

| Change | Files | Why | Risk |
|--------|-------|-----|------|
| Add **1–2 autonomy actions** that call **`identity_verifier`** or **`tool_registry.call_tool`** with trust gates | `core.py`, `config/autonomy.json` | Uses existing modules | Trust/safety review per tool |
| **Architect registry** export into **`CapabilityRegistry.refresh`** (merge metadata) | `capability_registry.py`, `elysia.py` or `core.py` | One view of “registered” vs “wired” | Duplication if names diverge |

### Priority 3 — speculative

| Change | Files | Why | Risk |
|--------|-------|-----|------|
| Replace fixed action enum with **small tool schema** (name + args) validated against registry | `mistral_engine.py`, `core.py` | True tool routing | Large behavior change; safety critical |
| Unify **`ai_tool_registry` package** and **`ai_tool_registry_engine.py`** | Multiple | Single tool story | Refactor scope |

---

## Document maintenance

- Re-run this mapping after major changes to `elysia.py` init order, `elysia_sub_modules.py` imports, or `GuardianCore` constructor.
- **Version:** derived from repository state at authoring time; line numbers in `elysia.py` / `core.py` may drift.
