# Local memory pipeline checkpoint

**Date:** 2026-05-30  
**Status:** Known-good milestone — Memory review/search UI foundation + import UI + unified import + three source lanes  
**Scope:** Operator-run local ingestion and UI contracts only. No dashboard wiring, no live runtime memory, no models.

---

## Branch and commit

| Field | Value |
| ----- | ----- |
| Branch | `codex/limited-live-activation-wrapper` |
| HEAD (at checkpoint) | `df24d40` — `docs(ui): checkpoint memory screen foundation` |

After the Memory review/search UI foundation commit, branch tip includes the new review/search contract and static prototype.
Prior restore tag `memory_screen_ui_foundation_clean_1` points at `df24d40`.

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

### Previous milestone (unified memory import command)

```text
unified_memory_import_clean_1
```

Points at `44612d0` — `docs(local): checkpoint unified memory import`.

Restore:

```powershell
git fetch origin tag unified_memory_import_clean_1
git checkout unified_memory_import_clean_1
```

Inspect:

```powershell
git show unified_memory_import_clean_1
```

### Current milestone (Memory screen UI foundation)

```text
memory_screen_ui_foundation_clean_1
```

Points at `df24d40` — `docs(ui): checkpoint memory screen foundation`.

Restore:

```powershell
git fetch origin tag memory_screen_ui_foundation_clean_1
git checkout memory_screen_ui_foundation_clean_1
```

Inspect:

```powershell
git show memory_screen_ui_foundation_clean_1
```

### Latest work (Memory review/search UI foundation — branch tip)

UI contract and static prototype for pending candidate review, approved memory search, and context bundle placeholders.
No server routes wired yet. See [MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md](MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md).

---

## What works now

### Memory review/search UI foundation (user-facing structure)

UI contract and static prototype for review, search, and context bundle placeholders. No server routes wired yet.
See [MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md](MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md) and
[MEMORY_REVIEW_SEARCH_UI_CONTRACT.json](MEMORY_REVIEW_SEARCH_UI_CONTRACT.json).

1. **Pending candidates section** — list/filter by source type; candidate cards with preview and status
2. **Review actions** — approve/reject/edit with operator confirmation (contract only)
3. **Approved memory section** — browse approved items with source filter
4. **Search approved memory** — read-only search contract and prototype UI
5. **Context bundle section** — future placeholder; local file output explained

### Memory screen UI foundation (import — prior milestone)

UI contract and static prototype for a future dashboard Memory import screen. No server routes wired yet.
See [MEMORY_SCREEN_UI_FOUNDATION.md](MEMORY_SCREEN_UI_FOUNDATION.md) and
[MEMORY_SCREEN_UI_CONTRACT.json](MEMORY_SCREEN_UI_CONTRACT.json).

6. **Memory import UI contract** — preview/apply request/response shapes, three source types, safety flags
7. **Static Memory import prototype** — `project_guardian/ui/static/memory_import_screen.html` (mock data only)
8. **Plain-language user safety copy** — confirm-before-save, pending review, local files only, no live accounts
9. **Preview / apply UI structure** — Add files → Preview → Confirm import

### Unified memory import (backend entry point)

One command routes preview/apply to the existing safe importers. See
[UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md).

5. **Unified preview** — `python scripts/memory_import.py preview ...`
6. **Unified apply** — dry-run default; `--apply` stages pending candidates only
7. **Source auto-detection** — transcription text, ChatGPT export JSON, `.eml`
8. **Explicit source type routing** — `--source-type transcription|chatgpt_export|email_export`
9. **Ambiguous mixed folders fail safely** — require explicit `--source-type`

### Three source lanes + shared pipeline

**Shared downstream path:** preview/apply → pending candidates → review approval → approved export →
local memory store → search → context bundle.

| Lane | Inputs | Backend |
| ---- | ------ | ------- |
| Transcription / text | `.txt`, `.md`, `.vtt`, `.srt` | import session preview/apply |
| ChatGPT export | `conversations.json` or export-shaped JSON | ChatGPT export preview/apply |
| Email export | `.eml` (`.mbox` = `supported_later`) | email export preview/apply |

10. **Memory candidate staging** — `review_status=pending`, `live_memory_written=false`
11. **Candidate review** — approve/reject/edit with audit trail
12. **Approved export** — `memory_candidates/approved_memory_export.jsonl`
13. **Approved local memory store** — `memory_store/approved_memory_store.jsonl`
14. **Approved memory search** — read-only case-insensitive search
15. **Approved memory context bundle** — Markdown + JSON for future local model handoff
16. **Full pipeline smoke** — `--source-type transcription|chatgpt_export|email_export`

### Important files

| File | Purpose |
| ---- | ------- |
| `docs/MEMORY_REVIEW_SEARCH_UI_CONTRACT.json` | Review/search/context UI contract |
| `docs/MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md` | Review/search screen layout and CLI mapping |
| `project_guardian/ui/static/memory_review_search.html` | Static review/search prototype (no server wiring) |
| `docs/MEMORY_SCREEN_UI_CONTRACT.json` | Import preview/apply UI contract |
| `docs/MEMORY_SCREEN_UI_FOUNDATION.md` | Import screen layout and backend mapping |
| `project_guardian/ui/static/memory_import_screen.html` | Static import prototype (no server wiring) |
| `scripts/memory_import.py` | Unified preview/apply CLI |
| `scripts/review_memory_candidates.py` | Pending candidate review CLI |
| `scripts/search_approved_memory_store.py` | Approved memory search CLI |
| `scripts/build_approved_memory_context.py` | Context bundle CLI |

Related docs:

