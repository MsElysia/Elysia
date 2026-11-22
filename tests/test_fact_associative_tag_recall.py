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
    scoped = bundle(store, "What is the Larkspur deck finish?")
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
