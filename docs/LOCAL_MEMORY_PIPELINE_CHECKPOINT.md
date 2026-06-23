# Local memory pipeline checkpoint

**Date:** 2026-05-30  
**Status:** Known-good milestone — transcription and ChatGPT export lanes complete end-to-end  
**Scope:** Operator-run local ingestion only. No UI wiring, no live runtime memory, no models.

---

## Branch and commit

| Field | Value |
| ----- | ----- |
| Branch | `codex/limited-live-activation-wrapper` |
| HEAD (at checkpoint) | `0a55e52` — `test(local): cover chatgpt export memory pipeline` |

After the checkpoint document commit, the annotated restore tag
`local_memory_pipeline_chatgpt_clean_1` points at the checkpoint commit on this branch.

---

## Restore tags

### Previous milestone (transcription-only smoke)

```text
local_memory_pipeline_clean_1
```

Points at `3ea3d5d` — `docs(local): checkpoint memory pipeline milestone`.

Restore:

```powershell
git fetch origin tag local_memory_pipeline_clean_1
git checkout local_memory_pipeline_clean_1
```

### Current milestone (transcription + ChatGPT export smoke)

```text
local_memory_pipeline_chatgpt_clean_1
```

Restore:

```powershell
git fetch origin tag local_memory_pipeline_chatgpt_clean_1
git checkout local_memory_pipeline_chatgpt_clean_1
```

Inspect:

```powershell
git show local_memory_pipeline_chatgpt_clean_1
```

---

## What works now

Two source lanes flow through the same approved local memory pipeline:

**Shared downstream path:** pending candidates → review approval → approved export →
local memory store → search → context bundle.

### Source lane 1 — phone / transcription files

1. **Import session preview** — classify explicit file/folder paths
2. **Import session apply** — confirm preview and stage transcription memory candidates
3. **Transcription ingestion** — normalize `.txt`, `.md`, `.vtt`, `.srt` into local text/metadata/manifest

### Source lane 2 — local ChatGPT export files

1. **ChatGPT export preview** — read local `conversations.json`, write session preview JSON/Markdown
2. **ChatGPT export apply** — stage pending candidates with `source_type=chatgpt_export` (dry-run default; `--apply` required)
3. **Symlink guard** — export and preview paths rejected before `resolve()`

### Source lane 3 — local email export files (`.eml`)

1. **Email export preview** — classify explicit `.eml` paths; `.mbox` as `supported_later` only
2. **Email export apply** — stage pending candidates with `source_type=email_export` (dry-run default; `--apply` required)
3. **Attachment-safe extraction** — plain/HTML body only; attachments ignored; no network

### Shared pipeline steps (all lanes)

4. **Memory candidate staging** — `memory_candidates/review_queue.jsonl`
5. **Candidate review** — operator approve/reject/edit with audit trail
6. **Approved export** — `memory_candidates/approved_memory_export.jsonl`
7. **Approved local memory store** — `memory_store/approved_memory_store.jsonl`
8. **Approved memory search** — read-only case-insensitive search over the local store
9. **Approved memory context bundle** — Markdown + JSON context packages for future local model use
10. **Full pipeline smoke** — end-to-end verification on temporary sample data with `--source-type transcription` or `--source-type chatgpt_export`

Related docs:

- [PHONE_TRANSCRIPTION_INGESTION_MVP.md](PHONE_TRANSCRIPTION_INGESTION_MVP.md)
- [CHATGPT_EXPORT_IMPORT_MVP.md](CHATGPT_EXPORT_IMPORT_MVP.md)
- [EMAIL_EXPORT_IMPORT_MVP.md](EMAIL_EXPORT_IMPORT_MVP.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)

---

## Important commands

Default destination for phone transcriptions: `data/phone_transcriptions/`

### Import session (transcription lane)

```powershell
python scripts/preview_memory_import_session.py --dest-dir <path> --input <file-or-folder>
python scripts/preview_memory_import_session.py --dest-dir <path> --input <folder> --recursive
python scripts/apply_memory_import_session.py --session-json <path>/import_session_preview.json
python scripts/apply_memory_import_session.py --session-json <path>/import_session_preview.json --apply
```

### ChatGPT export (ChatGPT lane)

```powershell
python scripts/preview_chatgpt_export.py --export-json <path> --dest-dir <path>
python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json
python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json --apply
```

### Email export (email lane)

```powershell
python scripts/preview_email_export.py --dest-dir <path> --input <file-or-folder>
python scripts/preview_email_export.py --dest-dir <path> --input <folder> --recursive
python scripts/apply_email_export.py --preview-json <path>/email_export_preview.json --apply
```

