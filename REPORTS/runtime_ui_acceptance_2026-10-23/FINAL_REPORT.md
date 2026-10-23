# Elysia Runtime UI Acceptance — 2026-10-23

**Verdict: PARTIAL**

The browser dashboard (`project_guardian/ui_control_panel.py`, Flask + Socket.IO on port 5000)
now talks to its backend correctly and reports status truthfully. This was proven in a real
headless Chrome against the real dashboard code. It is **not** a full PASS for three reasons:

1. All testing ran on a Linux cloud VM with a clone of `MsElysia/Elysia` `main` at `722d8e4`, not on the
   operator's Windows installation. The operator's uncommitted JavaScript repair from 2026-10-22,
   the running services on ports 5000/8888, and the 2026-10-22 diagnosis report don't exist here.
2. No real local model was available. Ollama isn't installed on this VM, and downloading a model
   was out of scope. Model routing was verified against a clearly labelled Ollama-API **stub**, so
   `llama3.2:3b` itself was not exercised.
3. The normal launcher can't import the dashboard on `main`: `project_guardian/core.py` imports
   `project_guardian.module_activity`, which doesn't exist on `main`. This is a backend file outside
   the dashboard's ownership boundary, so it is reported below and was not changed. The real
   GuardianCore/UnifiedElysiaSystem chat path (`elysia.py` → `unified_chat_completion`) therefore
   could not be run end-to-end.

---

## 1. Original browser/runtime failures (reproduced on unmodified `main` 722d8e4)

| # | Failure | Evidence |
|---|---------|----------|
| F1 | `/api/status` returned **HTTP 500** whenever the orchestrator was missing **or** had no `start_time`. A nested `from datetime import datetime` inside `get_status()` made `datetime` function-local. Every `datetime.now()` outside that branch raised `UnboundLocalError`, including the error-fallback handler. This was the PR #149 defect, and it **remains on main**. | `evidence/base_A_status.txt`, `base_B_status.txt`, `base_D_status.txt` (all HTTP 500); server log `UnboundLocalError: cannot access local variable 'datetime'` |
| F2 | The header showed green **"Running"** in every scenario: with no orchestrator, with a stopped orchestrator, and with `/api/status` failing. Causes: (a) the JS fetch-failure handler injected a fabricated `{system:{running:true}, loop:{running:true}}` payload; (b) timers at 2s and 4s forced "Connected"/"Connected (Limited)" with a green indicator before any response; (c) the backend computed `running = … or has_core` (components constructed counted as running) and set `loop.running = initialized` when there was no loop. | `evidence/baseline_no_orchestrator.json`, `base_C_*.json`, `base_D_*.json` timelines: `Running / status-running` while every `/api/status` returned 500 |
| F3 | **A killed server still showed "Running" indefinitely.** Polling errors were swallowed ("keep showing last known status"). | `evidence/base_B_fictional.json`: after `server interrupted` the timeline stays `Running` for 8+ s; screenshot `base_B_fictional_after_interrupt.png` |
| F4 | **No model information** anywhere in the UI. There was no endpoint for configured or installed models (`/api/models` → 404). | `evidence/base_B_models.txt` |
| F5 | The Trust card never populated (always `-`), while the backend fabricated `components: 1, average_trust: 0.8`. | `ui_control_panel.py` (old lines 2353-2355), screenshot |
| F6 | The chat panel parsed every response as JSON without checking the HTTP status, and had no timeout. A non-JSON 500 showed a parse error, and a hung model would leave "Sending..." forever. The label claimed "OpenAI/OpenRouter", although routing is local-first through the unified router. | `ui_control_panel.py` `sendApiChat` |
| F7 | (Cross-boundary, not repaired) `import project_guardian.<anything>` fails on `main` with `ModuleNotFoundError: project_guardian.module_activity` (from `core.py:51`). The module exists only on unmerged branches, e.g. commit `7081570 fix(guardian): restore missing import dependencies`. | pytest collection errors; `python -c "import project_guardian.ui_control_panel"` |

