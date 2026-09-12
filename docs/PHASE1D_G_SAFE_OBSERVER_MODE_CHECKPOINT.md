# Phase 1d-G — Safe Observer Mode checkpoint

**Date:** 2026-05-30  
**Milestone:** Phase 1d-G Safe Observer Mode checkpoint  
**Current verified HEAD:** `f270c48` — `docs(autonomy): record real-planning dry-run command baseline`

This checkpoint freezes the verified "Safe Observer Mode" state. It does **not** authorize live execution, real autonomy, proposal implementation, WebScout/browser autonomy, mutation execution, or dirty hunk staging.

---

## Safe commands

```
python scripts/run_elysia_dry_run_report.py
python scripts/run_elysia_dry_run_report.py --json
python scripts/run_elysia_dry_run_report.py --mode real-planning
python scripts/run_elysia_dry_run_report.py --mode real-planning --json
```

---

## What Safe Observer Mode CAN do

- run bounded dry-run report batches
- run deterministic stub dry-run mode
- run explicit real-planning dry-run mode
- produce `decision_trace`
- produce `decision_trace_summary`
- produce `dry_run_report`
- print a text safety report
- print a JSON safety report
- prove no execution occurred

## What Safe Observer Mode CANNOT do

- no live execution
- no real autonomy mode
- no tools/capabilities execution
- no mutation execution
- no proposal implementation
- no WebScout/browser activity
- no server/API/UI approval routes
- no default file/audit writing
- no `config/autonomy.json` enablement

---

## Verified gates

| Gate | Result |
|------|--------|
| Targeted dry-run contract tests | **64 passed, 3 warnings** |
| Safe-stack smoke | **450 passed, 3 warnings** |
| Full collection | clean (Cursor: 441 collected; Codex: 400 collected) |
| Command matrix | passed (stub text/json, real-planning text/json) |
| Audit line count | unchanged across default runs |
| `config/autonomy.json` | `enabled=false` |

Command matrix detail: stub text → exit 0 SAFE; stub json → exit 0 parseable `safe=true`; real-planning text → exit 0 SAFE; real-planning json → exit 0 parseable `safe=true`. Real-planning invariants: `completed_cycles=3`, `any_executed=false`, `execution_call_count=0`, `legacy_fallback_reached=false`.

---

## Current risk boundaries

- `project_guardian/core.py` remains dirty/unstaged.
- `elysia/api/server.py` remains dirty/unstaged.
- Do **not** use `git add -A`.
- Do **not** stage dirty hunks casually.
- Full runtime pytest still has known failures/errors outside this gate (see `docs/PHASE1C2_COLLECTION_REPAIR_BASELINE.md`).

---

## Safe run instruction

To safely run observer mode:

```
python scripts/run_elysia_dry_run_report.py --mode real-planning
```

For machine-readable output:

```
python scripts/run_elysia_dry_run_report.py --mode real-planning --json
```

These commands still execute nothing.

---

## Explicit warning

This checkpoint **does not authorize** live execution, real autonomy, proposal implementation, WebScout/browser autonomy, mutation execution, or dirty hunk staging.

---

## Recommended next branches

- **Branch A** — dirty `core.py`/`server.py` cleanup
- **Branch B** — Safe Observer Mode user documentation
- **Branch C** — full runtime pytest failure classification
- **Branch D** — design Phase 2 live-action allowlist only (design, no implementation)

---

## Final verdict

**PASS** for the Safe Observer Mode checkpoint.
