# Memory Hub operator guide

This guide is for running the local Memory Hub workflow from the static UI
prototypes and existing command-line tools. It does not add any backend route,
account integration, model call, embedding call, watcher, or live memory write.

## Safety model

Memory work in this slice is local and operator controlled:

- Use only files already exported or created by the operator.
- Do not connect ChatGPT, Gmail, Outlook, IMAP, SMTP, or any live account.
- Do not save memory until an explicit confirm/apply step.
- Keep new candidates pending until an operator reviews them.
- Search only approved local memory.
- Build context bundles as local files for later explicit use.

The static pages are prototypes. They do not call backend scripts, fetch data,
open sockets, refresh automatically, or connect server routes.

## Static UI entry points

Open the local static entry page:

```powershell
start project_guardian/ui/static/index.html
```

From there:

1. Open **Memory Hub**.
2. Open **Import Memory** to review the import flow.
3. Open **Review & Search** to review pending-memory, search, and context
   bundle mockups.

Direct local pages:

```powershell
start project_guardian/ui/static/memory_hub.html
start project_guardian/ui/static/memory_import_screen.html
start project_guardian/ui/static/memory_review_search.html
```

## Source lanes

The current local-only memory pipeline supports these source lanes:

| Lane | Local input | Notes |
| ---- | ----------- | ----- |
| Transcription/text | `.txt`, `.md`, `.vtt`, `.srt` | Uses import session preview/apply. |
| ChatGPT export | `conversations.json` or export-shaped JSON | Uses local export files only. |
| Email export | `.eml` | Uses local message files only; attachments are ignored. |

`.mbox`, PDF, DOCX, image, and live account import are intentionally not part of
this milestone.

## Preview before staging

Use the unified import command to preview local files:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --input <file-or-folder>
```

For explicit source lanes:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type transcription --input <path>
python scripts/memory_import.py preview --dest-dir <path> --source-type chatgpt_export --input <path>
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
```

Preview should classify inputs and write reviewable session artifacts. It must
not stage candidates, call models, generate embeddings, write live runtime
memory, or enable autonomy.

## Confirm import

After reviewing a preview, apply only when the operator is ready:

```powershell
python scripts/memory_import.py apply --session-json <path-to-preview-json> --apply
```

The apply step stages pending candidates for review. Pending candidates are not
approved memory.

## Review and approve

Use the review CLI to inspect and decide what becomes approved memory:

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id>
python scripts/review_memory_candidates.py --dest-dir <path> reject <candidate_id>
python scripts/review_memory_candidates.py --dest-dir <path> edit <candidate_id> --replacement-text "..."
```

Keep the review step deliberate. Only approved memories should become
searchable.

## Search and context bundle

Search approved memory locally:

```powershell
python scripts/search_approved_memory_store.py --dest-dir <path> search "example query"
```

Build a local context bundle for later explicit handoff:

```powershell
python scripts/build_approved_memory_context.py --dest-dir <path> --query "example query"
```

Context bundles are files. This workflow does not send them to a model.

## Smoke checks

Run the three local source-lane smokes when validating the workflow:

```powershell
python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription
python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export
python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export
```

Expected safety flags:

```text
model_called=false
embeddings_used=false
live_memory_written=false
autonomy_enabled=false
```

## Stop conditions

Stop and investigate before continuing if any command reports:

- `model_called=true`
- `embeddings_used=true`
- `live_memory_written=true`
- `autonomy_enabled=true`
- unexpected live account, network, watcher, or server-route behavior

