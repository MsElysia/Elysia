# Email export import MVP

**Status:** Operator-run local `.eml` import only  
**Scope:** Preview and apply local email export files. No Gmail, Outlook, IMAP, SMTP, APIs, or live accounts.

---

## Purpose

Stage memory candidates from user-provided local `.eml` files through the same
review-first pipeline used for transcriptions and ChatGPT exports.

Safe pattern:

```text
local .eml file/folder
  → preview
  → apply with --apply
  → extracted readable email text
  → pending memory candidates only
  → no live memory write
```

---

## CLI

### Preview

```powershell
python scripts/preview_email_export.py --dest-dir <path> --input <file-or-folder>
python scripts/preview_email_export.py --dest-dir <path> --input <folder> --recursive
```

### Apply

```powershell
python scripts/apply_email_export.py --preview-json <path>/email_export_preview.json
python scripts/apply_email_export.py --preview-json <path>/email_export_preview.json --apply
```

Dry-run is the default. `--apply` is required to stage candidates.

---

## Session layout

Preview and apply artifacts:

```text
<dest-dir>/email_import_sessions/<session_id>/
  email_export_preview.json
  email_export_preview.md
  email_export_apply_report.json
  email_export_apply_report.md
  extracted_text/
  metadata/
```

Review queue:

```text
<dest-dir>/memory_candidates/review_queue.jsonl
```

---

## File classification

| Category          | Meaning                         | Examples |
| ----------------- | ------------------------------- | -------- |
| `supported_now`   | Imported on apply               | `.eml`   |
| `supported_later` | Listed but not imported yet     | `.mbox`  |
| `unsupported`     | Not an email export format      | `.txt`   |
| `skipped`         | Symlink, oversize, scan rules   | symlinks |

---

## Candidate fields

Each staged candidate includes:

- `source_type: email_export`
- `review_status: pending`
- `suggested_memory_type: email_history`
- `live_memory_written: false`
- `safety_notes: operator_review_required`

Metadata includes `from`, `to`, `cc`, `date`, `subject`, `message_id`,
`attachments_ignored`, `html_body_used`, and `extraction_warnings`.

---

## Safety

- Local `.eml` files only (explicit `--input` paths)
- Symlinks not followed (checked before `resolve()`)
- File size validated on apply
- Attachments not extracted or written
- No remote images, links, or account access
- Duplicate apply protection via review queue
- No network, API, model, embedding, or vector DB usage

---

## Tests

```powershell
python -m pytest project_guardian/tests/test_email_export_ingest.py -q
```

---

## Related

- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
- [LOCAL_MEMORY_PIPELINE_CHECKPOINT.md](LOCAL_MEMORY_PIPELINE_CHECKPOINT.md)
- [CHATGPT_EXPORT_IMPORT_MVP.md](CHATGPT_EXPORT_IMPORT_MVP.md)
