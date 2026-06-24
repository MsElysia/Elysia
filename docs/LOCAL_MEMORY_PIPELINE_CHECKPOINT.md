# Local memory pipeline checkpoint

**Date:** 2026-05-30  
**Status:** Known-good milestone — Memory review/search UI foundation + import UI + unified import + three source lanes  
**Scope:** Operator-run local ingestion and UI contracts only. No dashboard wiring, no live runtime memory, no models.

---

## Branch and commit

| Field | Value |
| ----- | ----- |
| Branch | `codex/limited-live-activation-wrapper` |
| HEAD (at checkpoint) | `956b3ab` — `docs(ui): checkpoint memory review search foundation` |

Branch tip may include Memory Hub static shell after `memory_review_search_ui_foundation_clean_1`.
Restore tag `memory_review_search_ui_foundation_clean_1` points at `956b3ab`.

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

### Previous milestone (Memory import UI foundation)

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

### Current milestone (Memory review/search UI foundation)

```text
memory_review_search_ui_foundation_clean_1
```

Restore:

```powershell
git fetch origin tag memory_review_search_ui_foundation_clean_1
git checkout memory_review_search_ui_foundation_clean_1
```

Inspect:

```powershell
git show memory_review_search_ui_foundation_clean_1
```

---

## What works now

The Memory UI now covers **import**, **review/search**, and a **Memory Hub** entry page (static only).

### Memory Hub UI foundation (entry page)

Static hub linking import and review/search prototypes. No server routes, no backend calls.
See [MEMORY_HUB_UI_FOUNDATION.md](MEMORY_HUB_UI_FOUNDATION.md) and
[MEMORY_HUB_UI_CONTRACT.json](MEMORY_HUB_UI_CONTRACT.json).

1. **Memory Hub static page** — `project_guardian/ui/static/memory_hub.html`
2. **Four hub sections** — Import, Review Pending, Search Approved, Context Bundle placeholder
3. **Links to existing prototypes** — import and review/search screens
4. **Mock status only** — no JavaScript backend or network calls

### Memory review/search UI foundation (user-facing structure)

UI contract and static prototype for review, search, and context bundle placeholders. No server routes wired yet.
See [MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md](MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md) and
[MEMORY_REVIEW_SEARCH_UI_CONTRACT.json](MEMORY_REVIEW_SEARCH_UI_CONTRACT.json).

1. **Memory review/search UI contract** — pending list, approve/reject/edit, search, context bundle shapes
2. **Static Memory review/search prototype** — `project_guardian/ui/static/memory_review_search.html` (mock data only)
3. **Pending candidate review design** — list/filter by source type; candidate cards with preview and status
4. **Approve/reject/edit design** — operator confirmation required (contract only)
5. **Approved memory search design** — read-only search contract and prototype UI
6. **Context bundle placeholder design** — future local file output explained; operator confirm required

### Memory import UI foundation (prior milestone)

UI contract and static prototype for a future dashboard Memory import screen. No server routes wired yet.
See [MEMORY_SCREEN_UI_FOUNDATION.md](MEMORY_SCREEN_UI_FOUNDATION.md) and
[MEMORY_SCREEN_UI_CONTRACT.json](MEMORY_SCREEN_UI_CONTRACT.json).

7. **Memory import UI contract** — preview/apply request/response shapes, three source types, safety flags
8. **Static Memory import prototype** — `project_guardian/ui/static/memory_import_screen.html` (mock data only)
9. **Plain-language user safety copy** — confirm-before-save, pending review, local files only, no live accounts
10. **Preview / apply UI structure** — Add files → Preview → Confirm import

### Unified memory import (backend entry point)

One command routes preview/apply to the existing safe importers. See
[UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md).

11. **Unified memory import command** — `python scripts/memory_import.py preview|apply`
12. **Unified preview** — dry-run classification and session JSON/Markdown
13. **Unified apply** — dry-run default; `--apply` stages pending candidates only
14. **Preview/apply dry-run gates** — explicit `--apply` required to stage candidates
15. **Source auto-detection** — transcription text, ChatGPT export JSON, `.eml`
16. **Explicit source type routing** — `--source-type transcription|chatgpt_export|email_export`
17. **Ambiguous mixed folders fail safely** — require explicit `--source-type`

### Three source lanes + shared pipeline

**Shared downstream path:** preview/apply → pending candidates → review approval → approved export →
local memory store → search → context bundle.

| Lane | Inputs | Backend |
| ---- | ------ | ------- |
| Transcription / text | `.txt`, `.md`, `.vtt`, `.srt` | import session preview/apply |
| ChatGPT export | `conversations.json` or export-shaped JSON | ChatGPT export preview/apply |
| Email export | `.eml` (`.mbox` = `supported_later`) | email export preview/apply |

18. **Pending candidate staging** — `review_status=pending`, `live_memory_written=false`
19. **Candidate review (CLI)** — approve/reject/edit with audit trail
20. **Approved export** — `memory_candidates/approved_memory_export.jsonl`
21. **Approved local memory store** — `memory_store/approved_memory_store.jsonl`
22. **Approved memory search (CLI)** — read-only case-insensitive search
23. **Approved memory context bundle (CLI)** — Markdown + JSON for future local model handoff
24. **Full pipeline smoke** — `--source-type transcription|chatgpt_export|email_export`

