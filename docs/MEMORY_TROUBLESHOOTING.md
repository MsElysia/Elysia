# Memory troubleshooting guide

This guide covers common local Memory Hub problems. It assumes the safe workflow:
local files only, preview before apply, review before approval, and no live
account, model, embedding, or server-route access.

## Import file is not recognized

Check the source type and file extension:

| Expected lane | Common extensions |
| ------------- | ----------------- |
| Transcription/text | `.txt`, `.md`, `.vtt`, `.srt` |
| ChatGPT export | `conversations.json` or compatible export-shaped JSON |
| Email export | `.eml` |

Use an explicit source type when the folder contents are not obvious:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type transcription --input <path>
```

Do not add PDF, DOCX, image, `.mbox`, or live account inputs. Those lanes are not
implemented in this slice.

## Mixed folder is rejected

Mixed folders can contain files from more than one source lane. Keep one source
type per folder when possible.

If the folder is intentionally one lane, pass the source type explicitly:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
```

If it is genuinely mixed, split it into separate folders and preview each lane
on its own.

## ChatGPT export is not detected

Confirm that the local export was extracted and contains `conversations.json`.
Point the preview command at the JSON file or the folder containing it:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type chatgpt_export --input <path>\conversations.json
```

This workflow does not log in to ChatGPT or fetch account data. It only reads
the local export file selected by the operator.

## Email `.eml` is not detected

Confirm the message was saved as a local `.eml` file and not as a shortcut,
mailbox archive, or proprietary client item.

Preview with the explicit email lane:

```powershell
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
```

`.mbox` is design-only for now and should not be expected to import.

## Candidate is not appearing

Common causes:

- You only ran preview and did not run apply.
- Apply was run without the explicit `--apply` confirmation flag.
- The preview had no supported files.
- The candidate was written to a different `--dest-dir`.

Confirm from the same destination folder:

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
```

Pending candidates are expected. They are not approved memory yet.

## Search returns nothing

Search uses approved local memory. It will not return pending candidates.

Check that candidates were approved and exported into the local memory store
before searching:

```powershell
python scripts/search_approved_memory_store.py --dest-dir <path> search "example query"
```

Try a shorter query or a term that appears directly in an approved memory.

## Context bundle is missing

Context bundles are built on explicit operator request. They are not created by
preview, apply, or approval alone.

Build one after approved memory exists:

```powershell
python scripts/build_approved_memory_context.py --dest-dir <path> --query "example query"
```

The context bundle is a local file artifact. It is not sent to a model by this
workflow.

## Dry-run confusion

Preview is always non-destructive. Apply should require explicit confirmation:

```powershell
python scripts/memory_import.py apply --session-json <path-to-preview-json> --apply
```

If `--apply` is omitted, treat the result as a dry-run style report and verify
whether candidates were actually staged.

## Where files are written

Memory pipeline files are written under the destination directory passed with
`--dest-dir`. Use the same destination directory for preview, apply, review,
search, and context bundle commands.

Typical artifacts include:

- import preview JSON and Markdown
- apply report JSON and Markdown
- pending candidate review queue
- approved memory export
- approved memory store
- context bundle files

## Safety stop signs

Stop and inspect before continuing if any output reports:

```text
model_called=true
embeddings_used=true
live_memory_written=true
autonomy_enabled=true
```

Also stop if a workflow asks for live account credentials, starts a watcher,
opens a server route, or tries to access network services.

