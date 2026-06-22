# ChatGPT export import MVP

Operator-run preview and apply for **local** ChatGPT export JSON files. No live
ChatGPT account access, no OpenAI API, no models, no embeddings, no live memory
writes, and no server routes.

## Flow

1. **Preview** — classify conversations and estimate candidates
2. **Apply** — stage eligible conversations as pending memory candidates (requires `--apply`)

This follows the same safe pattern as phone transcription import and import session
preview/apply.

## Preview

```powershell
python scripts/preview_chatgpt_export.py --export-json <path>/conversations.json --dest-dir <path>
python scripts/preview_chatgpt_export.py --export-json <path>/conversations.json --dest-dir <path> --limit 10
```

Output:

```text
<dest-dir>/chatgpt_import_sessions/<session_id>/
  chatgpt_export_preview.json
  chatgpt_export_preview.md
```

Preview metadata includes `model_called: false`, `embeddings_used: false`,
`live_memory_written: false`, `import_applied: false`.

## Apply

```powershell
python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json
python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json --apply
```

Dry-run is default. `--apply` writes:

- Extracted conversation text under `extracted_text/`
- Per-conversation metadata under `metadata/`
- Pending candidates in `memory_candidates/review_queue.jsonl`

Apply reports:

```text
<dest-dir>/chatgpt_import_sessions/<session_id>/
  chatgpt_export_apply_report.json
  chatgpt_export_apply_report.md
```

## Candidate fields

Each staged candidate includes:

- `source_type: chatgpt_export`
- `review_status: pending`
- `suggested_memory_type: conversation_history`
- `live_memory_written: false`
- `safety_notes: operator_review_required`

## Safety

- Local export file only (explicit `--export-json`)
- Symlinks not followed
- Export size validated on apply
- Duplicate apply protection via review queue
- No network, API, model, embedding, or vector DB usage

## Tests

```powershell
python -m pytest project_guardian/tests/test_chatgpt_export_ingest.py -q
```

## Related

- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
- [LOCAL_MEMORY_PIPELINE_CHECKPOINT.md](LOCAL_MEMORY_PIPELINE_CHECKPOINT.md)
