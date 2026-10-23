# Elysia Runtime UI Acceptance — 2026-10-23

**Verdict: PARTIAL**

The dashboard defects identified in PR #149 were reproduced and repaired, and the
repaired interface is verified truthful against a live local server and a DOM-level
browser simulation. It cannot be a full PASS: this environment is a Linux cloud VM,
not the operator's Windows machine — no Ollama service, no `llama3.2:3b`, and no
services on ports 5000/8888 were running at inspection time, so real local-model
generation and the full GuardianCore orchestrator could not be exercised end to end.
Those items are listed as remaining limitations with exact retest steps.

## Environment revalidation (Phase 1)

- Repo: `/workspace`, branch work on `cursor/elysia-dashboard-acceptance-d59d`.
  Working tree was clean at start; no uncommitted operator changes existed to preserve.
  `REPORTS/runtime_diagnosis_2026-10-22/` does not exist in this checkout (historical, Windows-side).
- Actually-executed dashboard: `project_guardian/ui_control_panel.py`
  (Flask + Flask-SocketIO, `UIControlPanel`, default 127.0.0.1:5000, template inline).
  A separate minimal Flask API exists at `elysia/api/server.py` (port 8123) — not the browser dashboard.
  FastAPI panel `project_guardian/ui/app.py` serves Guardian task pages, also not the Elysia dashboard.
- Live check at inspection (2026-10-23 evening ET): nothing listening on 5000, 8888, or 11434;
  no Ollama binary/process. Oct 22 baseline (ports 5000/8888 up, `llama3.2:3b`) is **not** today's state here.
- Configured local model in this checkout: `mistral:7b`
  (`config/mistral_decider.json` → `mistral_decider_model`; resolver `project_guardian/ollama_model_config.py`).
  There is no model-selection UI control and previously no `/api/models` endpoint in the dashboard.

## Original failures reproduced (Phase 2, before repair)

Using Flask test client against the real `ui_control_panel.py`:

| Check | Before repair |
|---|---|
| `GET /` | 200 |
| `GET /api/ping` | 200, identifies `elysia-control-panel` |
| `GET /api/status` (orchestrator `None`) | **500** — `UnboundLocalError: datetime` at the error handler |
| `GET /api/status` (idle orchestrator, no `start_time`) | **500** — same defect |
| `GET /api/status` (idle, components present) | 200 but `system.running=true`, `loop.running=true` although `_running=False` and no loop exists — **false "Running"** |
| `GET /api/models` | **404** (missing) |
| `POST /api/chat` (no chat backend) | 400 (misleading; not a client error) |
| JS on `/api/status` fetch failure | Fabricated `updateDashboard({system:{running:true,...}, loop:{running:true,...}})` → false Running |
| JS safety timers (2s/4s) | Forced `Connected (Limited)` + `status-running` class with no backend response |
| JS polling failure | Kept last known status forever — disconnection never shown |
| `start()` server failure | `_server_ready.set()` even on error → `is_ready()` could lie; no exception propagated |

Root cause of the 500: module-level `from datetime import datetime` was shadowed by a
function-local `from datetime import datetime` inside `get_status()`; every earlier/late
`datetime.now()` in that function (including in its own `except` handler) raised
`UnboundLocalError` whenever the inner import had not executed. This is the PR #149 defect, still present.

Inline JavaScript syntax itself parses cleanly (`node --check`) — yesterday's syntax repair held;
the remaining JS defects were truthfulness/error-handling, not syntax.

## Repairs completed (Phase 3 — dashboard-owned files only)

All in `project_guardian/ui_control_panel.py`:

