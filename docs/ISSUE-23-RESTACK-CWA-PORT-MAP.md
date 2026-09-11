# Issue #23 Restack — Semantic Port Map

**Date:** 2026-09-11  
**Source verified product:** `776647f80f7d08810f1655c7a2b02fe597c385af`  
**Source parent (audit):** `79b6c6456eae1d6a400c8b08516a8478d769d25e`  
**Target base tip:** `4ff2dc92dd7d9bc393225bce35de9239a9cad6a5` (`autopilot-003-issue23-restack`)  
**Working branch:** `cursor/autopilot-003-issue23-restack-cwa`

## Classification

| Change | Class |
|--------|-------|
| Audit descriptor / `mode=` on `init_guardian_core` | ALREADY_PRESENT (partial) |
| `no_guardian_core` / singleton test isolation | ALREADY_PRESENT |
| Singleton conflict checks / `get_existing` / bg guard on ensure | PORT_REQUIRED (#27 gap) |
| `elysia.py mode="operational"` | PORT_REQUIRED (#27 gap) |
| `tests/test_guardian_audit_bootstrap.py` | PORT_REQUIRED (#27 gap) |
| `GuardianCore` construct-only + `activate()` | REWRITE_FOR_TARGET (core.py) |
| `activate_guardian_core` | PORT_REQUIRED |
| Operational path uses activate | PORT_REQUIRED |
| Production callers (UI/run_elysia/interface) | PORT_REQUIRED |
| `tests/test_guardian_construct_without_activate.py` + stubs | PORT_REQUIRED |
| CWA docs | DOC_ONLY / PORT_REQUIRED |
| Parent OpenClaw helpers in elysia_interface | OBSOLETE_ON_TARGET |
| Cherry-pick / merge of `776647f` history | FORBIDDEN |

## Rule
Port **semantics** onto PR #26 lineage tip. Do not cherry-pick wholesale. Preserve tip autonomy/#22 surfaces.
