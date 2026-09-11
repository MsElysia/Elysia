# AUTOPILOT-003 — Dynamic Inspection (RESTACK Construct-Without-Activate)

**Date:** 2026-09-11  
**Branch:** `cursor/autopilot-003-issue23-restack-cwa`  
**SHA:** `7374820642fad52a6264c86df8632c3a630df592`  
**Mode:** Construct / `get_guardian_core` ONLY — no `activate()`, `ensure_monitoring_started()`, `start_ui_panel()`, planner probes, or loop starts.

## Method

- Worktree stubs: `tests/_stubs` (`openai`, `requests`) plus MagicMock for other optional deps.
- `PYTHONPATH`: worktree root + `tests/_stubs` (+ local vega-deps for import resolution).
- Operational traps:
  - `socket.socket`, `subprocess.Popen` / `run` / `call`, `openai.OpenAI`, `run_startup_planner_probe` → hard `TrapHit` raise.
  - `threading.Thread.start` → record hit + neutralize body + start real no-op thread (join-safe). Tip lineage can `join()` after start; a hard raise there deadlocks without proving construct inertness. Zero starts still means trap armed and clean.
- Config (primary double cycle): isolated empty `memory_filepath`, `defer_heavy_startup=True`, `_test_skip_external_storage=True`, `enable_vector_memory=False`, monitors/UI flags on, `ui_config.auto_start=False`, `enable_guardian_layer=False`, EAI config `enabled=false` (matches tip CWA unit-test collateral under Thread traps).
- Supplemental wiring pass: same traps with EAI enabled (`guardian_layer` still false) to classify EAI objects.
- Cycle: `reset_singleton` → `get_guardian_core(config)` → attribute inspection → `reset_singleton` — **twice** (plus supplemental EAI pass). Fresh classifications from this run (not copied from CWA product report).

## Activation / run flags (both primary cycles)

| Flag | Observed |
|------|----------|
| `core._activated` | `False` |
| `core._running` | `False` |
| `core._initialized` | `True` |
| `elysia_loop.running` | `False` |
| `ui_panel.running` | `False` |
| `SystemMonitor._started` | `False` |
| `ResourceMonitor.monitoring_active` | `False` (`_resource_monitor_startup_deferred=True`) |
| `runtime_health` | constructed; thread not started (log: “thread not started until activate”) |
| `AutoPromptEvolutionScheduler._running` | `False` |
| Hard trap hits (socket/subprocess/provider/probe) | **none** |
| `Thread.start` hits | **none** |
| Teardown | singleton `None`, `_monitoring_started=False`, `_any_instance_initialized=False` (both cycles; distinct `id`s) |

**Interpretation:** Classifications below are **wiring evidence from a constructed object graph**, not operational proof of capability. Import success alone was not used to claim LIVE_*. Wiring ≠ operational proof.

## Classifications

