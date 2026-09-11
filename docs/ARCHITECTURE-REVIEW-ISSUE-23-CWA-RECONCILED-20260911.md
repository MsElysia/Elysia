# Architecture Review — AUTOPILOT-003 Issue #23 CWA Reconciliation

| Field | Value |
|-------|-------|
| **VERDICT** | **READY_FOR_INTEGRATION_REVIEW** |
| **Confidence** | **0.87** |
| **Date** | 2026-09-11 |
| **Reviewer** | Independent architecture reviewer (not Vega; not the implementer) |
| **Product SHA reviewed** | `0a2d135990e8acd3b2a5bbf7539f082ec448de73` |
| **Product branch** | `cursor/autopilot-003-issue23-cwa-reconciled` |
| **Confirmed product SHA** | Match (`git rev-parse` / worktree locked to `0a2d135…`) |
| **Docs tip (not product)** | `3c3ead559ef42171832b31c5a7c4776b596b466e` — docs-only commits above product (`d0e1905` → `fd53e2d` → `3c3ead5`) |
| **Base (official restack tip)** | `d791084e716dfcfdaa686374276611ebc0e2a0e6` (`restack(#23): add missing GuardianCore test helper dependency`) |
| **Source verified CWA (reference only)** | `7374820642fad52a6264c86df8632c3a630df592` — **PASS does not transfer** |
| **Vega input** | `docs/VEGA-ISSUE-23-CWA-RECONCILED-20260911.md` on `codex/vega-reverify-23-cwa-reconciled` @ `46e33dac` (**PASS**, confidence 0.88) — consulted; not rubber-stamped |
| **Map / inspection** | `docs/ISSUE-23-CWA-RECONCILIATION-MAP-20260911.md`; inspection report lives on docs tip (`docs/AUTOPILOT-003-DYNAMIC-INSPECTION-RECONCILED-20260911.md`) |

## Mission

Independent architecture gate for reconciling verified construct-without-activate (CWA) semantics onto the newer official restack tip `d791084`, without transferring source PASS and without collapsing construct → operational.

## Method

- Locked review to exact **product** SHA `0a2d135` (not docs tip `3c3ead5`).
- Static review of authoritative surfaces: `project_guardian/core.py` (`__init__` / `_initialize_system` / `activate`), `project_guardian/guardian_singleton.py`, `elysia_sub_guardian.py`, production callers, helper merge, Issue #23 tests/docs/map.
- Compared base `d791084` vs product: base `_initialize_system` still called `ensure_monitoring_started`; product removed construct-time start and added explicit `activate()`.
- Confirmed key product blobs identical to source CWA `7374820` (semantic port landed), while ancestry is `d791084` → `0a2d135` (helper-add tip preserved as parent).
- Ran `compileall` on CWA surfaces + `pytest` Issue #23 suites on this SHA: **20 passed**.
- Did not re-run Vega adversarial suite or full #22 lineage union in this review (Vega/inspection already reported those on `0a2d135`).
- No merge, force-push, product-branch mutation, deploy, or live providers.

## Lineage (architecture-relevant)

```
* 0a2d135  reconcile(#23): port CWA onto restack tip d791084   ← PRODUCT
| * 3c3ead5  docs tip (inspection/map residual notes)         ← NOT PRODUCT
|/
* d791084  official restack tip (helper-add)                  ← BASE
```

Source CWA `7374820` is a **sibling** under `4ff2dc9` with `d791084`. Reconcile is a semantic port onto C, not a transfer of B's prior PASS.

## Checklist findings

### 1. Verified CWA semantics survived on tip — PASS

- `GuardianCore.__init__` sets `_activated=False` / `_running=False`; AST walk confirms `__init__` does **not** call `ensure_monitoring_started`, `activate`, or `start_deferred_initialization`; it does call construct-safe `_initialize_system`.
- `_initialize_system` seeds memory/tasks/trust, keeps `_activated`/`_running` false, verifies wiring, builds runtime-health with `start=False`.
- `activate()` is the operational boundary; sets `_activated`/`_running` and starts authorized surfaces when bg services allow.
- Core product files match source CWA blobs (`core.py`, `guardian_singleton.py`, `elysia_sub_guardian.py`, CWA tests, helpers).
- Independent re-run: `tests/test_guardian_construct_without_activate.py` + `tests/test_guardian_audit_bootstrap.py` → **20 passed**.

### 2. Newer official-restack behavior survived (helper-add from `d791084`) — PASS

- Parent of product commit is exactly `d791084`.
- `tests/guardian_core_test_helpers.py` remains present with the same public API surface introduced on C (`minimal_guardian_core_test_config`, `write_task_contract_file`, `repo_relative_mutation_workspace`, `reset_guardian_core_test_state`, `load_unified_elysia_system_class`, `minimal_unified_elysia_system`).
- Helper content is the CWA-aware merge (ImportError-tolerant reset, ExitStack-style optional OpenClaw patching) — preserves C's **"helpers exist"** intent while keeping B's resilience. Not a blind overwrite that drops the restack dependency.

### 3. No duplicate lifecycle paths that collapse construct → operational — PASS

