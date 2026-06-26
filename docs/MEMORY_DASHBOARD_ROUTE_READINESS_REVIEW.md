# Memory dashboard route readiness review

Review date: 2026-06-26

Starting commit: `021ae28 docs(memory): update route test harness handoff`

Current clean tag used: `memory_dashboard_route_tests_clean_1`

Readiness decision: `GO_WITH_HUMAN_APPROVAL`

This is a review-only document. It does not authorize route implementation.

## Scope

Campaign 3 reviewed whether a future local-only Memory dashboard static route is ready to
propose. It did not add a route, did not add Flask/FastAPI wiring, and did not modify
`elysia/api/server.py` or `project_guardian/core.py`.

## Current static Memory pages

The current static Memory pages live under `project_guardian/ui/static/`:

- `index.html`
- `memory_hub.html`
- `memory_import_screen.html`
- `memory_review_search.html`
- `memory_first_run_setup.html`
- `memory_safety.html`
- `memory_diagnostics.html`

These pages are local static prototypes. They can still be opened without a server:

```powershell
start project_guardian/ui/static/index.html
```

## Current route contract

The route contract exists at:

```text
project_guardian/local_ingestion/memory_dashboard_route_contract.py
```

Current contract status:

- Allowlist exists for exactly the seven static Memory HTML files.
- Traversal rejection exists.
- Encoded traversal rejection exists.
- Double-encoded traversal rejection exists.
- Absolute path rejection exists.
- Unknown filename rejection exists.
- Directory-only path rejection exists.
- Safe resolution returns only files under `project_guardian/ui/static/`.
- No Flask import.
- No FastAPI import.
- No `elysia.api.server` import.
- No `project_guardian.core` import.
- Safety flags remain false: `model_called`, `embeddings_used`, `live_memory_written`, `autonomy_enabled`.

Focused tests:

```powershell
python -m pytest project_guardian/tests/test_memory_dashboard_route_contract.py -q
```

## Dashboard/UI discovery

Inspected files and directories:

- `project_guardian/ui/templates/`
- `project_guardian/ui/static/`
- `project_guardian/ui/app.py`
- `project_guardian/ui_control_panel.py`
- `Elysia_Control_Panel_Standalone.html`
- `elysia/api/server.py`
- `project_guardian/local_ingestion/memory_dashboard_route_contract.py`
- `project_guardian/tests/test_memory_dashboard_route_contract.py`
- route design, risk review, acceptance, and harness docs

Discovery summary:

| Surface | Current role | Route readiness notes |
| ------- | ------------ | --------------------- |
| `project_guardian/ui/static/` | Contains seven static Memory prototype HTML files. | Good route source directory if future implementation uses the contract allowlist. |
| `project_guardian/ui/templates/` | FastAPI/Jinja dashboard templates such as `dashboard.html`, review pages, task pages, mutation pages, history pages. | No Memory static route found. |
| `project_guardian/ui/app.py` | FastAPI local control panel with existing page and API routes plus loopback middleware. | Best future implementation candidate if explicitly approved. It already owns local dashboard HTML routing. |
| `project_guardian/ui_control_panel.py` | Large Flask/rendered control panel with many live `/api/*` endpoints and memory actions. | Not recommended for first static route implementation because it mixes live controls, API calls, and memory actions. |
| `Elysia_Control_Panel_Standalone.html` | Standalone HTML dashboard snapshot with many `fetch(API_BASE + ...)` calls. | Not recommended for static Memory route wiring. |
| `elysia/api/server.py` | Flask API server with `/api/*` routes including memory ranking and live-action governance endpoints. | Do not use for this route unless separately approved; mixing static prototypes into the API server is unnecessary risk. |

Existing static serving appears limited: no current allowlisted Memory route was found in the
dashboard code. The static pages are currently opened directly from disk.

Route implementation would likely need to touch only:

- `project_guardian/ui/app.py`
- focused future route tests, for example `project_guardian/tests/test_memory_dashboard_static_route.py`
- docs/handoff files

Route implementation must not touch:

- `elysia/api/server.py`
- `project_guardian/core.py`
- model routing code
- account access code
- live memory/vector code
- broad dashboard rewrites

## Safety status

- `config/autonomy.json` remains `enabled=false`.
- No route is currently implemented by Campaign 3.
- No server/API route was added.
- No Flask/FastAPI route wiring was added.
- No browser `fetch`, XHR, WebSocket, or API calls were added.
- No backend command execution was added.
- No account/API/network/model/embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No watchers, daemons, schedulers, or background monitors were added.

## GO / NO-GO decision

Decision: `GO_WITH_HUMAN_APPROVAL`

Rationale:

- The static Memory pages exist and are already covered by static safety tests.
- The route contract exists and rejects unknown filenames, traversal, encoded traversal, double
  encoded traversal, absolute paths, and directory-only paths.
- A narrow future route can likely be implemented in `project_guardian/ui/app.py` without touching
  `elysia/api/server.py` or `project_guardian/core.py`.
- Existing direct-open static workflow remains safer and should stay available.
- Human approval is still required because any route implementation touches dashboard route code.

## Recommendation

Prepare a future narrow implementation prompt only after explicit human approval. The prompt should
authorize exactly one route file, ideally `project_guardian/ui/app.py`, plus focused route tests and
docs. If human approval is not granted, continue with safer non-route work such as static docs,
operator checklists, or fixture galleries.

## Required human approval

Route implementation must not begin without explicit human approval naming the route file and exact
purpose. Approval must explicitly allow touching `project_guardian/ui/app.py` or a different
approved route file.

## Exact future implementation boundary

Allowed future files, only after approval:

- `project_guardian/ui/app.py`
- `project_guardian/tests/test_memory_dashboard_static_route.py`
- `docs/MEMORY_DASHBOARD_ROUTE_IMPLEMENTATION_GATES.md`
- `docs/CODEX_LONG_TERM_HANDOFF.md`

Files that must remain untouched unless separately approved:

- `elysia/api/server.py`
- `project_guardian/core.py`
- `project_guardian/ui_control_panel.py`
- `Elysia_Control_Panel_Standalone.html`
- model routing, account access, live memory, and vector DB modules

Exact tests required for a future route implementation:

```powershell
python -m pytest project_guardian/tests/test_memory_dashboard_route_contract.py -q
python -m pytest project_guardian/tests/test_memory_dashboard_static_route.py -q
python -m pytest project_guardian/tests/test_memory_static_pages_safety.py -q
python -m pytest project_guardian/tests/test_memory_hub_navigation.py -q
python -m pytest project_guardian/tests/test_memory_doctor.py -q
python -m pytest project_guardian/tests/test_memory_demo_workspace.py -q
python -m pytest project_guardian/tests/test_memory_health_smoke.py -q
python scripts/run_safe_stack_smoke_tests.py
python scripts/run_elysia_dry_run_report.py --mode real-planning
```

## Rollback points

- Prior clean tag: `memory_dashboard_route_tests_clean_1`
- New Campaign 3 tag after this review: `memory_route_readiness_clean_1`