| Component | Class | Evidence | Notes |
|-----------|-------|----------|-------|
| **memory** | `LIVE_CANONICAL` | `core.memory` → `MemoryCore` | Attached; shared timeline confirmed. Vector path disabled for this run (`enable_vector_memory=False`). `remember()` during construct loads JSON (empty isolated file). |
| **DreamEngine** | `LIVE_CANONICAL` | `core.dreams` → `DreamEngine` | Constructed with `memory` + `mutation`; `prompt_evolver` wired after. Not invoked. |
| **ConsensusEngine** | `LIVE_CANONICAL` | `core.consensus` → `ConsensusEngine` | Present; **10** agents registered via `_register_core_agents`. No votes cast during inspect. |
| **CapabilityRegistry** | `LIVE_SUPPORTING` | `core._orchestration_registry` → `CapabilityRegistry` | Attached at construct with empty `_snapshot`; refresh/ranking happens later (e.g. after `wire_modules`). |
| **ModuleRegistry (core adapters)** | `LIVE_CANONICAL` | `core.module_registry` → `ModuleRegistry` | Registered: memory, mutation, safety, trust, tasks, consensus, trust_eval_*, feedback_loop. |
| **tool registry (`_modules["tool_registry"]`)** | `UNREACHABLE` | `core._modules is None` | Not attached at construct; depends on Elysia `wire_modules` / external module bag. |
| **mutation / recovery** | `LIVE_CANONICAL` | `MutationEngine` + `RollbackEngine` + `ReviewQueue` + `ApprovalStore` | Mutation/recovery graph constructed and adapter-registered. No mutate/rollback executed. |
| **browser / tool adapters** | `LIVE_SUPPORTING` (WebReader / SubprocessRunner / AnalysisEngine); dedicated browser / WebScout on core → `UNREACHABLE` | `web_reader`, `subprocess_runner`, `analysis_engine` present; no `browser` / `webscout` / `web_scout` attrs | Startup verification logged WebScout “simulated mode” (no API keys) — import/verify side path, not construct-wired on core. |
| **safety** | `LIVE_CANONICAL` (DevilsAdvocate); EAI + TrustPolicy → `LIVE_SUPPORTING` | `safety` → `DevilsAdvocate`; supplemental pass: `eai_safety` / `eai_safety_framework` → `EAISafetyFramework`; `trust` / `trust_policy` present | Primary cycles disabled EAI for tip Thread-trap collateral; supplemental construct proved EAI object graph. No challenge/review exercised. |
| **ElysiaLoop object** | `LIVE_CANONICAL` (presence); **not started** | `core.elysia_loop` → `ElysiaLoopCore`, `running=False` | Loop object + shared `TimelineMemory` wired; `start()` not called. |
| **UI panel object** | `LIVE_SUPPORTING` | `core.ui_panel` → `UIControlPanel` when `ui_config.enabled=True` | Object graph only; `running=False`; `start()` / auto-start not invoked (`auto_start=False`). |
| **monitors** | `LIVE_SUPPORTING` **constructed**; **not started** | `SystemMonitor`, `ResourceMonitor`, `RuntimeHealthMonitor` (as `core.runtime_health`), `AutoPromptEvolutionScheduler` | Constructed during `__init__` / `_initialize_system(start=False)` / `_init_runtime_health_monitoring(start=False)`; start flags all false. Operational start requires `activate()`. |
| **GuardianLayer** | `OPTIONAL` (gated) / construct **hang risk** when enabled | Default tip CWA test config sets `enable_guardian_layer=False` | See Safety defects. |

### Legend (used)

- `LIVE_CANONICAL` — present on constructed core with clear primary wiring  
- `LIVE_SUPPORTING` — present and wired as supporting/operational surface (or gated helper)  
- `OPTIONAL` — config-gated; may be absent on intentional inspect config  
- `UNREACHABLE` — not attached on this construct path (may exist via later wiring / import elsewhere)  
- Not observed as primary classes here: `EXPERIMENTAL`, `LEGACY`, `STUB`, `GENERATED`, `UNKNOWN`

## Construct → inspect → teardown (twice)

| Cycle | Construct | `_activated` / `_running` | Traps | Teardown clean | Instance `id` |
|-------|-----------|---------------------------|-------|----------------|---------------|
| 1 | `get_guardian_core` OK | `False` / `False` | none | yes | distinct |
| 2 | `get_guardian_core` OK (new after reset) | `False` / `False` | none | yes | distinct from cycle 1 |
| 3 (supplemental EAI) | OK with EAI enabled | `False` / `False` | none | yes | distinct |

## Safety defects

### NEW (RESTACK tip / this host)

1. **`GuardianLayer` construct can block `get_guardian_core`** when `enable_guardian_layer=True`. Under the armed trap harness, construct with guardian layer enabled did not finish within 20s (and previously hung indefinitely after EAI/UI path). **Zero `Thread.start` trap hits** during the hang — this is not an activate/thread-start leak; it is a construct-time stall in the guardian fingerprint path (Windows `platform.processor()` / fingerprint generation is the likely culprit). Tip Issue #23 unit tests already set `enable_guardian_layer=False` for collateral reasons. **Not an activate() regression**, but it is a construct-blocking risk if guardian layer is left on by default in production configs.

### Not new / expected

- Startup verification warnings `deferred_init_pending` and `dashboard_not_ready` — consistent with Issue #23 inert construct.
- Hard-raising `Thread.start` (instead of join-safe neutralize) deadlocks tip join paths; inspection used join-safe recording. No starts observed on successful cycles.

## Limits

- No providers, network, live probes, or activation.
- Wiring ≠ capability: components classified LIVE_* were not exercised beyond attribute presence and start-flag checks.
- `tool_registry` and dedicated browser agents require post-construct wiring / activate paths outside this experiment.
- Primary double cycle disabled EAI + GuardianLayer for tip Thread-trap collateral; EAI wiring confirmed on supplemental pass only.
