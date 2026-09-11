# Architecture review — Issue #23 construct-without-activate

| Field | Value |
| --- | --- |
| Date | 2026-09-11 |
| Reviewer role | Independent architecture review (did **not** implement CWA; did **not** author Vega suite) |
| Product SHA | `776647f80f7d08810f1655c7a2b02fe597c385af` |
| Worktree | `.worktrees/guardian-23-construct-without-activate` |
| Product branch | `cursor/guardian-23-construct-without-activate` |
| Docs branch | `codex/review-23-cwa` |
| Precursor | PR #27 audit descriptor @ `79b6c6456eae1d6a400c8b08516a8478d769d25e` (ancestor of HEAD) |
| Vega input | PASS @ confidence 0.86; 20 tests green; residuals assessed below |
| **VERDICT** | **READY_FOR_INTEGRATION_REVIEW** |

---

## Scope of claim under review

Issue #23 claims: **construct / retrieve / inspect must not operationally activate**. Explicit activation (`GuardianCore.activate` / `activate_guardian_core` / operational `init_guardian_core` when background services allowed) starts monitors, loop, prompt evolution, UI, planner probes, and runtime-health threads. Precursor PR #27 audit-mode descriptor must remain intact.

This is **not** a claim of absolute constructor purity (no disk/env/object-graph work). Documented construct-allowed effects (config/object graph, memory/task/trust seed, API-key env wiring) remain in scope as construction.

---

## Review questions

### 1. Is construction truly side-effect-free at the authoritative layer?

**Yes, for the claimed operational invariant.**

Authoritative construct surfaces:

- `GuardianCore.__init__` → `_initialize_system()` seeds memory/tasks/trust only; sets `_activated=False` / `_running=False`; builds runtime-health graph via `_init_runtime_health_monitoring(start=False)`; never calls `ensure_monitoring_started`.
- Resource-monitor thread is **not** started at construct; `_resource_monitor_startup_deferred=True` in both deferred and non-deferred boot modes.
- UI: object graph only (`UIControlPanel` with `running=False`); no `start` / listen during construct even if `ui_config.auto_start` is true.
- Nested monitors (`SystemMonitor` / `Heartbeat`) create objects only; threads start on `start_monitoring` / `start`.
- `get_guardian_core` / `get_existing_guardian_core` construct or return; neither activates.

Residual construct-time effects (seed writes, env keys, Flask app construction without listen) match the side-effect map’s `CONSTRUCTION_REQUIRED` / `AMBIGUOUS` classes and do not violate CWA.

### 2. Is activation explicit?

**Yes.** Primary gate is `GuardianCore.activate(*, start_ui=None)` (idempotent; respects `enable_background_services` and subsystem flags; never re-enables caller-disabled services). Thin wrapper: `activate_guardian_core`. Operational bootstrap: `init_guardian_core(..., mode="operational")` → get then activate when BG services allowed. Audit mode never constructs or activates.

### 3. Duplicate lifecycle systems?

**Mild residual parallelism — not a competing construct path.**

| Surface | Role |
| --- | --- |
| `activate` / `activate_guardian_core` | Authoritative operational start |
| `ensure_monitoring_started` | Public helper still callable without `activate`; used **by** activate; also tests / `manual_verification_script.py` |
| `start_deferred_initialization` (Phase B) | Explicit heavy-memory path; can start deferred resource monitor |
| `start_ui_panel` | Explicit UI start (also reachable from activate) |

This is **known parallel API surface**, not a second silent construct→activate system. Complexity cost is real but bounded.

### 4. Operational callers still explicit/correct?

**Yes for production paths in the bounded change set.**

Updated: `elysia_sub_guardian` operational path, `run_elysia.py`, `start_ui_panel.py`, `start_control_panel.py`, `elysia_interface` dashboard open (`activate_guardian_core(..., start_ui=True)`), dashboard readiness test. Unified path `elysia.py` → `init_guardian_core(..., mode="operational")` still activates when BG on, then may spawn Phase B after dashboard ready.

Documented legacy residual: other scripts that construct without `activate` no longer get free monitor/UI start — intentional; not mass-edited.

`elysia_interface._init_core` retrieves/constructs with monitoring flags off and does **not** activate — appropriate for attach/CLI inspect, not a silent operational boot.

### 5. Can lower-level code bypass the activation boundary in a way that breaks the claim?

**No material construct/retrieve/inspect bypass found.**

Bypasses that **do** start work require an **explicit** non-construct call:

