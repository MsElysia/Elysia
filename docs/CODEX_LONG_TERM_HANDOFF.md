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

## Campaign 13 - Memory static responsive and print polish (Codex)

### Campaign summary

- Campaign name: Memory static responsive, print, and user-preference CSS polish
- Starting clean tag: `memory_static_landmarks_skiplinks_clean_1`
- Starting HEAD: `f47cba5 docs(ui): add memory static landmarks and skip links`
- Target pages: Memory static HTML pages served through `/memory/...`

### Completed work

- Added narrow-screen responsive CSS to the Memory static pages.
- Added print-friendly CSS that removes skip/page navigation controls and keeps page content readable on white backgrounds.
- Added reduced-motion media-query handling for current and future static page transitions.
- Added safe color-scheme declarations that keep the existing dark palette readable.
- Added `project_guardian/tests/test_memory_static_responsive_print.py`.

### Safety notes

- Skip links, main landmarks, breadcrumb navigation, route labels, and normalized `/memory/...` links were preserved.
- Route implementation did not change.
- No new route was added.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Recommended next campaign: return to a functional Memory workflow improvement rather than more visual polish unless a clear static UI issue is found.

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

## Campaign 9 - Memory route navigation graph coverage (Codex)

### Campaign summary

- Campaign name: Memory route navigation graph coverage
- Starting clean tag: `memory_static_route_links_clean_1`
- Starting HEAD: `e4c9b65 docs(ui): normalize memory static route links`
- Target behavior: verify static Memory pages through `/memory/...` routes

### Completed work

- Added `project_guardian/tests/test_memory_route_navigation_graph.py`.
- Covered routed serving of all allowlisted Memory pages.
- Verified routed Memory page links stay within the route contract allowlist and resolve through the local `/memory/...` route.

### Safety notes

- No route implementation changed.
- No new route was added.
- No static page behavior was changed.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.

## Campaign 10 - Memory static page identity (Codex)

### Campaign summary

- Campaign name: Memory static page title, breadcrumb, and route-label consistency
- Starting clean tag: `memory_route_navigation_graph_clean_1`
- Starting HEAD: `1e7a4e4 test(ui): cover memory route navigation graph`
- Target pages: Memory static HTML pages served through `/memory/...`

### Completed work

- Added consistent Memory page titles, top-level headings, breadcrumb text, and visible local route labels.
- Route labels use allowlisted `/memory/...` targets and identify the local static route for each page.
- Added `project_guardian/tests/test_memory_static_page_identity.py`.

### Safety notes

- Route implementation did not change.
- No new route was added.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.

## Campaign 11 - Memory static accessibility identity polish (Codex)

### Campaign summary

- Campaign name: Memory static accessibility and identity polish
- Starting clean tag: `memory_static_page_identity_clean_1`
- Starting HEAD: `c3b8c7c docs(ui): add memory static page identity`
- Target pages: Memory static HTML pages served through `/memory/...`

### Completed work

- Confirmed all Memory static pages use `lang="en"`.
- Added one page-specific meta description to each Memory static page.
- Marked the active breadcrumb/current page item with `aria-current="page"`.
- Added `project_guardian/tests/test_memory_static_accessibility_identity.py`.

### Safety notes

- Route implementation did not change.
- No new route was added.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.

## Campaign 12 - Memory static landmarks and skip links (Codex)

### Campaign summary

- Campaign name: Memory static landmark and skip-link accessibility polish
- Starting clean tag: `memory_static_accessibility_identity_clean_1`
- Starting HEAD: `ec59fbc docs(ui): polish memory static accessibility identity`
- Target pages: Memory static HTML pages served through `/memory/...`

### Completed work

- Added visible-on-focus `Skip to main content` links to Memory static pages.
- Added one `<main id="main-content">` landmark per Memory static page.
- Wrapped breadcrumb identity in `nav aria-label="Memory breadcrumb"`.
- Labeled page navigation groups with `aria-label="Memory page navigation"` where appropriate.
- Added page-local visible focus styles for links and buttons.
- Added `project_guardian/tests/test_memory_static_landmarks_skiplinks.py`.

### Safety notes

- Route implementation did not change.
- No new route was added.
- No backend calls were added.
- No fetch, XHR, or WebSocket usage was added.
- No account, model, API, network, or embedding access was added.
- No live runtime memory or vector DB writes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.

## Campaign 14 - Memory import review handoff smoke (Codex)

### Campaign summary

- Campaign name: Dry-run Memory import-to-review handoff coverage
- Starting clean tag: `memory_static_responsive_print_clean_1`
- Starting HEAD: `704bd43 docs(ui): polish memory static responsive print styles`
- Target command: `scripts/run_memory_import_review_handoff_smoke.py --json`

### Completed work

- Added a dry-run/local handoff smoke command that composes the existing local memory pipeline helpers.
- Covered transcription, ChatGPT export, and email export fixture source types.
- Verified import candidates, review queue artifacts, approved export/store readiness, search readiness, and context bundle artifacts in temp workspaces.
- Added `project_guardian/tests/test_memory_import_review_handoff.py`.
- Added `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_import_review_handoff_smoke.py --json` and inspect the JSON report.

