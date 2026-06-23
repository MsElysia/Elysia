# Local memory pipeline checkpoint

**Date:** 2026-05-30  
**Status:** Known-good milestone — unified memory import command + three source lanes end-to-end  
**Scope:** Operator-run local ingestion only. No UI wiring, no live runtime memory, no models.

---

## Branch and commit

| Field | Value |
| ----- | ----- |
| Branch | `codex/limited-live-activation-wrapper` |
| HEAD (at checkpoint) | `9084281` — `feat(local): add unified memory import command` |

After the checkpoint document commit, the annotated restore tag
`unified_memory_import_clean_1` points at the checkpoint commit on this branch.

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

### Previous milestone (transcription + ChatGPT export smoke)

```text
local_memory_pipeline_chatgpt_clean_1
```

Points at `50ddfd9` — `docs(local): checkpoint chatgpt memory pipeline`.

Restore:

```powershell
git fetch origin tag local_memory_pipeline_chatgpt_clean_1
git checkout local_memory_pipeline_chatgpt_clean_1
```

### Previous milestone (transcription + ChatGPT + email export smoke)

```text
local_memory_pipeline_email_clean_1
```

Points at `c4ddcfe` — `docs(local): checkpoint email memory pipeline`.

Restore:

```powershell
git fetch origin tag local_memory_pipeline_email_clean_1
git checkout local_memory_pipeline_email_clean_1
```

Inspect:

```powershell
git show local_memory_pipeline_email_clean_1
```

### Current milestone (unified memory import command)

```text
unified_memory_import_clean_1
```

Restore:

```powershell
git fetch origin tag unified_memory_import_clean_1
git checkout unified_memory_import_clean_1
```

Inspect:

```powershell
git show unified_memory_import_clean_1
```

---

## What works now

### Unified memory import (operator-friendly entry point)

One command routes preview/apply to the existing safe importers. This is the backend
contract for a future drag-and-drop Memory screen. See
[UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md).

1. **Unified preview** — `python scripts/memory_import.py preview ...`
2. **Unified apply** — `python scripts/memory_import.py apply ...` (dry-run default; `--apply` stages pending candidates)
3. **Source auto-detection** — single-type inputs detected safely (transcription text, ChatGPT export JSON, `.eml`)
4. **Explicit source type routing** — `--source-type transcription|chatgpt_export|email_export`
5. **Ambiguous mixed folders fail safely** — require explicit `--source-type` when multiple source kinds are present

Unified apply stops at pending candidate staging. It does **not** approve, export, store, search, or build context bundles.

### Three source lanes

**Shared downstream path:** preview/apply → pending candidates → review approval → approved export →
local memory store → search → context bundle.

#### Source lane 1 — phone / transcription files

- `.txt`, `.md`, `.vtt`, `.srt` via import session preview/apply

#### Source lane 2 — local ChatGPT export files

- `conversations.json` or ChatGPT-shaped JSON via ChatGPT export preview/apply
- Symlink guard on export and preview paths

#### Source lane 3 — local email export files (`.eml`)

- `.eml` via email export preview/apply; `.mbox` remains `supported_later`
- Attachment-safe extraction; symlinks rejected before `stat()`/`resolve()`

### Shared pipeline steps (all lanes)

6. **Memory candidate staging** — `memory_candidates/review_queue.jsonl` (`review_status=pending`, `live_memory_written=false`)
7. **Candidate review** — operator approve/reject/edit with audit trail
8. **Approved export** — `memory_candidates/approved_memory_export.jsonl`
9. **Approved local memory store** — `memory_store/approved_memory_store.jsonl`
10. **Approved memory search** — read-only case-insensitive search over the local store
11. **Approved memory context bundle** — Markdown + JSON context packages for future local model use
12. **Full pipeline smoke** — end-to-end verification on temporary sample data with:
    - `--source-type transcription`
    - `--source-type chatgpt_export`
    - `--source-type email_export`

Related docs:

- [UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md)
- [PHONE_TRANSCRIPTION_INGESTION_MVP.md](PHONE_TRANSCRIPTION_INGESTION_MVP.md)
- [CHATGPT_EXPORT_IMPORT_MVP.md](CHATGPT_EXPORT_IMPORT_MVP.md)
- [EMAIL_EXPORT_IMPORT_MVP.md](EMAIL_EXPORT_IMPORT_MVP.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)

---

## Important commands

### Unified memory import (recommended entry point)

```powershell
python scripts/memory_import.py preview --dest-dir <path> --input <file-or-folder>
python scripts/memory_import.py preview --dest-dir <path> --input <folder> --recursive
python scripts/memory_import.py preview --dest-dir <path> --source-type transcription --input <path>
python scripts/memory_import.py preview --dest-dir <path> --source-type chatgpt_export --input <path>
python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
python scripts/memory_import.py apply --session-json <path>
python scripts/memory_import.py apply --session-json <path> --apply
```

### Per-lane commands (still available)

