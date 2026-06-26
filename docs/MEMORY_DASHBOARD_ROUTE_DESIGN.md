# Memory dashboard route design

**Status:** Design and test planning only — **no route is implemented in this milestone.**  
**Branch context:** `codex/limited-live-activation-wrapper`  
**Checkpoint tag:** `memory_diagnostics_demo_clean_1`

This document plans how Elysia could later expose the existing static Memory Hub pages from
inside the local dashboard **without** wiring import, review, search, diagnostics, or demo
execution from the browser.

---

## Discovery summary (current UI/dashboard structure)

| Location | Role today | Memory static pages? |
| -------- | ---------- | -------------------- |
| `project_guardian/ui/static/` | Local-only static HTML prototypes (relative links, no scripts) | **Yes** — seven Memory pages |
| `project_guardian/ui/templates/` | Jinja templates for the FastAPI control panel (`dashboard.html`, reviews, mutations, etc.) | No Memory static mount |
| `project_guardian/ui/app.py` | FastAPI control panel app; template routes; **no** static Memory file server today | No |
| `project_guardian/ui_control_panel.py` | Embedded Flask/SocketIO dashboard with live `/api/memory/*` JSON routes (search, ranking, health) | Separate live API tab — **not** the static Memory Hub |
| `elysia/api/server.py` | Elysia API server (`/api/status`, `/api/chat`, `/api/memory/ranking/summary`, proposals, etc.) | **No** static Memory HTML routes |
| `Elysia_Control_Panel_Standalone.html` | Standalone HTML snapshot at repo root | Not wired to Memory static pages |

**Operator open today (no server):**

```powershell
start project_guardian/ui/static/index.html
```

Static pages use relative links only (`memory_hub.html`, etc.). They do not call `fetch`,
XHR, WebSocket, external assets, or backend API routes.

---

## Current static Memory pages

All files live under `project_guardian/ui/static/`:

| File | Purpose |
| ---- | ------- |
| `index.html` | Static entry card linking to Memory Hub and sub-pages |
| `memory_hub.html` | Memory Hub shell and navigation |
| `memory_import_screen.html` | Import UI contract / static prototype |
| `memory_review_search.html` | Review and search UI contract / static prototype |
| `memory_first_run_setup.html` | First-run local setup guide |
| `memory_safety.html` | What Elysia does and does not do (local-only) |
| `memory_diagnostics.html` | Diagnostics and demo workflow documentation (static) |

These pages are **prototypes**. They describe workflows and link to other static pages.
They do not execute import, review, search, diagnostics, or demo workspace creation.

---

## Current diagnostics and demo tooling (CLI only)

| Script | Role |
| ------ | ---- |
| `scripts/memory_doctor.py` | Read-only workspace inspection (`--dest-dir`, `--json`) |
| `scripts/create_memory_demo_workspace.py` | Fake demo workspace; dry-run by default; `--apply` required to write |
| `scripts/run_memory_health_smoke.py` | Temp-workspace health smoke; no user files by default |

These tools are **operator-run from the shell**. They must not be invoked from browser
JavaScript or from a future dashboard route handler.

---

## Desired future route shape

A future local-only dashboard route would:

- Serve **static HTML files only** from the allowlist below
- Bind to **localhost** (or an explicitly configured local-only host)
- **Not** execute import, review, search, diagnostics, or demo workspace creation
- **Not** accept arbitrary filesystem paths from the user
- **Not** call models, embeddings, APIs, internet, or live accounts
- **Not** write live runtime memory or vector DB
- **Not** enable autonomy or live execution
- **Not** add watchers, daemons, schedulers, or folder monitors

The route is a **file server for known HTML prototypes**, not a Memory pipeline executor.

---

## Example route options (for later implementation review)

| Option | Example URL | Notes |
| ------ | ----------- | ----- |
| A | `/memory` → `index.html` | Friendly entry; needs explicit default mapping |
| B | `/memory/` → directory index | Same as A with trailing slash convention |
| C | `/memory/<allowlisted_page>` | e.g. `/memory/memory_hub.html` — **recommended shape** |
| D | `/static/memory_hub.html` | Generic static mount — **riskier** unless strictly scoped |
| E | Reuse existing static mount in `ui/app.py` | Only if mount is restricted to allowlist (no directory browse) |

**Do not** expose:

- Raw directory listing under `project_guardian/ui/static/`
- User-supplied path segments outside the allowlist
- Files outside `project_guardian/ui/static/`

---

## Recommended safest option

1. **Prefer the smallest allowlisted static route** added to the **local FastAPI control panel**
   (`project_guardian/ui/app.py`) **only after explicit approval** — not in this design step.
2. Route shape: **`GET /memory`** redirects or serves `index.html`; **`GET /memory/<page>`**
   serves only allowlisted filenames from `project_guardian/ui/static/`.
3. Implementation rules:
   - Resolve `<page>` against a **fixed allowlist** (see below)
   - Reject unknown filenames with **404**
   - Reject `..`, absolute paths, and encoded traversal (`%2e%2e`, `%2f`, backslashes)
   - Use `Path.resolve()` and verify the resolved file is **under** the static directory
   - Serve with `text/html` only for allowlisted `.html` files
   - **Never** execute shell commands, subprocesses, or Python memory pipeline code from the route
   - **Never** wire route handlers to `memory_doctor.py`, `create_memory_demo_workspace.py`, or
     `run_memory_health_smoke.py`
4. **Do not** add this route to `elysia/api/server.py` unless a separate architecture review
   explicitly approves it. The Elysia API server already carries live `/api/memory/*` JSON
   endpoints; mixing static prototypes there increases confusion and risk.
5. Keep static page **prototype labels** visible so operators do not confuse static HTML with
   live dashboard Memory tab API behavior in `ui_control_panel.py`.

---

## File allowlist (future route may serve only these)

Under `project_guardian/ui/static/`:

- `index.html`
- `memory_hub.html`
- `memory_import_screen.html`
- `memory_review_search.html`
- `memory_first_run_setup.html`
- `memory_safety.html`
- `memory_diagnostics.html`

No other extensions, no nested paths, no query-string path overrides.

---

## Explicit non-goals

The future route must **not**:

- Run backend import from the dashboard
- Execute review actions (approve/reject/edit) from the dashboard
- Execute approved memory search from the dashboard
- Run diagnostics (`memory_doctor.py`) from the browser
- Create demo workspaces (`create_memory_demo_workspace.py`) from the browser
- Connect Gmail, Outlook, ChatGPT, IMAP, SMTP, or any live account
- Call models, embeddings, or external APIs
- Write vector DB or live runtime memory
- Enable autonomy or live execution
- Start watchers, daemons, schedulers, or automatic folder monitors
- Implement `.mbox`, PDF, DOCX, image, or broad filesystem import

---

## Related documentation

- [MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md](MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md)
- [MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md](MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md)
- [MEMORY_DIAGNOSTICS_AND_DEMO.md](MEMORY_DIAGNOSTICS_AND_DEMO.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)

---

## Implementation gate (this step)

**This document does not authorize route implementation.**

Before any route wiring:

1. Complete risk review and acceptance test plan (companion docs)
2. Obtain explicit approval to touch route code
3. Implement allowlisted route with focused tests
4. Re-run static safety tests, safe-stack smoke, and dry-run report with autonomy disabled

**Do not modify `elysia/api/server.py` or `project_guardian/core.py` as part of the first
Memory static route milestone unless explicitly approved.**