## Campaign 15 - Memory review decision branch smoke (Codex)

### Campaign summary

- Campaign name: Dry-run Memory review decision branch coverage
- Starting clean tag: `memory_import_review_handoff_clean_1`
- Starting HEAD: `1e3311a feat(local): add memory import review handoff smoke`
- Target command: `scripts/run_memory_review_decision_branches_smoke.py --json`

### Completed work

- Added a dry-run/local decision branch smoke command that composes existing local import, review, export, store, and search helpers.
- Covered approve, reject, and edit-then-approve decisions with local transcription fixtures.
- Verified rejected candidates are excluded from approved output and search.
- Verified edited candidate text is preserved in approved output.
- Added `project_guardian/tests/test_memory_review_decision_branches.py`.
- Added `docs/MEMORY_REVIEW_DECISION_BRANCHES.md`.
- Updated `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_decision_branches_smoke.py --json` and inspect the JSON report.

## Campaign 16 - Memory review decision idempotency smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review decision idempotency coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_decision_branches_clean_1`
- Starting HEAD: `3e9773e feat(local): add memory review decision branch smoke`
- Target command: `scripts/run_memory_review_decision_idempotency_smoke.py --json`

### Completed work

- Added a dry-run/local idempotency smoke command that composes existing local import, review, export, store, and search helpers.
- Applies the same approve/reject/edit decisions twice and re-runs export/store/search after each pass.
- Verified approved, rejected, and edited counts stay stable across repeated runs.
- Verified approved and rejected identifiers stay stable across repeated runs.
- Verified repeated export/store steps do not create duplicate approved records or duplicate local memory store records.
- Verified rejected candidates stay excluded from approved output and search.
- Verified edited candidate text stays preserved across repeated runs.
- No local ingestion/review helper repair was required; export and store already overwrite their output files and resolve the latest decision per candidate.
- Added `project_guardian/tests/test_memory_review_decision_idempotency.py`.
- Added `docs/MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`.
- Updated `docs/MEMORY_REVIEW_DECISION_BRANCHES.md` and `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_decision_idempotency_smoke.py --json` and inspect the JSON report.

## Campaign 17 - Memory review decision audit trail smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review decision audit trail coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_decision_idempotency_clean_1`
- Starting HEAD: `7de7688 feat(local): add memory review decision idempotency smoke`
- Target command: `scripts/run_memory_review_decision_audit_trail_smoke.py --json`

### Completed work

- Added a dry-run/local audit trail smoke command that composes existing local import, review, export, store, and search helpers.
- Applies approve/reject/edit decisions twice, then audits the append-only `review_decisions.jsonl` log.
- Verified every decision entry is valid JSON and carries the required audit fields (`decision_id`, `candidate_id`, `previous_status`, `new_status`, `decided_at`, `operator_required`, `live_memory_written`, `source_queue_path`).
- Verified approve, reject, and edit transitions are all represented in the log.
- Verified timestamps are present and chronological (non-decreasing).
- Verified repeated decisions do not corrupt latest-decision resolution (latest approved/rejected/edited counts stay 1/1/1).
- Verified rejected candidates stay excluded from approved output and search, and edited text stays preserved.
- No local ingestion/review helper repair was required; the review helpers already record deterministic decision ids, previous/new status, timestamps, and operator-required/dry-run-safe metadata.
- Added `project_guardian/tests/test_memory_review_decision_audit_trail.py`.
- Added `docs/MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`.
- Updated `docs/MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`, `docs/MEMORY_REVIEW_DECISION_BRANCHES.md`, and `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_decision_audit_trail_smoke.py --json` and inspect the JSON report.

## Campaign 18 - Memory review decision tamper evidence smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review decision tamper-evidence coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_decision_audit_trail_clean_1`
- Starting HEAD: `508c842 feat(local): add memory review decision audit smoke`
- Target command: `scripts/run_memory_review_decision_tamper_evidence_smoke.py --json`

### Completed work

- Added a dry-run/local tamper-evidence smoke that builds a valid append-only `review_decisions.jsonl` from local fixtures, then writes tampered copies inside a temp workspace and runs a self-contained, local-only audit checker (`audit_decision_log`) against each.
- The audit checker was added as a small, local-only helper inside the new smoke script; no existing local ingestion/review/server/core file was modified (the previous audit-trail smoke kept its validation inline, so a minimal standalone checker was the smallest safe addition).
- Proved the clean audit log returns `verdict=PASS`.
- Proved a malformed JSON line fails with a specific error containing `malformed_json`.
- Proved a missing required field fails with a specific error containing `missing_required_field`.
- Proved a non-chronological timestamp fails with a specific error containing `non_chronological`.
- Proved an unknown candidate id fails with a specific error containing `unknown_candidate` (optional case, implemented).
- Proved an unsupported status transition fails with a specific error containing `unsupported_transition` (optional case, implemented).
- Proved every tampered variant returns `verdict=FAIL` and the clean log still passes afterward.
- Added `project_guardian/tests/test_memory_review_decision_tamper_evidence.py`.
- Added `docs/MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md`.
- Updated `docs/MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`, `docs/MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`, `docs/MEMORY_REVIEW_DECISION_BRANCHES.md`, and `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only; tampered logs are written only inside the temp workspace.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_decision_tamper_evidence_smoke.py --json` and inspect the JSON report.

