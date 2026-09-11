# AUTOPILOT-003 — Dynamic Inspection (Construct-Without-Activate)

**Date:** 2026-09-11  
**Branch:** `cursor/guardian-23-construct-without-activate`  
**SHA:** `776647f80f7d08810f1655c7a2b02fe597c385af`  
**Predecessor:** Issue #23 construct-without-activate PASS  
**Mode:** Construct / `get_guardian_core` ONLY — no `activate()`, `ensure_monitoring_started()`, `start_ui_panel()`, planner probes, or loop starts.

## Method

- Worktree stubs: `tests/_stubs` (`openai`, `requests`) plus MagicMock for other optional deps.
- `PYTHONPATH`: worktree root + `tests/_stubs`.
- Operational traps: `socket.socket`, `subprocess.Popen` / `run` / `call`, and `threading.Thread.start` raise if touched.
- Config: `defer_heavy_startup=True`, `_test_skip_external_storage=True`, `enable_vector_memory=False`, monitors/UI flags on, `ui_config.auto_start=False`.
- Cycle: `reset_singleton` → `get_guardian_core(config)` → attribute inspection → `reset_singleton` — **twice**.

## Activation / run flags (both cycles)

| Flag | Observed |
|------|----------|
| `core._activated` | `False` |
| `core._running` | `False` |
| `core._initialized` | `True` |
| `elysia_loop.running` | `False` |
| `SystemMonitor._started` | `False` |
| `ResourceMonitor.monitoring_active` | `False` (`_resource_monitor_startup_deferred=True`) |
| `RuntimeHealthMonitor._running` | `False` |
| Trap hits | **none** (construct did not start threads / open sockets / spawn subprocesses) |
| Teardown | singleton `None`, `_monitoring_started=False`, `_any_instance_initialized=False` (both cycles) |

**Interpretation:** Classifications below are **wiring evidence from a constructed object graph**, not operational proof of capability. Import success alone was not used to claim LIVE_*.

## Classifications

| Component | Class | Evidence | Notes |
|-----------|-------|----------|-------|
| **memory** | `LIVE_CANONICAL` | `core.memory` → `MemoryCore` | Attached; shared with trust/mutation/consensus/safety/tasks. Vector path disabled for this run (`enable_vector_memory=False`). |
| **DreamEngine** | `LIVE_CANONICAL` | `core.dreams` → `DreamEngine` | Constructed with `memory` + `mutation`; `prompt_evolver` wired after. Not invoked. |
| **ConsensusEngine** | `LIVE_CANONICAL` | `core.consensus` → `ConsensusEngine` | Present; **10** agents registered via `_register_core_agents`. No votes cast during inspect. |
| **CapabilityRegistry** | `LIVE_SUPPORTING` | `core._orchestration_registry` → `CapabilityRegistry` | Empty orchestration helper attached at construct; refresh/ranking happens later (e.g. after `wire_modules`). |
| **ModuleRegistry (core adapters)** | `LIVE_CANONICAL` | `core.module_registry` → `ModuleRegistry` | Registered: memory, mutation, safety, trust, tasks, consensus, trust_eval_*, feedback_loop. |
| **tool registry (`_modules["tool_registry"]`)** | `UNREACHABLE` | `core._modules is None` | Not attached at construct; depends on Elysia `wire_modules` / external module bag. Do **not** infer tools from import. |
| **mutation / recovery** | `LIVE_CANONICAL` | `MutationEngine` + `RollbackEngine` + `ReviewQueue` + `ApprovalStore` | Mutation/recovery graph constructed and adapter-registered. No mutate/rollback executed. |
| **browser / tool adapters** | `LIVE_SUPPORTING` (WebReader / SubprocessRunner / AnalysisEngine); dedicated browser / WebScout on core → `UNREACHABLE` | `web_reader`, `subprocess_runner`, `analysis_engine` present | No dedicated `browser` / `webscout` attribute on constructed core. WebScout remains import-available elsewhere, not construct-wired. |
| **safety config** | `LIVE_CANONICAL` (DevilsAdvocate); EAI + TrustPolicy → `LIVE_SUPPORTING` | `safety` → `DevilsAdvocate`; `eai_safety` → `EAISafetyFramework`; `trust` / `trust_policy` present | Safety objects constructed; no challenge/review exercised. |
| **ElysiaLoop object** | `LIVE_CANONICAL` (presence); **not started** | `core.elysia_loop` → `ElysiaLoopCore`, `running=False` | Loop object + shared `TimelineMemory` wired; `start()` not called. |
| **UI panel object** | `LIVE_SUPPORTING` | `core.ui_panel` → `UIControlPanel` when `ui_config.enabled=True` | Object graph only; `start()` / auto-start not invoked (`auto_start=False`). |
| **monitors** | `LIVE_SUPPORTING` **constructed**; **not started** | `SystemMonitor`, `ResourceMonitor`, `RuntimeHealthMonitor`, `AutoPromptEvolutionScheduler` | Constructed during `__init__` / `_initialize_system(start=False)`; start flags all false. Operational start requires `activate()`. |

### Legend (used)

- `LIVE_CANONICAL` — present on constructed core with clear primary wiring  
- `LIVE_SUPPORTING` — present and wired as supporting/operational surface (or gated helper)  
- `UNREACHABLE` — not attached on this construct path (may exist via later wiring / import elsewhere)  
- Not observed here: `OPTIONAL`, `EXPERIMENTAL`, `LEGACY`, `STUB`, `GENERATED`, `UNKNOWN`

## Construct → inspect → teardown (twice)

| Cycle | Construct | `_activated` / `_running` | Traps | Teardown clean |
|-------|-----------|---------------------------|-------|----------------|
| 1 | `get_guardian_core` OK | `False` / `False` | none | yes |
| 2 | `get_guardian_core` OK (new instance after reset) | `False` / `False` | none | yes |

## Safety defects

**None found** during this bounded inspection.

Expected construct-only startup-verification warnings (`deferred_init_pending`, `dashboard_not_ready`) were observed; they are consistent with Issue #23 inert construct, not new defects.

## Limits

- No providers, network, live probes, or activation.
- Wiring ≠ capability: components classified LIVE_* were not exercised beyond attribute presence and start-flag checks.
- `tool_registry` and dedicated browser agents require post-construct wiring / activate paths outside this experiment.
