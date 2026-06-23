# Memory import UI roadmap

This document describes the backend foundation for a future drag-and-drop memory
import screen in Elysia / Project Guardian.

## Current status

The local memory pipeline already supports operator-run steps:

1. Ingest transcriptions
2. Review memory candidates
3. Export approved candidates
4. Write approved memory store
5. Search approved memory
6. Build approved memory context bundles

The **import session preview** step is the next backend layer for UI work. It
simulates what a drag-and-drop screen needs without building the UI yet.

## Unified memory import (backend foundation)

One command routes preview/apply to the existing safe importers. This is the backend
foundation for a future drag-and-drop Memory screen. See
[UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md) and
[MEMORY_SCREEN_UI_FOUNDATION.md](MEMORY_SCREEN_UI_FOUNDATION.md).

```powershell
python scripts/memory_import.py preview --dest-dir <path> --input <file-or-folder>
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
python scripts/memory_import.py apply --session-json <path>/import_session_preview.json
python scripts/memory_import.py apply --session-json <path>/email_export_preview.json --apply
```

Auto-detect works for single-type inputs (transcription text, ChatGPT export JSON, `.eml`).
Mixed folders fail safely unless `--source-type` is provided.

Static UI prototypes (no server wiring):

- Import: `project_guardian/ui/static/memory_import_screen.html`
- Review/search: `project_guardian/ui/static/memory_review_search.html`

See [MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md](MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md) and
[MEMORY_REVIEW_SEARCH_UI_CONTRACT.json](MEMORY_REVIEW_SEARCH_UI_CONTRACT.json).

## Import session preview (backend foundation)

Operators (or a future UI) provide **explicit** file or folder paths. Elysia
classifies what can be imported and writes a reviewable session preview.

This step is **preview-only**:

- No files are imported automatically
- No memory candidates are staged
- No models, embeddings, or live runtime memory are used
- No server/API routes are involved
- No background watchers or folder monitors are started

### CLI

```powershell
python scripts/preview_memory_import_session.py --dest-dir <path> --input <file-or-folder> --input <file-or-folder>
python scripts/preview_memory_import_session.py --dest-dir <path> --input <folder> --recursive
python scripts/preview_memory_import_session.py --dest-dir <path> --input <file> --session-dir <path>
```

### Session output

Default location:

```text
<dest-dir>/import_sessions/<session_id>/
  import_session_preview.json
  import_session_preview.md
```

### File classification

| Category          | Meaning                                      | Examples                          |
| ----------------- | -------------------------------------------- | --------------------------------- |
| `supported_now`   | Can use current transcription ingestion      | `.txt`, `.md`, `.vtt`, `.srt`     |
| `supported_later` | Planned future import types                  | `.json`, `.csv`, `.eml`, `.pdf`…  |
| `unsupported`     | Binary or unknown formats                    | images, executables, unknown text |
| `skipped`         | Symlinks, oversize files, scan-rule skips    | symlinks, files over max size     |

### Safety metadata

Each JSON preview includes:

- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `import_applied: false`

## Import session apply (confirm from preview)

After reviewing a session preview, operators can stage transcription memory
candidates from `supported_now` files only.

```powershell
python scripts/apply_memory_import_session.py --session-json <path>/import_session_preview.json
python scripts/apply_memory_import_session.py --session-json <path>/import_session_preview.json --apply
```

Dry-run is the default. `--apply` writes normalized text, metadata, manifest
entries, and `memory_candidates/review_queue.jsonl` using the existing
transcription ingestion pipeline.

Apply reports:

```text
<dest-dir>/import_sessions/<session_id>/
  import_session_apply_report.json
  import_session_apply_report.md
```

## ChatGPT export import (local file only)

Preview and apply local ChatGPT `conversations.json` exports. No account access,
API calls, or network use. See [CHATGPT_EXPORT_IMPORT_MVP.md](CHATGPT_EXPORT_IMPORT_MVP.md).

```powershell
python scripts/preview_chatgpt_export.py --export-json <path>/conversations.json --dest-dir <path>
python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json --apply
```

## Email export import (local `.eml` only)

Preview and apply local `.eml` email exports. No Gmail, Outlook, IMAP, SMTP, or
account access. `.mbox` is classified as `supported_later` only.
See [EMAIL_EXPORT_IMPORT_MVP.md](EMAIL_EXPORT_IMPORT_MVP.md).

```powershell
python scripts/preview_email_export.py --dest-dir <path> --input <file-or-folder>
python scripts/preview_email_export.py --dest-dir <path> --input <folder> --recursive
python scripts/apply_email_export.py --preview-json <path>/email_export_preview.json --apply
```

## Memory review/search UI foundation

Static prototype and contract for pending candidate review, approved memory browse/search,
and context bundle placeholders. No server wiring yet.

```powershell
start project_guardian/ui/static/memory_review_search.html
```

Backend CLIs (operator-run today):

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id>
python scripts/search_approved_memory_store.py --dest-dir <path> search "drywall quote"
python scripts/build_approved_memory_context.py --dest-dir <path> --query "drywall quote"
```

## Future UI direction (not built yet)

A future drag-and-drop screen should:

1. Let the user drop or select explicit files/folders
2. Call the preview layer to classify inputs
3. Show `supported_now`, `supported_later`, `unsupported`, and `skipped` counts
4. Display next-step guidance from the preview
5. Offer **Create memory candidates from this preview** which calls the apply layer

A future review/search screen should:

1. List pending candidates with source-type filters
2. Approve / reject / edit with operator confirmation
3. Search approved local memory (read-only)
4. Build context bundles on explicit operator request

## Tests

```powershell
python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
python -m pytest project_guardian/tests/test_import_session_preview.py -q
python -m pytest project_guardian/tests/test_import_session_apply.py -q
python -m pytest project_guardian/tests/test_chatgpt_export_ingest.py -q
python -m pytest project_guardian/tests/test_email_export_ingest.py -q
python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q
python scripts/run_local_memory_pipeline_smoke.py
python scripts/run_local_memory_pipeline_smoke.py --json
```

## Related docs

- [MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md](MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md) — review/search UI contract
- [MEMORY_SCREEN_UI_FOUNDATION.md](MEMORY_SCREEN_UI_FOUNDATION.md) — import UI contract
- [UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md) — unified preview/apply CLI
- [PHONE_TRANSCRIPTION_INGESTION_MVP.md](PHONE_TRANSCRIPTION_INGESTION_MVP.md) — current local ingestion pipeline
- [CHATGPT_EXPORT_IMPORT_MVP.md](CHATGPT_EXPORT_IMPORT_MVP.md) — ChatGPT export preview/apply
- [EMAIL_EXPORT_IMPORT_MVP.md](EMAIL_EXPORT_IMPORT_MVP.md) — email `.eml` export preview/apply
