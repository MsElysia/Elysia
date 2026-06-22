# Local memory pipeline checkpoint

**Date:** 2026-05-30  
**Status:** Known-good milestone — safe local memory pipeline complete end-to-end  
**Scope:** Operator-run local ingestion only. No UI wiring, no live runtime memory, no models.

---

## Branch and commit

| Field | Value |
| ----- | ----- |
| Branch | `codex/limited-live-activation-wrapper` |
| HEAD (at checkpoint) | `82eaee3` — `test(local): add memory pipeline smoke command` |

After the checkpoint document commit, the annotated restore tag points at the
checkpoint commit on this branch.

---

## Restore tag

```text
local_memory_pipeline_clean_1
```

Restore to this known-good state:

```powershell
git fetch origin tag local_memory_pipeline_clean_1
git checkout local_memory_pipeline_clean_1
```

Or inspect:

```powershell
git show local_memory_pipeline_clean_1
```

---

## What works now

The following operator-run local memory pipeline steps are implemented, tested,
and wired through explicit CLIs (no server routes, no autonomy):

1. **Import session preview** — classify explicit file/folder paths for future drag-and-drop UI
2. **Import session apply** — confirm preview and stage transcription memory candidates
3. **Transcription ingestion** — normalize `.txt`, `.md`, `.vtt`, `.srt` into local text/metadata/manifest
4. **Memory candidate staging** — write `memory_candidates/review_queue.jsonl`
5. **Candidate review** — operator approve/reject/edit with audit trail
6. **Approved export** — `memory_candidates/approved_memory_export.jsonl`
7. **Approved local memory store** — `memory_store/approved_memory_store.jsonl`
8. **Approved memory search** — read-only case-insensitive search over the local store
9. **Approved memory context bundle** — Markdown + JSON context packages for future local model use
10. **Full pipeline smoke** — end-to-end verification on temporary sample files

Related docs:

- [PHONE_TRANSCRIPTION_INGESTION_MVP.md](PHONE_TRANSCRIPTION_INGESTION_MVP.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)

---

## Important commands

Default destination for phone transcriptions: `data/phone_transcriptions/`

### Import session (UI backend foundation)

```powershell
python scripts/preview_memory_import_session.py --dest-dir <path> --input <file-or-folder>
python scripts/preview_memory_import_session.py --dest-dir <path> --input <folder> --recursive
python scripts/apply_memory_import_session.py --session-json <path>/import_session_preview.json
python scripts/apply_memory_import_session.py --session-json <path>/import_session_preview.json --apply
```

### Review and approved memory pipeline

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
python scripts/run_local_memory_pipeline_smoke.py
python scripts/run_local_memory_pipeline_smoke.py --json
python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription
python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export
```

The smoke command supports `--source-type transcription` (default) and
`--source-type chatgpt_export` for full local preview → apply → review → export →
store → search → context coverage on temporary sample data only.

---

## Safety guarantees

This milestone preserves the following constraints:

| Guarantee | Status |
| --------- | ------ |
| Autonomy disabled (`config/autonomy.json` → `enabled: false`) | Yes |
| No live execution | Yes |
| No model / embedding / internet calls in pipeline steps | Yes |
| No live runtime memory or vector DB writes | Yes |
| No server/API route wiring for local ingestion | Yes |
| No watchers or background folder monitors | Yes |
| User/source files preserved (read-only ingestion inputs) | Yes |
| Dry-run / explicit `--apply` gates where relevant | Yes |

Each pipeline artifact includes safety metadata where applicable (`model_called: false`,
`embeddings_used: false`, `live_memory_written: false`).

---

## Verification baseline

Verified at checkpoint creation:

| Check | Expected result |
| ----- | ----------------- |
| Local pipeline smoke | `python scripts/run_local_memory_pipeline_smoke.py --json` → `verdict: PASS` |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` → pytest PASSED |
| Dry-run report | `python scripts/run_elysia_dry_run_report.py --mode real-planning` → `SAFE`, `any_executed: False` |
| Local ingestion regressions | pytest slices for preview, apply, review, export, store, search, context, ingest, smoke |

Representative regression commands:

```powershell
python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q
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

## Milestone commit chain (local memory slice)

| Commit | Message |
| ------ | ------- |
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

- **UI drag-and-drop memory import** — wire preview/apply session layers to a control panel screen
- **ChatGPT export import** — new `supported_later` source types through the same preview/review pattern
- **Email export import** — `.eml` / `.mbox` through staged preview classification
- **Approved-memory local model prompt flow** — feed context bundles to Ollama/Mistral with explicit operator invocation

---

## Intentionally not done

The following remain out of scope for this milestone:

- No live memory / vector DB integration
- No local model call from pipeline steps
- No automatic folder watching or background ingestion
- No autonomy or live execution
- No broad account/API access from ingestion tools
- No server/API routes for import session or approved memory operations

---

## Operator note

This checkpoint protects real progress. Before adding UI wiring or new import
sources, confirm smoke and regressions still pass from this tag or branch tip.
