"""Fact-only, synthetic approved semantic association contract (EA-11A-B).

No new storage or web access; actual MemoryCore, authenticated restricted adapter,
and actual context bundle. Independent exact-head pytest execution required.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from project_guardian.local_memory_chat import (
    EVIDENCE_BYTE_CAP, EVIDENCE_ITEM_CAP, _context_tokens,
    build_context_from_adapter, canonical,
)
from project_guardian.restricted_runtime_adapter import (
    LocalPrincipal, OPERATOR_FACT_PERMISSIONS, RestrictedRuntimeAdapter,
)

STATEMENT = "Client selected water-based deck finish."
QUESTION = "Which coating did we decide on?"
TAG = {"concept": "#finish_choice", "aliases": ["coating"], "state": "selected_existing"}
CANDIDATE = {**TAG, "state": "candidate_proposed"}


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "facts.json"
    path.write_text("[]", encoding="utf-8")
    principal = LocalPrincipal("synthetic-operator", "fixture-only", OPERATOR_FACT_PERMISSIONS)
    headers = {"X-Elysia-Identity": "synthetic-operator", "X-Elysia-Token": "fixture-only"}

    def open_adapter():
        return RestrictedRuntimeAdapter(principals=[principal], memory_filepath=str(path))
    return path, headers, open_adapter


def save(adapter, headers, statement=STATEMENT, links=None):
    body = {"statement": statement}
    if links is not None:
        body["approved_semantic_links_v1"] = links
    response = adapter.handle("POST", "/api/restricted/v1/facts", headers=headers, body=body)
    assert response.status == 201, response.body
    assert response.body["persistence_verified"] is True
    return response.body["fact"]["fact_id"]


def bundle(store, query):
    path, headers, open_adapter = store
    before = path.read_bytes()
    adapter = open_adapter()
    assert adapter.memory.vector_search is None
    result = build_context_from_adapter(adapter, query, headers)
    assert path.read_bytes() == before
    assert result == build_context_from_adapter(adapter, query, headers)
    assert len(result["evidence"]) <= EVIDENCE_ITEM_CAP
    assert len(canonical(result["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP
    assert result["schema"] == "elysia.local-context.v1"
    assert result["no_memory_support"] == (not result["evidence"])
    unsigned = {k: v for k, v in result.items() if k != "bundle_sha256"}
    assert result["bundle_sha256"] == hashlib.sha256(canonical(unsigned).encode()).hexdigest()
    return result


def test_tag_recall_survives_reopen_with_source_identity_and_no_model_history(store):
    _, headers, open_adapter = store
    assert not set(_context_tokens(STATEMENT)) & set(_context_tokens(QUESTION))
    fact_id = save(open_adapter(), headers, links=[TAG])
    result = bundle(store, QUESTION)
    assert [r["source_id"] for r in result["evidence"]] == [fact_id]
    row = result["evidence"][0]
    assert row["revision"] == 1
    assert row["chunk_id"] == fact_id
    assert row["source_sha256"] == hashlib.sha256(STATEMENT.encode()).hexdigest()
    assert row["highlights"][0]["text"] == STATEMENT
    assert row["matched_tokens"] == []
    assert row["recall_reasons"][0]["type"] == "approved_semantic_tag"
    assert row["recall_reasons"][0]["concept"] == "finish_choice"
    assert row["recall_reasons"][0]["matched_alias"] == "coating"
    assert bundle(store, "Which enamel did we decide on?")["evidence"] == []


def test_candidate_quarantine_and_missing_explicit_approval(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    candidate = save(adapter, headers, links=[CANDIDATE])
    untagged = save(adapter, headers)
    assert candidate != untagged
    assert bundle(store, QUESTION)["evidence"] == []
    assert len(bundle(store, "What deck finish was selected?")["evidence"]) >= 1


@pytest.mark.parametrize("bad", [
    [{"concept": "finish_choice", "aliases": ["coating"], "state": "auto_promoted"}],
    [{"concept": "finish_choice", "aliases": ["coating"], "state": "selected_existing",
      "source_sha256": "0" * 64}],
    [{"concept": "finish_choice", "aliases": ["coating"], "state": "selected_existing",
      "project_id": " fact_bad " }],
    [{"concept": "finish_choice", "aliases": ["the"], "state": "selected_existing"}],
    [{"concept": "finish_choice", "aliases": ["coating", "coating"], "state": "selected_existing"}],
    [{"concept": "finish_choice", "aliases": ["coating"], "state": "selected_existing"}] * 9,
])
def test_invalid_link_fails_before_memory_write(store, bad):
    path, headers, open_adapter = store
    before = path.read_bytes()
    response = open_adapter().handle("POST", "/api/restricted/v1/facts",
                                     headers=headers, body={"statement": STATEMENT,
                                      "approved_semantic_links_v1": bad})
    assert response.status == 400, response.body
    assert path.read_bytes() == before


def test_unauthorized_alias_save_cannot_write(store):
    path, headers, open_adapter = store
    observer = RestrictedRuntimeAdapter(
        principals=[LocalPrincipal("viewer", "readonly-only", frozenset({"facts.retrieve"}))],
        memory_filepath=str(path),
    )
    before = path.read_bytes()
    rejected = observer.handle(
        "POST", "/api/restricted/v1/facts",
        headers={"X-Elysia-Identity": "viewer", "X-Elysia-Token": "readonly-only"},
        body={"statement": STATEMENT, "approved_semantic_links_v1": [TAG]},
    )
    assert rejected.status == 403
    assert path.read_bytes() == before


@pytest.mark.parametrize("corruption", ["source_sha256", "fact_id", "revision", "approving_actor", "boolean_revision", "boolean_confidence"])
def test_tampered_persisted_association_fails_closed(store, corruption):
    _, headers, open_adapter = store
    adapter = open_adapter()
    save(adapter, headers, links=[TAG])
    adapter.memory.load_if_needed()
    entry = next(e for e in adapter.memory.memory_log
                 if isinstance(e, dict) and e.get("category") == "restricted_fact")
    link = entry["metadata"]["approved_semantic_links_v1"][0]
    if corruption == "boolean_revision":
        link["revision"] = True
    elif corruption == "boolean_confidence":
        link["confidence"] = True
    else:
        link[corruption] = ("0" * 64 if corruption == "source_sha256" else
                            "fact_0000000000000000" if corruption == "fact_id" else
                            99 if corruption == "revision" else "forged-actor")
    adapter.memory._save()  # synthetic corruption; same existing primary store
    assert bundle(store, QUESTION)["evidence"] == []


def test_correction_invalidates_old_revision_tag_until_reapproved(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    fact_id = save(adapter, headers, links=[TAG])
    endpoint = f"/api/restricted/v1/facts/{fact_id}/corrections"
    new_statement = "Client selected acrylic coating for the deck."
    correction = adapter.handle("POST", endpoint, headers=headers, body={"statement": new_statement})
    assert correction.status == 200
    assert bundle(store, QUESTION)["evidence"]  # lexical can legitimately match coating
    assert not any(r.get("recall_reasons") for r in bundle(store, QUESTION)["evidence"])
    # A semantically disjoint alias still fails after correction.
    assert bundle(store, "What finish choice did we decide on?")["evidence"] == []
    next_statement = "Client selected opaque acrylic for the deck."
    corrected_again = adapter.handle("POST", endpoint, headers=headers, body={
        "statement": next_statement,
        "approved_semantic_links_v1": [TAG],
    })
    assert corrected_again.status == 200
    row = bundle(store, QUESTION)["evidence"][0]
    assert row["source_id"] == fact_id and row["revision"] == 3
    assert row["source_sha256"] == hashlib.sha256(next_statement.encode()).hexdigest()
    assert row["recall_reasons"][0]["type"] == "approved_semantic_tag"


def test_project_scoping_and_ambiguous_query_preserve_both_sources(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    first = save(adapter, headers, "Larkspur deck finish is water-based acrylic.",
                 [dict(TAG, project_id="larkspur")])
    second = save(adapter, headers, "Juniper deck finish is oil.",
                  [dict(TAG, project_id="juniper")])
    scoped = bundle(store, "What is the deck finish for project Larkspur?")
    assert [r["source_id"] for r in scoped["evidence"]] == [first]
    ambiguous = bundle(store, QUESTION)
    assert {r["source_id"] for r in ambiguous["evidence"]} == {first, second}
    assert not ambiguous["no_memory_support"]
    assert len(ambiguous["evidence"]) == 2
    assert ambiguous["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["juniper", "larkspur"]
    }


def test_approved_semantic_links_cannot_authorize_tools(store, monkeypatch):
    from project_guardian.local_memory_chat import (
        LocalOllama, ManualAuthorization, converse_bundle,
    )
    _, headers, open_adapter = store
    save(open_adapter(), headers, links=[TAG])
    memory = bundle(store, QUESTION)
    captured = []

    def fake_generate(model, messages, *, json_mode=False):
        payload = json.loads(messages[-1]["content"])
        captured.append(payload)
        return json.dumps({"answer": "Synthetic reply; no tools invoked."})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    result = converse_bundle(memory, QUESTION, ManualAuthorization(
        "req-synthetic", True, True, frozenset({"local.chat", "memory.read"})
    ), LocalOllama("fixture-model"), recent=())
    assert result["tools_executed"] == []
    assert result["memory_written"] is False
    assert captured[0]["recent_conversation"] == []
    assert captured[0]["context_bundle"]["evidence"][0]["recall_reasons"][0]["type"] == "approved_semantic_tag"


def test_single_current_fact_two_approved_projects_both_matched_requires_clarification(store):
    _, headers, open_adapter = store
    statement = "Client selected acrylic finish for the work."
    fact_id = save(open_adapter(), headers, statement, [
        {**TAG, "project_id": "larkspur"},
        {"concept": "surface_choice", "aliases": ["coating"],
         "state": "selected_existing", "project_id": "juniper"},
    ])
    result = bundle(store, QUESTION)
    assert len(result["evidence"]) == 1
    row = result["evidence"][0]
    assert row["source_id"] == row["chunk_id"] == fact_id
    assert row["revision"] == 1
    assert row["source_sha256"] == hashlib.sha256(statement.encode()).hexdigest()
    assert row["project_ids"] == ["juniper", "larkspur"]
    assert "project_id" not in row
    assert {r["project_id"] for r in row["recall_reasons"]} == {"juniper", "larkspur"}
    assert result["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["juniper", "larkspur"],
    }


def test_identical_lexical_facts_keep_project_source_provenance_without_alias_hit(store):
    _, headers, open_adapter = store
    statement = "The deck finish is acrylic."
    adapter = open_adapter()
    first = save(adapter, headers, statement, [{**TAG, "project_id": "larkspur"}])
    second = save(adapter, headers, statement, [{**TAG, "project_id": "juniper"}])
    result = bundle(store, "What is the deck finish?")
    rows = result["evidence"]
    assert len(rows) == 2
    assert {r["source_id"] for r in rows} == {first, second}
    assert {tuple(r["project_ids"]) for r in rows} == {("juniper",), ("larkspur",)}
    assert all("recall_reasons" not in r for r in rows)
    assert all(r["source_sha256"] == hashlib.sha256(statement.encode()).hexdigest()
               and r["revision"] == 1 for r in rows)
    assert result["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["juniper", "larkspur"],
    }


def test_ambiguity_survives_four_item_and_evidence_byte_capping(store):
    _, headers, open_adapter = store
    projects = ["aster", "birch", "cedar", "dogwood", "elm", "fir"]
    adapter = open_adapter()
    for i, project in enumerate(projects):
        statement = f"Record {i} specifies acrylic finish. " + "Z" * 1930
        assert len(statement) <= 2000
        save(adapter, headers, statement, [{**TAG, "project_id": project}])
    result = bundle(store, QUESTION)
    assert 0 < len(result["evidence"]) < len(projects)
    assert result["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": projects,
    }
    assert all(r["source_sha256"] == hashlib.sha256(
        r["highlights"][0]["text"].encode()).hexdigest()
        for r in result["evidence"] if not r["highlights"][0].get("excerpted"))


def test_explicit_project_filters_other_links_and_retains_source(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    same = save(adapter, headers, STATEMENT, [
        {**TAG, "project_id": "larkspur"},
        {"concept": "surface_choice", "aliases": ["coating"],
         "state": "selected_existing", "project_id": "juniper"},
    ])
    other = save(adapter, headers, "Juniper project uses an oil finish.",
                 [{**TAG, "project_id": "juniper"}])
    result = bundle(store, "Which coating for project Larkspur?")
    assert [r["source_id"] for r in result["evidence"]] == [same]
    row = result["evidence"][0]
    assert row["project_id"] == "larkspur"
    assert row["project_ids"] == ["larkspur"]
    assert {r["project_id"] for r in row["recall_reasons"]} == {"larkspur"}
    assert other not in {r["source_id"] for r in result["evidence"]}
    assert "project_ambiguity" not in result


@pytest.mark.parametrize("linked_id_sorts_first", [True, False])
def test_explicit_project_rejects_unlinked_lexical_homonym(
    store, linked_id_sorts_first, monkeypatch,
):
    """A project name in unlinked text never certifies its project membership."""
    from project_guardian.local_memory_chat import (
        LocalOllama, ManualAuthorization, converse_bundle,
    )

    _, headers, open_adapter = store
    adapter = open_adapter()
    initial = [
        save(adapter, headers, f"Initial independent memory {index} placeholder.")
        for index in range(2)
    ]
    lower_id, higher_id = sorted(initial)
    linked_id = lower_id if linked_id_sorts_first else higher_id
    unlinked_id = higher_id if linked_id_sorts_first else lower_id
    linked_statement = "Owner selected acrylic for the job."
    unlinked_statement = "Larkspur project coating is oil for an unrelated demonstration."
    for source_id in (lower_id, higher_id):
        is_linked = source_id == linked_id
        response = adapter.handle(
            "POST", f"/api/restricted/v1/facts/{source_id}/corrections",
            headers=headers,
            body={
                "statement": linked_statement if is_linked else unlinked_statement,
                **({"approved_semantic_links_v1": [
                    {**TAG, "project_id": "larkspur"}
                ]} if is_linked else {}),
            },
        )
        assert response.status == 200, response.body
        assert response.body["persistence_verified"] is True

    question = "Which coating for project Larkspur?"
    scoped = bundle(store, question)
    assert [row["source_id"] for row in scoped["evidence"]] == [linked_id]
    row = scoped["evidence"][0]
    assert row["chunk_id"] == linked_id and row["revision"] == 2
    assert row["source_sha256"] == hashlib.sha256(linked_statement.encode()).hexdigest()
    assert row["highlights"][0]["text"] == linked_statement
    assert row["project_id"] == "larkspur"
    assert row["project_ids"] == ["larkspur"]
    assert [reason["matched_alias"] for reason in row["recall_reasons"]] == ["coating"]
    assert all(reason["type"] == "approved_semantic_tag"
               and reason["project_id"] == "larkspur"
               for reason in row["recall_reasons"])
    assert unlinked_id not in json.dumps(scoped["evidence"])
    assert unlinked_statement not in json.dumps(scoped["evidence"])
    assert "project_ambiguity" not in scoped

    # This is the exact untrusted context forwarded to the local model,
    # not a promise about an actual Ollama generation.
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        return json.dumps({"answer": "Synthetic citation only."})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    response = converse_bundle(
        scoped, question,
        ManualAuthorization(
            "req-project-scope", True, True, frozenset({"local.chat", "memory.read"})
        ),
        LocalOllama("fixture-model"), recent=(),
    )
    assert [row["source_id"] for row in seen[0]["context_bundle"]["evidence"]] == [linked_id]
    assert unlinked_statement not in json.dumps(seen[0]["context_bundle"]["evidence"])
    assert response["tools_executed"] == [] and response["memory_written"] is False

    # Unscoped lexical fact retrieval must remain available.
    unscoped = bundle(store, "Which coating did we decide on?")
    assert unlinked_id in {row["source_id"] for row in unscoped["evidence"]}


def test_explicit_project_with_no_matching_link_excludes_unlinked_homonym(store):
    """A known project ID alone does not promote any unlinked lexical fact."""
    _, headers, open_adapter = store
    adapter = open_adapter()
    anchor_id = save(
        adapter, headers, "The owner photographed the southern gate yesterday.",
        [{"concept": "gate_condition", "aliases": ["roofing"],
          "state": "selected_existing", "project_id": "larkspur"}],
    )
    unlinked_statement = "Larkspur project coating is oil for an unrelated demonstration."
    unlinked_id = save(adapter, headers, unlinked_statement)
    question = "Which coating for project Larkspur?"
    scoped = bundle(store, question)
    assert scoped["evidence"] == []
    assert scoped["no_memory_support"] is True
    assert "project_ambiguity" not in scoped
    # Unscoped retrieval does not require a project link.
    unscoped = bundle(store, "Which coating did we decide on?")
    assert unlinked_id in {row["source_id"] for row in unscoped["evidence"]}
    assert anchor_id not in {row["source_id"] for row in scoped["evidence"]}


@pytest.mark.parametrize("matching_approved_fact", [True, False])
def test_named_project_document_without_approved_link_is_not_scoped_evidence(
    store, matching_approved_fact, monkeypatch,
):
    """Real completed document import must not impersonate a named-project fact."""
    from project_guardian.document_ingestion import DocumentLibrary
    from project_guardian.local_memory_chat import (
        LocalOllama, ManualAuthorization, converse_bundle,
    )

    _, headers, open_adapter = store
    adapter = open_adapter()
    linked_statement = "Owner selected acrylic for the job."
    if matching_approved_fact:
        fact_id = save(adapter, headers, linked_statement, [
            {**TAG, "project_id": "larkspur"}
        ])
    else:
        # This authentic link establishes the known project, but cannot
        # substantiate the coating question.
        fact_id = save(adapter, headers, "The owner photographed the southern gate yesterday.", [
            {"concept": "gate_condition", "aliases": ["roofing"],
             "state": "selected_existing", "project_id": "larkspur"}
        ])

    document_text = "Larkspur project coating is oil for an unrelated demonstration."
    receipt = DocumentLibrary(adapter.memory).import_bytes(
        "unrelated-demo.txt", document_text.encode("utf-8")
    )
    assert receipt["status"] == "completed", receipt
    assert receipt["chunk_count"] == 1
    assert receipt["duplicate"] is False
    assert receipt["source_id"].startswith("doc_")
    # Reopen primary store, checking the real completed receipt/chunk search path.
    persisted = DocumentLibrary(open_adapter().memory)
    docs = persisted.search("Which coating for project Larkspur?", context_distinct=True)
    assert len(docs) == 1
    doc = docs[0]
    assert doc["source_id"] == receipt["source_id"]
    assert doc["text"] == document_text
    assert doc["content_sha256"] == hashlib.sha256(document_text.encode()).hexdigest()

    question = "Which coating for project Larkspur?"
    scoped = bundle(store, question)
    if matching_approved_fact:
        assert [row["source_id"] for row in scoped["evidence"]] == [fact_id]
        row = scoped["evidence"][0]
        assert row["chunk_id"] == fact_id and row["revision"] == 1
        assert row["source_sha256"] == hashlib.sha256(linked_statement.encode()).hexdigest()
        assert row["highlights"][0]["text"] == linked_statement
        assert row["project_ids"] == ["larkspur"] and row["project_id"] == "larkspur"
        assert [reason["matched_alias"] for reason in row["recall_reasons"]] == ["coating"]
        assert all(reason["type"] == "approved_semantic_tag"
                   and reason["project_id"] == "larkspur"
                   for reason in row["recall_reasons"])
    else:
        assert scoped["evidence"] == []
        assert scoped["no_memory_support"] is True
    assert "project_ambiguity" not in scoped
    assert receipt["source_id"] not in json.dumps(scoped["evidence"])
    assert document_text not in json.dumps(scoped["evidence"])

    # Inspect exactly what the local model would see, without contacting Ollama.
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        return json.dumps({"answer": "Synthetic fixture response."})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(
        scoped, question,
        ManualAuthorization("req-doc-project", True, True,
                            frozenset({"local.chat", "memory.read"})),
        LocalOllama("fixture-model"), recent=(),
    )
    assert seen and seen[0]["context_bundle"] == scoped
    assert receipt["source_id"] not in json.dumps(seen[0]["context_bundle"]["evidence"])
    assert reply["tools_executed"] == [] and reply["memory_written"] is False

    # The same completed import remains searchable without a project cue.
    unscoped = bundle(store, "Which coating did we decide on?")
    document_rows = [
        row for row in unscoped["evidence"] if row["source_id"] == receipt["source_id"]
    ]
    assert len(document_rows) == 1
    evidence = document_rows[0]
    assert evidence["source_id"] == doc["source_id"]
    assert evidence["chunk_id"] == doc["chunk_id"]
    assert evidence["source_sha256"] == doc["content_sha256"]
    assert evidence["highlights"][0]["text"] == document_text
    assert evidence["filename"] == "unrelated-demo.txt"
    assert evidence["page"] == 1 and evidence["revision"] == 1
    assert evidence["trust"] == "untrusted_document"
    assert unscoped["no_memory_support"] is False


@pytest.mark.parametrize("invalid_project", [
    "moonbeam__court", "moonbeam___court", "moonbeam_court_", "_moonbeam_court",
])
def test_empty_project_components_rejected_on_save_and_correction_without_write(
    store, invalid_project,
):
    path, headers, open_adapter = store
    adapter = open_adapter()
    current = save(adapter, headers, "Owner approved acrylic for the surface.", [
        {**TAG, "project_id": "moonbeam_court"}
    ])
    before = path.read_bytes()
    rejected_save = adapter.handle(
        "POST", "/api/restricted/v1/facts",
        headers=headers, body={
            "statement": "Owner approved oil for the surface.",
            "approved_semantic_links_v1": [{**TAG, "project_id": invalid_project}],
        },
    )
    assert rejected_save.status == 400, rejected_save.body
    assert path.read_bytes() == before
    rejected_correction = adapter.handle(
        "POST", f"/api/restricted/v1/facts/{current}/corrections",
        headers=headers, body={
            "statement": "Owner changed the decision to oil.",
            "approved_semantic_links_v1": [{**TAG, "project_id": invalid_project}],
        },
    )
    assert rejected_correction.status == 400, rejected_correction.body
    assert path.read_bytes() == before
    assert [row["source_id"] for row in bundle(
        store, "Which coating for project moonbeam court?"
    )["evidence"]] == [current]


@pytest.mark.parametrize("name", [
    "moonbeam__court", "moonbeam___court", "moonbeam_court_",
    "_moonbeam_court", "moonbeam _ court", "moonbeam court_",
    "moonbeam--court", "moonbeam-court-",
])
def test_malformed_project_spelling_requires_model_visible_clarification(
    store, name, monkeypatch,
):
    from project_guardian.local_memory_chat import (
        LocalOllama, ManualAuthorization, converse_bundle,
    )

    _, headers, open_adapter = store
    adapter = open_adapter()
    approved_statement = "Owner selected acrylic for the surface."
    approved_id = save(adapter, headers, approved_statement, [
        {**TAG, "project_id": "moonbeam_court"}
    ])
    other_id = save(adapter, headers, "Owner selected oil for the surface.", [
        {**TAG, "project_id": "juniper"}
    ])
    question = "Which coating for project " + name + "?"
    memory = bundle(store, question)
    assert memory["project_ambiguity"]["requires_clarification"] is True
    assert memory["project_ambiguity"]["unknown_project_hints"]
    assert {row["source_id"] for row in memory["evidence"]} == {approved_id, other_id}
    assert {row["project_id"] for row in memory["evidence"]} == {
        "moonbeam_court", "juniper"
    }
    assert memory["evidence"][0]["source_sha256"] in {
        hashlib.sha256(approved_statement.encode()).hexdigest(),
        hashlib.sha256("Owner selected oil for the surface.".encode()).hexdigest(),
    }
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        assert "requires_clarification" in messages[0]["content"]
        return json.dumps({"answer": "Which project do you mean?"})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(
        memory, question,
        ManualAuthorization("req-project-grammar", True, True,
                            frozenset({"local.chat", "memory.read"})),
        LocalOllama("fixture-model"), recent=(),
    )
    assert seen[0]["context_bundle"]["project_ambiguity"] == memory["project_ambiguity"]
    assert reply["tools_executed"] == [] and reply["memory_written"] is False


def test_persisted_malformed_project_link_does_not_authorize_recall(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    statement = "Owner approved acrylic for the surface."
    malformed_id = save(adapter, headers, statement, [
        {**TAG, "project_id": "moonbeam_court"}
    ])
    valid_id = save(adapter, headers, "Owner approved oil for the surface.", [
        {**TAG, "project_id": "moonbeam_court"}
    ])
    adapter.memory.load_if_needed()
    entry = next(e for e in adapter.memory.memory_log
                 if isinstance(e, dict)
                 and e.get("category") == "restricted_fact"
                 and e.get("metadata", {}).get("fact_id") == malformed_id)
    entry["metadata"]["approved_semantic_links_v1"][0]["project_id"] = "moonbeam__court"
    adapter.memory._save()  # disposable synthetic persisted-link corruption
    named = bundle(store, "Which coating for project moonbeam court?")
    assert [row["source_id"] for row in named["evidence"]] == [valid_id]
    assert named["evidence"][0]["revision"] == 1
    assert named["evidence"][0]["source_sha256"] == hashlib.sha256(
        "Owner approved oil for the surface.".encode()
    ).hexdigest()
    assert named["evidence"][0]["recall_reasons"][0]["matched_alias"] == "coating"
    assert "project_ambiguity" not in named
    assert malformed_id not in json.dumps(named["evidence"])
    assert malformed_id not in {
        row["source_id"] for row in bundle(store, QUESTION)["evidence"]
    }


@pytest.mark.parametrize("name", [
    "moonbeam court", "moonbeam-court", "moonbeam_court", "moonbeam - court",
])
def test_valid_project_spelling_keeps_original_source_identity(store, name):
    _, headers, open_adapter = store
    statement = "Owner approved acrylic for the surface."
    correct = save(open_adapter(), headers, statement, [
        {**TAG, "project_id": "moonbeam_court"}
    ])
    result = bundle(store, "Which coating for project " + name + "?")
    assert [row["source_id"] for row in result["evidence"]] == [correct]
    row = result["evidence"][0]
    assert row["revision"] == 1
    assert row["source_sha256"] == hashlib.sha256(statement.encode()).hexdigest()
    assert row["project_ids"] == ["moonbeam_court"]
    assert row["recall_reasons"][0]["matched_alias"] == "coating"
    assert "project_ambiguity" not in result


@pytest.mark.parametrize("prefix", ["Straße ﬁnance:", "aﬃnity", "İstanbul Straße"])
@pytest.mark.parametrize("malformed", [
    "_moonbeam_court", "moonbeam__court", "moonbeam_court_",
])
def test_unicode_prefix_malformed_project_cannot_silently_narrow_context(
    store, prefix, malformed, monkeypatch,
):
    """Casefold expansion before a project cue cannot shift grammar offsets."""
    from project_guardian.local_memory_chat import (
        LocalOllama, ManualAuthorization, converse_bundle,
    )

    _, headers, open_adapter = store
    adapter = open_adapter()
    correct_statement = "Owner approved acrylic for the surface."
    other_statement = "Owner approved oil for the surface."
    correct = save(adapter, headers, correct_statement, [
        {**TAG, "project_id": "moonbeam_court"},
    ])
    other = save(adapter, headers, other_statement, [
        {**TAG, "project_id": "juniper"},
    ])
    question = f"{prefix} Which coating for project {malformed} to select finish?"
    memory = bundle(store, question)
    assert memory["project_ambiguity"]["requires_clarification"] is True
    assert memory["project_ambiguity"]["unknown_project_hints"]
    assert memory["project_ambiguity"]["project_ids"] == ["juniper", "moonbeam_court"]
    assert {row["source_id"] for row in memory["evidence"]} == {correct, other}
    assert {row["source_sha256"] for row in memory["evidence"]} == {
        hashlib.sha256(correct_statement.encode()).hexdigest(),
        hashlib.sha256(other_statement.encode()).hexdigest(),
    }
    assert all(row["revision"] == 1 for row in memory["evidence"])
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        assert "requires_clarification" in messages[0]["content"]
        return json.dumps({"answer": "Which project do you mean?"})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(
        memory, question,
        ManualAuthorization("req-unicode-scope", True, True,
                            frozenset({"local.chat", "memory.read"})),
        LocalOllama("fixture-model"), recent=(),
    )
    assert seen[0]["context_bundle"]["project_ambiguity"] == memory["project_ambiguity"]
    assert reply["tools_executed"] == [] and reply["memory_written"] is False


@pytest.mark.parametrize("prefix", ["Straße", "aﬃnity", "İstanbul Straße"])
@pytest.mark.parametrize("valid", [
    "moonbeam court", "moonbeam-court", "moonbeam_court",
])
def test_unicode_prefix_valid_project_preserves_full_name_scope(
    store, prefix, valid,
):
    _, headers, open_adapter = store
    adapter = open_adapter()
    correct_statement = "Owner approved acrylic for the surface."
    correct = save(adapter, headers, correct_statement, [
        {**TAG, "project_id": "moonbeam_court"},
    ])
    shorter = save(adapter, headers, "Owner approved teal for the surface.", [
        {**TAG, "project_id": "moonbeam"},
    ])
    other = save(adapter, headers, "Owner approved oil for the surface.", [
        {**TAG, "project_id": "juniper"},
    ])
    question = f"{prefix}: Which coating for project {valid}?"
    memory = bundle(store, question)
    assert [row["source_id"] for row in memory["evidence"]] == [correct]
    row = memory["evidence"][0]
    assert row["revision"] == 1 and row["chunk_id"] == correct
    assert row["source_sha256"] == hashlib.sha256(correct_statement.encode()).hexdigest()
    assert row["project_ids"] == ["moonbeam_court"]
    assert row["recall_reasons"][0]["matched_alias"] == "coating"
    assert "project_ambiguity" not in memory
    assert shorter not in json.dumps(memory["evidence"])
    assert other not in json.dumps(memory["evidence"])


def test_unicode_prefix_coordinated_projects_remain_ambiguous(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    first = save(adapter, headers, "Owner approved acrylic for the surface.", [
        {**TAG, "project_id": "moonbeam_court"},
    ])
    second = save(adapter, headers, "Owner approved oil for the surface.", [
        {**TAG, "project_id": "juniper"},
    ])
    memory = bundle(
        store, "Straße ﬁnance: Which coating for project moonbeam court and project juniper?"
    )
    assert {row["source_id"] for row in memory["evidence"]} == {first, second}
    assert memory["project_ambiguity"] == {
        "requires_clarification": True,
        "project_ids": ["juniper", "moonbeam_court"],
    }


def test_unknown_named_project_and_multiple_known_projects_never_silent_select(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    save(adapter, headers, STATEMENT, [{**TAG, "project_id": "larkspur"}])
    unknown = bundle(store, "Which coating for project moonbeam?")
    assert unknown["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["larkspur"],
        "unknown_project_hints": ["moonbeam"],
    }
    save(adapter, headers, "Other client approved oil finish.",
         [{**TAG, "project_id": "juniper"}])
    multiple = bundle(store, "Which coating for Larkspur and Juniper projects?")
    assert multiple["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["juniper", "larkspur"],
    }


def test_correction_excludes_stale_project_link_and_proposed_project_is_not_scope(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    old = save(adapter, headers, STATEMENT, [{**TAG, "project_id": "larkspur"}])
    save(adapter, headers, "Future color under consideration.",
         [{**CANDIDATE, "project_id": "juniper"}])
    corrected = adapter.handle("POST", f"/api/restricted/v1/facts/{old}/corrections",
                               headers=headers,
                               body={"statement": "Client switched to opaque acrylic."})
    assert corrected.status == 200
    result = bundle(store, QUESTION)
    assert result["evidence"] == []
    assert "project_ambiguity" not in result


def test_identical_text_same_project_is_deduplicated_with_verified_identity(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    first = save(adapter, headers, STATEMENT, [{**TAG, "project_id": "larkspur"}])
    second = save(adapter, headers, STATEMENT, [{**TAG, "project_id": "larkspur"}])
    result = bundle(store, QUESTION)
    assert len(result["evidence"]) == 1
    row = result["evidence"][0]
    assert row["source_id"] in {first, second}
    assert row["source_sha256"] == hashlib.sha256(STATEMENT.encode()).hexdigest()
    assert row["revision"] == 1
    assert row["project_ids"] == ["larkspur"]
    assert "project_ambiguity" not in result


@pytest.mark.parametrize("matching_alias_on_higher_source", [True, False])
def test_identical_statement_prefers_approved_query_alias_without_identity_merge(
    store, matching_alias_on_higher_source,
):
    """Two current identical facts: the alias match, not ID order, wins."""
    _, headers, open_adapter = store
    adapter = open_adapter()
    initial = [
        save(adapter, headers, f"Draft {index}: {STATEMENT}",
             [{**TAG, "project_id": "larkspur", "aliases": ["enamel"]}])
        for index in range(2)
    ]
    lower_id, higher_id = sorted(initial)
    selected = higher_id if matching_alias_on_higher_source else lower_id
    ignored = lower_id if matching_alias_on_higher_source else higher_id
    # Corrections legally give both different original facts the same exact
    # current statement, and deterministically place 'coating' on either ID.
    for source_id in (lower_id, higher_id):
        alias = "coating" if source_id == selected else "enamel"
        revised = adapter.handle(
            "POST", f"/api/restricted/v1/facts/{source_id}/corrections",
            headers=headers,
            body={
                "statement": STATEMENT,
                "approved_semantic_links_v1": [
                    {**TAG, "project_id": "larkspur", "aliases": [alias]}
                ],
            },
        )
        assert revised.status == 200, revised.body
        assert revised.body["persistence_verified"] is True

    result = bundle(store, "Which coating for the deck?")
    assert [row["source_id"] for row in result["evidence"]] == [selected]
    item = result["evidence"][0]
    assert item["chunk_id"] == selected
    assert item["revision"] == 2
    assert item["source_sha256"] == hashlib.sha256(STATEMENT.encode()).hexdigest()
    assert item["highlights"][0]["text"] == STATEMENT
    assert item["project_ids"] == ["larkspur"]
    assert [reason["matched_alias"] for reason in item["recall_reasons"]] == ["coating"]
    assert all(reason["type"] == "approved_semantic_tag"
               and reason["project_id"] == "larkspur"
               and reason["concept"] == "finish_choice"
               for reason in item["recall_reasons"])
    assert ignored not in json.dumps(result["evidence"])
    assert "project_ambiguity" not in result

    # Without a matching tag, keep the existing lexical/ID tie break.
    lexical = bundle(store, "What deck finish was selected?")
    assert len(lexical["evidence"]) == 1
    assert lexical["evidence"][0]["source_id"] == lower_id
    assert "recall_reasons" not in lexical["evidence"][0]
    assert bundle(store, "Which paint for the deck?")["evidence"] == []

    # Corruption must not turn a formerly approved match into a recall vote.
    adapter.memory.load_if_needed()
    entry = next(e for e in adapter.memory.memory_log
                 if isinstance(e, dict)
                 and e.get("category") == "restricted_fact"
                 and e.get("metadata", {}).get("fact_id") == selected
                 and e.get("metadata", {}).get("revision") == 2)
    entry["metadata"]["approved_semantic_links_v1"][0]["source_sha256"] = "0" * 64
    adapter.memory._save()
    assert bundle(store, "Which coating for the deck?")["evidence"] == []


def test_ambiguous_context_reaches_model_as_untrusted_data_not_tool_authority(store, monkeypatch):
    from project_guardian.local_memory_chat import LocalOllama, ManualAuthorization, converse_bundle
    _, headers, open_adapter = store
    adapter = open_adapter()
    save(adapter, headers, STATEMENT, [{**TAG, "project_id": "larkspur"}])
    save(adapter, headers, "Client selected oil deck finish.",
         [{**TAG, "project_id": "juniper"}])
    memory = bundle(store, QUESTION)
    captured = []

    def fake_generate(model, messages, *, json_mode=False):
        captured.append(json.loads(messages[-1]["content"]))
        return json.dumps({"answer": "Which project do you mean?"})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    result = converse_bundle(memory, QUESTION, ManualAuthorization(
        "req-ambiguity", True, True, frozenset({"local.chat", "memory.read"})
    ), LocalOllama("fixture-model"), recent=())
    assert captured[0]["context_bundle"]["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["juniper", "larkspur"],
    }
    assert result["tools_executed"] == [] and result["memory_written"] is False



def test_partial_project_prefix_requires_clarification_in_rendered_bundle(store, monkeypatch):
    """Original independent RED: moonbeam is NOT moonbeam_court."""
    from project_guardian.local_memory_chat import LocalOllama, ManualAuthorization, converse_bundle
    _, headers, open_adapter = store
    adapter = open_adapter()
    statement = "Client approved acrylic for the surface."
    source_id = save(adapter, headers, statement, [
        {**TAG, "project_id": "moonbeam_court"},
    ])
    q = "Which coating for project moonbeam?"
    result = bundle(store, q)
    assert {row["source_id"] for row in result["evidence"]} == {source_id}
    assert result["project_ambiguity"] == {
        "requires_clarification": True,
        "project_ids": ["moonbeam_court"],
        "unknown_project_hints": ["moonbeam"],
    }
    row = result["evidence"][0]
    assert row["source_sha256"] == hashlib.sha256(statement.encode()).hexdigest()
    assert row["revision"] == 1
    assert row["recall_reasons"][0]["type"] == "approved_semantic_tag"
    captured = []

    def fake_generate(model, messages, *, json_mode=False):
        captured.append(json.loads(messages[-1]["content"]))
        assert "requires_clarification" in messages[0]["content"]
        return json.dumps({"answer": "Which project do you mean?"})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(result, q, ManualAuthorization(
        "req-partial", True, True, frozenset({"local.chat", "memory.read"})
    ), LocalOllama("fixture-model"), recent=())
    assert captured[0]["context_bundle"]["project_ambiguity"] == result["project_ambiguity"]
    assert reply["tools_executed"] == [] and reply["memory_written"] is False


def test_exact_multiword_project_and_shorter_approved_collision(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    short = save(adapter, headers, "Moonbeam exterior approved oil.",
                 [{**TAG, "project_id": "moonbeam"}])
    long = save(adapter, headers, "Moonbeam court interior approved acrylic.",
                [{**TAG, "project_id": "moonbeam_court"}])
    for name in ("moonbeam court", "moonbeam-court", "moonbeam_court"):
        result = bundle(store, "Which coating for project " + name + "?")
        assert [row["source_id"] for row in result["evidence"]] == [long]
        assert result["evidence"][0]["project_ids"] == ["moonbeam_court"]
        assert "project_ambiguity" not in result
    short_result = bundle(store, "Which coating for project moonbeam?")
    assert [row["source_id"] for row in short_result["evidence"]] == [short]
    assert "project_ambiguity" not in short_result


def test_partial_extension_of_short_name_requires_clarification(store):
    _, headers, open_adapter = store
    source_id = save(open_adapter(), headers, "Moonbeam exterior approved oil.",
                     [{**TAG, "project_id": "moonbeam"}])
    result = bundle(store, "Which coating for project moonbeam court?")
    assert {row["source_id"] for row in result["evidence"]} == {source_id}
    assert result["project_ambiguity"] == {
        "requires_clarification": True,
        "project_ids": ["moonbeam"],
        "unknown_project_hints": ["moonbeam_court"],
    }


def test_project_hints_unknown_single_letter_and_multiple_exact_names(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    one = save(adapter, headers, "Moonbeam exterior approved oil.",
               [{**TAG, "project_id": "moonbeam"}])
    two = save(adapter, headers, "Moonbeam court interior approved acrylic.",
               [{**TAG, "project_id": "moonbeam_court"}])
    unknown = bundle(store, "Which coating for project x?")
    assert unknown["project_ambiguity"]["unknown_project_hints"] == ["x"]
    assert {row["source_id"] for row in unknown["evidence"]} == {one, two}
    multiple = bundle(store, "Which coating for project moonbeam and project moonbeam court?")
    assert multiple["project_ambiguity"] == {
        "requires_clarification": True,
        "project_ids": ["moonbeam", "moonbeam_court"],
    }
    assert {row["source_id"] for row in multiple["evidence"]} == {one, two}


def test_exact_project_scoping_after_correction_and_candidate_quarantine(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    current = save(adapter, headers, "Moonbeam court selected acrylic.",
                   [{**TAG, "project_id": "moonbeam_court"}])
    old = save(adapter, headers, "Moonbeam selected oil.",
               [{**TAG, "project_id": "moonbeam"}])
    endpoint = f"/api/restricted/v1/facts/{old}/corrections"
    response = adapter.handle("POST", endpoint, headers=headers, body={
        "statement": "Client withdrew the original decision."
    })
    assert response.status == 200
    save(adapter, headers, "Tentative synthetic coating choice.",
         [{**CANDIDATE, "project_id": "moonbeam"}])
    named = bundle(store, "Which coating for project moonbeam court?")
    assert [row["source_id"] for row in named["evidence"]] == [current]
    assert "project_ambiguity" not in named
    partial = bundle(store, "Which coating for project moonbeam?")
    assert partial["project_ambiguity"]["unknown_project_hints"] == ["moonbeam"]
    assert all(row["source_id"] != old for row in partial["evidence"])


def test_trailing_bare_project_requires_model_visible_clarification(store, monkeypatch):
    """Independent RED: a trailing 'project?' is an unresolved scope cue."""
    from project_guardian.local_memory_chat import LocalOllama, ManualAuthorization, converse_bundle

    _, headers, open_adapter = store
    statement = "Client approved acrylic for the surface."
    source_id = save(open_adapter(), headers, statement, [
        {**TAG, "project_id": "moonbeam_court"},
    ])
    q = "Which coating for project?"
    memory = bundle(store, q)
    assert [row["source_id"] for row in memory["evidence"]] == [source_id]
    assert memory["evidence"][0]["source_sha256"] == hashlib.sha256(
        statement.encode("utf-8")
    ).hexdigest()
    assert memory["project_ambiguity"] == {
        "requires_clarification": True,
        "project_ids": ["moonbeam_court"],
        "unknown_project_hints": ["project"],
    }
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        assert "requires_clarification" in messages[0]["content"]
        return json.dumps({"answer": "Which project do you mean?"})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(memory, q, ManualAuthorization(
        "req-trailing-project", True, True, frozenset({"local.chat", "memory.read"})
    ), LocalOllama("fixture-model"), recent=())
    assert seen[0]["context_bundle"]["project_ambiguity"] == memory["project_ambiguity"]
    assert reply["tools_executed"] == [] and reply["memory_written"] is False


def test_long_project_consumes_suffix_project_without_cross_scope(store, monkeypatch):
    """Independent RED: moonbeam_court must not also match the project court."""
    from project_guardian.local_memory_chat import LocalOllama, ManualAuthorization, converse_bundle

    _, headers, open_adapter = store
    adapter = open_adapter()
    long_text = "Client approved acrylic for the surface."
    long_id = save(adapter, headers, long_text, [{**TAG, "project_id": "moonbeam_court"}])
    suffix_id = save(adapter, headers, "Client approved oil for the surface.", [
        {**TAG, "project_id": "court"},
    ])
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        return json.dumps({"answer": "The approved surface is acrylic."})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    for spelling in ("moonbeam court", "moonbeam-court", "moonbeam_court"):
        q = "Which coating for project " + spelling + "?"
        memory = bundle(store, q)
        assert [row["source_id"] for row in memory["evidence"]] == [long_id]
        row = memory["evidence"][0]
        assert row["project_ids"] == ["moonbeam_court"]
        assert row["source_sha256"] == hashlib.sha256(long_text.encode()).hexdigest()
        assert suffix_id not in {item["source_id"] for item in memory["evidence"]}
        assert "project_ambiguity" not in memory
        reply = converse_bundle(memory, q, ManualAuthorization(
            "req-long-project", True, True, frozenset({"local.chat", "memory.read"})
        ), LocalOllama("fixture-model"), recent=())
        assert [item["source_id"] for item in seen[-1]["context_bundle"]["evidence"]] == [long_id]
        assert "project_ambiguity" not in seen[-1]["context_bundle"]
        assert reply["tools_executed"] == [] and reply["memory_written"] is False


def test_explicit_project_cue_outranks_incidental_project_topic_word(store, monkeypatch):
    """RED before correction: deck in 'deck finish' is not a second project cue."""
    from project_guardian.local_memory_chat import LocalOllama, ManualAuthorization, converse_bundle

    _, headers, open_adapter = store
    adapter = open_adapter()
    approved = {"concept": "#finish_choice", "aliases": ["finish"], "state": "selected_existing"}
    deck_id = save(adapter, headers, "Client approved oil for the surface.", [
        {**approved, "project_id": "deck"},
    ])
    larkspur_statement = "Client approved acrylic for the surface."
    larkspur_id = save(adapter, headers, larkspur_statement, [
        {**approved, "project_id": "larkspur"},
    ])
    q = "What deck finish for project larkspur?"
    memory = bundle(store, q)
    assert [item["source_id"] for item in memory["evidence"]] == [larkspur_id]
    assert memory["evidence"][0]["project_ids"] == ["larkspur"]
    assert memory["evidence"][0]["source_sha256"] == hashlib.sha256(
        larkspur_statement.encode("utf-8")
    ).hexdigest()
    assert memory["evidence"][0]["revision"] == 1
    assert deck_id not in {item["source_id"] for item in memory["evidence"]}
    assert "project_ambiguity" not in memory
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        return json.dumps({"answer": "Larkspur selected acrylic."})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(memory, q, ManualAuthorization(
        "req-explicit-cue", True, True, frozenset({"local.chat", "memory.read"})
    ), LocalOllama("fixture-model"), recent=())
    context = seen[0]["context_bundle"]
    assert [row["source_id"] for row in context["evidence"]] == [larkspur_id]
    assert "project_ambiguity" not in context
    assert reply["tools_executed"] == [] and reply["memory_written"] is False


def test_unscoped_project_name_colliding_with_alias_keeps_all_sources(store, monkeypatch):
    """RED before correction: alias 'coating' must not select project coating."""
    from project_guardian.local_memory_chat import LocalOllama, ManualAuthorization, converse_bundle

    _, headers, open_adapter = store
    adapter = open_adapter()
    coating_statement = "Client approved oil for the surface."
    larkspur_statement = "Client approved acrylic for the surface."
    coating_id = save(adapter, headers, coating_statement, [
        {**TAG, "project_id": "coating"},
    ])
    larkspur_id = save(adapter, headers, larkspur_statement, [
        {**TAG, "project_id": "larkspur"},
    ])
    q = "Which coating did we decide on?"
    memory = bundle(store, q)
    rows = memory["evidence"]
    assert {row["source_id"] for row in rows} == {coating_id, larkspur_id}
    assert {tuple(row["project_ids"]) for row in rows} == {
        ("coating",), ("larkspur",),
    }
    assert {row["source_sha256"] for row in rows} == {
        hashlib.sha256(coating_statement.encode("utf-8")).hexdigest(),
        hashlib.sha256(larkspur_statement.encode("utf-8")).hexdigest(),
    }
    assert all(row["revision"] == 1 for row in rows)
    assert memory["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["coating", "larkspur"],
    }
    seen = []

    def fake_generate(model, messages, *, json_mode=False):
        seen.append(json.loads(messages[-1]["content"]))
        assert "requires_clarification" in messages[0]["content"]
        return json.dumps({"answer": "Which project do you mean?"})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(memory, q, ManualAuthorization(
        "req-ambiguous-alias", True, True, frozenset({"local.chat", "memory.read"})
    ), LocalOllama("fixture-model"), recent=())
    assert {row["source_id"] for row in seen[0]["context_bundle"]["evidence"]} == {
        coating_id, larkspur_id,
    }
    assert seen[0]["context_bundle"]["project_ambiguity"] == memory["project_ambiguity"]
    assert reply["tools_executed"] == [] and reply["memory_written"] is False


def test_unscoped_proper_project_name_does_not_silently_filter_other_project(store):
    """Bare project names cannot be distinguished from ordinary topical terms."""
    _, headers, open_adapter = store
    adapter = open_adapter()
    one = save(adapter, headers, "Larkspur deck finish is acrylic.", [
        {**TAG, "project_id": "larkspur"},
    ])
    two = save(adapter, headers, "Juniper deck finish is oil.", [
        {**TAG, "project_id": "juniper"},
    ])
    memory = bundle(store, "What is the Larkspur deck finish?")
    assert {row["source_id"] for row in memory["evidence"]} == {one, two}
    assert memory["project_ambiguity"] == {
        "requires_clarification": True, "project_ids": ["juniper", "larkspur"],
    }


@pytest.mark.parametrize(("continuation", "unknown"), [
    pytest.param(" and Juniper", None, id="G04-conjoined-and"),
    pytest.param(" or Juniper", None, id="G05-conjoined-or"),
    pytest.param(", Juniper", None, id="G06-comma-known-name"),
    pytest.param(" and Moonbeam", "moonbeam", id="G08-conjoined-unknown"),
    pytest.param(" or Moonbeam", "moonbeam", id="G08-or-unknown"),
])
def test_one_project_cue_must_resolve_coordinated_names_not_silently_filter(
    store, monkeypatch, continuation, unknown,
):
    """Test-only expected-RED grammar contract against pinned existing source.

    Real restricted adapter and persistent synthetic MemoryCore; explicit
    per-source SHA/revision and model-visible ambiguity must survive retrieval.
    """
    from project_guardian.local_memory_chat import LocalOllama, ManualAuthorization, converse_bundle

    path, headers, open_adapter = store
    adapter = open_adapter()
    larkspur_text = "Client approved acrylic for the surface."
    juniper_text = "Client approved oil for the surface."
    larkspur_id = save(adapter, headers, larkspur_text, [
        {**TAG, "project_id": "larkspur"},
    ])
    juniper_id = save(adapter, headers, juniper_text, [
        {**TAG, "project_id": "juniper"},
    ])
    before = path.read_bytes()
    question = "Which coating for project Larkspur" + continuation + "?"
    memory = bundle(store, question)
    rows = {row["source_id"]: row for row in memory["evidence"]}
    expected = {
        larkspur_id: ("larkspur", larkspur_text),
        juniper_id: ("juniper", juniper_text),
    }
    # With multiple or unresolved references, never silently drop B's fact.
    assert set(rows) == set(expected)
    for fact_id, (project, statement) in expected.items():
        row = rows[fact_id]
        assert row["chunk_id"] == fact_id
        assert row["revision"] == 1
        assert row["project_ids"] == [project]
        assert row["source_sha256"] == hashlib.sha256(statement.encode("utf-8")).hexdigest()
        assert row["highlights"][0]["text"] == statement
        assert row["recall_reasons"][0]["type"] == "approved_semantic_tag"

    warning = memory.get("project_ambiguity")
    assert warning is not None
    assert warning["requires_clarification"] is True
    assert warning["project_ids"] == ["juniper", "larkspur"]
    if unknown is None:
        # Comma and conjunction of TWO approved identities is not an unknown.
        assert "unknown_project_hints" not in warning
    else:
        assert warning["unknown_project_hints"] == [unknown]

    captured = []

    def fake_generate(model, messages, *, json_mode=False):
        captured.append(json.loads(messages[-1]["content"]))
        assert "requires_clarification" in messages[0]["content"]
        return json.dumps({"answer": "Which project do you mean?"})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    reply = converse_bundle(memory, question, ManualAuthorization(
        "req-coordinated-baseline", True, True,
        frozenset({"local.chat", "memory.read"}),
    ), LocalOllama("fixture-model"), recent=())
    visible = captured[0]["context_bundle"]
    assert {row["source_id"] for row in visible["evidence"]} == set(expected)
    assert visible["project_ambiguity"] == warning
    assert reply["tools_executed"] == []
    assert reply["memory_written"] is False
    assert path.read_bytes() == before


def test_uncertain_conjoined_task_cannot_confidently_select_only_first_project(store):
    """G09: 'and deck sanding' may be task prose; clarify, never invent a project."""
    _, headers, open_adapter = store
    adapter = open_adapter()
    larkspur_id = save(adapter, headers, "Client approved acrylic for the surface.", [
        {**TAG, "project_id": "larkspur"},
    ])
    juniper_id = save(adapter, headers, "Client approved oil for the surface.", [
        {**TAG, "project_id": "juniper"},
    ])
    memory = bundle(store, "Which coating for project Larkspur and deck sanding?")
    assert {row["source_id"] for row in memory["evidence"]} == {larkspur_id, juniper_id}
    warning = memory["project_ambiguity"]
    assert warning["requires_clarification"] is True
    assert warning["project_ids"] == ["juniper", "larkspur"]
    assert "deck" not in warning["project_ids"]
