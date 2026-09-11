# VEGA Re-Verify — AUTOPILOT-003 Issue #23 Restack (CWA)

| Field | Value |
|-------|-------|
| **VERDICT** | **PASS** |
| **Confidence** | **0.86** |
| **Date** | 2026-09-11 |
| **Verifier** | Independent Vega (did not implement the port) |
| **Target SHA** | `7374820642fad52a6264c86df8632c3a630df592` |
| **Confirmed HEAD** | Match (`cursor/autopilot-003-issue23-restack-cwa` → reverify branch `codex/vega-reverify-23-restack-cwa`) |
| **Worktree** | `C:\Users\Owner\Project guardian\.worktrees\autopilot-003-issue23-restack` |
| **Source product PASS** | `776647f` — **does not transfer**; this run falsifies `7374820` independently |

## Mission

Attempt to cause Guardian **operational** activity merely by constructing, retrieving, inspecting, or reusing Guardian on this restack candidate. Fail the candidate if construct/audit/getter paths start monitors, loop, UI, probes, or mark `_activated`/`_running` without explicit `activate` / `activate_guardian_core`.

## Commands run

Python: `C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`

```
PYTHONPATH=<worktree>;<worktree>/tests/_stubs;C:\Users\Owner\Project guardian\.worktrees\vega-test-15\.vega-deps
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

python -m pytest -q tests/test_guardian_audit_bootstrap.py tests/test_guardian_construct_without_activate.py
# → 20 passed (reconfirmed twice)

python -m compileall -q elysia_sub_guardian.py project_guardian/guardian_singleton.py project_guardian/core.py
# → exit 0
```

Lineage spot-check: `tests/test_guardian_singleton.py` **collection ERROR** in this runtime (`ModuleNotFoundError: pyttsx3`) without the Issue #23 stub installer — treated as **environment residual**, not a product falsification of construct-without-activate. Issue #23 suites install stubs themselves and pass.

## Probe matrix (independent)

| Probe | Result |
|-------|--------|
| Audit descriptor `init_guardian_core(mode="audit")` / `describe_guardian_bootstrap` | No construct; no sockets/threads/subprocesses under forbid patches |
| Omitted `mode=` / malformed mode | `TypeError` / `ValueError` — no operational start |
| Direct `GuardianCore(...)` | `_activated=False`, `_running=False` |
| `get_guardian_core` / repeated get / stale singleton | Same instance; remains non-activated; inspect helpers do not start ops |
| False / omitted service flags on construct | Construct only; no activation |
| Teardown (`reset_singleton`) / reopen | New instance; not activated |
| UI helpers | `activate()` with `auto_start=False` does not start UI; `start_ui=True` does |
| Operational caller transition | Explicit `activate_guardian_core` sets `_activated`/`_running` |
| Old helper `ensure_monitoring_started` from construct path | **Not called** by `get_guardian_core` or `_initialize_system` (static + source inspect) |
| `ensure_monitoring_started` as parallel API | **Can** start monitoring **without** setting `_activated` — residual (see below) |

Independent scripted probe (reuse of Issue #23 import stubs, not product edits): `INDEP_PROBE_OK` — construct/inspect idle; `EMS True activated False hits {'m': 1, 'l': 0}` for parallel ensure; explicit activate then succeeds.

Static:

- `ensure_monitoring_started` **absent** from `_initialize_system`
- `ensure_monitoring_started(` / `activate(` **not called** from `get_guardian_core` body (docstring mentions only)
- Product call sites of `ensure_monitoring_started(`: `project_guardian/core.py` inside `activate()` only; plus legacy `manual_verification_script.py`

## Evidence summary

1. **HEAD lock:** `7374820642fad52a6264c86df8632c3a630df592` confirmed before probes.
2. **Adversarial suites:** 20/20 pass covering audit purity, construct-zero operational surfaces, activate idempotency, bg-false gating, UI auto_start gating, singleton disable conflicts, reset hygiene.
3. **Bytecode:** `compileall` clean on the three Issue #23 surface modules.
4. **Falsification attempt failed:** Could not cause operational activation via construct/retrieve/inspect/reuse alone on this SHA.
5. **Caller skim:** `start_ui_panel.py` / `start_control_panel.py` / `run_elysia.py` / dashboard path in `elysia_interface.py` use construct-then-`activate`; `_init_core` remains construct-only.

## Residuals (not FAIL for Issue #23 construct gate)

1. **Phase B / parallel API — `ensure_monitoring_started`:** Still public. Callers can start monitor/loop **without** going through `activate()` and without flipping `_activated`. Production construct path does not invoke it; `activate()` does. Treat as intentional legacy/parallel surface until a follow-up deprecates or routes it through activate.
2. **Phase B deferred ops:** Resource monitor / planner probe may remain deferred after activate when `defer_heavy_startup` + thin memory — activate marks operational while some threads await Phase B. Out of scope for “construct must not activate,” but relevant for full boot semantics.
3. **`_normalize_config` pass-through:** Operational bootstrap drops many keys (`_test_skip_external_storage`, `enable_guardian_layer`, etc.) and defaults `ui_config.auto_start=True`. Construct graph under `mode="operational"` remains heavy (Phase A object graph), even when bg-false skips activate.
4. **Doc drift:** `docs/boot_memory_map.md` still claims `_initialize_system` calls `ensure_monitoring_started` — false on this SHA.
5. **Legacy script:** `manual_verification_script.py` still calls `ensure_monitoring_started` directly.
6. **Runtime deps:** Broader lineage tests without Issue #23 stubs fail import (`pyttsx3`) in this verifier environment.

## Next

1. Accept `7374820` for Issue #23 construct-without-activate gate (this reverify **PASS**).
2. Optional follow-ups (separate issues): deprecate/wrap `ensure_monitoring_started` behind activate; refresh `boot_memory_map.md`; harden `_normalize_config` pass-through for test/ops keys; Phase B activation-vs-deferred-thread contract tests.
3. Do **not** treat prior `776647f` PASS as evidence for this restack tip.

---

*Report only — no product code changes. Branch: `codex/vega-reverify-23-restack-cwa`.*