## Campaign 19 - Memory review decision tamper recovery smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review decision tamper recovery and quarantine coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_decision_tamper_evidence_clean_1`
- Starting HEAD: `f4b44ad feat(local): add memory review decision tamper smoke`
- Target command: `scripts/run_memory_review_decision_tamper_recovery_smoke.py --json`

### Completed work

- Added a dry-run/local recovery-and-quarantine smoke that builds a valid append-only `review_decisions.jsonl` from local fixtures, saves a known-good copy, corrupts the working log (malformed JSON line plus a missing required field), and proves safe recovery.
- Reuses the local-only `audit_decision_log` checker from the tamper-evidence smoke by import; no existing local ingestion/review/server/core file was modified.
- Proved the clean audit log returns `verdict=PASS` and resolves to the expected approve/reject/edit latest decisions.
- Proved the corrupted working log returns `verdict=FAIL` and the specific error types are captured (`malformed_json`, `missing_required_field`).
- Proved corruption is detected before recovery runs.
- Proved the corrupt log is copied into a temp-only `quarantine/` directory, preserved exactly (not overwritten or silently repaired), with a `quarantine_manifest.json` recording original/quarantine/known-good paths, detected error types, timestamp, `dry_run=true`, `local_only=true`, `silently_repaired=false`, `live_memory_written=false`, and `operator_required=true`.
- Proved the corrupt log is never trusted for latest-decision resolution (loading latest decisions from it raises `MemoryCandidateReviewError`).
- Proved recovery re-resolves latest decisions from the known-good copy only, matching the pre-corruption state.
- Proved the rejected candidate stays excluded from the approved export and edited text stays preserved after recovery.
- Added `project_guardian/tests/test_memory_review_decision_tamper_recovery.py`.
- Added `docs/MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md`.
- Updated `docs/MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md`, `docs/MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`, `docs/MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`, `docs/MEMORY_REVIEW_DECISION_BRANCHES.md`, and `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only; corrupt logs, quarantine copies, and manifests are written only inside the temp workspace.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_decision_tamper_recovery_smoke.py --json` and inspect the JSON report.

## Campaign 20 - Memory review recovery audit trail smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review recovery audit-trail coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_decision_tamper_recovery_clean_1`
- Starting HEAD: `e0c6229 feat(local): add memory review decision tamper recovery smoke`
- Target command: `scripts/run_memory_review_recovery_audit_trail_smoke.py --json`

### Completed work

- Added a dry-run/local recovery audit-trail smoke that builds a valid review decision log, corrupts it, quarantines it, recovers from known-good clean data, and appends every recovery step to `recovery_audit.jsonl`.
- Reuses the local-only `audit_decision_log` checker from the tamper-evidence smoke by import; no existing local ingestion/review/server/core file was modified.
- Proved every quarantine/recovery action is written to the recovery audit log with required fields and chronological timestamps.
- Proved expected recovery events are present: `corruption_detected`, `quarantine_created`, `corrupt_log_preserved`, `manifest_written`, `known_good_resolution_used`, `recovery_completed`.
- Proved recovery audit entries carry `operator_required=true`, `dry_run=true`, `local_only=true`, `silently_repaired=false`, and `live_memory_written=false`.
- Proved corruption is detected before quarantine; the corrupt log is preserved byte-for-byte and is never trusted for latest-decision resolution.
- Proved recovery re-resolves latest decisions from the known-good copy only; rejected candidates stay excluded and edited text stays preserved.
- Added `project_guardian/tests/test_memory_review_recovery_audit_trail.py`.
- Added `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`.
- Updated `docs/MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md`, `docs/MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md`, `docs/MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`, `docs/MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`, `docs/MEMORY_REVIEW_DECISION_BRANCHES.md`, and `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only; recovery audit logs, quarantine copies, and manifests are written only inside the temp workspace.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_recovery_audit_trail_smoke.py --json` and inspect the JSON report.

## Campaign 21 - Memory review recovery audit tamper evidence smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review recovery audit tamper-evidence coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_recovery_audit_trail_clean_1`
- Starting HEAD: `19d9235 feat(local): add memory review recovery audit smoke`
- Target command: `scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json`

### Completed work

