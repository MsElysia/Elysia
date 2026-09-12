# Local memory pipeline checkpoint

**Date:** 2026-05-30  
**Status:** Known-good milestone — Memory Hub navigation + Hub/import/review UI + unified import + three source lanes  
**Scope:** Operator-run local ingestion and static UI contracts only. No live dashboard routes, no live runtime memory, no models.

### Route design milestone (after `memory_diagnostics_demo_clean_1`)

Local-only dashboard route **design and risk review** added (no route wired):

- `docs/MEMORY_DASHBOARD_ROUTE_DESIGN.md`
- `docs/MEMORY_DASHBOARD_ROUTE_RISK_REVIEW.md`
- `docs/MEMORY_DASHBOARD_ROUTE_ACCEPTANCE_TESTS.md`
- `project_guardian/tests/test_memory_dashboard_route_design_docs.py`

Restore tag for diagnostics/demo sprint: `memory_diagnostics_demo_clean_1` (`93ec530`).

---

## Branch and commit

| Field | Value |
| ----- | ----- |
| Branch | `codex/limited-live-activation-wrapper` |
| HEAD (at checkpoint) | `8b7ce7e` — `docs(ui): link memory hub from dashboard` |

After the checkpoint document commit, the annotated restore tag
`memory_hub_navigation_clean_1` points at the checkpoint commit on this branch.

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

### Previous milestone (Memory review/search UI foundation)

```text
memory_review_search_ui_foundation_clean_1
```

Points at `956b3ab` — `docs(ui): checkpoint memory review search foundation`.

Restore:

```powershell
git fetch origin tag memory_review_search_ui_foundation_clean_1
git checkout memory_review_search_ui_foundation_clean_1
```

Inspect:

```powershell
git show memory_review_search_ui_foundation_clean_1
```

### Previous milestone (Memory Hub UI foundation)

```text
memory_hub_ui_foundation_clean_1
```

Points at `2b95775` — `docs(ui): checkpoint memory hub foundation`.

Restore:

```powershell
git fetch origin tag memory_hub_ui_foundation_clean_1
git checkout memory_hub_ui_foundation_clean_1
```

Inspect:

```powershell
git show memory_hub_ui_foundation_clean_1
```

### Current milestone (Memory Hub navigation)

```text
memory_hub_navigation_clean_1
```

Restore:

```powershell
git fetch origin tag memory_hub_navigation_clean_1
git checkout memory_hub_navigation_clean_1
```

Inspect:

```powershell
git show memory_hub_navigation_clean_1
```

---

## What works now

Elysia has a discoverable static Memory UI entry point with no server route or backend call:

```text
project_guardian/ui/static/index.html
  → memory_hub.html
    → memory_import_screen.html
    → memory_review_search.html
```

### Memory Hub navigation (current milestone)

Static entry page with Memory card linking to the Hub. No server routes, no JavaScript backend calls.
See [MEMORY_HUB_UI_FOUNDATION.md](MEMORY_HUB_UI_FOUNDATION.md) and
[MEMORY_HUB_UI_CONTRACT.json](MEMORY_HUB_UI_CONTRACT.json).

1. **Static UI entry point** — `project_guardian/ui/static/index.html`
2. **Memory card** — “Import, review, and search local memories”
3. **Safety copy on entry** — local files only; no account connection required
4. **Relative links only** — hub, import, and review/search prototypes

### Memory Hub UI foundation

5. **Memory Hub static prototype** — `project_guardian/ui/static/memory_hub.html`
6. **Memory Hub UI contract** — `prototype_only: true`, `backend_calls_allowed: false`
7. **Four hub sections** — Import, Review Pending, Search Approved, Context Bundle placeholder

### Memory import UI foundation

See [MEMORY_SCREEN_UI_CONTRACT.json](MEMORY_SCREEN_UI_CONTRACT.json).

8. **Memory import UI contract** — preview/apply shapes, three source types, safety flags
9. **Static Memory import prototype** — `project_guardian/ui/static/memory_import_screen.html`

### Memory review/search UI foundation

See [MEMORY_REVIEW_SEARCH_UI_CONTRACT.json](MEMORY_REVIEW_SEARCH_UI_CONTRACT.json).

10. **Memory review/search UI contract** — pending list, approve/reject/edit, search, context bundle
11. **Static Memory review/search prototype** — `project_guardian/ui/static/memory_review_search.html`
12. **Approve/reject/edit design** — operator confirmation required (contract only)
13. **Approved memory search design** — read-only search
14. **Context bundle placeholder design** — local file output explained

### Unified memory import (backend entry point)

See [UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md).

15. **Unified memory import command** — `python scripts/memory_import.py preview|apply`
16. **Preview/apply dry-run gates** — explicit `--apply` required to stage candidates
17. **Three source lanes** — transcription/text, ChatGPT export, email `.eml`
18. **Ambiguous mixed folders fail safely** — require explicit `--source-type`

### Pipeline backend (CLI)

