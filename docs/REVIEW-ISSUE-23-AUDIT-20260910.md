# Architecture Review — Issue #23 Audit Bootstrap

**Date:** 2026-09-10  
**Reviewer:** Independent architecture reviewer (did not implement #23; did not author Vega suite)  
**Target SHA:** `79b6c6456eae1d6a400c8b08516a8478d769d25e`  
**Source branch/worktree:** `cursor/guardian-23-audit-bootstrap` @  
`C:\Users\Owner\Project guardian\.worktrees\guardian-23-audit-bootstrap`  
**Review branch:** `codex/review-23-audit` (docs-only, from target SHA)  
**Vega input:** PASS — `codex/vega-reverify-23-audit` / `docs/VEGA-ISSUE-23-AUDIT-REVERIFY-20260910.md`

## VERDICT

**READY_FOR_INTEGRATION_REVIEW**

Issue #23 audit-bootstrap claim is architecturally sound for the bounded scope.  
Issue #23 must **not** be fully closed: `get_guardian_core` / `GuardianCore.__init__` remain activating.

---

## Scope reviewed

Commit `79b6c64` (`fix(guardian): add explicit audit bootstrap mode for Issue #23`):

| Path | Role |
|------|------|
| `elysia_sub_guardian.py` | Authoritative audit/operational boundary |
| `elysia.py` | Production caller → `mode="operational"` |
| `project_guardian/guardian_singleton.py` | Operational singleton conflict + bg gate |
| `tests/test_guardian_audit_bootstrap.py` | Adversarial zero-activation tests |
| `tests/conftest.py` / `pytest.ini` | `no_guardian_core` isolation |
| `docs/ISSUE-23-AUDIT-BOOTSTRAP.md` | Boot map + remaining limitation |

Cross-checked residual activation in `project_guardian/core.py` (`__init__` → resource monitor / UI auto-start / `_initialize_system` → `ensure_monitoring_started` / runtime health).

---

## Findings against review focus

### 1. Is the safe boundary authoritative for the audit path?

**Yes.**

- `init_guardian_core(..., *, mode: Literal["audit","operational"])` is keyword-only; omitting `mode` is a `TypeError`.
- `mode == "audit"` early-returns `GuardianBootstrapAudit(_normalize_config(..., use_environment=False))` **before** any `project_guardian` import.
- `describe_guardian_bootstrap()` is a thin public alias that only calls `init_guardian_core(..., mode="audit")` — not a second policy engine.
- Descriptor fields make non-runtime status explicit: `runtime_constructed=False`, `runtime_wiring_verified=False`, plus `limitation` stating descriptor-only / no live wiring proof.

### 2. Is operational startup still explicit?

**Yes.**

- No default `mode`; production `elysia.py` passes `mode="operational"` at the sole UnifiedElysiaSystem init site.
- Operational path alone imports singleton helpers, may call `ensure_monitoring_started`, and may schedule upstream live probes when flags allow.
- Caller opt-out `enable_background_services=False` still normalizes monitoring/probe/UI auto-start off and skips `ensure_monitoring_started` / probe schedule at the bootstrap layer (tested).

### 3. Were duplicate initialization systems introduced?

**No material duplicate.**

- Added surface is one authoritative function + one preferred inspection name + one frozen descriptor type.
- Pre-existing `RuntimeBootstrap` / orchestrator bootstrap is orthogonal and untouched by this change.
- Singleton conflict rejection when a live instance is stronger than a caller’s disable flags is a safety patch on the **existing** operational path, not a parallel bootstrap.

### 4. Can inspection/audit accidentally become a second runtime?

**No, for the claimed path.**

- Audit never constructs `GuardianCore`, never touches the singleton, never starts monitors/UI/probes/threads/sockets from that path (Vega + unit tests agree).
- Returning a distinct `GuardianBootstrapAudit` type (not a core-shaped object) reduces “looks like a live guardian” confusion.
- Residual risk remains **outside** audit mode: direct `get_guardian_core` / `GuardianCore(...)` still activate — correctly scoped as remaining #23 work, not an audit-path failure.

### 5. Do naming/docs accurately distinguish descriptor vs live runtime verification?

**Yes (authoritative docs).**

- Code + `docs/ISSUE-23-AUDIT-BOOTSTRAP.md` + docstrings state audit is config/architecture preview only.
- Preferred name `describe_guardian_bootstrap` signals inspection intent; `init_guardian_core(mode="audit")` remains the shared authoritative boundary.
- Note (non-blocking): older maps such as `ELYSIA_ARCHITECTURE_MAP.md` still describe pre-mode `init_guardian_core(config)` signatures. They are stale relative to #23’s authoritative doc and should not be treated as the boot contract. Integration can optionally refresh those later; they do not undermine the audit boundary itself.

### 6. Does this reduce rather than increase ambiguity?

**Yes.**

- Forced explicit `mode` removes silent “init means activate” default at the public bootstrap API.
- Clear BYPASS callout for lower-level constructors prevents false closure narrative.
- Descriptor limitation string reduces the hazard of treating audit output as live wiring evidence.

### 7. Remaining limitation recorded; #23 must not fully close?

**Confirmed.**

Documented in:

- `docs/ISSUE-23-AUDIT-BOOTSTRAP.md` — “BYPASS (still active; remaining #23 work)” and “REMAINING LIMITATIONS (do not close #23 fully)”
- `init_guardian_core` docstring — `get_guardian_core` / `GuardianCore.__init__` remain capable of activation

Source confirmation: `GuardianCore.__init__` can start resource monitoring (when not deferred), auto-start UI when `ui_config.auto_start`, and `_initialize_system` calls `ensure_monitoring_started` plus runtime health start when enabled. That is construct-with-activate, not delivered by this SHA.

**Bounded follow-on for full #23 closure (out of scope for this verdict):**

1. Move activation out of `GuardianCore.__init__` behind an explicit activate API.
2. Default `get_guardian_core` to non-activating construction.
3. Keep `init_guardian_core(mode="audit")` / `describe_guardian_bootstrap` as the inspection-only public path.

---

## Vega concordance

Independent Vega PASS at the same SHA is consistent with this architecture review: no material audit-path bypass found; residual limitation correctly classified as remaining work rather than claim failure.

---

## Integration guidance

- Accept `79b6c64` into integration review for the **audit-bootstrap** claim only.
- Keep Issue #23 open (or partially complete) until construct-without-activate lands.
- Do not treat `GuardianBootstrapAudit` as runtime verification evidence in CI/gates.
- Prefer `describe_guardian_bootstrap` in inspection/tooling call sites; require `mode=` at every `init_guardian_core` call.
