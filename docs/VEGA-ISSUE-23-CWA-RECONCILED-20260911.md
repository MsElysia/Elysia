# VEGA ISSUE #23 CWA RECONCILED REVERIFY — 2026-09-11

Independent adversarial verification of construct-without-activate (CWA)
reconciliation. Verifier did **not** implement the port and did **not** modify
product code. Prior PASS on source CWA `7374820` does **not** transfer.

## TARGET SHA (exact product)

`0a2d135990e8acd3b2a5bbf7539f082ec448de73`  
Branch (product): `cursor/autopilot-003-issue23-cwa-reconciled`  
Base: `d791084e716dfcfdaa686374276611ebc0e2a0e6`  
Source verified CWA (reference only): `7374820642fad52a6264c86df8632c3a630df592`

**Docs tip note:** product branch tip has moved to docs-only commits above
`0a2d135` (`d0e1905` → `fd53e2d` → `3c3ead5` at verify time). This report
verifies **product code at `0a2d135`**, not the docs tip.

## VERDICT

**PASS**

## CONFIDENCE

**0.88** — prescribed CWA + audit suites green; independent VEGA adversarial
suite green; static confirm `ensure_monitoring_started` only on `activate()`;
production callers construct-then-activate; residuals are explicit non-construct
APIs / Phase-B / known hang surface.

## Commands + results

```
git rev-parse HEAD
→ 0a2d135990e8acd3b2a5bbf7539f082ec448de73

python -m pytest -q \
  tests/test_vega_issue23_cwa_reverify.py \
  tests/test_guardian_audit_bootstrap.py \
  tests/test_guardian_construct_without_activate.py
→ 28 passed

python -m compileall -q \
  elysia_sub_guardian.py \
  project_guardian/guardian_singleton.py \
  project_guardian/core.py
→ exit 0
```

(Project venv: `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe`)

## Attack surface results (construct / retrieve / inspect)

| Probe | Result |
|-------|--------|
| Direct `GuardianCore(...)` | Inert (`_activated`/`_running` False; zero monitor/loop/UI/probe/health starts) |
| `get_guardian_core(...)` | Inert; does **not** call `ensure_monitoring_started` |
| Audit descriptor `init_guardian_core(mode="audit")` / `describe_guardian_bootstrap` | Descriptor only; no singleton |
| Omitted / default flags + `ui_config.auto_start=True` | Construct still inert |
| Explicit false flags | Construct inert; `activate()` gated (no monitor/UI starts) |
| Malformed truthy string flag | Construct still inert |
| Repeated construction / nested get | Same singleton; remains inert |
| Stale singleton after activate + `reset_singleton` | Re-open construct inert |
| Teardown / reopen | Re-construct inert |
| UI helpers / production scripts | `start_ui_panel.py`, `start_control_panel.py`, `run_elysia.py`, `elysia_interface.py` construct then `activate` / `activate_guardian_core` |
| Operational caller transition | `elysia_sub_guardian` operational path uses `get_guardian_core` then `activate_guardian_core`; exercise via activate wrapper after construct |
| `ensure_monitoring_started` awareness | Explicit call can start monitoring **without** going through construct; documented residual (not construct collapse) |

## Claims confirmed

- `GuardianCore(...)` / `get_guardian_core(...)` are construct/retrieve only.
- Operational start requires `activate()` / `activate_guardian_core()`.
- Audit path remains inert.
- `ensure_monitoring_started` is invoked from `GuardianCore.activate` only (not `__init__` / `_initialize_system`).
- Explicit false / omitted flags do not auto-activate on construct.

## Residuals (not FAIL for CWA claim)

1. **`ensure_monitoring_started`** remains a public parallel start API (used by
   `activate`); explicit call can start monitors without setting `_activated`.
   Does **not** collapse the construct path.
2. **`start_deferred_initialization()` (Phase B)** can start the resource
   monitor as an explicit heavy-boot step — not construct.
3. **GuardianLayer hang risk** when `enable_guardian_layer=True` — bounded
   residual from prior inspections; harnesses keep it disabled.
4. Legacy scripts that only construct still need an explicit `activate()` if
   they expect monitors/UI (documented intentional residual).

## Material new bypass?

**None** found on `0a2d135`.

## Next

Architecture / integration review of reconciled CWA onto restack tip; keep #23
open until governance merge decision. No merge / force-push / live providers
exercised by this verify.
