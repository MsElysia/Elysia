# AUTOPILOT-003 Dynamic Inspection — CWA Reconciled (2026-09-11)

## Product under inspection

| Field | Value |
|-------|--------|
| Branch | `cursor/autopilot-003-issue23-cwa-reconciled` |
| Product SHA | `0a2d135990e8acd3b2a5bbf7539f082ec448de73` |
| Base | `d791084e716dfcfdaa686374276611ebc0e2a0e6` |
| Source CWA (PASS does not transfer) | `7374820642fad52a6264c86df8632c3a630df592` |

Fresh inspection only. Do not treat `7374820` or `881608c` reports as evidence for this SHA.

## Method

Twice: `reset_singleton` → `get_guardian_core` (construct/inspect config) → inspect flags → teardown/`reset`.

Config (canonical inspect): UI/resource/runtime-health/prompt-evolution/GuardianLayer/EAI disabled.

Traps armed: `socket.socket`, `subprocess.Popen`/`run`, `threading.Thread.start` (count), plus observed monitor/loop/UI running flags.

## Results

| Cycle | `_activated` | `_running` | monitor running | loop running | UI running | trap hits |
|-------|--------------|------------|-----------------|--------------|------------|-----------|
| 1 | False | False | False | False | False | socket=0 subprocess=0 thread=0 |
| 2 | False | False | False | False | False | same (cumulative 0) |

Log evidence: `Runtime health monitor constructed (thread not started until activate)`; Phase A construct-only end message; teardown stopped resource/runtime monitors without prior start.

## Classifications (fresh, wiring ≠ operational proof)

| Component | Class | Note |
|-----------|-------|------|
| Memory / DreamEngine / Consensus / ModuleRegistry / mutation stack | LIVE_CANONICAL | constructed |
| Capability/UI objects / monitors / WebReader+SubprocessRunner+AnalysisEngine / EAI+TrustPolicy | LIVE_SUPPORTING | constructed, not started |
| Planner live probes / provider sockets | UNREACHABLE at construct | traps zero |
| GuardianLayer (when enabled) | UNKNOWN / residual hang risk | harness disabled here |

## Residuals

- `ensure_monitoring_started` remains a public parallel start API (may start monitors without `_activated`) — unchanged intent vs source CWA; tip `d791084` still called it from `_initialize_system` before this port.
- Official tip `d791084` imported `module_activity` without the module file (broken import); this reconcile restores the module as part of CWA port.
- GuardianLayer hang when `enable_guardian_layer=True`: treat as `UNCHANGED_BOUNDED_RESIDUAL` pending isolated timeout probe (not activation leak in prior evidence).

## Verdict for construct gate

Construct/get/inspect on `0a2d135` did not activate operational services under traps. Independent Vega required; prior PASS not transferred.