Default destination for phone transcriptions: `data/phone_transcriptions/`

```powershell
python scripts/preview_memory_import_session.py --dest-dir <path> --input <file-or-folder>
python scripts/apply_memory_import_session.py --session-json <path>/import_session_preview.json --apply
python scripts/preview_chatgpt_export.py --export-json <path> --dest-dir <path>
python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json --apply
python scripts/preview_email_export.py --dest-dir <path> --input <file-or-folder>
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

Smoke modes use temporary folders only. Default `--source-type` is `transcription`.

---

## Safety guarantees

| Guarantee | Status |
| --------- | ------ |
| Autonomy disabled (`config/autonomy.json` → `enabled: false`) | Yes |
| No live execution | Yes |
| No model / API / embedding / internet calls in pipeline steps | Yes |
| No live runtime memory or vector DB writes | Yes |
| No server/API route wiring for local ingestion | Yes |
| No watchers or background folder monitors | Yes |
| Local exported files only (explicit paths; no live account access) | Yes |
| No live ChatGPT account access | Yes |
| No live email account access (no Gmail/Outlook/IMAP/SMTP) | Yes |
| Attachments ignored on email import | Yes |
| Ambiguous mixed folders fail safely unless `--source-type` is explicit | Yes |
| User/source files preserved (read-only ingestion inputs; export hash verified on apply) | Yes |
| Dry-run / explicit `--apply` gates where relevant | Yes |

Each pipeline artifact includes safety metadata where applicable (`model_called: false`,
`embeddings_used: false`, `live_memory_written: false`, `autonomy_enabled: false`).

---

## Verification baseline

Verified at checkpoint creation:

| Check | Expected result |
| ----- | ----------------- |
| Unified import tests | `python -m pytest project_guardian/tests/test_unified_memory_import.py -q` → all passed |
| Transcription smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription` → `verdict: PASS` |
| ChatGPT export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export` → `verdict: PASS` |
| Email export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export` → `verdict: PASS` |
| Email export regression | `python -m pytest project_guardian/tests/test_email_export_ingest.py -q` → all passed |
| ChatGPT export regression | `python -m pytest project_guardian/tests/test_chatgpt_export_ingest.py -q` → all passed |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` → pytest PASSED |
| Dry-run report | `python scripts/run_elysia_dry_run_report.py --mode real-planning` → `SAFE`, `any_executed: False` |

Representative regression commands:

```powershell
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q
python -m pytest project_guardian/tests/test_email_export_ingest.py -q
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

## Milestone commit chain (unified import slice)

| Commit | Message |
| ------ | ------- |
| `9084281` | `feat(local): add unified memory import command` |
| `c4ddcfe` | `docs(local): checkpoint email memory pipeline` ← `local_memory_pipeline_email_clean_1` |
| `8958d19` | `test(local): cover email export memory pipeline` |
| `69f9c8e` | `fix(local): skip email symlinks before stat` |
| `b9311f4` | `feat(local): import email export candidates` |
| `50ddfd9` | `docs(local): checkpoint chatgpt memory pipeline` ← `local_memory_pipeline_chatgpt_clean_1` |
| `0a55e52` | `test(local): cover chatgpt export memory pipeline` |
| `2174efb` | `fix(local): reject chatgpt export symlinks before resolve` |
| `e5c98a7` | `feat(local): import chatgpt export candidates` |
| `3ea3d5d` | `docs(local): checkpoint memory pipeline milestone` ← `local_memory_pipeline_clean_1` |
| `82eaee3` | `test(local): add memory pipeline smoke command` |
| `e6ee36a` | `feat(local): apply memory import sessions` |
| `148e370` | `feat(local): preview memory import sessions` |

Earlier transcription ingestion MVP commits precede this chain.

---

## What this enables next

Safe follow-on work from this checkpoint:

- **Dashboard Memory screen** — wire unified preview/apply to a control panel view
- **Drag-and-drop import zone** — call `memory_import.py preview` from UI with explicit paths
- **Local model prompt/context handoff** — feed approved context bundles to Ollama/Mistral with explicit operator invocation
- **`.mbox` support later** — extend email lane beyond single `.eml` files
- **Document/PDF import later** — additional source lanes using the same downstream pipeline
- **Later approved runtime memory/vector integration** — only after explicit operator approval and separate safety review

---

## Intentionally not done

The following remain out of scope for this milestone:

- No UI yet
- No server/API routes for import or approved memory operations
- No live ChatGPT account access
- No live email account access
- No `.mbox` import yet
- No local model call from pipeline steps
- No embeddings
- No live runtime memory / vector DB writes
- No automatic folder watching or background ingestion
- No autonomy or live execution

---

## Operator note

This checkpoint protects real progress. Before adding the Memory screen UI, local model calls, or additional
import types, confirm unified import tests, all three smoke modes, and regressions still pass from tag
`unified_memory_import_clean_1` or branch tip.