- Added a dry-run/local recovery audit tamper-evidence smoke that runs the existing recovery audit-trail flow to build a valid `recovery_audit.jsonl`, then writes tampered copies inside a temp workspace and runs a self-contained, local-only audit checker (`audit_recovery_log`) against each.
- Reuses recovery audit constants from the recovery audit-trail smoke by import; no existing local ingestion/review/server/core file was modified.
- Proved the clean recovery audit log returns `verdict=PASS`.
- Proved a malformed JSON line fails with a specific error containing `malformed_json`.
- Proved a missing required field fails with a specific error containing `missing_required_field`.
- Proved a non-chronological timestamp fails with a specific error containing `non_chronological`.
- Proved an unsupported recovery event type fails with a specific error containing `unsupported_event` (implemented).
- Proved unsafe metadata (for example `dry_run=false`) fails with a specific error containing `unsafe_metadata` (implemented).
- Proved every tampered variant returns `verdict=FAIL` and the clean log still passes afterward.
- Added `project_guardian/tests/test_memory_review_recovery_audit_tamper_evidence.py`.
- Added `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`.
- Updated `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`, `docs/MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md`, `docs/MEMORY_REVIEW_DECISION_TAMPER_EVIDENCE.md`, `docs/MEMORY_REVIEW_DECISION_AUDIT_TRAIL.md`, `docs/MEMORY_REVIEW_DECISION_IDEMPOTENCY.md`, `docs/MEMORY_REVIEW_DECISION_BRANCHES.md`, and `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`.

### Safety notes

- Uses local fixtures and temporary workspaces only; tampered recovery audit logs are written only inside the temp workspace.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_recovery_audit_tamper_evidence_smoke.py --json` and inspect the JSON report.

## Campaign 22 - Memory review recovery audit tamper recovery smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review recovery audit tamper-recovery coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_recovery_audit_tamper_evidence_clean_1`
- Starting HEAD: `a37d9ca feat(local): add memory recovery audit tamper smoke`
- Target command: `scripts/run_memory_review_recovery_audit_tamper_recovery_smoke.py --json`

### Completed work

- Added a dry-run/local recovery audit tamper-recovery smoke that runs the existing recovery audit-trail flow to build a valid `recovery_audit.jsonl`, saves a known-good copy, corrupts the working log (malformed JSON plus unsafe metadata), detects corruption, quarantines the corrupt log with a manifest, and re-resolves recovery audit state from the known-good copy only.
- Reuses `audit_recovery_log` from the recovery audit tamper-evidence smoke and recovery audit constants from the recovery audit-trail smoke by import; no existing local ingestion/review/server/core file was modified.
- Proved the clean recovery audit log returns `verdict=PASS`.
- Proved the corrupted recovery audit log returns `verdict=FAIL` before recovery.
- Proved corruption is detected before quarantine.
- Proved the corrupt recovery audit log is preserved byte-for-byte in quarantine.
- Proved a quarantine manifest is written with original/quarantine/known-good paths, error types, and safety metadata (`dry_run=true`, `local_only=true`, `silently_repaired=false`, `operator_required=true`).
- Proved recovery audit state is re-resolved from known-good data only and recovered events match the pre-corruption state.
- Proved the corrupt recovery audit log is not trusted for recovery validation.
- Added `project_guardian/tests/test_memory_review_recovery_audit_tamper_recovery.py`.
- Added `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_RECOVERY.md`.
- Updated `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`, `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`, `docs/MEMORY_REVIEW_DECISION_TAMPER_RECOVERY.md`, `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; corrupt recovery audit logs, quarantine copies, and manifests are written only inside the temp workspace.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_recovery_audit_tamper_recovery_smoke.py --json` and inspect the JSON report.

