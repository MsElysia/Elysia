# Architecture Review — AUTOPILOT-003 Issue #23 Restack (CWA)

| Field | Value |
|-------|-------|
| **VERDICT** | **READY_FOR_INTEGRATION_REVIEW** |
| **Confidence** | **0.84** |
| **Date** | 2026-09-11 |
| **Reviewer** | Independent architecture reviewer (not Vega; not the implementer) |
| **Product SHA reviewed** | `7374820642fad52a6264c86df8632c3a630df592` |
| **Product branch** | `cursor/autopilot-003-issue23-restack-cwa` |
| **Confirmed HEAD at review** | Match (`git rev-parse` → `7374820…`) |
| **Worktree** | `C:\Users\Owner\Project guardian\.worktrees\autopilot-003-issue23-restack` |
| **Target base ported onto** | `4ff2dc92dd7d9bc393225bce35de9239a9cad6a5` |
| **Source verified product (reference only)** | `776647f80f7d08810f1655c7a2b02fe597c385af` — **PASS does not transfer** |
| **Vega input** | `docs/VEGA-ISSUE-23-RESTACK-CWA-REVERIFY-20260911.md` on `codex/vega-reverify-23-restack-cwa` @ `40bebe6` (**PASS**, confidence 0.86) — consulted; not rubber-stamped |

## Mission

Independent architecture gate for construct-without-activate restack onto the AUTOPILOT / PR #26 lineage tip. Determine whether construct/get/audit boundaries are sound, activation is explicit, tip lineage semantics are preserved, and documentation is honest enough for integration review.

## Method

- Locked review to exact product SHA `7374820` (branch tip of `cursor/autopilot-003-issue23-restack-cwa`).
- Static review of authoritative surfaces: `elysia_sub_guardian.py`, `project_guardian/guardian_singleton.py`, `project_guardian/core.py` (`__init__` / `_initialize_system` / `activate`), production callers, Issue #23 docs, port map, restack manifest.
- Cross-checked Vega PASS residuals; did not re-run adversarial pytest in this review (Vega already reported 20/20 on this SHA).
- No merge, force-push, deploy, or live provider/network activation.

## Checklist findings

### 1. Authoritative constructor boundary — PASS

- `GuardianCore.__init__` initializes `_activated=False`, `_running=False`, builds the inspectable object graph, and ends in `_initialize_system()`.
- `_initialize_system` is explicitly construct-safe: seeds memory/tasks/trust, sets `_initialized=True` with `_running`/`_activated` false, calls `_verify_startup` (wiring checks only), and `_init_runtime_health_monitoring(start=False)`.
- Resource-monitor thread is deferred until explicit `activate()` / Phase B (`_resource_monitor_startup_deferred=True` even when `defer_heavy_startup=False`).
- UI Control Panel object may be constructed when `ui_config.enabled`, but construct path does **not** call `start_ui_panel` / auto-start the server.
- `get_guardian_core` constructs/retrieves only; docstring and body do not call `activate` or `ensure_monitoring_started`.

### 2. Explicit activation API — PASS

- `GuardianCore.activate(*, start_ui=None)` is present, idempotent, respects `enable_background_services` and subsystem disable flags, and sets `_activated`/`_running`.
- `activate_guardian_core` is a thin explicit wrapper.
- `init_guardian_core(mode="operational")` uses get-then-activate when background services allowed; `mode="audit"` remains descriptor-only (`GuardianBootstrapAudit`) with no `project_guardian` import/construct.
- Production callers reviewed (`start_ui_panel.py`, `start_control_panel.py`, `run_elysia.py`, `elysia_interface.open_web_dashboard`) use construct-then-activate. `elysia_interface._init_core` remains construct-only (correct for inspect attach).

### 3. Compatibility with newer AUTOPILOT / PR #26 lineage — PASS (scoped)

- Product commit is a single restack atop `4ff2dc9` (documented tip), not a cherry-pick of `776647f` history — matches port-map FORBIDDEN rule.
- Autopilot control-plane surfaces under `elysia_collective_seed/autopilot/` remain present; restack focus is Guardian bootstrap/lifecycle, not ledger/dispatcher rewrite.
- **Issue #25 claim-boundary:** not claimed by this architecture review. No claim-boundary product surface was proven present as part of this restack. Restack manifest language (“Preserve #22/#25…”) is a **port requirement**, not evidence that #25 landed on this tip. Integration review must not inherit a #25 claim from this SHA.

### 4. Duplicate lifecycle / bypass APIs — PASS with residual

