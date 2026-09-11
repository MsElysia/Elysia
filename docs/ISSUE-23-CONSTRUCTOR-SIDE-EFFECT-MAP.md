# Issue #23 — Constructor side-effect map (construct-without-activate)

**Baseline:** PR #27 / `79b6c6456eae1d6a400c8b08516a8478d769d25e`  
**Branch:** `cursor/guardian-23-construct-without-activate`  
**Date:** 2026-09-10

## Classification legend
- `CONSTRUCTION_REQUIRED` — needed to build inspectable object graph
- `ACTIVATION_ONLY` — must move behind explicit activate
- `AMBIGUOUS` — construct-time OK if documented; prefer activate if heavy/network
- `LEGACY` — historical coupling
- `UNSAFE_CONSTRUCTOR_SIDE_EFFECT` — currently activates from construct

## Map (high signal)

| Side effect | Location | Class |
|-------------|----------|-------|
| Config/path/object graph | `GuardianCore.__init__` | CONSTRUCTION_REQUIRED |
| `resource_monitor.start_monitoring` (non-deferred) | core.py ~442 | UNSAFE_CONSTRUCTOR_SIDE_EFFECT |
| `start_ui_panel` via `ui_config.auto_start` | core.py ~616–617 | UNSAFE_CONSTRUCTOR_SIDE_EFFECT |
| `_initialize_system` from `__init__` | core.py ~652 | LEGACY / mixes construct+activate |
| `ensure_monitoring_started(self)` | `_initialize_system` ~734 | UNSAFE_CONSTRUCTOR_SIDE_EFFECT |
| `prompt_evolution_scheduler.start` | via ensure_monitoring | ACTIVATION_ONLY |
| `elysia_loop.start` (fallback path) | via ensure_monitoring | ACTIVATION_ONLY |
| `run_startup_planner_probe` (network) | `_initialize_system` ~757 | UNSAFE_CONSTRUCTOR_SIDE_EFFECT |
| `_running = True` | `_initialize_system` ~770 | ACTIVATION_ONLY |
| `runtime_health.start_monitoring` | ~7612 | UNSAFE_CONSTRUCTOR_SIDE_EFFECT |
| memory/task seed writes | `_initialize_system` | AMBIGUOUS (allow minimal seed at construct; no threads) |
| API keys → `os.environ` | `__init__` | AMBIGUOUS (keep at construct for wiring inspect) |
| `schedule_upstream_routing_live_probes` | operational init only | ACTIVATION_ONLY (already outside __init__) |
| Audit descriptor | `init_guardian_core(mode=audit)` | already safe (PR #27) |

## Target boundary
1. `__init__` / `get_guardian_core` → construct/retrieve only (no monitor/UI/loop/health/probe start; `_running` stays False).
2. `GuardianCore.activate()` + `activate_guardian_core()` → explicit operational start (idempotent).
3. `init_guardian_core(mode=operational)` → get then activate when `enable_background_services`.
4. Preserve PR #27 audit path unchanged.
