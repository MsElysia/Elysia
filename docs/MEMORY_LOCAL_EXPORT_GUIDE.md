# Local memory export guide

This guide explains how to prepare local ChatGPT and email export files for the
Memory Hub workflow. It does not add account access, API access, network calls,
or live import behavior.

## Safety rules

- Export files manually with the account owner present.
- Copy completed export files into a local working folder.
- Run Elysia import commands only against those local files.
- Do not give Elysia account credentials, browser sessions, tokens, mailbox
  passwords, or API keys.
- Do not connect Gmail, Outlook, IMAP, SMTP, ChatGPT, or any live service.
- Keep imports preview-first and review candidates before approval.

## Local folder layout

A simple folder layout keeps imports easy to inspect:

```text
memory_exports/
  chatgpt/
    conversations.json
  email/
    client-note-001.eml
    estimate-thread-002.eml
  transcription/
    project-call-notes.md
```

Use short folder names and keep one source type per folder when possible. Mixed
folders should use an explicit `--source-type` during preview.

## ChatGPT conversation export

Use a locally downloaded export file. The current supported shape is a
`conversations.json` file or compatible export-shaped JSON.

Preparation checklist:

1. Export conversations manually from the ChatGPT product UI.
2. Wait for the export archive to finish.
3. Download the archive yourself.
4. Extract the archive locally.
5. Copy `conversations.json` into a local working folder.
6. Preview it with the local import command.

Preview:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type chatgpt_export --input <path>\conversations.json
```

Confirm only after reviewing the preview:

```powershell
python scripts/memory_import.py apply --session-json <path-to-preview-json> --apply
```

This workflow does not log in to ChatGPT, call a ChatGPT API, or fetch account
data automatically.

## Email `.eml` export

Use local `.eml` files that were exported manually from an email client or
mailbox tool. The current supported lane is `.eml`; `.mbox` is planned later
and is not implemented in this milestone.

Preparation checklist:

1. Choose the specific messages you want to review for memory.
2. Export or save each message as `.eml`.
3. Copy the `.eml` files into a local working folder.
4. Avoid adding mailbox archives, attachments, or unrelated folders.
5. Preview with the explicit email source type.

Preview:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>\email
```

Confirm only after reviewing the preview:

```powershell
python scripts/memory_import.py apply --session-json <path-to-preview-json> --apply
```

This workflow does not connect to Gmail, Outlook, IMAP, SMTP, or any mailbox
account. Attachments are not part of the current lane.

## Transcription and text files

For notes, transcripts, captions, or text exports, use local `.txt`, `.md`,
`.vtt`, or `.srt` files.

Preview:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type transcription --input <path>
```

## Review before approval

All imports should move through pending candidates first:

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id>
python scripts/review_memory_candidates.py --dest-dir <path> reject <candidate_id>
```

Only approved memories should become searchable.

## Validation smoke checks

Run the local smokes after changing export preparation docs or import behavior:

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

