# Issue #23 — Construct without activate

**Branch:** `cursor/guardian-23-construct-without-activate`  
**Base:** PR #27 / `79b6c6456eae1d6a400c8b08516a8478d769d25e` (audit descriptor preserved)

## Boundary

| API | Behavior |
|-----|----------|
| `GuardianCore(...)` / `get_guardian_core(...)` | **Construct / retrieve only** — object graph, config, memory seed/tasks/trust. No monitor/loop/prompt-evolver/UI/planner-probe/runtime-health thread start. `_running` / `_activated` stay False. |
| `GuardianCore.activate(*, start_ui=None)` | **Explicit operational start** — idempotent. Gates on `enable_background_services` and subsystem flags. Never re-enables caller-disabled services. |
| `activate_guardian_core(core, *, start_ui=None)` | Thin wrapper around `core.activate(...)`. |
| `ensure_monitoring_started` | Lower-level helper used **by** activate, not by construct. |
| `init_guardian_core(mode="audit")` | Unchanged (PR #27) — pure `GuardianBootstrapAudit` descriptor. |
| `init_guardian_core(mode="operational")` | `get_guardian_core` then `activate_guardian_core` when `enable_background_services`. Probes only after activate / when flag true. |

## UI rules on activate

- Start UI only if `start_ui is True`, **or** (`start_ui is None` and `ui_config.auto_start` and UI enabled) **and** background services allowed.
- `start_ui=False` never starts UI even if `auto_start` is true.

## Side-effect map

See `docs/ISSUE-23-CONSTRUCTOR-SIDE-EFFECT-MAP.md` (pre-change inventory). Construct-time unsafe starts listed there are moved behind `activate()`.

## Production callers updated

- `elysia_sub_guardian.py` — operational path activates explicitly
- `elysia_interface.py` — `open_web_dashboard` activates with `start_ui=True`
- `start_ui_panel.py`, `start_control_panel.py`, `run_elysia.py` — construct then activate

## Legacy residual

Other scripts that call `GuardianCore(...)` / `get_guardian_core(...)` directly (e.g. `run_elysia_interactive.py`, `quick_system_test.py`, various harnesses) **need an explicit `activate()`** if they expect monitors/UI. They are not mass-edited in this bounded task.

## Tests

- `tests/test_guardian_audit_bootstrap.py` — audit path still inert; operational uses activate
- `tests/test_guardian_construct_without_activate.py` — construct zero-start, activate idempotency, flag gating, singleton conflict/reset
