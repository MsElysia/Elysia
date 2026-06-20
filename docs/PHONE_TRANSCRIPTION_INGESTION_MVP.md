# Phone transcription ingestion MVP

Operator-run local import for phone voice-to-text and transcription exports.
This tool does **not** enable autonomy, live monitoring, background watchers, or
server/API routes.

## Purpose

Import `.txt`, `.md`, `.vtt`, and `.srt` files from a folder you choose,
preserve the originals unchanged, normalize text for later memory work, and
write metadata plus a manifest under a local destination folder.

Optional memory-candidate staging prepares imports for **operator review** only.
Nothing is added to live memory, vector DB, or core memory automatically.

## Safety properties

- Source files are never deleted, moved, renamed, or modified.
- Symlinks are skipped.
- Only allowed text-like extensions are read.
- Binary-looking content and oversize files are skipped.
- Dry-run is the default; writing requires `--apply`.
- Memory-candidate staging requires `--apply` and only writes a local review queue.
- No recursive scan unless `--recursive` is passed.
- Duplicate content (by SHA-256 of normalized text) is not overwritten.
- Duplicate memory candidates (by stable candidate ID) are not written twice.

## Default destination

`data/phone_transcriptions/` under the repository root.

## CLI

Dry run (default):

```powershell
python scripts/ingest_phone_transcriptions.py --source-dir <path>
```

Apply writes:

```powershell
python scripts/ingest_phone_transcriptions.py --source-dir <path> --dest-dir <path> --apply
```

Stage review-queue memory candidates (requires `--apply`):

```powershell
python scripts/ingest_phone_transcriptions.py --source-dir <path> --apply --stage-memory-candidates
```

`--stage-memory-candidates` without `--apply` exits with a clear error. Dry-run
never writes memory candidate files.

Optional flags:

- `--recursive` — include subfolders (non-recursive by default)
- `--max-file-mb 5` — skip files larger than the limit (default: 5 MB)

## Output layout

```text
<dest-dir>/
  ingest_manifest.jsonl
  text/<hash12>_<name>.txt
  metadata/<hash12>_<name>.meta.json
  memory_candidates/review_queue.jsonl   # only with --stage-memory-candidates --apply
```

Each metadata sidecar includes:

- `original_filename`
- `original_path`
- `imported_at` (UTC ISO-8601)
- `source_size_bytes`
- `detected_extension`
- `sha256`
- `output_text_path`
- `output_metadata_path`
- `status`

Each memory-candidate record includes:

- `candidate_id` (stable hash of source SHA-256 + original filename)
- `source_type` (`phone_transcription`)
- `source_text_path`, `source_metadata_path`, `source_sha256`
- `original_filename`, `imported_at`, `staged_at`
- `review_status` (`pending`)
- `suggested_memory_type` (`personal_note`)
- `text_preview`, `text_length`
- `safety_notes` (`operator_review_required`)
- `live_memory_written` (`false`)

## Memory candidate review (not live memory)

After staging candidates, review them with the operator CLI. This records
approval/rejection/edit decisions locally only. **Nothing is written to live
memory, vector DB, or core memory.**

List pending candidates:

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> list --all
```

Approve, reject, or edit:

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id> --notes "useful memory"
python scripts/review_memory_candidates.py --dest-dir <path> reject <candidate_id> --notes "not useful"
python scripts/review_memory_candidates.py --dest-dir <path> edit <candidate_id> --replacement-text-file <path> --notes "cleaned up"
```

You may pass `--queue-path` instead of `--dest-dir` when pointing directly at
`memory_candidates/review_queue.jsonl`.

Review artifacts:

```text
<dest-dir>/memory_candidates/
  review_decisions.jsonl
  approved_candidates.jsonl
  rejected_candidates.jsonl
  edited/<candidate_id>.txt
```

The original `review_queue.jsonl` and imported source text/metadata remain
append-only and unchanged by review actions.

## Tests

```powershell
python -m pytest project_guardian/tests/test_transcription_ingest.py -q
python -m pytest project_guardian/tests/test_memory_candidate_review.py -q
```

## Out of scope (this MVP)

- Autonomy loops or live execution
- API/server endpoints
- Folder watchers or schedulers
- Automatic memory or vector DB writes
- Background processing
