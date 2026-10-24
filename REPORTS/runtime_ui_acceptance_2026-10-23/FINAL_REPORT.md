# Elysia Runtime UI Acceptance — 2026-10-23

## Verdict: PARTIAL

The existing dashboard is usable and now reports backend loss truthfully. Its
page, polling, navigation, theme persistence, model-status display, and chat
route passed an isolated browser test using the real dashboard template and
Flask routes.

This is not a full production PASS. No Elysia, dashboard, status API, or Ollama
process was running in this Linux cloud checkout at inspection time or after
testing. The normal launcher cannot currently import `GuardianCore`, so the
Windows installation and a real local-model response could not be certified.
No provider was activated and no model was downloaded.

## Scope and baseline

- Repository baseline: `main` at `722d8e4`.
- Working tree was clean; no uncommitted JavaScript or operator changes were
  present to preserve.
- No `AGENTS.md` was present.
- The requested historical report
  `REPORTS/runtime_diagnosis_2026-10-22/FINAL_REPORT.md` was not present.
- Historical PR #149 was inspected. Its reported status-scoping and false
  Running defects were still reproducible in current source.
- Initial listeners on `127.0.0.1:5000`, `:8888`, `:8123`, and `:11434`: none.
- Final listeners on those four ports: none.

## Executed connection path

The normal intended path is:

1. `elysia.py` creates `UnifiedElysiaSystem`.
2. `elysia_sub_guardian.py` creates `GuardianCore` with the UI enabled.
3. `project_guardian/core.py` creates `UIControlPanel`.
4. `project_guardian/ui_control_panel.py` serves the browser and UI API on
   loopback port 5000.
5. The dashboard polls its same-origin `/api/status`; Socket.IO is optional.
6. `/api/chat` delegates to `UnifiedElysiaSystem.chat_with_llm()` when attached.
7. Unified routing may call the configured Ollama model through the existing
   planner/router stack.

Port 8888 is a separate `elysia.py` status/chat server, not the server directly
polled by the dashboard. The browser test executed item 4 onward with an
isolated fictional orchestrator because the normal startup path is blocked.

## Original failures

1. `/api/status` imported `datetime` inside the route after earlier references.
   Python consequently treated it as a local variable and the
   no-orchestrator path raised `UnboundLocalError`.
2. Merely having core objects or loaded memories caused `/api/status` to report
   the system as running even when `_running` and the event loop were false.
3. A failed initial status request injected fabricated
   `running: true`/`initialized: true` data into the browser.
4. Later polling failures retained the last Running state indefinitely.
5. Chat errors used successful HTTP 200 responses and had no browser timeout,
   allowing poor failure feedback.
6. The dashboard did not expose the configured or actually installed local
   model list. The historical `llama3.2:3b` claim is not current configuration:
   this checkout configures `mistral:7b`.
7. The normal package/launcher import is blocked by missing runtime
   dependencies in this environment. After supplying Flask and OpenAI in a
   temporary test path, import next failed on `pyttsx3`; source also imports the
   absent `project_guardian.module_activity`. These are backend/launcher
   ownership defects and were not repaired here.

## Repairs completed

- Removed fabricated success fallback data from browser initialization.
- Added explicit Offline rendering on timeout, HTTP failure, or connection
  refusal.
- Changed volatile metrics (uptime, event loop, queue, active tasks) to
  `Unknown` when the backend becomes unreachable, avoiding stale status.
- Fixed `datetime` scoping in `/api/status`.
- Based `system.running` only on runtime flags, not component presence or
  loaded memory.
- Added read-only `/api/models`, which reports:
  - configured Ollama model;
  - Ollama base URL;
  - installed model names from `/api/tags`;
  - exact configured-model availability;
  - reachability and actionable transport error.
- Added a Local Model card to the existing dashboard.
- Corrected the chat label so it does not claim only OpenAI/OpenRouter routing.
- Made backend/model chat failures HTTP 503 and added a 60-second browser
  timeout with an actionable message.
- Added regression tests for ping identity, no-orchestrator status, false
  Running prevention, model status, chat failure status, and disconnect wiring.

## Functional evidence

### HTTP

The isolated acceptance server used the real `UIControlPanel` and a disposable
fictional orchestrator.

- `GET /api/ping` → HTTP 200:
  `{"ok":true,"orchestrator":true,"port":5000,"service":"elysia-control-panel"}`
- `GET /api/status` → HTTP 200 with
  `system.running=true`, `system.initialized=true`, and `loop.running=true` for
  the running fictional instance.
- `GET /api/models` → HTTP 200 with `configured_model="mistral:7b"`,
  `available_models=[]`, `configured_available=false`, `reachable=false`, and
  a connection-refused error for `127.0.0.1:11434`.
