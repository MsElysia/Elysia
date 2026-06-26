# Memory dashboard route implementation gates

This document defines the mandatory gates before any local-only Memory dashboard route can be
implemented. It is not an implementation prompt.

## Prerequisites

All prerequisites must be true before route implementation starts:

- Design doc exists: `docs/MEMORY_DASHBOARD_ROUTE_DESIGN.md`.
- Risk review exists: `docs/MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md`.
- Route contract exists: `project_guardian/local_ingestion/memory_dashboard_route_contract.py`.
- Route contract tests pass:
  `python -m pytest project_guardian/tests/test_memory_dashboard_route_contract.py -q`.
- Readiness review exists: `docs/MEMORY_DASHBOARD_ROUTE_READINESS_REVIEW.md`.
- Readiness review says `GO_WITH_HUMAN_APPROVAL`.
- A human explicitly approves implementation and names the exact route file.
- `config/autonomy.json` remains `enabled=false`.

## Allowed future implementation files

Only after explicit approval, a route implementation may touch:

- the narrow route file named by the readiness review, currently recommended as
  `project_guardian/ui/app.py`
- `project_guardian/local_ingestion/memory_dashboard_route_contract.py`, only if a contract bug is
  found and fixed with tests
- focused route tests, for example `project_guardian/tests/test_memory_dashboard_static_route.py`
- docs and handoff files

## Forbidden files and areas unless separately approved

- `project_guardian/core.py`
- `elysia/api/server.py`
- broad server refactors
- `project_guardian/ui_control_panel.py`
- `Elysia_Control_Panel_Standalone.html`
- model routing code
- account access code
- live runtime memory code
- vector DB code
- autonomy or live execution code
- watchers, daemons, schedulers, background monitors, or automatic loops

## Required route behavior

A future route must:

- serve only allowlisted static Memory pages
- map `/memory` and `/memory/` to `index.html`
- reject unknown filenames
- reject traversal
- reject backslash traversal
- reject encoded traversal
- reject double-encoded traversal
- reject absolute Windows paths
- reject absolute POSIX paths
- reject drive-root style paths
- reject directory-only path values
- use the route contract for filename validation and safe resolution
- return 404 or 400 for rejected values
- avoid directory listings
- avoid backend command execution
- avoid file writes
- avoid diagnostics/demo command execution from the browser
- avoid import, review, search, and context-bundle execution from the browser
- avoid account/model/API/network access
- avoid live runtime memory or vector DB writes
- keep autonomy disabled

## Required tests before implementation commit

Run and pass:

```powershell
python -m pytest project_guardian/tests/test_memory_dashboard_route_contract.py -q
python -m pytest project_guardian/tests/test_memory_dashboard_static_route.py -q
python -m pytest project_guardian/tests/test_memory_dashboard_route_readiness_docs.py -q
python -m pytest project_guardian/tests/test_memory_dashboard_route_design_docs.py -q
python -m pytest project_guardian/tests/test_memory_static_pages_safety.py -q
python -m pytest project_guardian/tests/test_memory_hub_navigation.py -q
python -m pytest project_guardian/tests/test_memory_doctor.py -q
python -m pytest project_guardian/tests/test_memory_demo_workspace.py -q
python -m pytest project_guardian/tests/test_memory_health_smoke.py -q
python scripts/run_safe_stack_smoke_tests.py
python scripts/run_elysia_dry_run_report.py --mode real-planning
```

The dry-run report must be `SAFE`, `all_dry_run=True`, and `any_executed=False`.

## Explicit stop rules

Stop immediately if:

- route implementation requires a broad server refactor
- `project_guardian/core.py` would be touched
- `elysia/api/server.py` would be touched without separate explicit approval
- autonomy or live execution becomes involved
- route behavior needs backend action execution
- route behavior needs diagnostics/demo command execution from browser UI
- route behavior needs account/model/API/network access
- route behavior needs live runtime memory or vector DB writes
- route behavior needs watchers, daemons, schedulers, or background monitors
- static Memory pages would need browser `fetch`, XHR, WebSocket, or API calls

## Non-route fallback

If any gate fails, continue with safer non-route work such as docs, static UI references, operator
checklists, fixture galleries, or release-candidate notes.
