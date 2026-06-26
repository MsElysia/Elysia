# Memory dashboard route test harness

**Status:** Contract and tests only. No Memory dashboard route is implemented by this harness.

## Purpose

This harness defines the safety contract a future local-only Memory dashboard route must satisfy
before route wiring is allowed. It gives future implementation work a small, pure validation layer
and a focused pytest suite that can run without a server.

The route is not implemented yet because serving static Memory pages from the dashboard needs a
clear allowlist, traversal rejection, no-execution guarantees, and human approval before any Flask,
FastAPI, or other route code is touched.

## Contract module

The contract lives at:

```text
project_guardian/local_ingestion/memory_dashboard_route_contract.py
```

It may define only safe constants and pure helpers:

- allowlisted static Memory filenames
- fixed static directory resolution
- safe filename validation
- safe allowlisted path resolution
- forbidden path examples
- future route names
- false safety flags

It must not serve files, register routes, import Flask, import FastAPI, import
`elysia/api/server.py`, import `project_guardian/core.py`, execute commands, write files, call
network/model/API/account access, or write live runtime memory/vector DB.

## Allowed static files

Only these files under `project_guardian/ui/static/` may be served by a future route:

- `index.html`
- `memory_hub.html`
- `memory_import_screen.html`
- `memory_review_search.html`
- `memory_first_run_setup.html`
- `memory_safety.html`
- `memory_diagnostics.html`

## Rejected path examples

The contract rejects unknown files, traversal, encoded traversal, absolute paths, and directory
names. Examples include:

- `dashboard.html`
- `elysia.py`
- `config.json`
- `anything.exe`
- `memory_unknown.html`
- `../config/autonomy.json`
- `..\config\autonomy.json`
- `memory/../../secret.txt`
- `%2e%2e/config/autonomy.json`
- `%252e%252e/config/autonomy.json`
- `memory_hub.html%00.txt`
- `C:\Users\example\secret.txt`
- `/etc/passwd`
- `F:\ElysiaMemory\secret.txt`
- `.`
- `..`
- `/`
- `project_guardian/ui/static/`

## Future route expectations

A future implementation may use the contract like this:

1. Accept only `/memory`, `/memory/`, or `/memory/<allowlisted_page>`.
2. Map `/memory` and `/memory/` to `index.html`.
3. Pass the final filename segment to `is_safe_static_memory_page_name`.
4. Resolve only through `resolve_static_memory_page`.
5. Return 404 or 400 for every rejected value.
6. Serve the resolved HTML file without directory listing.
7. Do not call memory import, review, search, diagnostics, demo workspace, model, embedding,
   account, network, live memory, or vector DB code.

Future route tests should import the contract and assert that the route behavior matches the
contract results. The contract tests live at:

```text
project_guardian/tests/test_memory_dashboard_route_contract.py
```

## Explicit non-implementation statements

- No route wiring was added in this campaign.
- `elysia/api/server.py` was not touched.
- `project_guardian/core.py` was not touched.
- No Flask/FastAPI route was added.
- No browser `fetch`, XHR, WebSocket, or API calls were added.
- No backend command execution was added.
- No watcher, daemon, scheduler, or background monitor was added.
- No autonomy or live execution was enabled.