## Campaign 23 - Memory review recovery inspection bundle smoke (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review recovery inspection bundle coverage
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_recovery_audit_tamper_recovery_clean_1`
- Starting HEAD: `fd7bba6 feat(local): add memory recovery audit tamper recovery smoke`
- Target command: `scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json`

### Completed work

- Added a dry-run/local recovery inspection bundle smoke that runs the existing recovery-audit tamper-recovery flow, then writes a `recovery_inspection_bundle/` directory with an operator-readable inspection summary and Markdown README.
- Reuses `run_memory_review_recovery_audit_tamper_recovery_smoke` by import; no existing local ingestion/review/server/core file was modified.
- Proved the bundle directory and inspection summary are created inside the temp workspace.
- Proved the summary includes quarantine manifest path, quarantined corrupt log path, known-good recovery audit path, and recovered event sequence.
- Proved SHA-256 hashes are included for corrupt log, known-good copy, and quarantine manifest and match the artifact files.
- Proved corrupt log preservation, known-good resolution, and recovered event sequence match known-good state.
- Proved summary confirms `dry_run=true`, `local_only=true`, `silently_repaired=false`, and `operator_required=true`.
- Added `project_guardian/tests/test_memory_review_recovery_inspection_bundle.py`.
- Added `docs/MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md`.
- Updated `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_RECOVERY.md`, `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_EVIDENCE.md`, `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TRAIL.md`, `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; inspection bundle files are written only inside the temp workspace.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json` and inspect the JSON report.

## Campaign 24 - Memory review recovery inspection error types (Cursor)

### Campaign summary

- Campaign name: Dry-run Memory review recovery inspection error-type summary
- Implemented by Cursor because Codex hit usage limits.
- Starting clean tag: `memory_review_recovery_inspection_bundle_clean_1`
- Starting HEAD: `ec027e8 feat(local): add memory recovery inspection bundle smoke`
- Target command: `scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json`

### Completed work

- Updated the recovery inspection bundle smoke so `inspection_summary.json` directly includes `detected_error_types`, `detected_error_type_count`, and `detected_error_types_match_manifest` copied from the quarantine manifest.
- Proved error types are loaded from the manifest, not hardcoded.
- Proved the summary error-type count matches the manifest list length.
- Proved operators can triage corruption from the summary without opening the manifest.
- Preserved existing paths, hashes, recovered event sequence, and safety metadata fields.
- Updated `project_guardian/tests/test_memory_review_recovery_inspection_bundle.py`.
- Updated `docs/MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md`, `docs/MEMORY_REVIEW_RECOVERY_AUDIT_TAMPER_RECOVERY.md`, `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; inspection bundle files are written only inside the temp workspace.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- Route implementation did not change.
- No backend command execution from UI was added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json` and inspect detected error types in the JSON report.

## Campaign 25 - Memory review recovery inspection workspace reset (Cursor)

- Campaign name: Dry-run Memory review recovery inspection stale-workspace rerun handling
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `6343bbc feat(local): surface recovery inspection error types`
- Starting clean tag: `memory_review_recovery_inspection_error_types_clean_1`
- Final clean tag: `memory_review_recovery_inspection_workspace_reset_clean_1`

### What changed

- Added `--reset-workspace` to the recovery inspection bundle smoke for explicit operator rerun on a kept `--base-dir`.
- Detect stale kept workspaces and return clear guidance instead of unsafe automatic deletion.
- Reset removes only known generated dry-run artifacts under the supplied base directory (`source/`, `dest/`, `known_good/`, `quarantine/`, `recovery_inspection_bundle/`, `recovery_audit.jsonl`).
- JSON report now includes `stale_workspace_detected`, `workspace_reset_performed`, `workspace_reset_paths`, and `workspace_reset_safe`.
- Updated `scripts/run_memory_review_recovery_inspection_bundle_smoke.py`.
- Updated `project_guardian/tests/test_memory_review_recovery_inspection_bundle.py`.
- Updated `docs/MEMORY_REVIEW_RECOVERY_INSPECTION_BUNDLE.md`, `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Reset is explicit operator action only; no automatic deletion on stale detection.
- Reset refuses unsafe base directories (repo root, home, drive root, empty path).
- Reset does not delete arbitrary files, repo source files, live memory paths, vector DB paths, or account data.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No live runtime memory or vector DB writes were added.
- No UI actions, browser calls, POST forms, or routes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can rerun with `python scripts/run_memory_review_recovery_inspection_bundle_smoke.py --json --base-dir .\tmp\recovery-inspection-rerun --keep-temp --reset-workspace`.

## Campaign 26 - Memory review approved promotion bundle (Cursor)

