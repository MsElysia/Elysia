# Memory dashboard route acceptance tests

**Status:** Test plan for a **future** route implementation — **no route exists yet.**

All tests below must pass before a Memory dashboard static route is accepted for merge.

---

## 1. Allowlist and serving

| # | Test | Expected |
| - | ---- | -------- |
| 1.1 | `GET /memory` or `/memory/` | Serves `index.html` from allowlist |
| 1.2 | `GET /memory/memory_hub.html` | 200, HTML body matches static file |
| 1.3 | Each allowlisted page (`index.html`, `memory_hub.html`, `memory_import_screen.html`, `memory_review_search.html`, `memory_first_run_setup.html`, `memory_safety.html`, `memory_diagnostics.html`) | 200 when requested by exact allowlisted name |
| 1.4 | `GET /memory/unknown.html` | 404 |
| 1.5 | `GET /memory/not_in_allowlist.txt` | 404 |
| 1.6 | Route serves only allowlisted Memory static pages | No other files under `ui/static/` exposed |

---

## 2. Path traversal rejection

| # | Test | Expected |
| - | ---- | -------- |
| 2.1 | `GET /memory/../app.py` | 404 or 400 — no file served |
| 2.2 | `GET /memory/..%2f..%2fconfig/autonomy.json` | 404 or 400 |
| 2.3 | `GET /memory/%2e%2e/index.html` | 404 or 400 |
| 2.4 | `GET /memory/..%5c..%5cREADME.md` | 404 or 400 |
| 2.5 | Absolute path in route segment | Rejected |
| 2.6 | Backslash in route segment | Rejected |

---

## 3. Encoded traversal rejection

| # | Test | Expected |
| - | ---- | -------- |
| 3.1 | `%2e%2e` in path | Rejected before filesystem access |
| 3.2 | `%2f` embedded in filename segment | Rejected |
| 3.3 | Double-encoded traversal attempts | Rejected |

---

## 4. No execution or side effects

| # | Test | Expected |
| - | ---- | -------- |
| 4.1 | Route handler | Does not execute scripts or subprocesses |
| 4.2 | Route handler | Does not call backend memory import commands |
| 4.3 | Route handler | Does not create demo workspaces |
| 4.4 | Route handler | Does not run diagnostics (`memory_doctor.py`) |
| 4.5 | Route handler | Does not write files to disk |
| 4.6 | Route handler | Does not call model/API/network/account access |
| 4.7 | Route handler | Does not write runtime memory/vector DB |
| 4.8 | Served HTML | Contains no `fetch(`, `XMLHttpRequest`, or `WebSocket` (static safety suite) |
| 4.9 | Served HTML | No external `http://` or `https://` asset URLs |

---

## 5. Configuration and stack safety

| # | Test | Expected |
| - | ---- | -------- |
| 5.1 | `config/autonomy.json` | `"enabled": false` before and after route tests |
| 5.2 | Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` — pytest PASSED |
| 5.3 | Dry-run report | `python scripts/run_elysia_dry_run_report.py --mode real-planning` — verdict **SAFE** |
| 5.4 | Memory health smoke | `python scripts/run_memory_health_smoke.py --json` — `verdict=PASS`, safety flags false |
| 5.5 | Local pipeline smokes | transcription, chatgpt_export, email_export — all PASS |

---

## 6. Regression suites (must remain green)

```powershell
python -m pytest project_guardian/tests/test_memory_static_pages_safety.py -q
python -m pytest project_guardian/tests/test_memory_hub_navigation.py -q
python -m pytest project_guardian/tests/test_memory_hub_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
python -m pytest project_guardian/tests/test_memory_doctor.py -q
python -m pytest project_guardian/tests/test_memory_demo_workspace.py -q
python -m pytest project_guardian/tests/test_memory_health_smoke.py -q
```

Future route-specific pytest module (to be added at implementation time):

```text
project_guardian/tests/test_memory_dashboard_static_route.py
```

---

## 7. Explicit non-goals (acceptance failures)

Implementation **fails** acceptance if any of the following appear:

- Browser `fetch`, XHR, or WebSocket added to static Memory pages for pipeline execution
- HTTP endpoints that wrap diagnostics or demo workspace scripts
- Directory listing or arbitrary path static mount
- Changes to `config/autonomy.json` enabling autonomy
- Live memory or vector DB writes from route handlers
- Modifications to `elysia/api/server.py` without separate approved review
- Watchers, daemons, or background folder monitors

---

## Related documentation

- [MEMORY_DASHBOARD_ROUTE_DESIGN.md](MEMORY_DASHBOARD_ROUTE_DESIGN.md)
- [MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md](MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md)

**This document does not instruct route implementation in the current design-only milestone.**
