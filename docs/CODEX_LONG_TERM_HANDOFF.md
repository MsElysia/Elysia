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
