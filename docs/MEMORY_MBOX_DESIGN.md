# Local `.mbox` memory import design

This document sketches a future local-only `.mbox` import lane. It is design
only. This overnight loop does not implement `.mbox` parsing, does not modify
importer scripts, and does not add live mailbox access.

## Current state

The supported email lane is local `.eml` files. `.mbox` remains a planned source
type and should continue to be classified as not implemented until a dedicated
future task adds parser code and tests.

## Non-goals

- No Gmail, Outlook, IMAP, SMTP, or mailbox account connection.
- No browser automation.
- No API calls.
- No broad filesystem crawling.
- No background watcher or automatic mailbox monitor.
- No attachment extraction in the first `.mbox` milestone.
- No live runtime memory or vector DB writes.
- No model or embedding calls.

## Future input contract

A future `.mbox` lane should accept only explicit local file paths selected by
the operator:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type mbox_export --input <path>\mailbox.mbox
```

The command above is illustrative only. It should fail until the future lane is
implemented.

Future preview output should include:

- source type: `mbox_export`
- mailbox file path
- message count
- skipped message count
- unsupported attachment count
- candidate count
- parser warnings
- safety flags

Required safety flags:

```text
model_called=false
embeddings_used=false
live_memory_written=false
autonomy_enabled=false
```

## Parsing boundaries

A future implementation should:

1. Read one explicitly provided `.mbox` file.
2. Parse messages into local preview records.
3. Normalize sender, recipients, subject, date, and plain text body.
4. Skip binary attachments.
5. Skip oversize messages with an explicit reason.
6. Preserve a stable local message identifier for review.
7. Stage only pending candidates after explicit `--apply`.

It should not recursively scan mail folders, watch mailbox locations, or infer
account credentials.

## Review flow

The downstream flow should remain the same as `.eml`:

```text
preview -> confirm apply -> pending candidates -> review -> approved export -> local store -> search -> context bundle
```

Pending `.mbox` candidates should use `review_status=pending` and should not be
searchable until approved.

## Future tests

A future `.mbox` task should add tests for:

- explicit local file required
- missing file fails safely
- mailbox messages preview without staging candidates
- `--apply` required before pending candidates are written
- attachments skipped
- oversize messages skipped
- malformed messages reported without crashing
- safety flags remain false
- no account/API/network calls
- no watcher or background monitor

## Acceptance criteria for future implementation

The `.mbox` lane should be accepted only when:

- focused `.mbox` preview/apply tests pass
- existing `.eml` tests still pass
- unified import tests still pass
- local memory pipeline smokes still pass
- safe-stack smoke still passes
- dry-run report remains SAFE

