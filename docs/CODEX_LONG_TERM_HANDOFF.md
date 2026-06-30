# Codex long-term Elysia handoff

This document tracks autonomous Codex campaigns that are allowed to improve Elysia while keeping
Elysia autonomy and live execution disabled.

## Campaign 1 - Memory dashboard route design

### Campaign summary

- Campaign name: Memory dashboard route design
- Starting clean tag: `memory_diagnostics_demo_clean_1`
- Starting HEAD: `93ec530 docs(memory): update diagnostics demo handoff`
- Starting branch: `codex/limited-live-activation-wrapper`
- Ending code HEAD before this handoff document: `1ca16dc docs(memory): add dashboard route design review`
- Ending campaign HEAD after this handoff document: see `git log -1`
- Campaign tag: `memory_dashboard_route_design_clean_1`
- Cycles attempted: 2
- Cycles completed: 2
- Codex commits made before tag: 2
- Total commits in campaign ancestry after starting tag: 3
- Note: `2edb8ec docs(ui): design local memory dashboard route` was an already-pushed
  Cursor-authored docs-only commit that appeared in ancestry before final tagging. It was
  inspected and is route-design-adjacent; it does not touch protected files or implement a route.

### Commits

| Commit | Purpose |
| ------ | ------- |
| `1ca16dc docs(memory): add dashboard route design review` | Added the design doc, risk review, acceptance test plan, and static doc validation tests for a future local-only Memory dashboard route. |
| `2edb8ec docs(ui): design local memory dashboard route` | Cursor-authored docs-only update linking the route design milestone from existing memory checkpoint/roadmap docs. |
| handoff commit | Added this long-term handoff entry. |

### Files changed

- `docs/CODEX_LONG_TERM_HANDOFF.md`
- `docs/LOCAL_MEMORY_PIPELINE_CHECKPOINT.md`
- `docs/MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md`
- `docs/MEMORY_DASHBOARD_ROUTE_DESIGN.md`
- `docs/MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md`
- `docs/MEMORY_IMPORT_UI_ROADMAP.md`
- `project_guardian/tests/test_memory_dashboard_route_design_docs.py`

### Completed work

- Documented the current static Memory UI pages and local-only CLI tooling.
- Designed a future route shape for serving static Memory HTML through an allowlisted local route.
- Documented that no route is implemented or authorized by this campaign.
- Documented path traversal, arbitrary file serving, command execution, account/API/model access, live memory writes, and operator-confusion risks.
- Defined future acceptance tests for allowlisted static files, traversal rejection, encoded traversal rejection, no backend command execution, no file writes, and no account/model/API/network access.
- Added static tests that validate the design, risk review, and acceptance-test docs.

### Skipped work

- No server route was implemented.
- No browser JavaScript calls were added.
- No route test harness was added in this campaign; that belongs to Campaign 2.
- No model, embedding, account, API, network, live runtime memory, or vector DB integration was added.
- No `.mbox`, PDF, DOCX, OCR, image, phone sync, or live account import was implemented.

### Tests run