1. Removed the function-local `from datetime import datetime` — fixes `/api/status` 500.
2. Truthful running: `is_running = bool(_running or loop_running)` (constructed components/memory no longer imply Running); loop status with no loop object is `running: false` (was mirroring `initialized`).
3. JS: deleted fabricated Running fallback, premature "Connected" timer, and forced `Connected (Limited)` timers. Added `showOffline()`: failed/timed-out status fetch, polling failure, and Socket.IO `disconnect` now show **Offline** (`status-stopped`), never stale Running. `updateDashboard` derives Running only from explicit `system.running`/`loop.running`; initialized-but-idle shows **Initialized**, backend-down shows **Offline**.
4. `POST /api/chat` with no chat backend now returns **503** (was 400); empty message still 400.
5. New `GET /api/models`: returns configured model (canonical resolver), live local Ollama probe (`/api/tags`, 1.5s timeout, localhost only — no external/paid calls), `configured_available_locally`, and which chat backend is wired. Availability is never fabricated.
6. `start()`: readiness event is no longer set on server error; a bind/run failure raises `RuntimeError` with the captured server error (aligns with existing `tests/test_dashboard_listening.py` expectation). No Codex-owned launch/task/memory modules were modified.

## Features actually tested (Phase 4)

- New regression suite `tests/test_dashboard_status_truth.py` — **10 passed** (status 200 in both former-500 cases, idle≠Running, running only with live loop, ping identity, chat 503/400, chat reply via stub `ask_ai`, `/api/models` truthful shape, no fabricated-Running in template, inline JS parses under `node --check`).
- Live server (real Socket.IO/Werkzeug on 127.0.0.1:5000, stub orchestrator):
  `GET /` 200; `/api/ping` 200 `elysia-control-panel`; `/api/status` 200 with `running:false`;
  `/api/models` 200 `configured_model:"mistral:7b"`, `local_ollama.available:false` with actionable connection-refused error; fictional `POST /api/chat` → `{"success":true,"reply":"stub-reply: ..."}`. Server then stopped; subsequent curl exits 7 (connection refused) — the UI polling path for exactly this case is covered below.
- DOM browser simulation (jsdom executing the real template JS, zero JS errors in all scenarios):
  backend fetch fails → `Offline`/`status-stopped`; backend idle → `Initialized`; backend running → `Running`. "Initializing" transitions truthfully in every case.
- Existing suites `tests/test_dashboard_listening.py` / `test_dashboard_idempotent.py`: **fail identically before and after** this change in this VM (6 failed, 3 skipped) due to missing optional deps in the import chain (`pyttsx3`, etc.) — verified via `git stash` baseline comparison; not a regression from these repairs.

## Remaining limitations

1. **Real local-model chat not verified**: no Ollama on this VM; `/api/chat` was verified through to a stub `ask_ai`, and `/api/models` correctly reports Ollama unreachable. Retest on Windows: start Ollama, confirm `GET /api/models` shows `available:true` and the configured tag listed, then send one fictional chat message.
2. **Full GuardianCore orchestrator not booted here** (heavy optional dependency chain unavailable in this VM); status truthfulness was verified against stub orchestrators covering None/idle/running-loop shapes.
3. **No true browser/screenshot run**: verification used jsdom DOM execution of the real template plus live HTTP. A headed-browser pass (theme toggle, tabs, refresh persistence, Socket.IO push) still needs one manual run on the Windows install; theme/tab handlers are wired in the template but were not clicked through in a real browser here.
4. Model *selection* remains display-only via the new `/api/models` data; there is no UI control to switch models (pre-existing absence, not a wiring defect).
5. Decorative/unwired controls were not claimed as working; only status, ping, chat, models, and status-driven indicators were verified.

## Files modified

- `project_guardian/ui_control_panel.py` (repairs above)
- `tests/test_dashboard_status_truth.py` (new regression tests)
- `REPORTS/runtime_ui_acceptance_2026-10-23/FINAL_REPORT.md` (this report)

## Rollback

```bash
git checkout main -- project_guardian/ui_control_panel.py
rm tests/test_dashboard_status_truth.py
# or: git revert <this PR's commit>
```

No data, credentials, provider, or gate changes were made; no external/paid API calls; no models downloaded.
