# Startup storage fallback baseline

**Milestone:** Startup storage fallback baseline  
**Verified commit:** `c8cd3d4` — fix(startup): allow storage fallback during health check  
**Status:** Verified PASS (Cursor + Codex)  
**Date recorded:** 2026-05-30

---

## Summary

Normal Elysia startup (`python -u elysia.py`) previously exited immediately with code 1 when the configured USB drive (`F:\`) was absent. Startup health treated missing external storage as a critical failure before runtime storage fallback could apply. Commit `c8cd3d4` aligns startup health with runtime fallback behavior so startup proceeds when a safe writable fallback exists.

---

## Original failure

| Symptom | Detail |
|---------|--------|
| Command | `python -u elysia.py` |
| Exit code | **1** |
| Traceback | None |
| Last error | `[Startup] External storage not writable: F:\ - [WinError 3] The system cannot find the path specified: 'F:\\'` |
| Follow-up | `Startup health check failed - check logs above` |
| Root cause | `config/external_storage.json` points to `F:\`; `project_guardian/startup_health.py` treated missing/unwritable primary external storage as **critical** and called `sys.exit(1)` in `elysia.py` before `UnifiedElysiaSystem.start()` |
| Mismatch | Runtime storage (`project_guardian/external_storage.py`) already supports fallback drives and local `%LOCALAPPDATA%\ElysiaGuardian\memory`, but startup health did not honor that chain |

---

## Fixed behavior (commit `c8cd3d4`)

Implementation: `project_guardian/startup_health.py` — `_assess_external_storage_startup()`  
Tests: `project_guardian/tests/test_startup_config.py` — `TestExternalStorageStartupFallback`

| Scenario | Behavior |
|----------|----------|
| Primary `external_drive` writable | Startup proceeds; no warning |
| Primary missing, fallback drive writable | Startup proceeds; **warning** records fallback drive used |
| No configured drive writable, local fallback writable | Startup proceeds; **warning** records local fallback path |
| No writable path (configured + local) | Startup **fails** (critical); exit code 1 unchanged for true storage failure |

Check order:

1. `external_drive` from `config/external_storage.json`
2. `fallback_drives` list
3. Local fallback via `get_default_fallback_path()` (same helper as runtime storage)

Side effects: temporary `.health_check` write/delete probes only. No config file changes required for the fix.

---

## Verification results

### Safe Observer real-planning dry-run

```bash
python scripts/run_elysia_dry_run_report.py --mode real-planning
```

| Field | Result |
|-------|--------|
| Exit code | **0** |
| Safety verdict | **SAFE** |
| Cycles | requested=3, completed=3 |
| `all_dry_run` | True |
| `any_executed` | False |
| `execution_call_count` | 0 |
| `legacy_fallback_reached` | False |

### Safe-stack smoke

```bash
python scripts/run_safe_stack_smoke_tests.py
```

| Field | Result |
|-------|--------|
| Exit code | **0** |
| Tests | **450 passed**, 3 warnings |

### Normal startup

```bash
python -u elysia.py
```

| Field | Result |
|-------|--------|
| Storage health gate | **Passed** — no longer exits at missing `F:\` when fallback exists |
| Backend state | Reached running backend / status endpoint state |
| Confirmed lines | `Unified Elysia System is running`; `Status endpoint: http://127.0.0.1:8888/status` |
| Shutdown | Manually stopped after confirmation (server loop observed) |

### Autonomy / live execution

| Check | Result |
|-------|--------|
| `config/autonomy.json` `enabled` | **false** (unchanged) |
| Autonomy enabled during verification | **No** |
| Live execution enabled | **No** |

---

## Safety boundaries

This fix **does not**:

- Enable autonomy
- Enable live execution
- Run tools, capabilities, mutation, proposal implementation, WebScout, or browser activity
- Modify `config/autonomy.json`
- Change autonomy dry-run guards or Safe Observer command behavior

This fix **only** changes startup storage health behavior in `project_guardian/startup_health.py` so missing configured external storage is not fatal when a writable fallback path exists.

Safe Observer (`scripts/run_elysia_dry_run_report.py`) remains the verified dry-run entry point for autonomy observation; it is unrelated to this startup repair.

---

## Remaining known risks

| Risk | Status |
|------|--------|
| `project_guardian/core.py` | Dirty, **unstaged** — must be cleaned/quarantined before live-action expansion |
| `elysia/api/server.py` | Dirty, **unstaged** — must be cleaned/quarantined before live-action expansion |
| Startup stability | Improved; **not** proof that live autonomy is safe |
| Full runtime pytest | Out of scope for this baseline; failures not classified here |
| Dirty worktree | Must not be used as verification proof |

---

## Recommended next branches

| Branch | Focus |
|--------|-------|
| **A** | Dirty `core.py` / `server.py` cleanup and quarantine |
| **B** | Safe Observer user guide |
| **C** | Full runtime pytest failure classification |
| **D** | Phase 2 live-action allowlist design only (no enablement) |

---

## Related commits

```
c8cd3d4 fix(startup): allow storage fallback during health check
64ff8da docs(autonomy): checkpoint safe observer mode
```

## Related files

- `project_guardian/startup_health.py`
- `project_guardian/external_storage.py` (runtime fallback reference; not modified by `c8cd3d4`)
- `config/external_storage.json` (committed config; unchanged by fix)
- `project_guardian/tests/test_startup_config.py`
