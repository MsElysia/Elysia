# Memory Hub UI foundation

**Status:** Static hub shell only — no server wiring, no backend calls  
**Restore tag (prior):** `memory_review_search_ui_foundation_clean_1`

---

## Purpose

Give normal users one entry page for the Memory experience:

**Memory Hub** → Import Memory → Review Pending Memories → Search Approved Memory → Context Bundle placeholder

This milestone links existing static prototypes. It does **not** connect to `elysia/api/server.py`, call CLIs, or use network assets.

---

## Where the UI lives

| Asset | Path |
| ----- | ---- |
| Static UI entry (navigation) | `project_guardian/ui/static/index.html` |
| Memory Hub (this page) | `project_guardian/ui/static/memory_hub.html` |
| UI contract | `docs/MEMORY_HUB_UI_CONTRACT.json` |
| Import prototype | `project_guardian/ui/static/memory_import_screen.html` |
| Review/search prototype | `project_guardian/ui/static/memory_review_search.html` |

Open locally:

```powershell
start project_guardian/ui/static/index.html
start project_guardian/ui/static/memory_hub.html
```

The static entry page (`index.html`) shows a **Memory** card linking to the Memory Hub. No server route or backend call is required — open the HTML file directly in a browser.

---

## Hub layout

1. **Header** — Elysia Memory
2. **Plain-language safety copy** — local files, confirm before save, pending review, searchable when approved
3. **Four cards** — Import, Review Pending, Search Approved, Build Context Bundle
4. **Supported sources** — transcription/text, ChatGPT export, email `.eml`
5. **Safety panel** — no live accounts, models, embeddings, live memory writes, or server routes
6. **What happens next** — end-to-end operator flow
7. **Mock status** — placeholder counts only (not live data)

All navigation uses relative links to sibling static HTML files. No JavaScript, fetch, XHR, WebSocket, or external CDN assets.

---

## User flow (documented on hub)

1. Preview files (import screen)
2. Confirm import
3. Review pending memories
4. Approve / reject / edit
5. Search approved memory
6. Build context bundle later

---

## Safety guarantees

| Guarantee | This milestone |
| --------- | -------------- |
| Prototype only | Yes |
| No backend calls from browser | Yes |
| No external network assets | Yes |
| No server/API routes | Yes |
| No live account access | Yes |
| No model / embedding calls | Yes |
| No live runtime memory writes | Yes |

---

## Verification

```powershell
python -m pytest project_guardian/tests/test_memory_hub_ui_contract.py -q
```

---

## Intentionally not done

- No dashboard route
- No live backend wiring
- No fetch/XHR from hub page
- No automatic status refresh

---

## Related docs

- [MEMORY_HUB_UI_CONTRACT.json](MEMORY_HUB_UI_CONTRACT.json)
- [MEMORY_SCREEN_UI_FOUNDATION.md](MEMORY_SCREEN_UI_FOUNDATION.md)
- [MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md](MEMORY_REVIEW_SEARCH_UI_FOUNDATION.md)
- [MEMORY_IMPORT_UI_ROADMAP.md](MEMORY_IMPORT_UI_ROADMAP.md)
