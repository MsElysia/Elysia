# Memory dashboard route risk review

**Status:** Pre-implementation risk review — **no route wired in this milestone.**

This review covers safety risks, mitigations, and required gates before a future local-only
dashboard route serves static Memory Hub HTML pages.

---

## Route safety risks

| Risk | Description |
| ---- | ----------- |
| **Path traversal** | Attacker or malformed URL (`../`, `%2e%2e`, encoded slashes) escapes `project_guardian/ui/static/` and reads arbitrary repo or host files. |
| **Arbitrary file serving** | Generic static mount or user-provided filename serves non-allowlisted files (`.env`, configs, Python source, logs). |
| **Command execution from browser** | Route handler or page JavaScript triggers shell commands, subprocess imports, or pipeline apply from a click. |
| **Unexpected backend calls** | Static pages or new dashboard JS call `/api/memory/*`, import endpoints, or Elysia API routes not intended for prototypes. |
| **Exposing local paths** | Error messages or directory listings reveal absolute filesystem paths, home directory, or workspace roots. |
| **Prototype vs live UI confusion** | Operators assume static Memory pages perform live import/review/search like the Flask Memory tab in `ui_control_panel.py`. |
| **Accidental account/API integration** | Future wiring connects ChatGPT, Gmail, Outlook, or cloud APIs from dashboard Memory navigation. |
| **Accidental autonomy enabling** | Route or companion code reads/writes `config/autonomy.json` or triggers autonomy execute-cycle endpoints. |
| **Accidental live memory/vector writes** | Route invokes import apply, review approve, memory store write, or vector index updates. |
| **Exposing demo workspace paths** | Diagnostics UI displays or accepts real user `--dest-dir` paths from the browser. |
| **Diagnostics look like live account access** | Static diagnostics page or routed copy implies Elysia reads email/ChatGPT accounts without manual export. |

---

## Mitigations

| Mitigation | Detail |
| ---------- | ------ |
| **Allowlisted static files only** | Serve exactly seven HTML filenames from `project_guardian/ui/static/`. Unknown name → 404. |
| **No user-provided file path routing** | Route parameter must match allowlist entry; never pass query/body paths to filesystem open. |
| **Traversal normalization** | Reject `..`, absolute paths, backslashes, and encoded traversal (`%2e%2e`, `%2f`, `%5c`) before open. |
| **Resolve-and-verify** | `resolved = (static_dir / name).resolve()`; assert `resolved.relative_to(static_dir.resolve())`. |
| **No backend command execution** | Route handler returns file bytes only; no subprocess, no import of `memory_import.py` or review CLIs. |
| **No fetch/XHR/WebSocket in static pages** | Keep existing static safety tests; block new JavaScript network calls in Memory HTML. |
| **No server-side memory writes** | Route must not call unified import apply, review approve, store write, or context bundle builders. |
| **No diagnostics/demo execution from browser** | Do not expose HTTP endpoints that wrap `memory_doctor.py`, `create_memory_demo_workspace.py`, or `run_memory_health_smoke.py`. |
| **Clear prototype labels** | Pages and dashboard link text state "static prototype", "local files only", "no account connection". |
| **Local-only binding** | Serve on localhost by default; document that exposing the route broadly is out of scope. |
| **Tests for safety boundaries** | Acceptance tests (companion doc) must pass before merge; include traversal and allowlist cases. |
| **Separate from Elysia API server** | Prefer `ui/app.py` for static Memory route; avoid adding static HTML to `elysia/api/server.py` without separate review. |
| **Autonomy remains disabled** | Verify `config/autonomy.json` `"enabled": false` before and after route work; block demo tools if enabled. |
| **No live memory/vector writes** | Route and pages document that pipeline writes happen only via operator CLI under explicit `--dest-dir`. |
| **No account/API/model/embedding calls** | Route implementation must not import LLM routers, API key managers, or embedding backends. |

---

## Required future implementation gates

Before merging any route implementation:

1. **Explicit approval** to touch route code (`project_guardian/ui/app.py` or approved alternative).
2. **Explicit route design review** — sign-off on allowlist, URL shape, and local-only binding.
3. **Focused route tests** — allowlist, traversal, encoded traversal, unknown file rejection.
4. **Static safety tests** — `test_memory_static_pages_safety.py` and navigation tests still pass.
5. **Dry-run report SAFE** — `python scripts/run_elysia_dry_run_report.py --mode real-planning`.
6. **Autonomy disabled** — `config/autonomy.json` unchanged with `"enabled": false`.
7. **No risky files** — `project_guardian/core.py` and `elysia/api/server.py` untouched unless
   separately approved; if `server.py` is ever approved, require dedicated security review.
8. **No watchers or background monitors** introduced alongside the route.
9. **No browser execution** of diagnostics, demo workspace creation, import, review, or search.

---

## Residual risk acceptance

A local-only allowlisted static route is **low risk** if it serves HTML only and passes the
acceptance tests. Residual risks are **operator confusion** (prototype vs live API tab) and
**future scope creep** (adding fetch/API wiring). Mitigate with documentation, labels, and
strict review gates — not by expanding route behavior in the first implementation PR.

---

## Related documentation

- [MEMORY_DASHBOARD_ROUTE_DESIGN.md](MEMORY_DASHBOARD_ROUTE_DESIGN.md)
- [MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md](MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md)

**This review does not authorize modifying `elysia/api/server.py` in the design step.**