### Review and approved memory pipeline (all lanes)

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id>
python scripts/export_approved_memory_candidates.py --dest-dir <path>
python scripts/write_approved_memory_store.py --dest-dir <path> --apply
python scripts/search_approved_memory_store.py --dest-dir <path> search --query "drywall quote"
python scripts/build_approved_memory_context.py --dest-dir <path> --query "drywall quote"
```

### End-to-end smoke (recommended verification)

```powershell
python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription
python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export
python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export
```

Transcription, ChatGPT export, and email export smoke modes use temporary folders only.
Default `--source-type` is `transcription`.

---

## Safety guarantees

| Guarantee | Status |
| --------- | ------ |
| Autonomy disabled (`config/autonomy.json` → `enabled: false`) | Yes |
| No live execution | Yes |
| No model / embedding / internet / account API calls in pipeline steps | Yes |
| No live runtime memory or vector DB writes | Yes |
| No server/API route wiring for local ingestion | Yes |
| No watchers or background folder monitors | Yes |
| Local exported files only (explicit paths; no live ChatGPT account access) | Yes |
| User/source files preserved (read-only ingestion inputs; export hash verified on apply) | Yes |
| Dry-run / explicit `--apply` gates where relevant | Yes |

Each pipeline artifact includes safety metadata where applicable (`model_called: false`,
`embeddings_used: false`, `live_memory_written: false`).

---

## Verification baseline

Verified at checkpoint creation:

| Check | Expected result |
| ----- | ----------------- |
| Transcription smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription` → `verdict: PASS` |
| ChatGPT export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export` → `verdict: PASS` |
| Email export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export` → `verdict: PASS` |
| ChatGPT export regression | `python -m pytest project_guardian/tests/test_chatgpt_export_ingest.py -q` → all passed |
| Email export regression | `python -m pytest project_guardian/tests/test_email_export_ingest.py -q` → all passed |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` → pytest PASSED |
| Dry-run report | `python scripts/run_elysia_dry_run_report.py --mode real-planning` → `SAFE`, `any_executed: False` |

Representative regression commands:

```powershell
python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q
python -m pytest project_guardian/tests/test_chatgpt_export_ingest.py -q
python -m pytest project_guardian/tests/test_import_session_preview.py -q
python -m pytest project_guardian/tests/test_import_session_apply.py -q
python -m pytest project_guardian/tests/test_memory_candidate_review.py -q
python -m pytest project_guardian/tests/test_approved_memory_export.py -q
python -m pytest project_guardian/tests/test_approved_memory_store.py -q
python -m pytest project_guardian/tests/test_approved_memory_search.py -q
python -m pytest project_guardian/tests/test_approved_memory_context.py -q
python -m pytest project_guardian/tests/test_transcription_ingest.py -q
```

---

## Milestone commit chain (local memory + ChatGPT slice)

| Commit | Message |
| ------ | ------- |
| `0a55e52` | `test(local): cover chatgpt export memory pipeline` |
| `2174efb` | `fix(local): reject chatgpt export symlinks before resolve` |
| `e5c98a7` | `feat(local): import chatgpt export candidates` |
| `3ea3d5d` | `docs(local): checkpoint memory pipeline milestone` ← `local_memory_pipeline_clean_1` |
| `82eaee3` | `test(local): add memory pipeline smoke command` |
| `e6ee36a` | `feat(local): apply memory import sessions` |
| `148e370` | `feat(local): preview memory import sessions` |
| `42cbd72` | `feat(local): build approved memory context bundles` |
| `38e7724` | `feat(local): search approved memory store` |
| `f657295` | `feat(local): write approved local memory store` |
| `80ec78a` | `feat(local): export approved memory candidates` |
| `71af5da` | `feat(local): add memory candidate review cli` |

Earlier transcription ingestion MVP commits precede this chain.

---

## What this enables next

Safe follow-on work from this checkpoint:

- **Email export import** — `.eml` preview/apply implemented; `.mbox` remains `supported_later`
- **UI drag-and-drop memory import** — wire preview/apply session layers to a control panel screen
- **Local model prompt/context handoff** — feed approved context bundles to Ollama/Mistral with explicit operator invocation
- **Later approved runtime memory/vector integration** — only after explicit operator approval and separate safety review

---

## Intentionally not done

The following remain out of scope for this milestone:

- No live ChatGPT account access
- No live email account access
- No local model call from pipeline steps
- No embeddings
- No live runtime memory / vector DB writes
- No server/API routes for import session or approved memory operations
- No automatic folder watching or background ingestion
- No autonomy or live execution

---

## Operator note

This checkpoint protects real progress. Before adding email import, UI wiring, or local
model calls, confirm both smoke modes and regressions still pass from tag
`local_memory_pipeline_chatgpt_clean_1` or branch tip.