- `POST /api/chat` with a fictional moon prompt → HTTP 200 and the expected
  disposable backend response.

This proves browser-to-dashboard routing and truthful model discovery. It does
not prove a response from Ollama because Ollama was not running.

### Browser

Passed:

- page loaded and left Initializing without JavaScript exceptions;
- prominent status and event-loop state reflected successful polling;
- all eight existing tabs navigated;
- Tasks empty state loaded;
- theme toggled dark/light and persisted over refresh;
- fictional chat reached `/api/chat` and displayed its response;
- configured model displayed as `mistral:7b`;
- unavailable Ollama displayed as Offline with no models claimed;
- refresh restored live status;
- after intentional server interruption, the header changed to
  `Offline — Failed to fetch`, and uptime/event loop/queue/active tasks all
  changed to `Unknown`;
- only expected `ERR_CONNECTION_REFUSED` network messages appeared after
  interruption; no JavaScript syntax/runtime exception occurred.

Not claimed:

- write-capable autonomy, learning, memory, task submission, wallet, speech,
  dream-cycle, or provider controls were intentionally not exercised;
- empty informational panels were inspected, not treated as proof of their
  backend features;
- the Logs tab currently shows client-side UI events. The server only emits a
  connect status event, so it is not a complete backend log stream;
- `/api/next-action` returned 503 in the isolated harness, correctly indicating
  that the feature was unavailable;
- there is no model selector to test. The new card reports actual configured
  and available models without pretending that the UI can change routing.

### Screenshots

Useful run artifacts:

- `/opt/cursor/artifacts/screenshots/01-dashboard-initial.webp`
- `/opt/cursor/artifacts/screenshots/05-light-theme.webp`
- `/opt/cursor/artifacts/screenshots/06-theme-persisted.webp`
- `/opt/cursor/artifacts/screenshots/07-chat-response.webp`
- `/opt/cursor/artifacts/screenshots/14-network-all-successful.webp`
- `/opt/cursor/artifacts/screenshots/17-reconnected-latest.webp`
- `/opt/cursor/artifacts/screenshots/18-offline-metrics-unknown.webp`

## Test results

Passed:

```text
PYTHONPATH=/tmp/elysia-ui-deps python3 -m pytest -q tests/test_runtime_ui_acceptance.py
6 passed in 0.23s

node --check /tmp/elysia-dashboard.js
exit 0

git diff --check
exit 0
```

Blocked:

```text
PYTHONPATH=/tmp/elysia-ui-deps python3 -m pytest -q \
  tests/test_dashboard_idempotent.py \
  tests/test_dashboard_listening.py \
  project_guardian/tests/test_dashboard_readiness.py

ImportError while loading project_guardian/tests/conftest.py:
ModuleNotFoundError: No module named 'pyttsx3'
```

The repository dependency manifests are not sufficient for this clean
environment: root requirements omit Flask-SocketIO, while the UI requirements
describe a different FastAPI UI. Temporary dependencies were installed only
under `/tmp`; repository manifests and credentials were not changed.

## Remaining limitations and ownership handoff

1. **Backend/launcher:** repair dependency packaging and the missing
   `project_guardian.module_activity` module/import, then run the normal Windows
   launcher. This is outside the dashboard ownership boundary.
2. **Actual local model:** start the operator's existing Ollama instance and
   verify `/api/models` lists its exact tags. If `llama3.2:3b` remains desired,
   reconcile it with the current canonical `mistral:7b` configuration before
   testing chat. No model should be downloaded implicitly.
3. **Model-route evidence:** the unified chat method discards route metadata,
   so the dashboard can prove that its backend answered but cannot identify
   which provider/model generated a reply. Backend ownership should expose safe
   route metadata if that evidence is required.
4. **Socket.IO CDN:** the page depends on an external Socket.IO script, but HTTP
   polling remains functional if it is blocked. Vendoring was not introduced.
5. **Control truthfulness:** controls whose backing component is unavailable
   remain visible and report endpoint errors when used. They were not
   misrepresented as tested.

## Files modified

- `project_guardian/ui_control_panel.py`
- `tests/test_runtime_ui_acceptance.py`
- `REPORTS/runtime_ui_acceptance_2026-10-23/FINAL_REPORT.md`

No Codex-owned launch, task, or memory module was modified.

## Rollback

The work is isolated on `cursor/runtime-ui-acceptance-d1d5`. The safest rollback
is to abandon the draft branch. If the commits have been applied elsewhere,
revert the commits from newest to oldest with `git revert`; do not reset the
operator's working tree. Temporary test dependencies are under
`/tmp/elysia-ui-deps` and are not part of the repository.