| Check | Result |
| ----- | ------ |
| Focused route design docs test | `31 passed, 3 warnings in 0.26s` |
| Memory and route-design pytest baseline | `175 passed, 3 warnings in 45.52s` |
| Memory health smoke | `verdict=PASS; doctor_verdict=HAS_CONTEXT_BUNDLE; candidates_created=3; approvals_created=3; search_result_count=3; context_bundle_created=true; safety flags false` |
| Transcription smoke | `verdict=PASS; candidates_created=2; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| ChatGPT smoke | `verdict=PASS; candidates_created=1; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| Email smoke | `verdict=PASS; candidates_created=1; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| Safe-stack smoke | `454 passed, 3 warnings in 9.24s; pytest PASSED` |
| Dry-run report | `SAFE; requested=3 completed=3; all_dry_run=True; any_executed=False; execution_call_count=0` |

### Safety notes

- `config/autonomy.json` remained `enabled=false`.
- Elysia autonomy was not enabled.
- Live execution was not enabled or run.
- No tools/capabilities/mutation/proposal implementation/WebScout/browser activity was run.
- No server/API route was added.
- No watcher, daemon, scheduler, background monitor, or automatic loop was added.
- No account/API/network/model/embedding access was added or used.
- No live runtime memory or vector DB writes were added.
- `project_guardian/core.py` was not staged or committed.
- `elysia/api/server.py` was not staged or committed.
- `config/autonomy.json` was not modified.
- Concurrent Cursor commit `2edb8ec` was docs-only and did not add a route, watcher,
  account access, model call, embedding call, live execution, or live memory/vector write.

### Recommended next Cursor task

Start Campaign 2: create a route test harness that describes safe future route behavior without implementing the route.

### Human approval needed

No human approval is needed before Campaign 2, because it is still test/design-only and does not implement a route. Human approval is required before any route implementation campaign.

## Campaign 2 - Memory dashboard route test harness

### Campaign summary

- Campaign name: Memory dashboard route test harness
- Starting clean tag: `memory_dashboard_route_design_clean_1`
- Starting HEAD: `3c3dbbc docs(memory): add long-term campaign handoff`
- Starting branch: `codex/limited-live-activation-wrapper`
- Ending code HEAD before this handoff document: `09083ea feat(local): add memory dashboard route contract`
- Ending campaign HEAD after this handoff document: see `git log -1`
- Campaign tag: `memory_dashboard_route_tests_clean_1`
- Cycles attempted: 2
- Cycles completed: 2
- Commits made before tag: 2

### Commits

| Commit | Purpose |
| ------ | ------- |
| `09083ea feat(local): add memory dashboard route contract` | Added a pure local route contract module, focused contract tests, the route test harness doc, and design/acceptance doc references. |
| handoff commit | Added this Campaign 2 handoff entry. |

### Files changed

- `docs/CODEX_LONG_TERM_HANDOFF.md`
- `docs/MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md`
- `docs/MEMORY_DASHBOARD_ROUTE_DESIGN.md`
- `docs/MEMORY_DASHBOARD_ROUTE_TEST_HARNESS.md`
- `project_guardian/local_ingestion/memory_dashboard_route_contract.py`
- `project_guardian/tests/test_memory_dashboard_route_contract.py`

### Completed work

- Added a pure contract module for future local-only Memory dashboard route behavior.
- Defined the exact allowed static Memory page allowlist.
- Added validation for unknown filenames, traversal, backslash traversal, encoded traversal, double-encoded traversal, null-byte style payloads, absolute Windows paths, absolute POSIX paths, drive-root style paths, and directory-only paths.
- Added safe path resolution that returns only allowlisted files under `project_guardian/ui/static/`.
- Added tests proving the contract module does not import Flask, FastAPI, `elysia.api.server`, or `project_guardian.core`.
- Added tests proving the contract does not expose command execution, file-writing helpers, backend command execution, account/API/network access, or live memory/vector writes.
- Documented how future route tests should use the contract before any route implementation.
- Updated acceptance/design docs to reference the contract and harness.

### Skipped work

- No Memory dashboard route was implemented.
- No Flask/FastAPI route wiring was added.
- No browser JavaScript calls were added.
- No backend command execution was added.
- No model, embedding, account, API, network, live runtime memory, or vector DB integration was added.
- No `.mbox`, PDF, DOCX, OCR, image, phone sync, live ChatGPT, or live email import was implemented.

### Tests run

| Check | Result |
| ----- | ------ |
| Focused route contract and design docs tests | `82 passed, 3 warnings in 0.85s` |
| Full Memory/route-contract pytest baseline | `226 passed, 3 warnings in 42.56s` |
| Memory health smoke | `verdict=PASS; doctor_verdict=HAS_CONTEXT_BUNDLE; candidates_created=3; approvals_created=3; search_result_count=3; context_bundle_created=true; safety flags false` |
| Transcription smoke | `verdict=PASS; candidates_created=2; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| ChatGPT smoke | `verdict=PASS; candidates_created=1; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| Email smoke | `verdict=PASS; candidates_created=1; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| Safe-stack smoke | `454 passed, 3 warnings in 14.14s; pytest PASSED` |
| Dry-run report | `SAFE; requested=3 completed=3; all_dry_run=True; any_executed=False; execution_call_count=0` |

### Safety notes

- `config/autonomy.json` remained `enabled=false`.
- Elysia autonomy was not enabled.
- Live execution was not enabled or run.
- No tools/capabilities/mutation/proposal implementation/WebScout/browser activity was run.
- No server/API route was added.
- No Flask/FastAPI route wiring was added.
- No watcher, daemon, scheduler, background monitor, or automatic loop was added.
- No account/API/network/model/embedding access was added or used.
- No live runtime memory or vector DB writes were added.
- `project_guardian/core.py` was not staged or committed.
- `elysia/api/server.py` was not staged or committed.
- `config/autonomy.json` was not modified.

### Recommended next Cursor task

Start Campaign 3: produce the route readiness GO / NO-GO review without implementing the route.

### Human approval needed

No human approval is needed before Campaign 3, because it is still review-only and does not implement a route. Human approval is required before any route implementation campaign.

## Campaign 3 - Memory dashboard route readiness review

### Campaign summary

