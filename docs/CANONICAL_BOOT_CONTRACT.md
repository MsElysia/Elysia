# Canonical Boot Contract

**Status:** Frozen reference for consolidators (2026-09-09)  
**Source map:** [`REPORTS/canonical_runtime_map.md`](../REPORTS/canonical_runtime_map.md)

This document defines what is **actually live** for Project Guardian / Elysia.  
Do not treat file existence, README history, or alternate CLIs as proof of the primary runtime.

---

## Primary live boot (desktop / operator)

```
START_ELYSIA_UNIFIED.bat
  → Start_Elysia_Backend.cmd
      → ensure_ollama_running.ps1
      → ensure_openclaw_running.ps1
      → python elysia.py   (ELYSIA_FORCE_FULL_BACKEND=1)
          → UnifiedElysiaSystem
          → GuardianCore via elysia_sub_guardian / guardian_singleton
          → Status HTTP  :8888
          → Flask UI     :5000 (UIControlPanel)
  → wait_for_elysia_backend.py
  → elysia_interface.py --attach-only
```

**Equivalents**

| Launcher | Role |
|----------|------|
| `Start Project Guardian.bat` | Direct `python elysia.py` |
| `START_ELYSIA_FULL.bat` | Alias → unified |
| `START_ELYSIA_LOCAL_MISTRAL.bat` | Unified path + local Mistral bias |
| Desktop `Elysia.lnk` | Points at `START_ELYSIA_UNIFIED.bat` |

**Operator surfaces after boot**

- Status / OpenAI-compat bridge: `http://127.0.0.1:8888/status`
- Control panel: `http://127.0.0.1:5000`

---

## Secondary (documented package entry — not desktop-primary)

```
python -m project_guardian
  → SystemOrchestrator
```

Still valid for orchestrator/API experiments. **Not** what the Windows desktop launchers run.  
Flask API historically associated with this path: `:8080`.

---

## Parallel package runtime (do not confuse with root `elysia.py`)

```
python -m elysia run
  → elysia.runtime.ElysiaRuntime
  → Runtime API ~:8123
```

Also used by `restart_elysia_runtime.ps1`. This is a **different composition root** from `GuardianCore`.

---

## Optional UI

| Command | Port | Notes |
|---------|------|-------|
| Auto-started from GuardianCore | 5000 | Flask `UIControlPanel` |
| `scripts/start_control_panel.ps1` | 8000 | FastAPI workbench |

---

## Protected live modules under `core_modules/`

These have **no** first-class `project_guardian` twin and are imported on the unified path via `sys.path` (see `elysia.py`). Do **not** delete or archive without a port plan:

- `architect_core.py` → `ArchitectCore`
- `ai_tool_registry.py` → `ToolRegistry` / `TaskRouter`
- `fractalmind.py` → `FractalMind`
- `harvest_engine.py` → `HarvestEngine`
- `hestia_bridge.py` → `HestiaBridge`
- `identity_mutation_verifier.py` → `IdentityMutationVerifier`

Guard test: `project_guardian/tests/test_protected_core_modules.py`

---

## Explicit non-goals for consolidators

- Do not merge `elysia-local-reconciliation-*` wholesale into `main`
- Do not enable live autonomy / `live_action_*` executors as part of cleanup
- Do not prepend `organized_project/` to `sys.path`
- Do not treat `elysia_collective_seed/` as Guardian runtime code
- Root `startup.py` is **not** part of live boot (absent)

---

## Related reports

- [`REPORTS/canonical_runtime_map.md`](../REPORTS/canonical_runtime_map.md)
- [`REPORTS/reconciliation_priority_queue.md`](../REPORTS/reconciliation_priority_queue.md)
