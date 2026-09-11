# AUTOPILOT-003 — Dynamic Inspection (Restack Construct-Without-Activate)

**Date:** 2026-09-11  
**Product branch:** `cursor/autopilot-003-issue23-restack-cwa`  
**Product SHA:** `7374820642fad52a6264c86df8632c3a630df592`  
**Docs branch:** `docs/autopilot-003-dynamic-inspection-restack-20260911`  
**Mode:** Construct / `get_guardian_core` ONLY — no `activate()`, `ensure_monitoring_started()`, `start_ui_panel()`, planner probes, loop starts, live providers, or network.

**Non-transfer:** Source Vega/dynamic PASS at `776647f80f7d08810f1655c7a2b02fe597c385af` does **not** transfer to this restack product. This report is evidence for `7374820` only.

## Method

- Detached worktree at exact product SHA `7374820`.
- Stubs: `tests/_stubs` (`openai`, `requests`) plus MagicMock for optional deps (`flask`, `flask_socketio`, `psutil`, etc.).
- `PYTHONPATH`: worktree root + `tests/_stubs`.
- Operational traps armed: `socket.socket`, `subprocess.Popen` / `run` / `call` (hard raise); `threading.Thread.start` (record + join-safe no-op; counts as trap if hit); `openai.OpenAI`; `run_startup_planner_probe`.
- Cycle cwd isolated under temp (avoids worktree `elysia_timeline.db` lock contention).
- Config: `defer_heavy_startup=True`, `_test_skip_external_storage=True`, `enable_vector_memory=False`, monitors on, `ui_config.enabled=True` / `auto_start=False`.
- Cycle: `reset_singleton` → `get_guardian_core(config)` → attribute inspection → `reset_singleton` — **twice**.
- **Harness note:** `GuardianLayer` construct was **disabled for this run** (`enable_guardian_layer=False`). Enabling it hangs indefinitely on this Windows host inside `GuardianLayer` fingerprinting (`platform.processor` / WMI). That is an inspect-environment limitation, not evidence of activate/live behavior. `guardian_layer` is therefore reported `null` / not classified LIVE here.

## Activation / run flags (both cycles)

| Flag | Observed |
|------|----------|
| `core._activated` | `False` |
| `core._running` | `False` |
| `core._initialized` | `True` |
| `elysia_loop.running` | `False` |
| `ui_panel.running` | `False` (`UIControlPanel` object present) |
| `SystemMonitor._started` | `False` |
| `ResourceMonitor.monitoring_active` | `False` (`_resource_monitor_startup_deferred=True`) |
| `prompt_evolution_scheduler._running` | `False` |
| Trap hits / thread starts | **none** |
| Teardown | singleton `None`, `_monitoring_started=False`, `_any_instance_initialized=False` (both cycles) |
| `guardian_layer` | `null` (disabled in harness; see Method) |

**Interpretation:** Classifications below are **wiring evidence from a constructed object graph**, not operational proof of capability. Import success alone was not used to claim LIVE_*.

## Classifications

| Component | Class | Evidence | Notes |
|-----------|-------|----------|-------|
| **memory** | `LIVE_CANONICAL` | `core.memory` → `MemoryCore` | Attached; shared TimelineMemory. Vector path disabled (`enable_vector_memory=False`). |
| **DreamEngine** | `LIVE_CANONICAL` | `core.dreams` → `DreamEngine` | Constructed with memory + mutation; prompt_evolver wired after. Not invoked. |
| **ConsensusEngine** | `LIVE_CANONICAL` | `core.consensus` → `ConsensusEngine` | **10** agents registered. No votes cast. |
| **CapabilityRegistry** | `LIVE_SUPPORTING` | `core._orchestration_registry` → `CapabilityRegistry` | Attached at construct; empty helper. |
| **ModuleRegistry (core adapters)** | `LIVE_CANONICAL` | `core.module_registry` → `ModuleRegistry` | memory, mutation, safety, trust, tasks, consensus, trust_eval_*, feedback_loop. |
| **tool registry (`_modules["tool_registry"]`)** | `UNREACHABLE` | `core._modules is None` | Not attached at construct. |
| **mutation / recovery** | `LIVE_CANONICAL` | `MutationEngine` + `RollbackEngine` + `ReviewQueue` + `ApprovalStore` | Graph constructed; no mutate/rollback executed. |
| **browser / tool adapters** | `LIVE_SUPPORTING` (WebReader / SubprocessRunner / AnalysisEngine); dedicated browser / WebScout → `UNREACHABLE` | attrs present as noted | No dedicated `browser` / `webscout` on constructed core. |
| **safety config** | `LIVE_CANONICAL` (DevilsAdvocate); EAI + TrustPolicy → `LIVE_SUPPORTING` | `safety` → `DevilsAdvocate`; `eai_safety` → `EAISafetyFramework`; trust / trust_policy present | No challenge/review exercised. |
| **ElysiaLoop object** | `LIVE_CANONICAL` (presence); **not started** | `ElysiaLoopCore`, `running=False` | |
| **UI panel object** | `LIVE_SUPPORTING` | `UIControlPanel`, `running=False` | Object graph only; auto-start false. |
| **monitors** | `LIVE_SUPPORTING` **constructed**; **not started** | `SystemMonitor`, `ResourceMonitor`, `AutoPromptEvolutionScheduler` | Start flags false. Operational start requires `activate()`. |
| **GuardianLayer** | `UNREACHABLE` (this run) | `null` | Harness disabled due to Windows WMI fingerprint hang; not a restack PASS transfer claim. |

### Legend

- `LIVE_CANONICAL` — present on constructed core with clear primary wiring  
- `LIVE_SUPPORTING` — present as supporting/operational surface (or gated helper)  
- `UNREACHABLE` — not attached on this construct path  

## Construct → inspect → teardown (twice)

| Cycle | Construct | `_activated` / `_running` | Traps | Teardown clean |
|-------|-----------|---------------------------|-------|----------------|
| 1 | `get_guardian_core` OK | `False` / `False` | none | yes |
| 2 | `get_guardian_core` OK (new instance after reset) | `False` / `False` | none | yes |

Raw harness output: worktree `_autopilot003_restack_inspect_result.json` at product SHA checkout (local artifact; not product commit).

## Safety defects

**None found** during this bounded inspection (with GuardianLayer skipped as noted).

Expected construct-only startup-verification warnings (`deferred_init_pending`, `dashboard_not_ready`) observed; consistent with Issue #23 inert construct.

## Limits

- No providers, network, live probes, or activation.
- Wiring ≠ capability.
- GuardianLayer not exercised on this host due to fingerprint/WMI hang; do not infer GuardianLayer LIVE from this report.
- `tool_registry` and dedicated browser agents require post-construct wiring / activate paths outside this experiment.
- Product SHA `7374820` was **not** modified; this file lives on the docs branch only.