- Campaign name: Memory dashboard route readiness review
- Starting clean tag: `memory_dashboard_route_tests_clean_1`
- Starting HEAD: `021ae28 docs(memory): update route test harness handoff`
- Starting branch: `codex/limited-live-activation-wrapper`
- Ending code HEAD before this handoff document: `3a174d6 docs(ui): add memory dashboard route readiness review`
- Ending campaign HEAD after this handoff document: see `git log -1`
- Campaign tag: `memory_route_readiness_clean_1`
- GO / NO-GO decision: `GO_WITH_HUMAN_APPROVAL`
- Cycles attempted: 2
- Cycles completed: 2
- Commits made before tag: 2

### Commits

| Commit | Purpose |
| ------ | ------- |
| `3a174d6 docs(ui): add memory dashboard route readiness review` | Added the GO / NO-GO readiness review, implementation gates, and readiness-doc tests. |
| handoff commit | Added this Campaign 3 handoff entry. |

### Files changed

- `docs/CODEX_LONG_TERM_HANDOFF.md`
- `docs/MEMORY_DASHBOARD_ROUTE_IMPLEMENTATION_GATES.md`
- `docs/MEMORY_DASHBOARD_ROUTE_READINESS_REVIEW.md`
- `project_guardian/tests/test_memory_dashboard_route_readiness_docs.py`

### Completed work

- Inspected `project_guardian/ui/templates/`, `project_guardian/ui/static/`, `project_guardian/ui/app.py`, `project_guardian/ui_control_panel.py`, `Elysia_Control_Panel_Standalone.html`, `elysia/api/server.py`, the route contract module/tests, and Campaign 1/2 route docs.
- Documented the current static Memory pages and direct-open fallback.
- Documented dashboard/UI discovery and recommended `project_guardian/ui/app.py` as the narrow future route file if explicitly approved.
- Documented why `elysia/api/server.py`, `project_guardian/core.py`, `project_guardian/ui_control_panel.py`, and `Elysia_Control_Panel_Standalone.html` should not be touched for the first route implementation.
- Issued readiness decision `GO_WITH_HUMAN_APPROVAL`.
- Added implementation gates requiring design, risk review, contract, contract tests, readiness review, human approval, allowlisted serving, traversal rejection, encoded traversal rejection, no backend command execution, no writes, safe-stack smoke, and dry-run SAFE.
- Added readiness-doc tests that prevent the review/gates docs from becoming accidental implementation instructions.

### Skipped work

- No Memory dashboard route was implemented.
- No Flask/FastAPI route wiring was added.
- No browser JavaScript calls were added.
- No backend command execution was added.
- No optional roadmap/checkpoint docs were updated because the required readiness/gates docs and handoff are sufficient for Campaign 3.
- No model, embedding, account, API, network, live runtime memory, or vector DB integration was added.
- No `.mbox`, PDF, DOCX, OCR, image, phone sync, live ChatGPT, or live email import was implemented.

### Tests run

| Check | Result |
| ----- | ------ |
| Focused readiness, contract, and design docs tests | `112 passed, 3 warnings in 0.94s` |
| Full Memory/readiness pytest baseline | `256 passed, 3 warnings in 37.47s` |
| Memory health smoke | `verdict=PASS; doctor_verdict=HAS_CONTEXT_BUNDLE; candidates_created=3; approvals_created=3; search_result_count=3; context_bundle_created=true; safety flags false` |
| Transcription smoke | `verdict=PASS; candidates_created=2; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| ChatGPT smoke | `verdict=PASS; candidates_created=1; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| Email smoke | `verdict=PASS; candidates_created=1; approvals_created=1; search_result_count=1; context_bundle_created=true; safety flags false` |
| Safe-stack smoke | `454 passed, 3 warnings in 14.55s; pytest PASSED` |
| Dry-run report | `SAFE; requested=3 completed=3; all_dry_run=True; any_executed=False; execution_call_count=0` |

### Safety notes

- `config/autonomy.json` remained `enabled=false`.
- Elysia autonomy was not enabled.
- Live execution was not enabled or run.
- No tools/capabilities/mutation/proposal implementation/WebScout/browser activity was run.
- No server/API route was added.
- No Flask/FastAPI route wiring was added.
- No watcher, daemon, scheduler, background monitor, or automatic loop was added.
- No account/API/network/model/embedding access was added or used.
- No live runtime memory or vector DB writes were added.
- `project_guardian/core.py` was not staged or committed.
- `elysia/api/server.py` was not staged or committed.
- `config/autonomy.json` was not modified.

### Recommended next Cursor task

Request explicit human approval before any route implementation. If approval is not granted, continue with Campaign 4 command polish or other safer non-route work.

### Human approval needed

Yes. Route implementation must not begin without explicit human approval naming the exact route file and purpose.

## Campaign 4 - Static Memory dashboard route (human-approved, Cursor)

### Campaign summary

