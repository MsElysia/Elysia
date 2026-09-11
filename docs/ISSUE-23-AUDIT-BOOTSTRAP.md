# Issue #23 — Audit-safe bootstrap (bounded completion)

## ISSUE
#23 EREBUS-003A-001: canonical runtime verification path has implicit active side effects

## STARTING STATE
- Primary dirty workspace: `elysia-local-reconciliation-20260909-1657` @ `4d9fceb` (untouched)
- Codex unfinished WIP recovered from `C:\Users\Owner\guardian-remote-fix-23`
  - branch `codex/remote-fix-23-bootstrap-mode`
  - preserved locally as `d864f59` (WIP/unverified commit; not discarded)
- Cursor branch: `cursor/guardian-23-audit-bootstrap` from `4d9fceb`

## UNFINISHED CODE RECOVERED
Codex draft introduced:
- required keyword `mode: audit|operational` on `init_guardian_core`
- `GuardianBootstrapAudit` pure descriptor for audit
- operational path gated by `enable_background_services`
- singleton reject when caller disables flags against stronger live instance
- `elysia.py` passes `mode="operational"`

Treated as unfinished/unverified; completed with docs, public `describe_guardian_bootstrap`, and adversarial tests.

## BOOT PATH (authoritative map)

```
elysia.py UnifiedElysiaSystem
  → init_guardian_core(..., mode="operational")
      → _normalize_config(use_environment=True)
      → get_guardian_core(config)              # construct only
      → activate_guardian_core (if bg on)      # monitors / loop / UI / health / probe
      → schedule_upstream_routing_live_probes  # conditional; after activate

init_guardian_core(..., mode="audit")
  → GuardianBootstrapAudit(normalized config)  # NO core, NO activation

get_guardian_core / GuardianCore(...)
  → construct only; call activate() for operational start
```

## IMPLEMENTATION
- Authoritative audit boundary on `init_guardian_core` / `describe_guardian_bootstrap`
- Audit never imports/constructs GuardianCore
- Explicit limitation string: descriptor does not prove live wiring
- Operational opt-out via `enable_background_services=False` preserved
- Tests: `tests/test_guardian_audit_bootstrap.py`

## SAFETY INVARIANTS (audit mode)
- No GuardianCore construction
- No monitoring / ElysiaLoop / prompt-evolution start
- No UI auto-start
- No live-routing probe scheduling
- No env-driven limit overrides
- No socket/subprocess/thread activation from the audit path itself

## REMAINING LIMITATIONS
Construct-without-activate is delivered on this branch (see
`docs/ISSUE-23-CONSTRUCT-WITHOUT-ACTIVATE.md`): `__init__` /
`get_guardian_core` construct only; operational start requires
`activate()` / `activate_guardian_core`. Audit descriptor (this doc / PR #27)
remains authoritative for `mode="audit"`.

Residual: some legacy scripts still call `GuardianCore(...)` without
`activate()` and will no longer get auto-started monitors/UI until updated.

## TESTS
See commit message / CI local run.
