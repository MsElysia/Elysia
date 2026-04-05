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