There were no JavaScript syntax errors or page exceptions on `main`. The 2026-10-22 "stuck on
Initializing" template defect is in the operator's local template and is absent from remote `main`,
which PR #149 also noted.

## 2. Repairs completed

All of these are in `project_guardian/ui_control_panel.py`: dashboard template plus UI API routes.

- **F1:** Removed the function-local `datetime` import. `/api/status` now returns 200 in all tested states.
- **F2 (backend):** `system.running` is now `_running` (set by both GuardianCore and SystemOrchestrator)
  or a live `elysia_loop.running`. `initialized` no longer counts "components exist". A missing loop
  reports `loop: {running:false, available:false}`. Added `system.orchestrator_available`.
- **F2/F3 (frontend):** Removed the fabricated-running fallback and the forced-status timers.
  A single `pollStatus()` runs every 2s with a 5s timeout:
  - Network failure or timeout → red **"Offline - backend unreachable (last contact Ns ago)"**, and the
    loop/uptime metrics show `unknown`.
  - Non-2xx → amber **"Backend error: HTTP 500 from /api/status"**.
  - No orchestrator → amber **"Backend online - orchestrator not available"**.
  - Initialized but not running → **"Initialized (not running)"**.
  - Recovery is detected automatically.
  - A Socket.IO disconnect triggers an immediate poll. The Socket.IO connect payload no longer overwrites status.