- Campaign name: Static Memory dashboard route (human-approved)
- Starting clean tag: `memory_route_readiness_clean_1`
- Starting HEAD: `e6de704 docs(memory): update route readiness handoff`
- Implementer: Cursor (operator-approved)
- Approved route file: `project_guardian/ui/app.py`
- Campaign tag: `memory_static_route_clean_1`
- Route type: static-only allowlisted HTML serving

### Completed work

- Added `/memory`, `/memory/`, and `/memory/{page}` GET routes in `project_guardian/ui/app.py`.
- Routes use `memory_dashboard_route_contract.resolve_static_memory_page`.
- Added `project_guardian/tests/test_memory_dashboard_static_route.py`.
- Updated readiness review, implementation gates, and this handoff.

### Safety notes

- Human approval was required and granted before implementation.
- Route is static-only; no memory pipeline actions from browser or route handler.
- No diagnostics/demo command execution from route.
- No account/API/network/model/embedding access added.
- No live runtime memory or vector DB writes added.
- `elysia/api/server.py` not modified.
- `project_guardian/core.py` not modified.
- `config/autonomy.json` not modified; remains `enabled=false`.

### Recommended next Cursor task

Add operator-facing documentation or a control-panel link to `/memory` that clearly labels the page
as a static prototype, without adding fetch/XHR/API calls to static Memory HTML.

## Campaign 5 - Memory Hub dashboard link (Codex)

### Campaign summary

- Campaign name: Memory Hub dashboard link
- Starting clean tag: `memory_static_route_clean_1`
- Starting HEAD: `d9e569f docs(ui): update memory route implementation handoff`
- Target dashboard file: `project_guardian/ui/templates/dashboard.html`
- Route linked: `/memory`
- Link type: static local prototype navigation only

### Completed work

- Added a visible `Memory Hub` link to the dashboard Quick Actions card.
- Labeled the link as a static local memory prototype for import, review, search, diagnostics, and safety guides.
- Added `project_guardian/tests/test_memory_dashboard_control_panel_link.py`.

### Safety notes

- The link does not execute memory actions.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.

## Campaign 6 - Memory Hub onboarding links (Codex)

### Campaign summary

- Campaign name: Memory Hub onboarding links
- Starting clean tag: `memory_dashboard_link_clean_1`
- Starting HEAD: `a29683b docs(ui): link memory hub from control panel`
- Target page: `project_guardian/ui/static/memory_hub.html`
- Link type: static local prototype navigation only

### Completed work

- Added a `Memory onboarding` section to the Memory Hub.
- Linked only to allowlisted `/memory/...` pages:
  - `/memory/memory_first_run_setup.html`
  - `/memory/memory_safety.html`
  - `/memory/memory_diagnostics.html`
  - `/memory/memory_import_screen.html`
  - `/memory/memory_review_search.html`
- Added `project_guardian/tests/test_memory_hub_onboarding_links.py`.
- Narrowly updated static page safety coverage to allow only contract-allowlisted `/memory/...` links.

### Safety notes

- No route implementation changed.
- No new route was added.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.

## Campaign 7 - Memory static page backlinks (Codex)

### Campaign summary

- Campaign name: Memory static page backlinks
- Starting clean tag: `memory_hub_onboarding_links_clean_1`
- Starting HEAD: `2a47b62 docs(ui): add memory hub onboarding links`
- Target pages:
  - `project_guardian/ui/static/memory_first_run_setup.html`
  - `project_guardian/ui/static/memory_safety.html`
  - `project_guardian/ui/static/memory_diagnostics.html`
  - `project_guardian/ui/static/memory_import_screen.html`
  - `project_guardian/ui/static/memory_review_search.html`

### Completed work

- Added visible `Back to Memory Hub` links on sibling static Memory pages.
- Backlinks point to `/memory/memory_hub.html`, an allowlisted `/memory/...` route target.
- Added `project_guardian/tests/test_memory_static_backlinks.py`.

### Safety notes

- No route implementation changed.
- No new route was added.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.

## Campaign 8 - Memory static route link normalization (Codex)

### Campaign summary

- Campaign name: Memory static route link normalization
- Starting clean tag: `memory_static_backlinks_clean_1`
- Starting HEAD: `d792562 docs(ui): add memory static page backlinks`
- Target pages: Memory static HTML pages under `project_guardian/ui/static/`

### Completed work

- Normalized remaining Memory static cross-links to `/memory/...` route paths.
- Updated the static index, first-run setup, safety, and diagnostics pages where relative sibling links remained.
- Added `project_guardian/tests/test_memory_static_route_links.py`.
- Updated navigation coverage to expect routed Memory static links.

### Safety notes

- No route implementation changed.
- No new route was added.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
