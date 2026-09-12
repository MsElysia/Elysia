# Memory screen UI foundation

**Status:** UI structure and contract only — no server wiring in this milestone  
**Branch checkpoint:** `unified_memory_import_clean_1`  
**Backend entry point:** `python scripts/memory_import.py`

---

## Purpose

Give normal users a clear Memory screen for local file import:

1. Add files (drag-and-drop zone or file picker)
2. Preview what will be imported
3. Confirm import (stage pending memories)
4. Review pending memories
5. Search approved memory later

This milestone delivers the screen layout, user-facing copy, and a JSON UI contract.
It does **not** connect to `elysia/api/server.py` or live runtime memory.

---

## Where the UI lives

| Asset | Path |
| ----- | ---- |
| Static prototype (open in browser) | `project_guardian/ui/static/memory_import_screen.html` |
| UI contract (machine-readable) | `docs/MEMORY_SCREEN_UI_CONTRACT.json` |
| Unified backend CLI | `scripts/memory_import.py` |
| Control panel Memory tab (existing, minimal) | `project_guardian/ui_control_panel.py` — search only today |

Open the static prototype locally:

```powershell
start project_guardian/ui/static/memory_import_screen.html
```

The prototype uses placeholder data only. Buttons show what will happen later; no API or CLI calls are made from the page.

---

## Screen layout

### 1. Import Memory

- Headline: **Import Memory**
- Drop zone: “Drag files here” / **Choose files**
- Supported sources callout:
  - Text / transcriptions (`.txt`, `.md`, `.vtt`, `.srt`)
  - ChatGPT export (`conversations.json` or export-shaped JSON)
  - Email export (`.eml` files)
- Optional source type selector (Auto-detect, Transcription, ChatGPT export, Email export)
- Destination folder field (`dest_dir`) for operator workspace
- **Preview** button

### 2. Preview results

Shows after preview (from contract `preview_response`):

- Detected `source_type`
- Files / conversations / emails seen
- Supported now / supported later / skipped counts (when available)
- Links to session JSON and Markdown paths
- Safety banner with required user-facing text

### 3. Confirm import

- **Confirm import** runs apply with `--apply`
- Dry-run apply available as “Preview apply (no changes)”
- Copy: “No memory is saved until you confirm.”

### 4. Review pending memories

Future section — lists `review_status=pending` candidates from `memory_candidates/review_queue.jsonl`.
Expected CLI: `python scripts/review_memory_candidates.py --dest-dir <path> list`

### 5. Search approved memory

Future section — search the approved local store after review/export pipeline.
Expected CLI: `python scripts/search_approved_memory_store.py --dest-dir <path> search --query "..."`

---

## User-facing safety copy (required)

These strings must appear on the Memory screen:

- **No memory is saved until you confirm.**
- **Imported items become pending memories for review.**
- **Approved memories can be searched later.**
- **Elysia does not connect to your email or ChatGPT account for this import.**
- **Only local files you choose are used.**

---

## How the UI should call the backend (later)

When wiring the dashboard, prefer a **safe subprocess bridge** that invokes the unified CLI with explicit paths. Do not add background folder watchers.

### Preview

```powershell
python scripts/memory_import.py preview --dest-dir <path> --input <file-or-folder>
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
python scripts/memory_import.py preview --dest-dir <path> --input <folder> --recursive --json
```

Map JSON output to `preview_response` fields in `docs/MEMORY_SCREEN_UI_CONTRACT.json`.

### Apply

```powershell
python scripts/memory_import.py apply --session-json <path>/import_session_preview.json
python scripts/memory_import.py apply --session-json <path>/email_export_preview.json --apply --json
```

Map JSON output to `apply_response` fields. `candidates_staged` is zero on dry-run.

### Downstream (not part of this UI milestone)

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id>
python scripts/export_approved_memory_candidates.py --dest-dir <path>
python scripts/write_approved_memory_store.py --dest-dir <path> --apply
python scripts/search_approved_memory_store.py --dest-dir <path> search --query "drywall quote"
python scripts/build_approved_memory_context.py --dest-dir <path> --query "drywall quote"
```

---

## Safety guarantees

| Guarantee | This milestone |
| --------- | -------------- |
| Autonomy disabled | Yes |
| No live execution | Yes |
| No model / API / embedding calls | Yes |
| No live runtime memory / vector DB writes | Yes |
| No server/API routes added | Yes |
| No watchers or background monitors | Yes |
| Local files only | Yes |
| No live ChatGPT or email account access | Yes |
| Attachments ignored on email import | Yes |
| Mixed folders fail safely unless source type explicit | Yes |

Every preview/apply summary must expose:

- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `autonomy_enabled: false`

---

## Verification

```powershell
python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription
```

---

## Intentionally not done

- No live dashboard wiring to server routes
- No drag-and-drop folder watcher
- No automatic import on file drop
- No `.mbox` import in UI yet
- No local model or embedding calls from the screen
- No runtime memory / vector writes from the screen

---

## Related docs

- [MEMORY_SCREEN_UI_CONTRACT.json](MEMORY_SCREEN_UI_CONTRACT.json)
- [UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
- [LOCAL_MEMORY_PIPELINE_CHECKPOINT.md](LOCAL_MEMORY_PIPELINE_CHECKPOINT.md)
