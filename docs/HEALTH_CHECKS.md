# Elysia Health Checks

Quick checks to verify key systems.

## 1. Resource Limits

**Config:** `elysia_config.py` → `get_resource_limits()`

- **Defaults:** memory 92%, CPU 95% (raised from 80%/90% to reduce warnings)
- **Override:** Set `ELYSIA_MEMORY_LIMIT=0.95` or `ELYSIA_CPU_LIMIT=0.98` before starting
- **Logs:** Watch for `Resource limit exceeded` or `[Memory Alert]` in `elysia_unified.log`

**Memory cleanup:** When memory log exceeds 3500 entries, auto-cleanup runs. Override with `ELYSIA_MEMORY_CLEANUP_THRESHOLD=5000`.

## 2. Chat

**Test:** While Elysia is running:

```powershell
python scripts/test_chat.py
python scripts/test_chat.py "Your message"
```

Or via API:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8888/chat" -Method POST -ContentType "application/json" -Body '{"message":"hello"}'
```

**Expected:** `{"reply": "...", "error": ""}`. If `error` is set, check API keys in `API keys/` folder.

## 3. Memory & Embeddings

**Logs:** Look for:

- `Generated embedding using sentence-transformers` → **OK** (real embeddings)
- `Using hash-based embedding fallback` → **Degraded** (install `requirements-optional.txt`)

**External storage:** `F:\ProjectGuardian\memory` (thumb drive). If F: is unavailable, config `fallback_drives` (G:, E:, D:) are tried before using LOCALAPPDATA.

## 4. Status & Dashboard

- **Status:** http://127.0.0.1:8888/status (JSON)
- **Ping:** http://127.0.0.1:5000/api/ping — returns `{"ok": true, "port", "orchestrator"}` immediately
- **Debug:** http://127.0.0.1:5000/api/debug — diagnostic info (flask, orchestrator, memory, loop, etc.)
- **Root (link to dashboard):** http://127.0.0.1:8888/
- **Dashboard:** http://127.0.0.1:5000 or 5001 (if 5000 is in use)