- Campaign name: Dry-run Memory review approved promotion bundle coverage
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `6729f72 feat(local): add recovery inspection workspace reset`
- Starting clean tag: `memory_review_recovery_inspection_workspace_reset_clean_1`
- Final clean tag: `memory_review_approved_promotion_bundle_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_bundle_smoke.py` to package approved and edited review candidates into `approved_promotion_bundle/promotion_manifest.json`.
- Proved rejected candidates are excluded with explicit counts.
- Proved edited candidates preserve both original and promoted text with review decision links and SHA-256 hashes.
- Added `project_guardian/tests/test_memory_review_approved_promotion_bundle.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_BUNDLE.md`.
- Updated `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md` and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; bundle files are written only inside the temp workspace.
- Does not write live runtime memory or vector DB data.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No UI actions, browser calls, POST forms, or routes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_bundle_smoke.py --json` and inspect promotion items in the JSON report.

## Campaign 27 - Memory review approved promotion tamper evidence (Codex)

- Campaign name: Dry-run Memory review approved promotion tamper-evidence coverage
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `d9df6c8 feat(local): add memory approved promotion bundle smoke`
- Starting clean tag: `memory_review_approved_promotion_bundle_clean_1`
- Target clean tag: `memory_review_approved_promotion_tamper_evidence_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_tamper_evidence_smoke.py`.
- Added a local-only promotion manifest checker that validates required manifest fields, required promotion item fields, promoted text hashes, candidate hashes, rejected-candidate exclusion, promotion item count, safety metadata, and the promotion manifest hash.
- Proves tampered copies fail with specific tokens for `malformed_json`, `missing_required_manifest_field`, `missing_required_promotion_item_field`, `promoted_text_hash_mismatch`, `candidate_hash_mismatch`, `rejected_candidate_included`, `promotion_item_count_mismatch`, `unsafe_metadata`, and `manifest_hash_mismatch`.
- Proves the clean approved-promotion manifest still passes after tamper checks.
- Added `project_guardian/tests/test_memory_review_approved_promotion_tamper_evidence.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_TAMPER_EVIDENCE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_BUNDLE.md`, `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; tampered manifest files are written only inside the temp workspace.
- Does not write live runtime memory or vector DB data.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No UI actions, browser calls, POST forms, or routes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_tamper_evidence_smoke.py --json` and inspect clean and tampered manifest paths in the JSON report.

## Campaign 28 - Memory review approved promotion operator handoff (Codex)

- Campaign name: Dry-run Memory review approved-promotion operator handoff
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `dd224e3 feat(local): add memory approved promotion tamper evidence smoke`
- Starting clean tag: `memory_review_approved_promotion_tamper_evidence_clean_1`
- Target clean tag: `memory_review_approved_promotion_operator_handoff_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_operator_handoff_smoke.py`.
- Builds a clean approved-promotion bundle, validates the clean promotion manifest, runs approved-promotion tamper-evidence coverage, then writes `approved_promotion_operator_handoff/operator_handoff.json`.
- Writes `approved_promotion_operator_handoff/OPERATOR_CHECKLIST.md` with a SHA-256 hash and a small README.
- Handoff includes approved and edited promotion items, rejected-exclusion count, promotion manifest path/hash, tamper-evidence verdict, and explicit future approval requirements.
- Marks the handoff ready for operator review only, not ready for live memory write, and keeps future live write blocked.
- Added `project_guardian/tests/test_memory_review_approved_promotion_operator_handoff.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_HANDOFF.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_TAMPER_EVIDENCE.md`, `docs/MEMORY_REVIEW_APPROVED_PROMOTION_BUNDLE.md`, `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; operator handoff files are written only inside the temp workspace.
- Does not write live runtime memory or vector DB data.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No UI actions, browser calls, POST forms, or routes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_operator_handoff_smoke.py --json --base-dir .\tmp\approved-promotion-operator-handoff --keep-temp` and inspect the handoff JSON/checklist.

## Campaign 29 - Memory review approved promotion operator approval gate (Codex)

- Campaign name: Dry-run Memory review approved-promotion explicit operator approval gate
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `eb2e0ff feat(local): add memory approved promotion operator handoff smoke`
- Starting clean tag: `memory_review_approved_promotion_operator_handoff_clean_1`
- Target clean tag: `memory_review_approved_promotion_operator_approval_gate_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_operator_approval_gate_smoke.py`.
- Builds the existing approved-promotion operator handoff, computes the current
  `operator_handoff.json` SHA-256 hash, and writes
  `approved_promotion_operator_approval_gate/operator_approval_gate.json`.
- Writes `approved_promotion_operator_approval_gate/APPROVAL_GATE_README.md`
  documenting the dry-run approval phrase
  `APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY`.
- Proves the handoff defaults to blocked and missing approval fails closed.
- Proves invalid approval tokens fail closed.
- Proves mismatched handoff hashes fail closed.
- Proves stale or mismatched handoff ids fail closed.
- Proves a valid explicit approval passes only for dry-run staging.
- Proves valid approval still does not allow live runtime memory writing or
  vector DB writing.
- Added `project_guardian/tests/test_memory_review_approved_promotion_operator_approval_gate.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVAL_GATE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_HANDOFF.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_TAMPER_EVIDENCE.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; approval-gate files are
  written only inside the temp workspace.
- Does not write live runtime memory or vector DB data.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No UI actions, browser calls, POST forms, or routes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_operator_approval_gate_smoke.py --json --base-dir .\tmp\approved-promotion-operator-approval-gate --keep-temp` and inspect the approval gate JSON/readme and local approval artifact.

## Campaign 30 - Memory review approved promotion operator-approved staging (Codex)

- Campaign name: Dry-run Memory review approved-promotion operator-approved staging package
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `f8ce76f feat(local): add memory approved promotion approval gate smoke`
- Starting clean tag: `memory_review_approved_promotion_operator_approval_gate_clean_1`
- Target clean tag: `memory_review_approved_promotion_operator_approved_staging_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_operator_approved_staging_smoke.py`.
- Builds the existing approved-promotion bundle, tamper-evidence checks, operator
  handoff, and approval gate, then writes
  `approved_promotion_operator_approved_staging/operator_approved_staging_manifest.json`.
- Writes `approved_promotion_operator_approved_staging/STAGING_README.md`
  documenting the dry-run approval phrase
  `APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY`.
- Staging only happens after a valid handoff and valid explicit operator approval.
- Missing or invalid approval fails closed and does not create a PASS staging
  manifest.
- Valid approval allows dry-run staging only.
- Staging includes approved and edited promotion items, preserves edited
  promoted text, and keeps rejected items excluded.
- Staging records promotion, handoff, and approval-gate SHA-256 hashes.
- Marks staging ready for operator-approved dry-run staging only, not ready for
  live memory write, and keeps future live write blocked.
- Added `project_guardian/tests/test_memory_review_approved_promotion_operator_approved_staging.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVAL_GATE.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_HANDOFF.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; staging files are written
  only inside the temp workspace.