- Construct/get/`_initialize_system` do not start monitors/loop/UI/probes.
- Operational path is `activate` / `activate_guardian_core` (and `init_guardian_core(mode="operational")` when bg enabled).
- Phase B `start_deferred_initialization` is an explicit heavy-boot step, not construct.
- Audit path (`mode="audit"`) remains descriptor-only.

### 4. Direct constructor / getter remain inert — PASS

- `GuardianCore(...)` and `get_guardian_core(...)` are construct/retrieve only (docstring + body).
- `get_existing_guardian_core` retrieves without create/activate.
- Production scripts (`run_elysia.py`, `start_control_panel.py`, `start_ui_panel.py`) construct then `activate`; dashboard path uses `activate_guardian_core(..., start_ui=True)`.
- `elysia_interface._init_core` remains construct-only (inspect/menu attach) — intentional, not an auto-activate bypass.

### 5. Target helper / test fixes preserved — PASS

- CWA + audit bootstrap tests and `_stubs` present on product.
- Dashboard readiness / tip autonomy companions (`module_activity.py`, `planner_readiness.py`) present and imported by core as required for the ported tip surface.
- Helper merge retains restack helper dependency while keeping CWA adaptations.

### 6. Legacy `ensure_monitoring_started` — residual, not unacceptable construct bypass — PASS with residual

- On base `d791084`, `ensure_monitoring_started` was invoked from `_initialize_system` (construct collapse).
- On product `0a2d135`, construct no longer calls it; only `GuardianCore.activate` imports/calls it among production lifecycle paths reviewed.
- **Residual (non-FAIL):** public `ensure_monitoring_started` can still start monitors without flipping `_activated` if called directly. Unchanged vs source CWA `7374820`; classified **bounded residual**, not a new tip regression and not a constructor collapse.

### 7. Docs distinguish product SHA vs docs/review commits — PASS

| Artifact | Assessment |
|----------|------------|
| Product commit `0a2d135` | Product port only; map at this SHA is Phase-1 map + ported CWA docs (no false "docs tip = product"). |
| Docs tip `3c3ead5` | Explicitly separates **Product SHA `0a2d135`** from inspection/map follow-ups; post-implementation table records product vs docs tip. |
| Inspection report | States product under inspection is `0a2d135`; docs tip does not alter product blobs. |
| Vega report | Verifies product `0a2d135`, notes docs tip movement. |
| This architecture review | Reviews `0a2d135` only; docs tip cited for honesty, not as product evidence. |

**Stale residual:** `docs/boot_memory_map.md` still claims `_initialize_system` calls `ensure_monitoring_started` — false on `0a2d135` (same class of residual as prior restack arch review).

### 8. PR #25 NOT claimed — PASS

- No product claim that PR #25 / claim-boundary landed via this reconcile.
- Docs tip map post-implementation explicitly marks `PR #25 | NOT_INHERITED`.
- This review likewise does **not** inherit or assert #25.

### 9. Unnecessary complexity — PASS

- Lifecycle split (`_initialize_system` vs `activate`) is the required semantic port onto tip, not a second framework.
- Keeping `ensure_monitoring_started` as an activate helper is pragmatic; public residual is follow-up, not reconcile bloat.
- Tip autonomy companion modules are import-surface necessities for the ported `core.py`, not speculative scaffolding.
- Semantic port (not forbidden history cherry-pick of old CWA lineage) matches the reconciliation map.

## Verdict rationale

On product `0a2d135`, construct/get/audit cannot drive operational lifecycle by themselves; activation is explicit. Official restack helper-add intent from `d791084` survives under a CWA-aware helper merge. Source CWA PASS at `7374820` is **not** transferred; product blobs match that semantics on the newer base. Residuals (`ensure_monitoring_started` public API, GuardianLayer hang when enabled, Phase B deferred ops, stale `boot_memory_map.md`, construct-only legacy callers) do **not** collapse the Issue #23 gate.

Therefore: **READY_FOR_INTEGRATION_REVIEW**.

## Residuals for integration / follow-up (non-blocking for this gate)

1. Deprecate or gate public `ensure_monitoring_started` so operational start always goes through `activate()` / `_activated`.
2. Refresh `docs/boot_memory_map.md` (still documents construct-time ensure).
3. GuardianLayer hang when `enable_guardian_layer=True` — bounded residual; harnesses keep it disabled.
4. Legacy construct-only callers (`elysia_interface._init_core`, any script that never activates) remain inspect-only until updated.
5. Do not treat docs tip `3c3ead5` (or source `7374820` PASS) as product evidence for merge decisions.
6. PR #25 remains out of scope / `NOT_INHERITED` unless separately proven.

## Non-goals / not reviewed as pass criteria

- Live provider activation, deployment, or merge to main.
- Mutating `cursor/autopilot-003-issue23-cwa-reconciled` product history.
- Transfer of Vega PASS from source CWA `7374820`.
- Full tip CI matrix beyond Issue #23 CWA suites exercised here.

---

*Report only — no product code changes. Branch: `codex/arch-review-23-cwa-reconciled`.*
