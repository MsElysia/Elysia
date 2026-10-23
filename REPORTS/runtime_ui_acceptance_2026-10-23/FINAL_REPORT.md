# Elysia Dashboard Runtime / UI Acceptance — 2026-10-23

**Verdict: PARTIAL**

The existing browser interface (`project_guardian/ui_control_panel.py`) now communicates
truthfully with its Flask backend: `/api/status` no longer returns HTTP 500, the header no
longer fabricates "Running", a lost backend is detected and shown as "Disconnected", model
availability is reported from the recorded planner probe, and chat failures are surfaced as
errors instead of successful replies. All of this was verified in a real headless Chrome
against a live Flask/Socket.IO instance.

It is PARTIAL, not PASS, because the verification ran on a clean cloud checkout of
`origin/main` (`722d8e4`), not on the operator's Windows installation, and because the
`project_guardian` package on `main` cannot be imported at all (two backend import defects
outside this task's ownership). The normal launchers therefore cannot start the dashboard on
`main`, and no real Ollama/`llama3.2:3b` route was available to exercise.

Executed: Friday 2026-10-23, 19:33–19:57 EDT (America/New_York). Agent: Cursor cloud agent
("Elysia Windows Dashboard and Integration Engineer"). Branch:
`cursor/dashboard-runtime-ui-acceptance-d019`, base `main` @ `722d8e4fe85d7e42ac34066c2d651849d15e734c`
(fetched; local `main` was identical to `origin/main`).

---

## 0. Environment and what could / could not be inspected

| Item | Finding |
|---|---|
| Checkout | `/workspace` on `main` @ `722d8e4`, `git status` clean. **No uncommitted operator changes existed in this checkout**, so there was nothing to preserve here. The "yesterday's JavaScript repair" and the 810-file local delta mentioned in PR #149 exist only on the operator's Windows machine and are not in the remote. |
| `AGENTS.md` | Not present in the repository (searched depth 3). |
| `REPORTS/runtime_diagnosis_2026-10-22/FINAL_REPORT.md` | Not present in the repository. The 22 Oct observations could not be re-read; they were treated as unverified history. |
| Running services | No Elysia process, nothing listening on 5000/8888, no Ollama (`127.0.0.1:11434` connection refused, `ollama` binary absent). Only VM infrastructure processes were present; none were touched. |
| Python / deps | CPython 3.12.3, Flask 3.1.3, Flask-SocketIO 5.7.0, Werkzeug 3.1.9, pytest 9.1.1. Installed with `pip --user`: flask, flask-socketio, flask-cors, pytest, requests, psutil, PyYAML, httpx, beautifulsoup4, cryptography, openai, pyttsx3, playwright. Nothing installed into the repo. |
| Browser | Google Chrome 156.0.8078.47 (system), driven headless via Playwright for Python. |
| External calls | None. No provider activation, no downloads of models, no credentials touched. The chat backend used in testing was a fictional in-process stub. |

### Execution path (confirmed by reading the code)

```
Browser  ──GET /──────────────► Flask (UIControlPanel.app, render_template_string)
         ──GET /api/status──► get_status()  → orchestrator attributes (GuardianCore / stub)
         ──Socket.IO────────► flask_socketio (only emits "Connected" on connect; no status pushes)
         ──POST /api/chat───► orchestrator._unified_system.chat_with_llm()  (when run under elysia.py:
                                 unified_llm_route → Ollama or cloud)
                               else orchestrator.ask_ai() → AIInteraction.ask_chatgpt() (cloud OpenAI)
```

* Dashboard code actually executed: `project_guardian/ui_control_panel.py` (HTML/JS template +
  Flask routes). There is no separate static JS/CSS file; the template is inline.
* Launchers: `start_ui_panel.py`, `start_control_panel.py` → `GuardianCore(ui_config=...)` →
  `UIControlPanel.start()` (thread, `socketio.run`). `project_guardian/ui/app.py` referenced by
  `tests/test_ui_smoke.py` (FastAPI) does **not** exist on `main`; that test skips.
* Live status polling is HTTP (`/api/status` every 2 s). Socket.IO only logs connect/disconnect.
* There is **no model selector** in the dashboard. Nothing in the UI let an operator choose a
  model before this work, and no selector was added (out of scope); a read-only
  Local Model / Model State readout was added instead (see §2).

---

## 1. Original browser/runtime failures (reproduced on `main` @ `722d8e4`)

All reproduced against a disposable fictional instance (`/tmp/elysia_verify/fictional_dashboard.py`,
not committed) that loads `ui_control_panel.py` directly and supplies a duck-typed orchestrator.

| # | Defect | Evidence |
|---|---|---|
| F1 | **`/api/status` → HTTP 500** (`UnboundLocalError: cannot access local variable 'datetime'`). A function-local `from datetime import datetime` inside `get_status()` made `datetime` local to the whole function, so every path that ran before that line (orchestrator `None`, or `start_time` is `None`) crashed, including the `except` handler. | `curl /api/status` → 500 for modes `none` and `idle`; server log shows the traceback at line 2390. Same defect PR #149 observed on Windows. **Still present.** |
| F2 | **False "Running" (backend).** `is_running = _running or loop_running or memory_loaded or has_core` — merely owning a `memory` object produced `system.running: true`; with no `elysia_loop`, `loop.running` was set to the *initialized* flag. | Flask test client, `_running=False`, `elysia_loop=None`, `start_time=now()` → `{"system":{"running":true},"loop":{"running":true}}`. |
| F3 | **False "Running" (frontend).** On any `/api/status` failure the JS called `updateDashboard({system:{running:true,initialized:true},loop:{running:true}})`, and the 2 s "safety" timers set the green `status-running` class. | Browser on baseline: `/api/status` was 500, yet header read **"Running"** at t=0.23 s; log: "Status fetch failed: HTTP 500 … - using fallback". Screenshot `baseline_idle/05_after_server_kill.png`. |
| F4 | **Server loss never detected.** Interval poll errors were swallowed ("keep showing last known status"). | Server killed at t≈14 s; header still "Running" / `status-running` 8 s later (16 samples). |
| F5 | **Chat errors reported as success.** `/api/chat` returned `success:true, reply:"Error: No OpenAI API key…"` when `ask_ai()` failed; the UI logged "Chat: OK". No request timeout: a hung model left "Sending…" forever. | Test client with stub `ask_ai` returning an `Error:` string → `success: true`. |
| F6 | **No model availability anywhere.** `/api/status` had no LLM/Ollama/planner information; the dashboard could not report whether the local model was reachable or installed. | Response keys: `loop, memory, modules, runtime, security, system, timestamp, trust`. |
| F7 | **Launcher import failure (backend, not repaired here).** `import project_guardian` fails: `core.py` imports `.module_activity` (file missing on `main`) and, after shimming that, `log_autonomy_exploration_routine`/`log_autonomy_routine` from `planner_readiness` (also missing on `main`). Both exist on other draft branches (e.g. commit `7081570 fix(guardian): restore missing import dependencies`). | `python3 -c "import project_guardian"` → `ModuleNotFoundError: No module named 'project_guardian.module_activity'`. `start_ui_panel.py` / `start_control_panel.py` cannot run. This is the "missing launcher import" from PR #149; **still present.** |
| — | JavaScript syntax error / stuck "Initializing" (22 Oct report, PR #149). | **Not reproducible on `main`**: `node --check` on the rendered inline script passes and no `pageerror` events occurred in any browser run. That defect lived in the operator's local template only. |

Baseline browser run also confirmed that tabs, theme toggle, chat round-trip, and
Pause/Resume (400 "not available" with no loop — truthful) worked.

---

## 2. Repairs completed (all in dashboard-owned files)

Commits on `cursor/dashboard-runtime-ui-acceptance-d019`:

* `b7d5fc9` fix(dashboard): truthful /api/status, model availability, chat error handling
* `7515ef0` fix(dashboard): show 'unknown' with reason when model config is unreadable

### `project_guardian/ui_control_panel.py`

| Fix | Change |
|---|---|
| F1 | Removed the function-local `from datetime import datetime`; the module-level import is used. `/api/status` returns 200 JSON in every path, including orchestrator `None` and the exception path. |
| F2 | `is_running = bool(_running_attr or loop_running)`. `is_initialized` keeps the broader signals so the UI does not stick on "Initializing". With no `elysia_loop`, `loop` is `{"running": false, "available": false, …}`. The exception path reports `loop.running: false`. |
| F3 | Fabricated fallback removed. Status failures route through `noteStatusFailure()` → `markBackendUnreachable()`; header shows **"Disconnected"** or **"Status error: HTTP nnn"** with the red `status-stopped` class. Interim text is "Connecting…"/"Connected (no status yet)" with the neutral `status-connected` class; "Connected (Limited)" and all `status-running` fallbacks are gone. `updateDashboard` only shows "Running" when the backend says `system.running` or `loop.running`; loaded memory/uptime now yield "Initialized". |
| F4 | Two consecutive poll failures (≈4 s) flip the header to Disconnected and log once; recovery logs "Backend status restored" and resumes normal state. |
| F5 | `/api/chat`: `ask_ai` replies that are empty or start with `Error:` / `[AI Interaction Error]` return `success:false, error:<text>`; "no backend" returns 400 with `success:false`. Frontend: 90 s `AbortController` timeout, non-JSON guard, result shows `Model error: …` / `Chat error: …` and logs `Chat failed`. |
| F6 | New read-only `UIControlPanel._collect_llm_status()` added to `/api/status` as `"llm"`: `state` (`ready`/`degraded`/`unavailable`/`unknown`), `canonical_model` (via `ollama_model_config.get_canonical_ollama_model`), `ollama_reachable`, `model_installed`, `installed_model_tags`, `chat_backend`, `detail`. Sourced only from `planner_readiness.snapshot_startup_dict()` (state recorded by the startup probe) — it never opens a connection, so polling every 2 s is safe. `compact_runtime_status()` was deliberately **not** used because its `maybe_refresh_model_install_if_stale()` can perform a 12 s Ollama health call. Two new metrics in the System Status card: **Local Model** and **Model State** (tooltip carries `detail` and `chat_backend`). When the package cannot be imported, `state` is `unknown` and `detail` carries the real import error. |

### `tests/test_dashboard_status_truth.py` (new, 22 tests)

Loads the packaged module when possible and falls back to a standalone load of
`ui_control_panel.py`, so the dashboard surface is testable while the backend package is broken.
Covers F1–F6 plus ping, template element presence, and a `node --check` syntax test on the
rendered JavaScript (skips if Node is absent).

---

## 3. Features actually tested (headless Chrome against a live Flask + Socket.IO instance)

Probe script: `/tmp/elysia_verify/browser_probe.py` (not committed). Captured console
messages, `pageerror`, failed requests, `/api/*` responses, status-text timeline, screenshots.
Fictional modes: `none` (no orchestrator), `idle` (memory, no loop, `_running=False`),
`running`, `chaterror`, `probed_ready` / `probed_unavailable` (fictional planner probe results
for `llama3.2:3b` recorded in-process — no Ollama contacted).

| Mission item | Result (repaired) | Notes |
|---|---|---|
| 1. Page loads without JS exceptions | **PASS** | `pageerror` = [] in all 7 runs; `node --check` passes. Console "Failed to load resource" entries are genuine 400/503/ERR_CONNECTION_REFUSED responses, listed below. |
| 2. "Initializing" transitions to correct state | **PASS** | idle: `Connecting…` (0.18 s) → **Initialized** (0.68 s). running: **Running**. none: **Error: Orchestrator not available** (red). Spinner hidden. |
| 3. `/api/ping` identifies the app | **PASS** | `{"ok":true,"service":"elysia-control-panel","port":…,"orchestrator":…}` HTTP 200. |
| 4. `/api/status` valid and accurate | **PASS** | 200 in all modes; `running` only when a run signal exists; `loop.available:false` when no loop; `llm` block present. |
| 5. Online/offline indicators reflect backend | **PASS** | After `SIGINT` to the server: Initialized → **Disconnected** (red) within ~3 s; log "Backend status unavailable: Backend unreachable (connection failed)". Baseline stayed "Running" indefinitely. |
| 6. Navigation / buttons / theme | **PASS (tested subset)** | All 8 tabs switch; Toggle Theme dark→light; Pause/Resume return truthful 400 "not available" without a loop. Not exercised: Dream Cycle, Speak, Submit Task, learning/wallet/harvest/research buttons (write-capable or provider-backed; see §6). |
| 7. Model selection shows actual models | **PARTIAL** | No selector exists in this UI. New readout shows **Local Model: llama3.2:3b / Model State: ready** when the probe recorded that, **unavailable** (with `connection refused` detail) when not, **unknown** (with the import error) when the package is unreadable. Values are the recorded startup probe, not a live `ollama list`. |
| 8. Fictional message reaches backend and returns | **PASS** | Control tab → "fictional acceptance ping" → `/api/chat` 200 → result "[fictional-local-model] echo: fictional acceptance ping"; log "Chat: OK". Route proven to `/api/chat` → `orchestrator.ask_ai`. The real model was not involved (none available). |
| 9. Model failures give actionable errors | **PASS** | `chaterror` mode: result "Model error: Error: No OpenAI API key configured…"; log "Chat failed: …". `none` mode: "Model error: No chat backend available (unified system or ask_ai)". 90 s timeout wired (not waited out). |
| 10. Logs/task status reflect real events | **PASS** | Logs tab shows load, Status update received, Theme, Chat OK/failed, Pause/Resume results, Disconnected, Backend status unavailable. Tasks tab `/api/tasks/list` 200 (empty list for the stub). |
| 11. Refresh preserves state | **PASS (theme)** | Theme `light` persisted via `localStorage`; status re-derived correctly after reload. Active tab is not persisted (never was; not a defect claimed by the UI). |
| 12. Interruption detected, no false "Running" | **PASS** | See item 5 and screenshots. |

Browser `/api/*` responses observed (idle mode): `/api/status 200`, `/api/ping 200`,
`/api/chat 200`, `/api/autonomy 200`, `/api/tasks/list 200`, `/api/introspection/debug 200`,
`/api/learning/settings 200`, `/api/learning/linked-accounts 200`, `/api/next-action 503`
(stub has no `get_next_action` — correct), `/api/control/pause|resume 400` (no loop — correct).

Screenshots (uploaded with the PR): `baseline_server_killed_still_running.png`,
`repaired_server_killed_disconnected.png`, `repaired_running_model_ready.png`.

---

## 4. Test results

```
# New regression tests, repaired module
python3 -m pytest tests/test_dashboard_status_truth.py -q
22 passed in 0.84s

# Same tests against the unmodified main module (git stash of ui_control_panel.py)
18 failed, 4 passed in 0.92s
```

Existing dashboard tests, run three times each with and without the repair (identical):

```
python3 -m pytest tests/test_dashboard_listening.py tests/test_dashboard_idempotent.py -q
4 failed, 5 passed   (baseline main)
4 failed, 5 passed   (repaired)
```

The 4 pre-existing failures are not caused or fixed by this work: two fail at import
(`No module named 'project_guardian.module_activity'`, F7) and two assert `start()` readiness
semantics (`_actual_port`, `DID NOT RAISE RuntimeError`) that drafts #147/#148/#149 address;
which two fail varies between runs (timing-dependent). `tests/test_ui_smoke.py` and the other
`test_ui_*` files skip (FastAPI `project_guardian.ui.app` does not exist on `main`).

Broader suite run: `tests/test_dashboard_* tests/test_ui_*` → `4 failed, 27 passed, 39 skipped`
(same 4 as above). `git diff --check` clean.

---

## 5. Backend and model connectivity evidence

* Live Flask/Socket.IO process: `python3 /tmp/elysia_verify/fictional_dashboard.py <mode> <port>`
  (`UIControlPanel.start()` → `socketio.run`, Werkzeug). Server logs captured in
  `/tmp/elysia_verify/*.log`; baseline log contains the `UnboundLocalError` traceback (3 hits).
* Browser → backend: Socket.IO connect ("Connected to Elysia system"), HTTP polling of
  `/api/status` every 2 s, chat POST round-trip, all observed in the Chrome network log.
* Model route: proven as far as `/api/chat` → `orchestrator.ask_ai` (stub). On the operator's
  machine the same route continues to `AIInteraction.ask_chatgpt` (cloud) unless Guardian runs
  under `elysia.py`, where `_unified_system.chat_with_llm` → `unified_llm_route` chooses Ollama or
  cloud. **No Ollama existed on this VM; `llama3.2:3b` availability could not be confirmed today.**
  The dashboard's `llm` block will show the real probe result when run on the operator's
  installation (it reads `planner_readiness` state written by `run_startup_planner_probe`).
* Nothing paid or external was called.

---

## 6. Remaining limitations and cross-boundary defects (not modified)

1. **Backend package does not import on `main` (Codex-owned, reported only).**
   `project_guardian/core.py` lines 51–56 import `module_activity` (missing file) and
   `log_autonomy_exploration_routine` / `log_autonomy_routine` from `planner_readiness`
   (missing functions). Until these land, `start_ui_panel.py`, `start_control_panel.py`, and
   `from project_guardian.ui_control_panel import …` all fail on `main`, and the dashboard's
   Local Model readout will show `unknown` with that import error as the detail. Both symbols
   exist on `origin/chatgpt/guardian-pr145-direct-save-fence-20261020` and in commit `7081570`.
2. **Chat default backend is cloud, not local.** Under plain `GuardianCore` the dashboard chat
   calls `ask_chatgpt` (OpenAI). Local-model chat only happens when Guardian is embedded in the
   unified Elysia system. The dashboard now labels this (`llm.chat_backend`), but routing is
   backend-owned and unchanged.
3. **Model readout is the recorded startup probe**, not a live `ollama list`. If Ollama goes
   down after startup, `Model State` stays as last recorded until the planner's own recheck
   updates it. A live probe was avoided to keep `/api/status` non-blocking.
4. **Not exercised (write-capable / provider-backed):** Trigger Dream Cycle, Speak (TTS),
   Submit Task, learning start/test, link Facebook/X tokens, wallet add, harvest, research
   proposal, prompt evolution, autonomy toggle (writes `config/autonomy.json`). Their wiring was
   read, not clicked. Items such as the "Learning Sources" success badges are static decoration.
5. **Pre-existing `start()` readiness tests fail/flake** (see §4); handled by drafts #147–#149.
6. **Socket.IO is connect-only.** No `status_update` events are emitted by the server; the client
   handler exists but is never fed. Live state comes from HTTP polling.
7. **Active tab is not persisted across refresh** (only theme is).
8. Verification was on Linux/Chrome in a cloud VM with a fictional orchestrator, not on the
   operator's Windows/Edge installation.

---

## 7. Files modified and rollback

Changed (2 files, +551 / −60):

* `project_guardian/ui_control_panel.py` — status route, chat route, `_collect_llm_status()`,
  template JS/HTML (System Status card, polling/failure handling, chat handler).
* `tests/test_dashboard_status_truth.py` — new.
* `REPORTS/runtime_ui_acceptance_2026-10-23/FINAL_REPORT.md` — this report.

Not committed (disposable, under `/tmp/elysia_verify/`): `fictional_dashboard.py`,
`browser_probe.py`, logs, JSON results, screenshots.

Rollback:

```
# Discard the whole draft (nothing is merged or deployed):
git branch -D cursor/dashboard-runtime-ui-acceptance-d019

# Or revert only the code repair, keeping the report:
git revert 7515ef0 b7d5fc9

# Or restore the single module to main's version:
git checkout 722d8e4 -- project_guardian/ui_control_panel.py
```

The operator's existing installation is untouched: all work happened in a cloud checkout on a
new branch; `main` was not modified; no files outside the repository were created except under
`/tmp` and the artifact upload directory.

---

## Verdict

**PARTIAL.** The interface now provably talks to its backend and tells the truth about state,
backend loss, chat failures, and (where the backend can report it) local model availability —
verified in a real browser, with regression tests that fail on the unmodified module. It is not
PASS because the backend on `main` cannot be launched through its normal entry points (F7,
outside this task's ownership) and no real local model was available to exercise end to end.
