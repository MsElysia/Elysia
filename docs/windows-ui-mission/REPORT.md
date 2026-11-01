# Windows chat and document integration — 2026-11-01

## Source and preservation baseline

Repository: https://github.com/MsElysia/Elysia

- Mission starting canonical/release: `2d2a7d1782ff1d6e001352b5d8db4a2c1ba6794c`.
- Existing combined candidate checkpoint: `c70ff778f50ae3f3d4b747523135b6bfa1b2d73f`, already present on both canonical and `codex/windows-chat-documents-20261101` when this continuation began. Do not undo that external checkpoint.
- PR #178 observed head: `2759ba43cf14ef9fb3be579d143183788f341af3`, draft/open.
- PR #179 observed head: `9045a01d948a8e48e41e0bcb7574c081ed740a38`, draft/open. Its body still described an older tip; use the actual head identity.
- This repair remains on `codex/windows-chat-documents-20261101`; no merge/promotion is part of this task. User's explicit draft-only instruction overrides repository instructions to push canonical and promote automatically.
- Primary checkout is dirty and on an unrelated branch. It was not reset, switched, or consolidated.
- Installed release: `C:\Users\Owner\Elysia-Windows-Release`. Inspected identity: original canonical SHA above. Desktop `elysia1` was observed targeting the older `windows-local-intel-20261029` worktree, contrary to release documentation. No shortcut change was made.
- Authoritative operational data: `C:\Users\Owner\Elysia-Windows-Integration-Data`. No migration or replacement. Disposable runtime/evidence/dependencies live under primary checkout `tmp/windows-ui-mission-*`.

## Capability inventory

| Capability | Baseline evidence | Candidate outcome |
|---|---|---|
| Local Ollama chat | Existing LocalOllama loopback transport, `/api/chat`, buried in Control | CONNECTED; real homepage reply observed |
| Conversations | Existing ConversationStore, resume/checkpoint APIs | BROKEN first-send default repaired; first message now creates a durable conversation |
| Persistent facts | RestrictedRuntimeAdapter and MemoryCore | Reused; existing authorization/correction/history tests preserved |
| Text inbox | `pilot/inbox_import.py`, startup/manual scanner | IMPLEMENTED; unchanged; not represented as browser upload |
| Selected-folder document search | Existing text/Markdown read-only interface | CONNECTED; unchanged request-scoped permission |
| Browser document imports | Absent at original starting canonical; present in combined checkpoint | CONNECTED; actual browser multipart defect repaired |
| TXT/MD/CSV/PDF/DOCX | New bounded extractor and deterministic chunks in canonical MemoryCore | TESTED; real TXT/PDF HTTP and browser extraction observed; DOCX/CSV extraction automated |
| Grounded document chat | Existing context bundle extended with completed document chunks | RUNTIME VERIFIED over HTTP using actual Ollama; host source references shown separately and saved with assistant turn |
| Scanned PDF OCR | No verified OCR installation/interface | NOT IMPLEMENTED; explicit unavailable explanation; never empty success |
| Activity | Existing status and HTTP polling; document receipts | CONNECTED; bounded actual events, job counts, source identity, last ingestion/retrieval; no content in routine events |
| Autonomy/cloud/learning | Deliberate contained runtime restrictions | DISABLED; no providers activated, no gates loosened |
| Advanced controls | Many legacy paths and intentionally unavailable integrations | Source inventory generated in `controls.csv`; broad runtime audit remains INCOMPLETE |

## Repairs in this continuation

1. The first homepage send previously omitted conversation storage unless Start new had been clicked. Every local send now obtains the existing ConversationStore. Storage failure returns failure rather than a successful saved-history receipt.
2. Multipart browser uploads inherited JSON Content-Type from restrictedHeaders. Dedicated authenticated upload headers let the browser supply the multipart boundary. Actual browser selection, extraction/preview and duplicate-aware save were observed after repair.
3. Document evidence references are displayed using textContent and stored beside the assistant message in the existing conversation record. No authorization fields are persisted with references.
4. Preview extraction shares the importer lock, preventing same-hash temporary-file races.
5. Activity separates live imports from interrupted processing receipts. Events contain operation names and timestamps, not document text, prompts or credentials. The synchronous importer has no backend queue; queued count is zero, and remaining selected files are held by the browser.
6. Document extraction and continuity regressions join the Linux/Windows hosted RC test slice; CI installs local parser dependencies. Flask 3.1 is required for bounded per-request upload parsing.

