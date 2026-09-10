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
  → init_guardian_core(..., mode="operational")   # only production caller
      → _normalize_config(use_environment=True)
      → get_guardian_core(config)                 # GuardianCore.__init__ (SIDE EFFECTS)
      → ensure_monitoring_started (if bg on)      # monitor / ElysiaLoop / prompt evolver
      → schedule_upstream_routing_live_probes     # conditional Timer

init_guardian_core(..., mode="audit")
  → GuardianBootstrapAudit(normalized config)     # NO core, NO activation

BYPASS (still active; remaining #23 work):
  get_guardian_core / direct GuardianCore(...)
    → __init__ may start UI, monitor, health, planner probe
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

## REMAINING LIMITATIONS (do not close #23 fully)
True construct-without-activate is **not** delivered: `GuardianCore.__init__` /
`get_guardian_core` can still auto-start when used directly. Next bounded task:
move activation out of `__init__` behind an explicit activate API and default
`get_guardian_core` to non-activating construction.

## TESTS
See commit message / CI local run.