1. `start_deferred_initialization()` → `_ensure_resource_monitor_started_after_deferred()` may start the resource-monitor thread while `_activated` stays false (Phase B residual).
2. Direct `ensure_monitoring_started(core)` can start system monitor / loop / prompt scheduler without flipping `_activated` (parallel API residual).
3. Direct `start_ui_panel()` remains an explicit UI start.

None of these are implied by construct, singleton retrieve, or audit inspect. They do **not** falsify the Issue #23 CWA claim as stated.

### 6. Singleton state understandable?

**Yes.** Module singleton + class `_any_instance_initialized`; conflict rejection when a weaker disable flag is requested against a stronger live instance; `reset_singleton` clears instance, monitoring guard, class flag, and clears `_activated`/`_running` on the prior instance. Construct after reset does not leak activation. Dual flags (`_activated` + `_running`) are slightly redundant but coherent with activate’s idempotent check.

### 7. Docs honest?

**Core Issue #23 docs are honest** (`ISSUE-23-CONSTRUCT-WITHOUT-ACTIVATE.md`, side-effect map, audit bootstrap update preserving PR #27). Audit descriptor contract at `79b6c64` remains ancestor and behaviorally intact (mode keyword, pure audit descriptor, no `project_guardian` import on audit).

Caveats:

- Comment/log lines distinguish “until Phase B” vs “until explicit activate()” by `defer_heavy_startup`; Phase B can still start the resource monitor without `_activated` — slight **mental-model drift** vs treating `_activated` as the sole “anything running” bit.
- Older docs (`boot_memory_map.md`, `GUARDIAN_SINGLETON_FIX.md`, TASK-0051 notes) still describe pre-CWA `_initialize_system` → `ensure_monitoring_started`; stale, out of this PR’s honesty bar for the Issue #23 docs themselves.

### 8. Complexity up/down?

**Net cognitive complexity down** for the primary story (construct ≠ activate). **Local complexity slightly up** from Phase-B coupling to resource monitor, dual activation flags, and retained public `ensure_monitoring_started`. Acceptable for a bounded lifecycle split.

---

## Vega residuals — severity

| # | Residual | Severity vs CWA claim | Disposition |
| --- | --- | --- | --- |
| 1 | Phase B can start resource monitor while `_activated` is false | **Low** for CWA (explicit Phase B, not construct). **Medium** for “single activation bit means all threads” mental model | Known parallel / post-activate boot phase; optional gate on `_activated` later |
| 2 | Public `ensure_monitoring_started` parallel start surface | **Low** for CWA; **Medium** API hygiene | Record as known parallel API; optional deprecate/wrap later |
| 3 | Comment drift Phase B vs activate | **Cosmetic / docs** | Optional comment tidy; current logs mostly distinguish modes |

**None of these residuals alone justify RETURN_FOR_REPAIR** against the claimed construct-without-activate invariant.

---

## Precursor PR #27

`79b6c64` is an ancestor of `776647f`. Diff on `elysia_sub_guardian.py` updates operational path to `activate_guardian_core` and tightens probe scheduling behind BG services; **audit mode and `GuardianBootstrapAudit` / `describe_guardian_bootstrap` remain**. Audit suite still present and exercised per Vega (10 audit + 10 CWA = 20).

---

## Implementation-complete recommendation

**Do not require a bounded repair follow-up before calling Issue #23 implementation complete** for the CWA claim.

Recommended status label:

`IMPLEMENTATION_COMPLETE_PENDING_RUNTIME_VERIFICATION`

with residuals recorded as **known parallel APIs / Phase-B coupling**, optional hardening (not blockers):

1. Gate `_ensure_resource_monitor_started_after_deferred` on `_activated` **or** document Phase B as an explicit co-equal operational action that may start the resource monitor.
2. Soft-deprecate direct `ensure_monitoring_started` for non-activate callers (keep as activate implementation detail).
3. Refresh stale pre-CWA docs when convenient.

Integration review should still verify live boot (UnifiedElysia + dashboard + Phase B) once under real deps — that is runtime verification, not architecture repair.

---

## Verdict

```
VERDICT: READY_FOR_INTEGRATION_REVIEW
sha: 776647f80f7d08810f1655c7a2b02fe597c385af
precursor_79b6c64: intact (ancestor + audit descriptor preserved)
cwa_invariant: holds at construct/retrieve/inspect
material_bypass: none
vega_residuals: do not block; record as known parallel APIs / Phase-B coupling
issue_23_status_recommendation: IMPLEMENTATION_COMPLETE_PENDING_RUNTIME_VERIFICATION
bounded_follow_up_required_before_complete: no
```
