# Control panel conversation memory

## Source of truth

Operator chat for the control panel and runtime API is stored in **ConversationStore**:

- Module: `project_guardian/conversation_store.py`
- Path: `data/runtime/conversations/<conversation_id>.jsonl`
- Messages are append-only, redacted, and capped per conversation.

`POST /api/chat`, `GET /api/chat/history`, and related routes read and write **only** this store (via `run_operator_chat_turn` and response helpers).

## Legacy file (import-only)

Historical control-panel chat may exist as:

- `data/runtime/control_panel_chat_history.json`

This file is **not** written at runtime. It is **not** read on every request after import.

### One-time import

When the import marker is missing:

- `data/runtime/conversations/.legacy_control_panel_chat_history_imported`

the first chat or history access may import sessions from the legacy JSON into canonical JSONL files. Import:

- Redacts secrets in message content
- Preserves `created_at` / `timestamp` when present
- Caps each session to the last 60 messages
- Skips sessions that already have canonical JSONL data
- Writes the marker and leaves the **original legacy file unchanged**

If the legacy file is absent, the marker is still written so import is not retried.

### Manual archive

After you verify messages in `data/runtime/conversations/`, you may manually move or delete `control_panel_chat_history.json`. The system does **not** delete it automatically.

## Diagnostics

Read-only:

```text
python scripts/control_panel_conversation_diagnostic.py
```

Reports legacy file presence, import marker state, and canonical conversation file count.

## Safety

- No autonomous patch apply or shell execution from conversation APIs
- No raw Think–Decide–Act traces in persisted metadata
- Bounded history for prompts and API responses
