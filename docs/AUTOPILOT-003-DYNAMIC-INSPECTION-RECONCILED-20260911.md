# AUTOPILOT-003 Dynamic Inspection — CWA Reconciled (2026-09-11)

## Product under inspection

| Field | Value |
|-------|--------|
| Branch | `cursor/autopilot-003-issue23-cwa-reconciled` |
| **Product SHA** | `0a2d135990e8acd3b2a5bbf7539f082ec448de73` |
| Docs tip (this report family) | follow-up docs commits after product; product SHA unchanged |
| Base | `d791084e716dfcfdaa686374276611ebc0e2a0e6` |
| Source CWA (PASS does **not** transfer) | `7374820642fad52a6264c86df8632c3a630df592` |

Fresh inspection + residual probes against product tree `0a2d135` (docs-only tip does not alter product blobs). Do not treat `7374820` / `881608c` reports as evidence for this SHA.

## Method (primary double cycle)

Twice: `reset_singleton` → `get_guardian_core` → inspect → teardown/`reset`.

Primary config: `enable_guardian_layer=False`, EAI config `enabled:false`, UI `auto_start=False`, resource/runtime-health/prompt surfaces constructed but not started at construct.

**Traps armed:** `socket.socket`, `subprocess.Popen`/`run`/`call`, `threading.Thread.start` (count + neutralize body), `openai.OpenAI` (if present), `planner_readiness.run_startup_planner_probe`. Observed flags: monitor/loop/UI/resource/runtime-health/prompt `_started`/`running`.

Harness: `_autopilot003_reconciled_inspect.py` (local, not product). Exit 0 = both cycles `construct_ok`.

## Primary results (`0a2d135`)

| Cycle | `_activated` | `_running` | SystemMonitor | ResourceMonitor | ElysiaLoop | PromptSched | UI | trap hits |
|-------|--------------|------------|---------------|-----------------|------------|-------------|----|-----------|
| 1 | **False** | **False** | False | False | False | False | False | socket=0 subprocess=0 thread=0 provider=0 planner=0 |
| 2 | **False** | **False** | False | False | False | False | False | same |

Teardown both cycles: `singleton_is_none=True`, `_monitoring_started=False`, `_any_instance_initialized=False`.

Log: `Runtime health monitor constructed (thread not started until activate)`; Phase A construct-only end.

## Lineage / control-plane regression (fresh)

Exact historical RECONCILE-22 union (evidence binding, soft-risk adversarial, verifier, lifecycle, seed control-plane):

```text
python -m pytest -q elysia_collective_seed \
  tests/test_autopilot_verifier.py \
  tests/test_autopilot_verifier_ledger_migration.py \
  tests/test_autopilot_verifier_lifecycle.py \
  tests/test_vega_verifier_boundaries.py \
  tests/test_autopilot_lifecycle_repairs.py \
  tests/test_vega_evidence_binding.py \
  tests/test_autopilot_evidence_binding.py \
  tests/test_autopilot_evidence_binding_regressions.py \
  tests/test_vega_evidence_binding_adversarial.py
```

| Suite | Result |
|-------|--------|
| Union / #22 lineage control-plane | **147 passed** in 4.36s |
| CWA (`test_guardian_construct_without_activate` + `test_guardian_audit_bootstrap`) | **20 passed** in 0.69s |
| `compileall` (core CWA surfaces) | **exit 0** |

No product repair required. Product SHA remains `0a2d135`.

## Bounded residual probes (subprocess + timeout)

Harness: `_autopilot003_reconciled_residual.py` (local).

| Probe | Result | Classification |
|-------|--------|----------------|
| `enable_guardian_layer=True` construct (25s subprocess timeout) | **TIMEOUT** mid Phase A (stderr reaches EAI-disabled skip; no activate log; no JSON completion) | **UNCHANGED_BOUNDED_RESIDUAL** — construct stall / join risk under Thread.start trap; tip CWA tests already disable layer; **not** proven activate leak; **not BLOCKING** for construct gate |
| EAI enabled + layer off construct | OK; `_activated=False` `_running=False` `thread_starts=0`; `EAISafetyFramework` constructed | **Construct-inert / LIVE_SUPPORTING** — not operational activation. Tip unit tests disable EAI under full `Thread` class mocks (harness conflict); start-method trap is safe. Mock conflict ≠ product activate regression |
| Public `ensure_monitoring_started` after construct | Starts `SystemMonitor` / prompt scheduler while `_activated` stays **False** | **UNCHANGED_BOUNDED_RESIDUAL** — legacy public bypass; tip did **not** gate it on `_activated` (identical to source CWA `7374820` singleton ensure body) |

### `ensure_monitoring_started` tip note

Reconcile did **not** remove or `_activated`-gate the public API. Construct path no longer calls it; `activate()` / `activate_guardian_core` remain the authorized start. Callers of the public ensure helper can still start monitors without flipping `_activated` — known residual, not a new tip regression vs B.

## Classifications (wiring ≠ operational proof)

| Component | Class | Note |
|-----------|-------|------|
| Memory / Dream / Consensus / ModuleRegistry / mutation stack | LIVE_CANONICAL | constructed |
| Monitors / loop / UI / prompt / WebReader+SubprocessRunner+AnalysisEngine / EAI+TrustPolicy | LIVE_SUPPORTING | constructed, not started on primary cycles |
| Planner live probes / provider sockets / subprocess | UNREACHABLE at construct | zero trap hits |
| GuardianLayer when enabled | UNCHANGED_BOUNDED_RESIDUAL | timeout under isolated probe |
| `ensure_monitoring_started` public bypass | UNCHANGED_BOUNDED_RESIDUAL | monitor starts without `_activated` |

## Verdict

- Construct/get/inspect on **product `0a2d135`**: no operational activation under traps (2/2 cycles).
- Lineage/control-plane: **147 passed**; CWA: **20 passed**.
- Residuals: GuardianLayer hang + ensure bypass remain **bounded / unchanged**; EAI construct inert OK.
- Independent Vega required; **`7374820` PASS does not transfer**.
- No FAIL needing product repair this run.
