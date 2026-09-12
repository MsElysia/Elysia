# Memory review/search UI foundation

**Status:** UI structure and contract only — no server wiring in this milestone  
**Restore tag (prior):** `memory_screen_ui_foundation_clean_1`  
**Backend entry points:** `scripts/review_memory_candidates.py`, `scripts/search_approved_memory_store.py`, `scripts/build_approved_memory_context.py`

---

## Purpose

Give operators a clear Memory review/search screen after import:

1. Show pending memory candidates
2. Approve / reject / edit candidates
3. Show approved memory
4. Search approved memory
5. Build or request context bundles (future wiring)

This milestone delivers screen layout, user-facing safety copy, and a JSON UI contract.
It does **not** connect to `elysia/api/server.py` or live runtime memory.

---

## Where the UI lives

| Asset | Path |
| ----- | ---- |
| Static prototype (open in browser) | `project_guardian/ui/static/memory_review_search.html` |
| UI contract (machine-readable) | `docs/MEMORY_REVIEW_SEARCH_UI_CONTRACT.json` |
| Import screen (prior milestone) | `project_guardian/ui/static/memory_import_screen.html` |
| Review CLI | `scripts/review_memory_candidates.py` |
| Search CLI | `scripts/search_approved_memory_store.py` |
| Context bundle CLI | `scripts/build_approved_memory_context.py` |

Open the static prototype locally:

```powershell
start project_guardian/ui/static/memory_review_search.html
```

The prototype uses placeholder data only. Buttons show what will happen later; no API or CLI calls are made from the page.

---

## Screen layout

### 1. Pending Memories

- Candidate count badge
- Source type filter: transcription, chatgpt_export, email_export
- Candidate cards with:
  - source type
  - suggested memory type
  - text preview
  - source file/path label
  - staged date
  - status (pending)

### 2. Review actions

Per candidate:

- **Approve** — writes audit decision; requires operator confirmation
- **Reject** — writes audit decision; requires operator confirmation
- **Edit before approval** — replacement text; requires operator confirmation
- **View source metadata** — read-only modal/panel

Expected CLI:

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id> --notes "..."
python scripts/review_memory_candidates.py --dest-dir <path> reject <candidate_id>
python scripts/review_memory_candidates.py --dest-dir <path> edit <candidate_id> --replacement-text "..."
```

### 3. Approved Memory

- Approved count
- Source type filter
- Approved item preview cards

After review, operators run export/store CLIs (or future UI wiring):

```powershell
python scripts/export_approved_memory_candidates.py --dest-dir <path>
python scripts/write_approved_memory_store.py --dest-dir <path> --apply
```

### 4. Search Approved Memory

- Search box
- Result count
- Result cards (memory_id, source type, preview, approved date)

Expected CLI:

```powershell
python scripts/search_approved_memory_store.py --dest-dir <path> search "drywall quote" --limit 10
python scripts/search_approved_memory_store.py --dest-dir <path> list --limit 10
```

Search is **read-only**.

### 5. Context Bundle

- Placeholder button: **Build context bundle**
- Explains bundles are local Markdown + JSON files under `<dest-dir>/memory_context/`
- Requires operator confirmation when wired

Expected CLI:

```powershell
python scripts/build_approved_memory_context.py --dest-dir <path> --query "drywall quote" --limit 5 --max-chars 8000
```

---

## User-facing safety copy (required)

These strings must appear on the review/search screen:

- **Pending memories are not active memory yet.**
- **Only approved memories are used for search/context.**
- **Review actions are operator controlled.**
- **No model is called during review.**
- **No live account access is used.**
- **No memory is written to live runtime memory or vector DB.**

---

## Data source paths

| Artifact | Default path |
| -------- | ------------ |
| Review queue | `<dest-dir>/memory_candidates/review_queue.jsonl` |
| Review decisions | `<dest-dir>/memory_candidates/review_decisions.jsonl` |
| Approved export | `<dest-dir>/memory_candidates/approved_memory_export.jsonl` |
| Approved store | `<dest-dir>/memory_store/approved_memory_store.jsonl` |
| Context bundle dir | `<dest-dir>/memory_context/` |

---

## How the UI should call the backend (later)

When wiring the dashboard, prefer a **safe subprocess bridge** that invokes existing CLIs with explicit paths. Do not add background folder watchers.

Map JSON CLI output to fields in `docs/MEMORY_REVIEW_SEARCH_UI_CONTRACT.json`.

Every response must expose:

- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `autonomy_enabled: false`

Review and context-bundle actions must require operator confirmation in the UI.

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
| No live account access | Yes |
| Search read-only | Yes |
| Review/context require operator confirm | Yes |

---

## Verification

```powershell
python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
```

---

## Intentionally not done

- No live dashboard route wiring
- No server/API routes for review or search
- No automatic export/store after approve
- No local model call from the screen
- No embeddings
- No runtime memory / vector writes from the screen

---

## Related docs

- [MEMORY_REVIEW_SEARCH_UI_CONTRACT.json](MEMORY_REVIEW_SEARCH_UI_CONTRACT.json)
- [MEMORY_SCREEN_UI_CONTRACT.json](MEMORY_SCREEN_UI_CONTRACT.json)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
- [LOCAL_MEMORY_PIPELINE_CHECKPOINT.md](LOCAL_MEMORY_PIPELINE_CHECKPOINT.md)
