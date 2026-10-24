# Elysia dashboard runtime UI acceptance — 2026-10-23

Verdict: **PARTIAL**

The Flask control panel now loads, leaves "Initializing...", reports the attached backend honestly, lists the configured local model, and delivers a fictional chat reply from that backend. The GuardianCore launcher and a live Ollama model were not available in this environment, so the full Windows stack from the October 22 note was not re-certified.

Inspection and browser verification ran on Friday, October 23, 2026, about 8:37 PM ET. HTTP timestamps below that end in no zone were produced by the UTC machine clock.

## 1. Original browser and runtime failures

This checkout is published `main` at `722d8e4` (merge of PR #2). `REPORTS/runtime_diagnosis_2026-10-22/FINAL_REPORT.md` is not in this repository. The working tree had no uncommitted JavaScript repair to preserve. Ports 5000 and 8888 were not listening, and Ollama was not running.

Reproduced on this tree before the repair:

| Defect | Where | What happened |
| --- | --- | --- |
| `/api/status` HTTP 500 | `project_guardian/ui_control_panel.py` `get_status` | An inner `from datetime import datetime` made `datetime` local to the whole function. With no orchestrator, or with an orchestrator and no `start_time`, the handler raised `UnboundLocalError`. The `except` block used `datetime` too, so Flask returned 500. This is the defect called out on draft PR #149. |
| False Running | Same file, status JSON and the page script | Merely having a memory or loop object set `running` and `initialized`. On a failed status fetch the page substituted `{running: true, initialized: true}` and painted the green Running indicator, including the 2-second "Connected (Limited)" timer. |
| Invented metrics | `/api/status` | Trust was reported as `0.8` and security counters as `0` when those values had not been read. The trust fields in the page were never filled from the response. |
| Chat could sit on "Sending..." | Control-tab script | The chat request had no timeout and treated a non-JSON error body as a thrown exception only after `response.json()`. |
| No model availability | Control panel | The page had no readout of the configured Ollama tag versus tags actually installed on loopback. |
| Launcher cannot import | `project_guardian/__init__.py` → `core.py` | Left unrepaired. See remaining limitations. |

`node --check` on the published page script succeeded. `window.toggleTheme` is defined on this `main`. The rendered-JavaScript syntax error described on PR #149 is not in this published template.

The page that actually serves the operator dashboard is the inline template in `UIControlPanel` (`project_guardian/ui_control_panel.py`), reached by `start_ui_panel.py` only after `GuardianCore` constructs. `project_guardian/ui/app.py` and `project_guardian/ui/templates/dashboard.html` are a separate FastAPI review UI and were not the process under test.

## 2. Repairs completed

All edits are on `cursor/dashboard-ui-acceptance-2389`.

- `/api/status` always returns JSON with a timestamp. Running is true only when `_running is True` or the event loop's `running is True`. Initialized is true only when `_initialized is True`. Missing uptime, queue size, memory count, violations, and trust are JSON `null`, which the page shows as an em dash.
- A status-collector exception returns HTTP 200 with `system.error` set and `running: false`, so the header shows the error instead of an uncaught 500.
- The page stays on "Connecting..." until `/api/status` returns. A failed or timed-out poll sets **Offline**, clears uptime, and marks the loop unknown. It does not keep the last Running state. Socket.IO disconnect checks `/api/ping` and uses the same Offline state when HTTP is gone.
- `GET /api/models` reports the canonical Ollama name (`ELYSIA_OLLAMA_MODEL`, `OLLAMA_MODEL`, then `config/mistral_decider.json`, otherwise `mistral:7b`) and the tags from loopback `GET /api/tags`. Non-loopback `OLLAMA_HOST` values are refused. The probe does not pull a model and does not call a paid API.
- `POST /api/chat` still uses an attached `chat_with_llm` or `ask_ai`. With neither attached, it returns HTTP 400 JSON whose `error` explains that no backend is attached and whether loopback Ollama is reachable. The button aborts after 20 seconds.
- Pause and resume return HTTP 400 `Event loop is not attached` when no loop is present, instead of raising on a missing orchestrator.
- The model config helper is loaded from `ollama_model_config.py` by file path so the panel can describe the model even when `import project_guardian` fails.

## 3. Features actually tested

Tested in headless Chrome (puppeteer-core, system Chrome) against a disposable in-process orchestrator on `127.0.0.1:8765`. That object had `_initialized = True`, `_running = False`, no loop, and `ask_ai` returning `FICTIONAL_REPLY:` plus the message. No provider, credential, or Ollama pull was used.

| Check | Result |
| --- | --- |
| Page load, zero `pageerror` events | Pass. Header left "Initializing..." / "Connecting..." and settled on **Initialized**. |
| `/api/ping` | HTTP 200 `{"ok": true, "service": "elysia-control-panel", "port": 8765, "orchestrator": true}` |
| `/api/status` | HTTP 200. `running: false`, `initialized: true`, `orchestrator_attached: true`, `uptime: null`, loop `attached: false`. Matches the fictional object. |
| Online / offline | While the server was up, Socket.IO connected and the header was Initialized. After the server process was stopped, the open page changed to **Offline** (red), loop `unknown`, uptime em dash. It did not remain Running. |
| Tabs | Dashboard, Learning, Tasks, Security, Memory, Introspection, Control, Logs each became the active pane. |
| Theme | Toggle switched `data-theme` to `light`. After reload the theme was still `light` and the header returned to Initialized. |
| Models | Configured `mistral:7b` from `config/mistral_decider.json`. Available `none`. Detail: connection refused to `http://127.0.0.1:11434/api/tags`. |
| Fictional chat | Control tab sent `hello fictional profile`. The result element became `FICTIONAL_REPLY:hello fictional profile`. HTTP replay of the same body was HTTP 200 `success: true`. |
| Empty chat | HTTP 400 `{"success": false, "error": "message is required", "reply": null}` |
| Pause with no loop | Log line: `Pause: Event loop is not attached`. Chrome recorded the HTTP 400. |
| Logs | The log pane recorded load, Socket.IO connect, status received, chat OK, and the pause result. |
| Suggest Next Action | Reselecting Dashboard calls `GET /api/next-action`. With no `get_next_action` method the route returns HTTP 503 `{"success": false, "error": "Next action not available"}`. The page script writes `data.error` into the card. This is an absent backend method, not a hung control. |

Not claimed as working:

- Autonomy enable writes `config/autonomy.json`. It was not clicked.
- Speak, dream cycle, memory snapshot, task submit, income, harvest, research proposal, prompt evolution, wallet, and learning actions call GuardianCore or the unified system. Those objects were not running. Their buttons are wired, and they fail when the backend method is missing.
- `project_guardian/ui/app.py` was not started.

Console notes that are not JavaScript exceptions: a Chrome warning that a password field is not inside a form, the HTTP 503 from next-action, and the HTTP 400 from pause. `requestfailed` was empty, and the log recorded `Socket.IO connected`, so the Socket.IO client script loaded in this environment.

## 4. Test results

```text
python3 -m pytest tests/test_dashboard_status_truth.py tests/test_dashboard_listening.py tests/test_dashboard_idempotent.py -q
22 passed in 9.83s
```

`tests/test_dashboard_status_truth.py` covers the datetime 500, idle-object false Running, explicit running flags, paused loop, collector exceptions, ping identity, model available and unavailable, chat with and without a backend, pause without a loop, `node --check` on the inline script, and refusal of a non-loopback Ollama host.

`tests/test_dashboard_listening.py` and `tests/test_dashboard_idempotent.py` now load the panel by file path. On this machine `from project_guardian.ui_control_panel import UIControlPanel` raises `ModuleNotFoundError: No module named 'openai'` inside `mutation.py` before the panel module is reached. The listening test for a failed server bind now expects `is_ready() is False` and a stored server error. `start()` is written not to raise in that case (`never raise` in `UIControlPanel.start`).

## 5. Backend and model connectivity

Executed path for this verification:

`UIControlPanel` constructed directly from `project_guardian/ui_control_panel.py` → Flask + Flask-SocketIO on `127.0.0.1:8765` → fictional `ask_ai`.

Normal operator path, not executed because import fails:

`start_ui_panel.py` → `from project_guardian import GuardianCore` → `core.py` imports `mutation.py` → `import openai` → `ModuleNotFoundError`.

`project_guardian/core.py` also imports `project_guardian.module_activity` (lines 51–55). That file is absent. It is reached only after the `openai` import succeeds. Draft PR #149's missing launcher import is still present. Those modules belong to the launcher and memory/task stack and were not edited.

Model evidence from the live panel (`GET /api/models`, HTTP 200):

```json
{
  "configured": {"provider": "ollama", "name": "mistral:7b", "available": false, "source": "config/mistral_decider.json or default"},
  "available": [],
  "ollama": {"reachable": false, "endpoint": "http://127.0.0.1:11434/api/tags", "error": "<urlopen error [Errno 111] Connection refused>"}
}
```

The October 22 note that `llama3.2:3b` was installed was not true of this machine today. No model was downloaded and no external provider was called. Chat success in the browser was the fictional `ask_ai` echo, which proves browser-to-backend routing for the supported chat route.

## 6. Remaining limitations

- **PARTIAL** because GuardianCore cannot boot here, and there is no local model process to answer a generation request.
- Cross-boundary, not modified: `project_guardian/__init__.py`, `core.py`, `mutation.py`, the missing `module_activity.py`, `start_ui_panel.py`, `start_control_panel.py`, task and memory modules.
- Installing `openai` or adding `module_activity.py` would be the next launcher repair and was left for the backend owner.
- Controls that need GuardianCore methods remain unavailable until that launcher imports.
- `stop()` still does not by itself close Socket.IO's listener; this run stopped the process.
- The model detail string includes Python's `urlopen` error text. It is accurate and a bit raw.

## 7. Files modified and rollback

| File | Change |
| --- | --- |
| `project_guardian/ui_control_panel.py` | Status truth, Offline UI, `/api/models`, chat errors, pause/resume guard |
| `tests/test_dashboard_status_truth.py` | New regression tests |
| `tests/dashboard_panel_loader.py` | Loads the panel without importing GuardianCore |
| `tests/test_dashboard_listening.py` | Use that loader; reset the start guard; assert failed bind is not ready |
| `tests/test_dashboard_idempotent.py` | Use that loader |
| `REPORTS/runtime_ui_acceptance_2026-10-23/FINAL_REPORT.md` | This report |
| `REPORTS/runtime_ui_acceptance_2026-10-23/evidence/` | HTTP bodies, headers, and Chrome screenshots |

Rollback: check out `main` and delete the branch. The original checkout at `722d8e4` does not contain these edits.

```bash
git checkout main
git branch -D cursor/dashboard-ui-acceptance-2389
git push origin --delete cursor/dashboard-ui-acceptance-2389
```

No merge, deploy, credential change, or provider activation was performed.