## Evidence and truthful limits

- Initial focused Windows run: 42 passed, including real PDF/DOCX/CSV extraction, preserved originals, restart retrieval, dedupe, interrupted-index retry and upload authentication.
- Existing intel RC slice: 134 passed, 2 deliberately deselected Windows symlink privilege cases.
- Expanded slice during development: 147 passed, 2 deselected. A subsequent sandboxed run: 146 passed, 1 junction test skipped (Windows access denied), 2 deselected. Use the final run record alongside this report; do not count repeated tests as independent scenarios.
- Real normal Python launcher started the contained server on loopback 5080 with a disposable data root and test interpreter. Initial missing-pyttsx3 launch failed and was correctly refused; installing that dependency only in the disposable environment resolved it.
- The stop tool initially refused a mismatched interpreter identity. Passing the actual test interpreter allowed verified cooperative shutdown and restart; no unrelated process was killed.
- In-app browser loaded the Windows server, displayed chat immediately, and received a real `llama3.2:3b` greeting. Native Chrome automation was unavailable in the preceding turn because URL policy could not be established; no browser-policy bypass was attempted.
- Live HTTP acceptance observed TXT/PDF extraction, durable chunks, byte-hash dedupe, keyword/paraphrased retrieval, correct PDF-based model answer, source metadata, malformed-PDF rejection and unauthenticated-upload denial.
- Real browser upload initially failed (JSON Content-Type), then succeeded after repair; previewed TXT/PDF content was visible and Save reported exact source IDs with no duplicates.
- Local model prose does not reliably copy full SHA identifiers. The application therefore displays the host-retrieved source/chunk metadata independently of the model wording. It does not claim arbitrary model prose is automatically fact-checked.
- Browser and HTTP observations refer to disposable candidate execution, not the installed release or the actual desktop-shortcut path. Operational acceptance and replacement remain pending approval.
- No cloud model, paid dependency, credential edit, autonomy/background activation, or personal document was used.

## Architecture and remaining limitations

UI routes reuse runtime MemoryCore; document_source receipts and document_chunk records are distinct from restricted_fact personal facts. Original bytes and bounded extraction files live in a managed sibling documents directory. The MemoryCore JSON save remains the persistence authority. No new vector database, conversation database, router, execution engine or authorization framework was introduced.

The importer is synchronous (30-second extraction deadline, 256 MiB Windows worker commit limit / 512 MiB POSIX address-space limit, 8 MiB source limit, bounded expanded DOCX/PDF/text output). Retry is manual, at most three attempts per content hash. Crash recovery hides unfinished chunks and deduplicates stable chunk IDs on retry. It does not automatically resume jobs or OCR scanned pages. Mixed image/text PDFs may contain textless pages; no image OCR is implied. Retrieval uses deterministic lexical overlap rather than verified semantic embeddings; paraphrases still need shared content words. Performance for very large existing memory stores and hostile multi-process writers needs further review before broad deployment.

Controls inventory is source-derived: 106 buttons/inputs/selects/textareas. It records handlers, candidate API paths, backend functions, gate information and verification limitations. It does not certify all legacy Advanced controls. The protected existing regression suite remains the evidence for unchanged tools/task execution.

## Rollback and controlled installation

Until approval: leave release, shortcut, operational data and previous pilot untouched. Stop only the identity-verified disposable runtime with the same ELYSIA_PILOT_DATA_ROOT and ELYSIA_PILOT_PYTHON used to start it. Keep this worktree and evidence for review; no reset or deletion is required to abandon it.

After explicit deployment approval: record current release/shortcut/interpreter/source identity, back up release source with the existing promotion tooling, install parser requirements into an isolated release dependency environment, and promote only the approved SHA. Preserve operational memory/settings/credentials. Verify the shortcut targets release `pilot/START_ELYSIA1.bat`, then run the acceptance packet. Restore the preserved source/dependency environment/shortcut if acceptance fails. Never overwrite operational memory with a source backup; retain all new document receipts and original bytes. Review `tools/windows_sync/promote_release.py` first: its canonical-ref assumptions must not silently substitute a different SHA for the approved draft tip.

Single next action after candidate/CI evidence is complete: operator reviews and approves the exact source and controlled installation packet. Installation approval does not authorize a merge to main.
