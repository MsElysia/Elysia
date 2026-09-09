# Elysia acceleration proposal

| File | Purpose |
|------|---------|
| [TASKS.md](TASKS.md) | Master checklist (7 tracks). |
| [OPERATOR_NOTES.md](OPERATOR_NOTES.md) | Corpus vs index, cadence template, tuning + missions placeholders. |
| [AUDIT_PARALLEL.md](AUDIT_PARALLEL.md) | Where parallel orchestration and memory parallelism still live. |
| [ROUTING_FALLBACK_MATRIX.md](ROUTING_FALLBACK_MATRIX.md) | Template to verify local vs cloud on your machine. |
| [replay_prompts.jsonl](replay_prompts.jsonl) | Fixed prompts for deliberate practice. |
| [replay_runs.md](replay_runs.md) | Optional session log. |

## Scripts (repo root)

```text
python scripts/elysia_selfbuild_operator.py status
python scripts/elysia_selfbuild_operator.py last-rag
python scripts/elysia_selfbuild_operator.py backup
python scripts/run_replay_prompts.py
```

## Optional: Langfuse-style JSONL traces (no extra pip packages)

Set before starting the backend (or in your launcher `.cmd`):

| Variable | Meaning |
|----------|---------|
| `ELYSIA_LLM_TRACE_JSONL` | Append one JSON object per line per `unified_chat_completion` (path to `.jsonl` file). |
| `ELYSIA_LLM_TRACE_PROJECT` | Optional label stored as `project` (e.g. `home_pc`). |
| `ELYSIA_LLM_TRACE_INCLUDE_USER_PREFIX` | `1` / `true` — include first 120 chars of user text (default: only length + hash prefix). |

Rows include `backend`, `latency_ms`, `reason`, `selfbuild_rag`, `success`, `reply_chars`, etc. Import into **Langfuse** or any notebook by reading JSONL.

## Optional: MCP stdio client (external tools)

Install `mcp` from `requirements-optional.txt`, copy `config/mcp_servers.example.json` → `config/mcp_servers.json`, then:

```text
python scripts/mcp_probe.py --config config/mcp_servers.json --server … --list-tools
```

See `OPTIONAL_DEPENDENCIES.md` (MCP section), `mcp_stdio_bridge.py`, and **`mcp_capability.py`** (allowlisted **`elysia_mcp_tool`** for chat when allowlist `enabled` + `pip install mcp`).