- Does not write live runtime memory or vector DB data.
- No live account access was added or used.
- No model calls were added or used.
- No embedding calls were added or used.
- No UI actions, browser calls, POST forms, or routes were added.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_operator_approved_staging_smoke.py --json --base-dir .\tmp\approved-promotion-operator-approved-staging --keep-temp` and inspect the staging manifest and README.

## Campaign 31 - Memory review approved promotion operator-approved staging tamper evidence (Cursor)

- Campaign name: Dry-run Memory review approved-promotion operator-approved staging tamper evidence
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `03b7666 feat(local): add memory approved promotion approved staging smoke`
- Starting clean tag: `memory_review_approved_promotion_operator_approved_staging_clean_1`
- Target clean tag: `memory_review_approved_promotion_operator_approved_staging_tamper_evidence_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke.py`.
- Builds a clean operator-approved staging package, validates it as `PASS`, then
  writes isolated corrupted staging-manifest copies that must return `FAIL`.
- Covered failures include malformed JSON, missing required fields, promoted-text
  hash mismatch, promotion/handoff/approval-gate hash mismatches, rejected
  inclusion, staging item-count mismatch, unsafe metadata, and live-write
  unblocked.
- Added `project_guardian/tests/test_memory_review_approved_promotion_operator_approved_staging_tamper_evidence.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING_TAMPER_EVIDENCE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVAL_GATE.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; tamper-evidence files are
  written only inside the temp workspace.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke.py --json --base-dir .\tmp\approved-promotion-operator-approved-staging-tamper-evidence --keep-temp` and inspect the clean package plus each tampered manifest.

## Campaign 32 - Memory review approved promotion live-write blockade (Cursor)

- Campaign name: Dry-run Memory review approved-promotion live-write blockade proof
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `5d326f9 feat(local): add approved staging tamper evidence smoke`
- Starting clean tag: `memory_review_approved_promotion_operator_approved_staging_tamper_evidence_clean_1`
- Target clean tag: `memory_review_approved_promotion_live_write_blockade_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_live_write_blockade_smoke.py`.
- Builds a clean operator-approved staging package, validates staging tamper
  evidence as `PASS`, then records simulated live-memory and vector-DB write
  requests and denies them before any write occurs.
- Writes `approved_promotion_live_write_blockade/live_write_blockade_report.json`
  and `LIVE_WRITE_BLOCKADE_README.md` only inside the temp workspace.
- Live memory write request is denied. Vector DB write request is denied. No
  write is attempted or performed. No runtime memory or vector DB file is
  created. Future live write requires a separate explicit milestone.
- Added `project_guardian/tests/test_memory_review_approved_promotion_live_write_blockade.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING_TAMPER_EVIDENCE.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVAL_GATE.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; denial reports are written
  only inside the temp workspace.