| Lane | Inputs | Backend |
| ---- | ------ | ------- |
| Transcription / text | `.txt`, `.md`, `.vtt`, `.srt` | import session preview/apply |
| ChatGPT export | `conversations.json` or export-shaped JSON | ChatGPT export preview/apply |
| Email export | `.eml` (`.mbox` = `supported_later`) | email export preview/apply |

19. **Pending candidate staging** — `review_status=pending`, `live_memory_written=false`
20. **Full pipeline smoke** — `--source-type transcription|chatgpt_export|email_export`

### Important files

| File | Purpose |
| ---- | ------- |
| `project_guardian/ui/static/index.html` | Static UI entry — links to Memory Hub |
| `project_guardian/ui/static/memory_hub.html` | Memory Hub page |
| `project_guardian/ui/static/memory_import_screen.html` | Static import prototype |
| `project_guardian/ui/static/memory_review_search.html` | Static review/search prototype |
| `docs/MEMORY_HUB_UI_CONTRACT.json` | Memory Hub + navigation contract |
| `docs/MEMORY_HUB_UI_FOUNDATION.md` | Hub layout and open instructions |
| `docs/MEMORY_SCREEN_UI_CONTRACT.json` | Import preview/apply UI contract |
| `docs/MEMORY_REVIEW_SEARCH_UI_CONTRACT.json` | Review/search/context UI contract |
| `scripts/memory_import.py` | Unified preview/apply CLI |

Related docs:

- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
- [UNIFIED_MEMORY_IMPORT_MVP.md](UNIFIED_MEMORY_IMPORT_MVP.md)

---

## Important commands

### Static Memory UI (local browser only)

```powershell
start project_guardian/ui/static/index.html
start project_guardian/ui/static/memory_hub.html
```

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
| No fetch / XHR / WebSocket / API calls in static pages | Yes |
| No external network assets in static pages | Yes |
| Static prototypes only — no backend calls from browser | Yes |
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
| Memory Hub navigation tests | `python -m pytest project_guardian/tests/test_memory_hub_navigation.py -q` → all passed |
| Memory Hub UI contract tests | `python -m pytest project_guardian/tests/test_memory_hub_ui_contract.py -q` → all passed |
| Review/search UI contract tests | `python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q` → all passed |
| Memory screen UI contract tests | `python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q` → all passed |
| Unified import tests | `python -m pytest project_guardian/tests/test_unified_memory_import.py -q` → all passed |
| Transcription smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type transcription` → `verdict: PASS` |
| ChatGPT export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type chatgpt_export` → `verdict: PASS` |
| Email export smoke | `python scripts/run_local_memory_pipeline_smoke.py --json --source-type email_export` → `verdict: PASS` |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` → pytest PASSED |
| Dry-run report | `python scripts/run_elysia_dry_run_report.py --mode real-planning` → `SAFE`, `any_executed: False` |

Representative regression commands:

```powershell
python -m pytest project_guardian/tests/test_memory_hub_navigation.py -q
python -m pytest project_guardian/tests/test_memory_hub_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_review_search_ui_contract.py -q
python -m pytest project_guardian/tests/test_memory_screen_ui_contract.py -q
python -m pytest project_guardian/tests/test_unified_memory_import.py -q
```

---

## Milestone commit chain (Memory Hub navigation + UI slice)

| Commit | Message |
| ------ | ------- |
| `8b7ce7e` | `docs(ui): link memory hub from dashboard` |
| `2b95775` | `docs(ui): checkpoint memory hub foundation` ← `memory_hub_ui_foundation_clean_1` |
| `2604aac` | `docs(ui): add memory hub foundation` |
| `956b3ab` | `docs(ui): checkpoint memory review search foundation` ← `memory_review_search_ui_foundation_clean_1` |
| `b7dbb11` | `docs(ui): add memory review search foundation` |
| `df24d40` | `docs(ui): checkpoint memory screen foundation` ← `memory_screen_ui_foundation_clean_1` |
| `44612d0` | `docs(local): checkpoint unified memory import` ← `unified_memory_import_clean_1` |
| `3ea3d5d` | `docs(local): checkpoint memory pipeline milestone` ← `local_memory_pipeline_clean_1` |

Earlier commits in the UI and pipeline chain precede this table.

---

## What this enables next

Safe follow-on work from this checkpoint:

- **Safe local-only dashboard route later** — serve `index.html` or hub from control panel without backend
- **Live-but-local UI wiring later** — safe subprocess bridge to existing CLIs
- **Review/search wiring later** — connect review/search UI to CLIs
- **Context bundle wiring later** — explicit operator invocation
- **Local model prompt/context handoff later** — feed approved context bundles
- **`.mbox` support later** — extend email lane beyond single `.eml` files

---

## Intentionally not done

The following remain out of scope for this milestone:

- No live dashboard route yet
- No server/API routes for import, review, or approved memory operations
- No backend calls from browser
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

This checkpoint protects real progress. Before wiring live dashboard routes or local-only UI behavior,
confirm Memory Hub navigation tests, Memory Hub tests, review/search UI contract tests, import UI contract tests,
unified import tests, all three smoke CLI modes, and safe-stack still pass from tag
`memory_hub_navigation_clean_1` or branch tip.
