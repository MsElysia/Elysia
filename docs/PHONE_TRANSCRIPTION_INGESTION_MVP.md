# Phone transcription ingestion MVP

Operator-run local import for phone voice-to-text and transcription exports.
This tool does **not** enable autonomy, live monitoring, background watchers, or
server/API routes.

## Purpose

Import `.txt`, `.md`, `.vtt`, and `.srt` files from a folder you choose,
preserve the originals unchanged, normalize text for later memory work, and
write metadata plus a manifest under a local destination folder.

## Safety properties

- Source files are never deleted, moved, renamed, or modified.
- Symlinks are skipped.
- Only allowed text-like extensions are read.
- Binary-looking content and oversize files are skipped.
- Dry-run is the default; writing requires `--apply`.
- No recursive scan unless `--recursive` is passed.
- Duplicate content (by SHA-256 of normalized text) is not overwritten.

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

Optional flags:

- `--recursive` — include subfolders (non-recursive by default)
- `--max-file-mb 5` — skip files larger than the limit (default: 5 MB)

## Output layout

```text
<dest-dir>/
  ingest_manifest.jsonl
  text/<hash12>_<name>.txt
  metadata/<hash12>_<name>.meta.json
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

## Tests

```powershell
python -m pytest project_guardian/tests/test_transcription_ingest.py -q
```

## Out of scope (this MVP)

- Autonomy loops or live execution
- API/server endpoints
- Folder watchers or schedulers
- Vector memory or embedding writes
