# Integration inventory (Windows RC)

Authority: source tree at worktree `windows-local-intel-20261029`, tip `f23280d` (+ RC docs/acceptance commits).

| Feature | Owning module | Runtime entry | Persistence | Authorization | Verification | Readiness |
|---------|---------------|---------------|-------------|---------------|--------------|-----------|
| Contained UI runtime | `ui_control_panel.py`, `start_contained_browser_memory.py` | pilot BAT → launch_verified_pilot → start_contained | disposable or `Elysia-Windows-Integration-Data` | contained disables | `/api/ping`, contained tests | **Connected** |
| Local Ollama chat | `local_memory_chat.py` | `/api/chat`, dashboard Ask local model | none for chat text | `allow_calculator` request flag; loopback only | accept_local_intel / RC E2E | **Connected** |
| Capability awareness | `capability_awareness.py` | `/api/local-model/capabilities`, Capabilities tab | none (read-only) | same policy as tools | test_capability_awareness | **Connected** |
| Durable memory teach/correct/history | restricted runtime + MemoryCore | `/api/restricted/v1/facts*` | memory under disposable/root | operator token headers | RC E2E + restricted tests | **Connected** |
| Conversation + checkpoint | `conversation_continuity.py` | `/api/conversations*` | conversation store under root | contained | continuity tests + RC E2E | **Connected** |
| Task steps / receipts | task state in conversation store | bind/execute/complete routes | durable under root | per-request authorize_* | task/document accepts | **Connected** |
| local.documents.search | `local_documents_search.py` | `/api/local-documents/search` + task execute | read-only folder | `authorize_documents_search` | docs accept + RC E2E | **Connected** |
| compose.extract_fields | `capability_composition.py` | task execute | receipt on step | `authorize_compose_extract` | structured extract accept | **Connected** |
| compose.extract_records | `capability_composition.py` | task execute | receipt on step | `authorize_compose_extract_records` | extract_records accept | **Connected** |
| calculator.labor | `local_memory_chat.py` + task binding | chat + task execute | receipt | `allow_calculator` / `authorize_calculator` | local intel + RC E2E | **Connected** |
| estimate.assemble / draft | composition / estimate paths | task execute | receipt | authorize_estimate_* | composition accept | **Connected** |
| Adaptive replan | composition evaluate/propose-replan/apply | `/api/composition/*` | task revisions | never inherits auth | adaptive_replan accept | **Connected** |
| Outcome feedback | `composition_outcome_feedback.py` | rank + propose attachment | outcome store under root | ranking never grants auth | outcome/comparable accepts | **Connected** |
| Capability registry (legacy) | `capability_registry.py` | orchestrator paths | n/a | separate legacy | not primary Windows intel UI | **Present / secondary** |
| Email / web / finance / calendar | descriptors only | Capabilities show unavailable | n/a | not authorized | capability awareness | **Unavailable** |
| Autonomy / cloud providers | control panel routes | contained config off | n/a | not authorized | contained startup tests | **Disabled** |
| Browser worker / inbox | pilot inbox_import | startup/manual scan | inbox under data root | exclusion locks | pilot tests | **Connected (pilot)** |

## Orphans / duplicates / disconnects

- Legacy `capability_registry.py` / orchestrator capability paths coexist with Windows `capability_awareness.py` — dashboard intel path uses awareness, not the legacy registry.
- Multiple historical accept_* scripts exercise slices; **RC E2E** is the same-session consolidator.
- No competing second Windows app was added; disposable runs reuse the same entry as the pilot BAT.

## Deliberately not wired as executable

Email, web search, finance, calendar, autonomy, cloud models, background missions, unrestricted shell/code execution.
