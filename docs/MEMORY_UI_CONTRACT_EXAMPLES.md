# Memory UI contract examples

These examples illustrate the static Memory UI contracts. They are not live API
payloads and do not imply server routes. All examples preserve the safe local
workflow: local files only, preview before apply, pending review before approval,
no model calls, no embeddings, no live runtime memory writes, and no autonomy.

## Preview response example

```json
{
  "source_type": "transcription",
  "session_json": "C:/memory_work/import_sessions/20260625/import_session_preview.json",
  "session_markdown": "C:/memory_work/import_sessions/20260625/import_session_preview.md",
  "files_seen": 2,
  "supported_now_count": 2,
  "supported_later_count": 0,
  "skipped_count": 0,
  "model_called": false,
  "embeddings_used": false,
  "live_memory_written": false,
  "autonomy_enabled": false
}
```

## Apply response example

```json
{
  "source_type": "chatgpt_export",
  "dry_run": false,
  "candidates_staged": 3,
  "apply_report_json": "C:/memory_work/chatgpt_export_apply_report.json",
  "apply_report_markdown": "C:/memory_work/chatgpt_export_apply_report.md",
  "review_status": "pending",
  "model_called": false,
  "embeddings_used": false,
  "live_memory_written": false,
  "autonomy_enabled": false
}
```

## Pending candidate example

```json
{
  "candidate_id": "candidate-chatgpt-001",
  "source_type": "chatgpt_export",
  "source_path": "C:/memory_exports/chatgpt/conversations.json",
  "review_status": "pending",
  "preview_text": "Client prefers email follow-up after estimates.",
  "created_by": "local_memory_import",
  "model_called": false,
  "embeddings_used": false,
  "live_memory_written": false,
  "autonomy_enabled": false
}
```

## Review decision example

```json
{
  "candidate_id": "candidate-chatgpt-001",
  "decision": "approve",
  "review_status": "approved",
  "reviewed_by": "operator",
  "audit_note": "Useful client preference; approved manually.",
  "model_called": false,
  "embeddings_used": false,
  "live_memory_written": false,
  "autonomy_enabled": false
}
```

## Approved search result example

```json
{
  "query": "email follow-up",
  "result_count": 1,
  "results": [
    {
      "memory_id": "memory-chatgpt-001",
      "source_type": "chatgpt_export",
      "text": "Client prefers email follow-up after estimates.",
      "review_status": "approved"
    }
  ],
  "model_called": false,
  "embeddings_used": false,
  "live_memory_written": false,
  "autonomy_enabled": false
}
```

## Context bundle result example

```json
{
  "query": "email follow-up",
  "bundle_markdown": "C:/memory_work/context_bundles/email-follow-up.md",
  "bundle_json": "C:/memory_work/context_bundles/email-follow-up.json",
  "memory_count": 1,
  "handoff_status": "local_file_created",
  "model_called": false,
  "embeddings_used": false,
  "live_memory_written": false,
  "autonomy_enabled": false
}
```

## UI display notes

- Preview responses should be shown before any confirm/apply action.
- Apply responses should label staged items as pending, not approved.
- Pending candidates should show source type, preview text, and review status.
- Review decisions should be operator initiated and auditable.
- Search results should display approved memory only.
- Context bundle results should show local output paths and should not imply a
  model handoff occurred.