- [UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
- [PHONE_TRANSCRIPTION_INGESTION_MVP.md](PHONE_TRANSCRIPTION_INGESTION_MVP.md)
- [CHATGPT_EXPORT_IMPORT_MVP.md](CHATGPT_EXPORT_IMPORT_MVP.md)
- [EMAIL_EXPORT_IMPORT_MVP.md](EMAIL_EXPORT_IMPORT_MVP.md)

---

## Important commands

### Unified memory import

```powershell
python scripts/memory_import.py preview --dest-dir <path> --input <file-or-folder>
python scripts/memory_import.py apply --session-json <path> --apply
```

### End-to-end smoke

```powershell
python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription
python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export
python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export
```

### Static prototypes (local browser only)

```powershell
start project_guardian/ui/static/memory_import_screen.html
start project_guardian/ui/static/memory_review_search.html
```

### Review and approved memory pipeline (CLI; not wired to UI yet)

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id>
python scripts/export_approved_memory_candidates.py --dest-dir <path>
python scripts/write_approved_memory_store.py --dest-dir <path> --apply
python scripts/search_approved_memory_store.py --dest-dir <path> search --query "drywall quote"
python scripts/build_approved_memory_context.py --dest-dir <path> --query "drywall quote"
```

---

## Safety guarantees

| Guarantee | Status |
| --------- | ------ |
| Autonomy disabled (`config/autonomy.json` → `enabled: false`) | Yes |
| No live execution | Yes |
| No model / API / embedding / internet calls | Yes |
| No live runtime memory or vector DB writes | Yes |
| No server/API route wiring | Yes |
| No watchers or background folder monitors | Yes |
| Local exported files only (no live account access) | Yes |
| No live ChatGPT account access | Yes |
| No live email account access (no Gmail/Outlook/IMAP/SMTP) | Yes |
| Attachments ignored on email import | Yes |
| Ambiguous mixed folders fail safely unless `--source-type` is explicit | Yes |
| Static prototype only — no backend calls from HTML page | Yes |
| Dry-run / explicit `--apply` gates where relevant | Yes |

Each pipeline artifact includes safety metadata where applicable (`model_called: false`,
`embeddings_used: false`, `live_memory_written: false`, `autonomy_enabled: false`).

---

## Verification baseline

Verified at checkpoint creation:

| Check | Expected result |
| ----- | ----------------- |
| Review/search UI contract tests | `python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q` → all passed |
| UI contract tests (import) | `python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q` → all passed |
| Unified import tests | `python -m pytest project_guardian/tests/test_unified_memory_import.py -q` → all passed |
| Transcription smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription` → `verdict: PASS` |
| ChatGPT export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export` → `verdict: PASS` |
| Email export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export` → `verdict: PASS` |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` → pytest PASSED |
| Dry-run report | `python scripts/run_elysia_dry_run_report.py --mode real-planning` → `SAFE`, `any_executed: False` |

Representative regression commands:

```powershell
python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q
python -m pytest project_guardian/tests/test_email_export_ingest.py -q
python -m pytest project_guardian/tests/test_chatgpt_export_ingest.py -q
```

---

## Milestone commit chain (Memory review/search UI + import UI slice)

| Commit | Message |
| ------ | ------- |
| (branch tip) | `docs(ui): add memory review search foundation` |
| `df24d40` | `docs(ui): checkpoint memory screen foundation` ← `memory_screen_ui_foundation_clean_1` |
| `4a32167` | `docs(ui): add memory screen import foundation` |
| `44612d0` | `docs(local): checkpoint unified memory import` ← `unified_memory_import_clean_1` |
| `9084281` | `feat(local): add unified memory import command` |
| `c4ddcfe` | `docs(local): checkpoint email memory pipeline` ← `local_memory_pipeline_email_clean_1` |
| `8958d19` | `test(local): cover email export memory pipeline` |
| `69f9c8e` | `fix(local): skip email symlinks before stat` |
| `b9311f4` | `feat(local): import email export candidates` |
| `50ddfd9` | `docs(local): checkpoint chatgpt memory pipeline` ← `local_memory_pipeline_chatgpt_clean_1` |
| `3ea3d5d` | `docs(local): checkpoint memory pipeline milestone` ← `local_memory_pipeline_clean_1` |

Earlier transcription ingestion MVP commits precede this chain.

---

## What this enables next

Safe follow-on work from this checkpoint:

- **Dashboard Memory screen wiring** — connect import UI to safe subprocess bridge for `memory_import.py`
- **Dashboard review/search wiring** — connect review/search UI to review and search CLIs
- **Review pending memories UI (live)** — wire list/approve/reject from `review_memory_candidates.py`
- **Approved memory search UI (live)** — wire read-only search from control panel
- **Local model prompt/context handoff** — feed approved context bundles with explicit operator invocation
- **`.mbox` support later** — extend email lane beyond single `.eml` files
- **Document/PDF import later** — additional source lanes using the same downstream pipeline

---

## Intentionally not done

The following remain out of scope for this milestone:

- No live dashboard route yet (import or review/search)
- No server/API routes for import, review, or approved memory operations
- No live ChatGPT account access
- No live email account access
- No `.mbox` import yet
- No local model call from pipeline or UI steps
- No embeddings
- No live runtime memory / vector DB writes
- No automatic folder watching or background ingestion
- No autonomy or live execution

---

## Operator note

This checkpoint protects real progress. Before wiring dashboard routes or adding more UI behavior,
confirm review/search UI contract tests, import UI contract tests, unified import tests, all three smoke modes, and safe-stack still pass from tag
`memory_screen_ui_foundation_clean_1` or branch tip.