### Important files

| File | Purpose |
| ---- | ------- |
| `docs/MEMORY_HUB_UI_CONTRACT.json` | Memory Hub static shell contract |
| `docs/MEMORY_HUB_UI_FOUNDATION.md` | Hub layout and navigation |
| `project_guardian/ui/static/memory_hub.html` | Memory Hub entry page (no server wiring) |
| `docs/MEMORY_REVIEW_SEARCH_UI_CONTRACT.json` | Review/search/context UI contract |
| `docs/MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md` | Review/search screen layout and CLI mapping |
| `project_guardian/ui/static/memory_review_search.html` | Static review/search prototype (no server wiring) |
| `docs/MEMORY_SCREEN_UI_CONTRACT.json` | Import preview/apply UI contract |
| `docs/MEMORY_SCREEN_UI_FOUNDATION.md` | Import screen layout and backend mapping |
| `project_guardian/ui/static/memory_import_screen.html` | Static import prototype (no server wiring) |
| `scripts/memory_import.py` | Unified preview/apply CLI |

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

### Review, search, and context (CLI; not wired to UI yet)

```powershell
python scripts/review_memory_candidates.py --dest-dir <path> list
python scripts/review_memory_candidates.py --dest-dir <path> approve <candidate_id>
python scripts/review_memory_candidates.py --dest-dir <path> reject <candidate_id>
python scripts/review_memory_candidates.py --dest-dir <path> edit <candidate_id> --replacement-text "..."
python scripts/search_approved_memory_store.py --dest-dir <path> search "drywall quote"
python scripts/build_approved_memory_context.py --dest-dir <path> --query "drywall quote"
```

### End-to-end smoke

```powershell
python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription
python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export
python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export
```

### Static prototypes (local browser only)

```powershell
start project_guardian/ui/static/memory_hub.html
start project_guardian/ui/static/memory_import_screen.html
start project_guardian/ui/static/memory_review_search.html
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
| Static prototypes only — no backend calls from HTML pages | Yes |
| Dry-run / explicit `--apply` gates where relevant | Yes |
| Review actions require operator confirmation (UI contract) | Yes |
| Search is read-only (UI contract and CLI) | Yes |

Each pipeline artifact includes safety metadata where applicable (`model_called: false`,
`embeddings_used: false`, `live_memory_written: false`, `autonomy_enabled: false`).

---

## Verification baseline

Verified at checkpoint creation:

| Check | Expected result |
| ----- | ----------------- |
| Review/search UI contract tests | `python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q` → all passed |
| Memory Hub UI contract tests | `python -m pytest project_guardian/tests/test_memory_hub_ui_contract.py -q` → all passed |
| Memory screen UI contract tests | `python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q` → all passed |
| Unified import tests | `python -m pytest project_guardian/tests/test_unified_memory_import.py -q` → all passed |
| Local memory smoke tests | `python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q` → all passed |
| Transcription smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription` → `verdict: PASS` |
| ChatGPT export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export` → `verdict: PASS` |
| Email export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export` → `verdict: PASS` |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` → pytest PASSED |
| Dry-run report | `python scripts/run_elysia_dry_run_report.py --mode real-planning` → `SAFE`, `any_executed: False` |

Representative regression commands:

```powershell
python -m pytest project_guardian/tests/test_memory_hub_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
python -m pytest project_guardian/tests/test_local_memory_pipeline_smoke.py -q
```

---

## Milestone commit chain (Memory review/search UI + import UI slice)

| Commit | Message |
| ------ | ------- |
| `b7dbb11` | `docs(ui): add memory review search foundation` |
| `df24d40` | `docs(ui): checkpoint memory screen foundation` ← `memory_screen_ui_foundation_clean_1` |
| `4a32167` | `docs(ui): add memory screen import foundation` |
| `44612d0` | `docs(local): checkpoint unified memory import` ← `unified_memory_import_clean_1` |
| `9084281` | `feat(local): add unified memory import command` |
| `c4ddcfe` | `docs(local): checkpoint email memory pipeline` ← `local_memory_pipeline_email_clean_1` |
| `8958d19` | `test(local): cover email export memory pipeline` |
| `50ddfd9` | `docs(local): checkpoint chatgpt memory pipeline` ← `local_memory_pipeline_chatgpt_clean_1` |
| `3ea3d5d` | `docs(local): checkpoint memory pipeline milestone` ← `local_memory_pipeline_clean_1` |

Earlier transcription ingestion MVP commits precede this chain.

---

## What this enables next

Safe follow-on work from this checkpoint:

- **Memory Hub dashboard link** — serve static hub as entry navigation
- **Safe dashboard route for static Memory screens** — local-only file serving
- **Live but local-only UI wiring later** — safe subprocess bridge to existing CLIs
- **Review pending memories UI wiring** — list/approve/reject/edit from `review_memory_candidates.py`
- **Approved memory search UI wiring** — read-only search from control panel
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

This checkpoint protects real progress. Before wiring dashboard routes or adding live UI behavior,
confirm review/search UI contract tests, import UI contract tests, unified import tests, local memory smoke tests,
all three smoke CLI modes, and safe-stack still pass from tag
`memory_review_search_ui_foundation_clean_1` or branch tip.