- Does not call any live memory writer.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- Future live write requires a separate explicit milestone.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_live_write_blockade_smoke.py --json --base-dir .\tmp\ap-live-write-blockade --keep-temp` and inspect the blockade report and README.

## Campaign 33 - Memory review approved promotion live-write blockade tamper evidence (Cursor)

- Campaign name: Dry-run Memory review approved-promotion live-write blockade tamper evidence
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `5588f54 feat(local): add approved promotion live write blockade smoke`
- Starting clean tag: `memory_review_approved_promotion_live_write_blockade_clean_1`
- Target clean tag: `memory_review_approved_promotion_live_write_blockade_tamper_evidence_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke.py`.
- Builds a clean live-write blockade report, validates it as `PASS`, then writes
  isolated corrupted report copies that must return `FAIL`.
- Covered failures include malformed JSON, missing fields, source-staging hash
  mismatch, live-write allowed/attempted/performed, vector write
  allowed/attempted/performed, nonzero created-file counts, missing denial
  reason, future milestone disabled, and unsafe metadata.
- Added `project_guardian/tests/test_memory_review_approved_promotion_live_write_blockade_tamper_evidence.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE_TAMPER_EVIDENCE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING_TAMPER_EVIDENCE.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; tamper-evidence files are
  written only inside the temp workspace.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke.py --json --base-dir .\tmp\ap-live-write-blockade-tamper --keep-temp` and inspect the clean report plus each tampered copy.

## Campaign 34 - Memory review approved promotion final readiness packet (Cursor)

- Campaign name: Dry-run Memory review approved-promotion final readiness packet
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `0f55553 feat(local): add approved promotion live write blockade tamper evidence smoke`
- Starting clean tag: `memory_review_approved_promotion_live_write_blockade_tamper_evidence_clean_1`
- Target clean tag: `memory_review_approved_promotion_final_readiness_packet_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_final_readiness_packet_smoke.py`.
- Builds the current valid dry-run safety chain and writes one operator packet
  with staged items, approval proof, source hashes, safety-chain PASS status,
  live-write blocked reasons, and operator next steps.
- The packet is dry-run only. Live memory writing remains blocked. Vector DB
  writing remains blocked. No live memory/vector write path is implemented.
  Future live write requires a separate explicit milestone.
- Added `project_guardian/tests/test_memory_review_approved_promotion_final_readiness_packet.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE_TAMPER_EVIDENCE.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; packet files are written
  only inside the temp workspace.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_final_readiness_packet_smoke.py --json --base-dir .\tmp\ap-final-readiness --keep-temp` and inspect the packet JSON and README.

## Campaign 35 - Memory review approved promotion final readiness packet tamper evidence (Cursor)

- Campaign name: Dry-run Memory review approved-promotion final readiness packet tamper evidence
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `49f885a feat(local): add approved promotion final readiness packet`
- Starting clean tag: `memory_review_approved_promotion_final_readiness_packet_clean_1`
- Target clean tag: `memory_review_approved_promotion_final_readiness_packet_tamper_evidence_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke.py`.
- Builds a clean final readiness packet, validates it as `PASS`, then writes
  isolated corrupted packet copies that must return `FAIL`.
- Covered failures include hash mismatches, item edits, rejected inclusion,
  safety-chain edits, live-write flag changes, missing blocked reasons, missing
  future milestone requirement, and unsafe metadata.
- Added `project_guardian/tests/test_memory_review_approved_promotion_final_readiness_packet_tamper_evidence.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET_TAMPER_EVIDENCE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_BLOCKADE_TAMPER_EVIDENCE.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; tamper-evidence files are
  written only inside the temp workspace.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- Future live write requires a separate explicit milestone.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke.py --json --base-dir .\tmp\ap-final-readiness-tamper --keep-temp` and inspect the clean packet plus each tampered copy.

## Campaign 36 - Memory review approved promotion final readiness operator acceptance gate (Cursor)

- Campaign name: Dry-run Memory review approved-promotion final readiness operator acceptance gate
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `fbd2193 feat(local): add approved promotion final readiness tamper evidence`
- Starting clean tag: `memory_review_approved_promotion_final_readiness_packet_tamper_evidence_clean_1`
- Target clean tag: `memory_review_approved_promotion_final_readiness_operator_acceptance_gate_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke.py`.
- Builds a valid final readiness packet and its tamper evidence, then requires a
  separate explicit operator acceptance artifact.
- Missing acceptance fails closed. An invalid acceptance phrase fails closed. A
  mismatched packet hash fails closed. A mismatched tamper-evidence hash fails
  closed. Valid acceptance only accepts final dry-run readiness. Valid
  acceptance does not authorize live memory writes. Valid acceptance does not
  authorize vector DB writes. Future live write still requires a separate
  explicit campaign.
- Added `project_guardian/tests/test_memory_review_approved_promotion_final_readiness_operator_acceptance_gate.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_OPERATOR_ACCEPTANCE_GATE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET_TAMPER_EVIDENCE.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; acceptance-gate files are
  written only inside the temp workspace.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- Future live write still requires a separate explicit campaign.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke.py --json --base-dir .\tmp\ap-final-acceptance-gate --keep-temp` and inspect the gate JSON, README, and fail-closed acceptance cases.

## Campaign 37 - Memory review approved promotion final readiness operator acceptance gate tamper evidence (Cursor)

- Campaign name: Dry-run Memory review approved-promotion final readiness operator acceptance gate tamper evidence
- Branch: `codex/limited-live-activation-wrapper`
- Starting HEAD: `acba79f feat(local): add approved promotion final readiness acceptance gate`
- Starting clean tag: `memory_review_approved_promotion_final_readiness_operator_acceptance_gate_clean_1`
- Target clean tag: `memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_clean_1`

### What changed

- Added `scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke.py`.
- Builds a clean acceptance gate report, validates it as `PASS`, then writes
  isolated corrupted copies that must return `FAIL`.
- Covered failures include phrase changes, hash mismatches, missing acceptance
  case, invalid case marked pass, valid case marked fail, live-write
  authorization, vector-write authorization, future campaign requirement
  removal, and unsafe metadata.
- Valid acceptance remains dry-run-only. Live memory writing remains blocked.
  Vector DB writing remains blocked. No live memory/vector write path is
  implemented. Future live write requires a separate explicit campaign.
- Added `project_guardian/tests/test_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence.py`.
- Added `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_OPERATOR_ACCEPTANCE_GATE_TAMPER_EVIDENCE.md`.
- Updated `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_OPERATOR_ACCEPTANCE_GATE.md`,
  `docs/MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_PACKET_TAMPER_EVIDENCE.md`,
  `docs/MEMORY_IMPORT_REVIEW_HANDOFF.md`, and this handoff.

### Safety notes

- Uses local fixtures and temporary workspaces only; tampered copies are
  written only inside the temp workspace.
- Live memory writing is not implemented or enabled.
- Vector DB writing is not implemented or enabled.
- Future live write still requires a separate explicit campaign.
- This campaign does not call models.
- This campaign does not call embeddings.
- This campaign does not use live accounts.
- This campaign does not add UI actions or routes.
- `elysia/api/server.py` was untouched.
- `project_guardian/core.py` was untouched.
- `config/autonomy.json` was untouched and remains `enabled=false`.
- Operators can run `python scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke.py --json --base-dir .\tmp\ap-final-acceptance-gate-tamper --keep-temp` and inspect the clean acceptance gate report plus each tampered copy.