- **F4:** New read-only **`GET /api/models`**. It returns the configured Ollama model, its source (env var,
  `config/mistral_decider.json`, default, or the runtime's own `ollama_model_config` when loaded), whether
  Ollama is reachable, the installed models from `GET /api/tags`, and whether the configured model is installed.
  If there's a mismatch, it includes an actionable message. It has a 2s timeout. It never pulls, chats,
  or contacts cloud providers. A new **Local Model** dashboard card shows this and states that model
  selection is not supported in the dashboard.
- **F5:** Trust values now come from `trust.get_trust_report()` when it's available, or show `n/a`. The Trust card is wired up.
- **F6:** Chat checks the HTTP status, tolerates non-JSON responses, shows backend errors verbatim, and
  aborts after 180s with an actionable message. The label now describes the actual routing, including
  possible cloud fallback when API keys are configured.

Unchanged: `start()`/readiness logic (owned by open drafts #147/#148/#149), routes other than
`/api/status` and `/api/models`, and all backend, launcher, task and memory modules.

## 3. Features actually tested

Environment: Ubuntu VM, CPython 3.12, Flask 3.1, Flask-SocketIO 5.x, Playwright driving Google Chrome
(headless). The dashboard module was loaded by file path through `scripts/dashboard_fictional_harness.py`
with a fictional in-memory orchestrator, bound to 127.0.0.1 only. There were no credentials, providers,
memory files or autonomy.

| Requirement | Result | Notes |
|---|---|---|
| 1. Page loads without JS exceptions | **PASS** | 0 page errors in all scenarios. Rendered inline JS passes `node --check`. |
| 2. Initializing → correct state | **PASS** | "Connecting..." → correct state in ≤0.2s. No forced states. |
| 3. `/api/ping` identifies app | **PASS** | `{"ok":true,"service":"elysia-control-panel",...}` 200 |
| 4. `/api/status` valid and accurate | **PASS** (was FAIL) | 200 in all states. `running` matches the fictional orchestrator's actual flags. |
| 5. Online/offline indicators | **PASS** (was FAIL) | Offline 0.2–0.3s after the kill. Recovery to Running about 2s after the restart (`after_E_recovery.json`). |
| 6. Navigation, buttons, theme | **PASS** for tested controls | All 8 tabs switch. Theme toggles and persists across reload. Pause/Resume round-trip and the header follows ("Paused" → "Running"). |
| 7. Model display | **PASS (display only)** | Configured vs. installed models are shown and mismatches flagged. **Model selection is not implemented** (no UI control, no backend endpoint). That's a missing feature, not a wiring defect. |
| 8. Fictional message reaches backend | **PASS via stub** | Browser → `POST /api/chat` → orchestrator `_unified_system.chat_with_llm` → Ollama `/api/chat` (stub) → reply shown: `[STUB llama3.2:3b] received: Fictional test: ...`. The real unified router was not exercised (see F7). |
| 9. Model failure → actionable error | **PASS** | Missing model: `Error: Ollama HTTP 404 for model 'mistral:7b' ...` plus a red Local Model card. Ollama down: `Error: Local model unreachable at http://127.0.0.1:11434 ...`. No endless loading. |
| 10. Logs/task status reflect real events | **PASS** (logs) | Logs panel records connect, disconnect, unreachable, recovery, pause and resume as they happen. Task queue values come from `/api/status`. Task list/introspection tabs were not deeply exercised (fictional orchestrator has no task engine). |
| 11. Refresh preserves state | **PARTIAL** | Theme persists. The active tab is not persisted, which was never implemented. Status re-derives correctly after reload. |
| 12. Interruption detected, no false Running | **PASS** (was FAIL) | See 5. |

Not tested, and not claimed: learning, dream cycle, autonomy execute, wallet, harvest, research proposal,
prompt evolution, memory snapshot/cleanup/rebuild, link Facebook/Twitter, speak. These are write-capable
or need real subsystems. In the fictional harness they return "not available" responses. One example is
`/api/next-action` → 503 `"Next action not available"`, which is truthful because the fictional
orchestrator has no `get_next_action`. That is intentional backend behaviour, not a frontend defect.

## 4. Test results

```
python -m pytest tests/test_dashboard_status_truth.py -q
  after repair:            14 passed
  against unmodified main: 11 failed, 3 passed   (regressions catch F1, F2, F4, F5 and the frontend fallback)

python -m pytest tests/test_dashboard_listening.py tests/test_dashboard_idempotent.py \
    tests/test_ui_smoke.py tests/test_ui_local_only.py tests/test_ui_observability.py -q
  before AND after repair: 4 failed, 5 passed, 27 skipped   (identical; no regression)
    failures: pre-existing. 3x test_dashboard_listening plus 1x test_dashboard_idempotent hit the
              module_activity import (F7) or start() readiness expectations addressed by PR #149.
    skips:    FastAPI UI (project_guardian/ui/app.py) tests; FastAPI is not installed and that UI is
              not the one served on port 5000.

git diff --check: clean
```

Browser scenario runs (raw JSON in `evidence/`, prefix `base_` = unmodified main, `after_` = repaired):

| Scenario | main (before) | repaired (after) |
|---|---|---|
| A. No orchestrator | `/api/status` 500; header **Running** | 200; **Backend online - orchestrator not available** |
| B. Running loop, stub model installed, chat, kill | 500; **Running**, still **Running** after kill | 200; Running → **Offline** 0.2s after kill; chat reply shown; theme persists |
| C. Configured model not installed | 500; Running; no model info | 200; Running; Local Model card shows **Configured model installed: NO** with a fix hint; chat shows the 404 error |
| D. Orchestrator stopped, Ollama down | 500; **Running** | 200; **Initialized (not running)**; card shows Ollama unreachable; chat shows connection error |
| E. Kill and restart | n/a | Running → Offline → Running |
| F. Tab/control sweep | n/a | 8/8 tabs; pause/resume reflected; 0 page errors |

## 5. Backend and model connectivity evidence

- `GET /api/ping` → `{"ok":true,"orchestrator":true,"port":5062,"service":"elysia-control-panel"}` (`evidence/after_B_ping.txt`)
- `GET /api/status` (after) → `{"system":{"running":true,"initialized":true,"orchestrator_available":true,...},"loop":{"running":true,...}}` (`after_B_status.txt`)
- `GET /api/models` with stub listing `llama3.2:3b` and `ELYSIA_OLLAMA_MODEL=llama3.2:3b` →
  `{"configured_model":"llama3.2:3b","configured_source":"env:ELYSIA_OLLAMA_MODEL","configured_model_installed":true,"installed_models":["llama3.2:3b"],"ollama_reachable":true}` (`after_B_models.txt`)
- Chat routing: browser → `/api/chat` → `_unified_system.chat_with_llm` → `POST {OLLAMA_BASE_URL}/api/chat` with `model=llama3.2:3b` → reply rendered (`after_B_fictional.json` → `chat_result`). **The model was a stub.**
- Real Ollama: **not available on this VM** (`curl 127.0.0.1:11434/api/tags` → connection refused). No model was downloaded and no cloud provider was contacted. The `openai` SDK was installed only so the package could be imported, and no API keys exist on the VM.
- Note for the operator: committed `config/mistral_decider.json` sets `mistral_decider_model: "mistral:7b"`. If the Windows runtime uses `llama3.2:3b` without `ELYSIA_OLLAMA_MODEL` set, the new Local Model card will flag the mismatch.

## 6. Remaining limitations and cross-boundary defects (reported, not modified)

1. **F7 `project_guardian.module_activity` missing on main** (backend, `core.py`). This blocks importing
   the dashboard through the package, the launcher, and 4 existing dashboard tests. Owner: backend/Codex.
   A fix exists on unmerged branches (commit `7081570`).
2. **`/api/chat` returns HTTP 200 with `success:false`** for model errors (backend convention). The UI now
   displays these correctly.
3. **The unified router may fall back to OpenAI/OpenRouter** when API keys are configured (`unified_llm_route.py`
   order `primary → openai → openrouter → ollama`). The UI label now says so. It's a backend policy, unchanged.
4. **`UIControlPanel.stop()` does not close the Socket.IO listener**, and startup readiness can signal before the
   server serves HTTP. Covered by open drafts #147/#148/#149, so this change deliberately leaves `start()`/`stop()` alone.
5. Port **8888** is the backend status API in `elysia.py` (used by the CLI), not the browser dashboard. It wasn't tested here.
6. Model selection is not implemented, and the active tab doesn't persist across reloads.
7. Must be re-verified on the operator's Windows install with real Ollama `llama3.2:3b`, using the steps below.

### Operator re-verification (Windows, read-only, no model download)

```powershell
git fetch origin cursor/dashboard-truthful-status-2ccc
git worktree add ..\elysia-ui-accept origin/cursor/dashboard-truthful-status-2ccc
cd ..\elysia-ui-accept
python -m pytest tests/test_dashboard_status_truth.py -q
$env:ELYSIA_OLLAMA_MODEL="llama3.2:3b"   # uses the already-installed local model via the real Ollama
python scripts/dashboard_fictional_harness.py --mode fictional --port 5055
# open http://127.0.0.1:5055 : header "Running", Local Model card "installed: yes",
# Control tab -> Chat sends to the real llama3.2:3b. Ctrl+C the harness -> header turns "Offline".
```

## 7. Files modified and rollback

Branch `cursor/dashboard-truthful-status-2ccc` (draft PR, not merged), based on `main` `722d8e4`:

| File | Change |
|---|---|
| `project_guardian/ui_control_panel.py` | `/api/status` fix and truthful flags; new `/api/models` + `get_local_model_status()`; frontend status/offline logic, Local Model card, Trust wiring, chat error handling |
| `tests/test_dashboard_status_truth.py` | New: 14 regression tests |
| `scripts/dashboard_fictional_harness.py` | New: fictional loopback-only dashboard launcher with an optional labelled Ollama stub |
| `scripts/dashboard_browser_probe.py` | New: Playwright acceptance probe |
| `REPORTS/runtime_ui_acceptance_2026-10-23/` | This report plus raw evidence JSON/HTTP captures |

**Rollback:** don't merge the draft PR. If applied elsewhere, `git revert` the branch's commits, or restore
the single file with `git checkout 722d8e4 -- project_guardian/ui_control_panel.py`. The new files are
standalone and can be deleted. No data, config, credential, or launcher files were touched.
