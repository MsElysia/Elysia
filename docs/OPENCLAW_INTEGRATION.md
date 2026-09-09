# OpenClaw + Elysia Integration

Use **OpenClaw** (Telegram, Slack, Discord, etc.) with **Elysia** as the brain. OpenClaw sends user messages to Elysia and delivers Elysia’s replies back to the channel.

## What Elysia Exposes

- **OpenAI-compatible chat:** `POST http://127.0.0.1:8888/v1/chat/completions`  
  Same request/response shape as OpenAI Chat Completions so OpenClaw can add Elysia as a custom LLM provider.

- **Simple chat (optional):** `POST http://127.0.0.1:8888/chat`  
  Body: `{"message": "user text"}` → `{"reply": "...", "error": "?"}`

## 1. Add Elysia as a Custom Provider in OpenClaw

In your OpenClaw config (e.g. `openclaw.json`), add Elysia under `models.providers`:

```json
{
  "models": {
    "providers": [
      {
        "id": "elysia",
        "name": "Elysia",
        "baseUrl": "http://127.0.0.1:8888",
        "apiKey": "optional-local",
        "apiType": "openai-completions",
        "models": [
          {
            "id": "elysia/main",
            "name": "Elysia",
            "contextWindow": 8192,
            "maxOutputTokens": 2048
          }
        ]
      }
    ]
  }
}
```

- **baseUrl:** `http://127.0.0.1:8888` (Elysia status server; change host/port if you run Elysia elsewhere).
- **apiKey:** Elysia’s status server does not require a key for local use; use any placeholder (e.g. `optional-local`) if OpenClaw requires one.
- **apiType:** `openai-completions` so OpenClaw calls `/v1/chat/completions`.

## 2. Use Elysia in a Channel

In OpenClaw, create or edit an agent and set its model to the Elysia model (e.g. `elysia/main`). Messages from Telegram/Slack/Discord will then be sent to Elysia and replies streamed back.

## 3. Requirements

- Elysia (Project Guardian) must be running and the status server listening on port 8888.
- OpenClaw Gateway must be able to reach `http://127.0.0.1:8888` (same machine or adjust `baseUrl` and firewall).

## 4. Optional Bearer token (production)

Elysia can require a shared secret for `/chat` and `/v1/chat/completions`:

- Set the environment variable **`ELYSIA_API_TOKEN`** to your secret (e.g. a long random string).
- Requests must send: **`Authorization: Bearer <your-secret>`**.
- If `ELYSIA_API_TOKEN` is not set, no auth is required (fine for localhost).

In OpenClaw, set the provider’s `apiKey` to the same value so it sends the header. Do not expose port 8888 to the internet without this (or a reverse proxy with auth).

---

## 5. Execution worker (Elysia → OpenClaw)

Elysia can call a **separate HTTP execution service** (same or different process from the OpenClaw chat gateway). Configure it in Project Guardian: `config/openclaw.json` (`base_url`, `enabled`, `timeout_seconds`).

- **Default `base_url` in-repo:** `http://127.0.0.1:18789` (typical OpenClaw gateway port on Windows). The old local stub used `8765`.
- **Override without editing JSON:** set `ELYSIA_OPENCLAW_BASE_URL` or `OPENCLAW_GATEWAY_URL` to the gateway root (no trailing slash).

### Health (reachability)

`OpenClawAdapter.is_available()` succeeds if **any** of these returns HTTP 200 with a body that parses as JSON (or is empty `{}` after parse):

- `GET {base_url}/health`
- `GET {base_url}/status`
- `GET {base_url}/api/health`
- `GET {base_url}/`

Implement at least one of these on your worker so Elysia reports `openclaw_available: true`.

### Skills list

- `GET {base_url}/skills`  
  Expected shape: `{"skills": [ {"name": "...", ...}, ... ]}`  
  If this fails, Elysia falls back to `default_skills` from config for counts only.

### Run a skill

Elysia’s `delegate_to_openclaw` calls `run_skill` with the **entire task envelope** as the adapter’s `args` parameter, so the HTTP body is:

1. **Preferred:** `POST {base_url}/skills/{skill_name}/run`  
   JSON body: `{"args": { "goal": "...", "skill": "...", "args": { ... }, "requested_by": "elysia", "created_at": "<iso8601>" } }`

2. **Fallback:** `POST {base_url}/run_skill`  
   JSON body: `{"skill": "<skill_name>", "args": { ...same envelope... } }`

3. **Fallback:** `POST {base_url}/tasks`  
   JSON body: `{"skill": "<skill_name>", "args": { ...same envelope... } }`

Your worker should read nested `goal`, top-level `args` inside the envelope (caller extras), and `skill` (redundant with URL/body but present for logging).

### Worker response shape

Return JSON parseable as an object. Elysia normalizes to:

- `ok` — boolean (default `true` if omitted)
- `task_id` or `id` — string
- `result` — object with actionable fields when possible (e.g. `summary`, `repos`, `links`, `files`, `detected_issues`, `recommendation`) for scoring
- `error` — string or null

### Task log and stop

- `GET {base_url}/tasks/{task_id}` or `GET {base_url}/task/{task_id}` or `GET {base_url}/task_log?task_id=...`
- `POST {base_url}/tasks/{task_id}/stop` or `POST {base_url}/stop_task` with body `{"task_id": "..."}`

Starter skill names used by autonomy defaults: `browser_research`, `github_scan`, `file_scan`, `daily_report`.

---

## 6. Autostart (like Ollama)

There is **no fixed OpenClaw binary path** in this repo (unlike `ollama.exe`). You can still automate startup in two ways:

### A) `Start_Elysia_Backend.cmd` (recommended, mirrors Ollama)

If `ensure_openclaw_running.ps1` exists next to the cmd file, the backend runs it before `elysia.py`. The script:

1. Reads `config/openclaw.json`.
2. If `autostart.enabled` is **false** (default), it exits immediately (no warning).
3. If **true**, it checks `{base_url}/health` (and `/status`, `/api/health`). If already up, it exits.
4. If down, it runs `autostart.command` (first element = executable, rest = arguments) with optional `working_directory`, then polls until reachable or timeout.

Set **`ELYSIA_OPENCLAW_AUTOSTART=0`** to skip this script entirely.

### B) Python (`elysia.py` / `OpenClawAdapter`)

When Elysia constructs `OpenClawAdapter`, it runs the same policy: if `autostart.enabled` and `openclaw.enabled` are true and the worker is not yet reachable, it spawns `autostart.command` and waits up to `max_wait_seconds`. On unified shutdown, Elysia calls `shutdown_autostart()` so a process **started by Elysia** is terminated (it does not kill a worker you started yourself unless Elysia spawned it).

**Fill in** `autostart.command` with whatever you use to start your worker, for example:

```json
"autostart": {
  "enabled": true,
  "command": ["C:\\\\Apps\\\\openclaw-worker.exe", "--listen", "127.0.0.1:8765"],
  "working_directory": "",
  "max_wait_seconds": 30,
  "log_directory": "data/runtime"
}
```

Leave `enabled: false` until you have a real command; Elysia will not guess an install path.