- Construct/get/`_initialize_system` do not invoke `ensure_monitoring_started`.
- `activate()` is the intended operational path and calls `ensure_monitoring_started` internally when bg services are enabled.
- **Residual (non-FAIL for this gate):** public `ensure_monitoring_started` remains callable and can start monitor/loop **without** flipping `_activated`. Also still used by `manual_verification_script.py`. This is a parallel/legacy surface, not a constructor collapse. Track for follow-up deprecation or routing through `activate()`.

### 5. Stale singleton / test isolation vs production semantics — PASS with notes

- Module singleton + class `_any_instance_initialized` guard remain.
- Conflict checks on retrieve reject weaker disable flags against a stronger live instance.
- `get_existing_guardian_core` is retrieve-without-create.
- `reset_singleton` clears instance, monitoring flag, class init flag, and clears `_activated`/`_running` on the discarded instance — adequate test hygiene.
- Issue #23 suites use `no_guardian_core` + local stubs; production semantics are not rewritten by those stubs.

### 6. Target-lineage regression risk — PASS (material for this gate)

- No evidence that the restack removes required #22/#26 control-plane contracts for the construct-without-activate gate.
- Deferred Phase B / thin-memory planner probe behavior is preserved under `activate` (operational nuance, not construct collapse).
- Broader tip regression beyond CWA is an integration concern; architecture gate for Issue #23 CWA does not require proving full tip CI green here.

### 7. Documentation truthfulness — PASS with residuals

| Doc | Assessment |
|-----|------------|
| `docs/ISSUE-23-RESTACK-CWA-PORT-MAP.md` | Honest classification; forbids wholesale cherry-pick; states tip preservation rule. |
| `docs/ISSUE-23-AUDIT-BOOTSTRAP.md` | Correct three-path map (audit / construct / activate); acknowledges construct-without-activate delivery and legacy-caller residual. |
| `docs/ISSUE-23-CONSTRUCT-WITHOUT-ACTIVATE.md` | Semantics accurate; **branch header still names source branch** `cursor/guardian-23-construct-without-activate` (cosmetic drift vs restack branch). |
| `docs/ISSUE-23-CONSTRUCTOR-SIDE-EFFECT-MAP.md` | Pre-change inventory (still lists UNSAFE construct effects) — truthful as inventory if read as such; not a post-restack status board. |
| `docs/boot_memory_map.md` | **Stale:** still claims `_initialize_system` calls `ensure_monitoring_started` — false on `7374820`. Residual (also noted by Vega). |
| Restack manifest | Correctly says no integration-readiness claim; #22/#25 preserve wording must not be read as #25 delivered. |

**Three states** are architecturally represented:

1. **DESCRIBE / AUDIT** — `init_guardian_core(mode="audit")` / `describe_guardian_bootstrap`
2. **CONSTRUCT / INSPECT** — `GuardianCore(...)` / `get_guardian_core` / bg-false operational normalize without activate
3. **OPERATIONAL** — explicit `activate` / `activate_guardian_core` (and operational init when bg enabled)

Docs do **not** falsely claim source `776647f` PASS transfers, and do **not** claim false readiness on the port map/manifest.

### 8. Complexity vs semantic port — PASS

- Target rewrite of `core.py` lifecycle (`_initialize_system` vs `activate`) is necessary on the tip; not an unnecessary second framework.
- Keeping `ensure_monitoring_started` as an activate helper is pragmatic; leaving it public is residual complexity, not restack bloat.
- Semantic port (not history merge) matches stated restack rules.

## Verdict rationale

Construct/get/audit cannot mark or drive operational lifecycle by themselves on `7374820`. Activation is explicit and idempotent. Restack sits on PR #26 tip without transferring source PASS or inventing a #25 claim. Residuals (`ensure_monitoring_started` parallel API, stale `boot_memory_map.md`, Phase B deferred ops after activate, `_normalize_config` key pass-through limits) do **not** collapse the Issue #23 construct-without-activate gate.

Therefore: **READY_FOR_INTEGRATION_REVIEW**.

## Residuals for integration / follow-up (non-blocking for this gate)

1. Deprecate or wrap public `ensure_monitoring_started` so operational start always goes through `activate()` and `_activated`.
2. Refresh `docs/boot_memory_map.md` to match construct-only `_initialize_system`.
3. Update CWA doc branch header to the restack product branch name.
4. Optional: harden `_normalize_config` pass-through for test/ops keys dropped today.
5. Do not treat #25 claim-boundary as delivered by this restack unless separately proven.
6. Legacy scripts that still call construct without activate will remain inspect-only until updated (documented intentional residual).

## Non-goals / not reviewed as pass criteria

- Live provider activation, deployment, or merge readiness beyond architecture gate.
- Full tip CI matrix / `pyttsx3` environment residuals noted by Vega.
- Transfer of source product PASS at `776647f`.

---

*Report only — no product code changes. Branch: `codex/arch-review-23-restack-cwa`.*
