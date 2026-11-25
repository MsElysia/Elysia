# EA-11A-B | Authorized fact-only semantic link extension

**Status:** isolated draft implementation; independent exact-SHA tests pending. No installed, cloud, or protected-gate acceptance.

- Existing authenticated `facts.save` and `facts.correct` accept only an optional `approved_semantic_links_v1` list alongside the existing statement, under their existing permissions. No extra endpoint or datastore. The server binds each record to minted fact_id, exact revision, exact UTF-8 statement SHA-256, actor, fixed rule/method and confidence.
- Caller is an authenticated operator with existing fact-write permission. The supplied `selected_existing` state is a **manual operator approval assertion**, not proof of membership in a separate global registry. Unknown concepts/aliases are not auto-generated, and no new taxonomy database/compact IDs are claimed.
- Each supplied link: `{"concept":"#finish_choice","aliases":["coating"],"state":"selected_existing","project_id":"larkspur"}`. The project_id is optional. `candidate_proposed` may be stored for audit but never influences recall. Bounds: up to 8 links, 8 aliases/link, normalized identifier/phrase lengths. Any extraneous source/actor/hash fields are rejected as client input; the server creates those binding fields.
- On read, each link must reconstruct the exact canonical persisted form and match the current fact id/revision/statement hash and actor. Malformed or missing links are ignored. A new correction event does **not** inherit an old revision's links; its approval must be supplied again.
- `build_context_from_adapter` validates links again, maps exact locally approved aliases/concepts only, applies optional explicit project label when present, preserves original source/revision/hash and emits typed `recall_reasons`. Nonmatching or candidate aliases never contribute. Unscoped lexical current facts/documents and the four-item and 10,000-byte limits are preserved; tagged context never grants tool or provider permissions. For a recognized explicit project query, only current facts with validated matching project links enter the model context. Imported documents have no approved project-link contract and are omitted from such scoped context even when their text names the project; this intentionally limits project-aware document recall until a separately authorized linkage mechanism exists.
- Tamper caveat: SHA-256 and record consistency catch stale/mismatched or partially tampered bindings. They are **not an integrity signature** against an actor who can rewrite an entire authoritative MemoryCore file and forge all matching fields; an authenticated/immutable audit source would require separately approved infrastructure.
- A test suite at `tests/test_fact_associative_tag_recall.py` covers disposable primary-store persistence/reopen, lexical-disjoint tag hit, candidate quarantine, invalid/unprivileged writes, corruption, correction invalidation, project-scope and ambiguity, and tool authorization. The prior document semantic T01 xfail remains unresolved and is not RC enrolled or claimed green. Cross-cloud payload disclosure is not implemented. No remote embeddings, migration or owner data.


## EA-11A-B-DOC1 bounded document extension (independent tests pending)

The existing contained, loopback, dashboard-operator authenticated multipart POST
/api/documents may optionally carry one approved_document_association_v1
form field, JSON encoded, alongside the file:

    {"preview_sha256":"<exact SHA-256 from document preview>","links":[{"concept":"#finish_choice","aliases":["coating"],"state":"selected_existing"}]}

Only a new single-chunk TXT is eligible. Explicit operator selection is required;
candidates, project IDs, malformed input, wrong SHA, duplicate or interrupted
sources and multi-chunk documents cannot attach associations. Ordinary imports
and default lexical document search retain their existing behavior. No dashboard
UI is added in this slice. The server binds raw hash, completed source/chunk ID,
text hash, authenticated actor and normalized tags in the existing completed
receipt only, after verifying the durable chunk. The chat context revalidates
the binding and emits an approved_semantic_tag reason; the text remains untrusted
document evidence, with no tool or provider authority. Recognized explicit project
queries still exclude all imported documents. Read-time consistency detects
mismatched records, not coordinated forgery of the authoritative local store.
No migration, legacy retagging, project-linked documents, cloud model, or installed
release acceptance is claimed.
