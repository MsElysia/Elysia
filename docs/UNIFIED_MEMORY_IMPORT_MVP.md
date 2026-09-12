# Unified memory import MVP

**Status:** Backend foundation for a future drag-and-drop Memory screen  
**Scope:** One CLI that routes preview/apply to existing safe importers. No UI, no server routes, no models.

---

## Purpose

Operators should not need separate scripts for each local memory source type. The unified
command auto-detects (where safe) or accepts an explicit `--source-type`, then delegates
to the existing transcription, ChatGPT export, or email export importers.

Supported source lanes:

| Source type | Input examples | Routed importer |
| ----------- | -------------- | ----------------- |
| `transcription` | `.txt`, `.md`, `.vtt`, `.srt` | import session preview/apply |
| `chatgpt_export` | `conversations.json`, ChatGPT-shaped JSON | ChatGPT export preview/apply |
| `email_export` | `.eml` files/folders | email export preview/apply |

---

## CLI

### Preview

```powershell
python scripts/memory_import.py preview --dest-dir <path> --input <file-or-folder>
python scripts/memory_import.py preview --dest-dir <path> --input <folder> --recursive
python scripts/memory_import.py preview --dest-dir <path> --source-type transcription --input <path>
python scripts/memory_import.py preview --dest-dir <path> --source-type chatgpt_export --input <path>
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
python scripts/memory_import.py preview --dest-dir <path> --input <path> --json
```

Preview prints a user-friendly summary:

- detected source type
- session JSON path
- session Markdown path
- files/conversations/emails seen
- candidates available later
- **No memory was written.**

### Apply

```powershell
python scripts/memory_import.py apply --session-json <path>
python scripts/memory_import.py apply --session-json <path> --apply
python scripts/memory_import.py apply --session-json <path> --json
```

Apply inspects the preview/session JSON to determine source type, then routes to the
matching apply behavior. Dry-run is default; `--apply` stages pending candidates only.

Apply prints:

- source type
- dry-run or applied
- candidates staged
- apply report path
- **No live memory was written.**

Unified apply does **not** approve, export, store, search, or build context bundles.

---

## Auto-detect rules

1. `conversations.json` or JSON shaped like a ChatGPT export → `chatgpt_export`
2. `.eml` files/folders → `email_export`
3. `.txt`, `.md`, `.vtt`, `.srt` files/folders → `transcription`
4. Mixed folders containing more than one source type → fail safely; require `--source-type`
5. Ambiguous inputs → fail safely with a message to pass `--source-type`
6. `.mbox` is **not** supported here (remains `supported_later` in email preview only)

Explicit `--source-type` overrides auto-detect where safe.

---

## Safety guarantees

| Guarantee | Status |
| --------- | ------ |
| Autonomy disabled | Yes |
| No live execution | Yes |
| No model / API / embedding calls | Yes |
| No live runtime memory or vector DB writes | Yes |
| No server/API route wiring | Yes |
| No watchers or background monitors | Yes |
| Local exported files only | Yes |
| No live ChatGPT or email account access | Yes |
| Dry-run / explicit `--apply` gates | Yes |

Unified preview/apply JSON summaries include:

- `source_type`
- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `autonomy_enabled: false`

---

## Tests

```powershell
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q
python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription
python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export
python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export
```

---

## Related docs

- [LOCAL_MEMORY_PIPELINE_CHECKPOINT.md](LOCAL_MEMORY_PIPELINE_CHECKPOINT.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
- [PHONE_TRANSCRIPTION_INGESTION_MVP.md](PHONE_TRANSCRIPTION_INGESTION_MVP.md)
- [CHATGPT_EXPORT_IMPORT_MVP.md](CHATGPT_EXPORT_IMPORT_MVP.md)
- [EMAIL_EXPORT_IMPORT_MVP.md](EMAIL_EXPORT_IMPORT_MVP.md)

---

## Intentionally not done

- No UI drag-and-drop screen yet
- No server/API routes
- No local model call or embeddings
- No runtime memory/vector write
- No `.mbox` import
- No autonomy or live execution
