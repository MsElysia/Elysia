# Memory command cookbook

Copy and adapt these local commands for the Memory Hub workflow. Replace
`<dest-dir>`, `<input-path>`, `<session-json>`, `<candidate_id>`, and query text
with local paths and values from your workspace.

This cookbook does not require account access, server routes, model calls,
embeddings, browser automation, or live runtime memory writes.

## Open the static Memory UI

```powershell
start project_guardian/ui/static/index.html
start project_guardian/ui/static/memory_hub.html
start project_guardian/ui/static/memory_safety.html
```

## Preview local files

Auto-detect a local input:

```powershell
python scripts/memory_import.py preview --dest-dir <dest-dir> --input <input-path>
```

Preview a transcription/text folder:

```powershell
python scripts/memory_import.py preview --dest-dir <dest-dir> --source-type transcription --input <input-path>
```

Preview a local ChatGPT export:

```powershell
python scripts/memory_import.py preview --dest-dir <dest-dir> --source-type chatgpt_export --input <input-path>\conversations.json
```

Preview local email `.eml` files:

```powershell
python scripts/memory_import.py preview --dest-dir <dest-dir> --source-type email_export --input <input-path>
```

## Apply import with confirmation

Apply only after reviewing preview output:

```powershell
python scripts/memory_import.py apply --session-json <session-json> --apply
```

If `--apply` is omitted, treat it as a non-confirmed apply check and verify
whether candidates were staged before continuing.

## List pending candidates

```powershell
python scripts/review_memory_candidates.py --dest-dir <dest-dir> list
python scripts/review_memory_candidates.py --dest-dir <dest-dir> list --all
```

## Approve, reject, or edit candidates

Approve:

```powershell
python scripts/review_memory_candidates.py --dest-dir <dest-dir> approve <candidate_id> --notes "approved by operator"
```

Reject:

```powershell
python scripts/review_memory_candidates.py --dest-dir <dest-dir> reject <candidate_id>
```

Edit with replacement text:

```powershell
python scripts/review_memory_candidates.py --dest-dir <dest-dir> edit <candidate_id> --replacement-text "cleaned memory text"
```

Edit from a local text file:

```powershell
python scripts/review_memory_candidates.py --dest-dir <dest-dir> edit <candidate_id> --replacement-text-file <path-to-cleaned-text>
```

## Export approved memory

```powershell
python scripts/export_approved_memory_candidates.py --dest-dir <dest-dir>
```

Optional explicit output:

```powershell
python scripts/export_approved_memory_candidates.py --dest-dir <dest-dir> --output <path-to-approved-export-jsonl>
```

## Write approved memory store

Dry-run style check:

```powershell
python scripts/write_approved_memory_store.py --dest-dir <dest-dir>
```

Confirmed write:

```powershell
python scripts/write_approved_memory_store.py --dest-dir <dest-dir> --apply
```

## Search approved memory

```powershell
python scripts/search_approved_memory_store.py --dest-dir <dest-dir> search "example query"
python scripts/search_approved_memory_store.py --dest-dir <dest-dir> list --limit 10
python scripts/search_approved_memory_store.py --dest-dir <dest-dir> show <memory_id>
python scripts/search_approved_memory_store.py --dest-dir <dest-dir> stats
```

## Build context bundle

```powershell
python scripts/build_approved_memory_context.py --dest-dir <dest-dir> --query "example query"
```

Context bundles are local files. This command does not send context to a model.

## Safety checks

After a smoke or pipeline run, expected flags are:

```text
model_called=false
embeddings_used=false
live_memory_written=false
autonomy_enabled=false
```

Stop if any of those become `true`, or if a command requests account
credentials, starts a watcher, connects a server route, or attempts network
access.

