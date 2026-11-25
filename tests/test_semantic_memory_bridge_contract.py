"""EA-11A-A: synthetic real-store acceptance contract, outside required RC.

Run normally for baseline controls and strict known gaps; use --runxfail
to expose the missing behavior. No network or operational memory.
"""
from __future__ import annotations

import hashlib
import json
from time import perf_counter_ns

import pytest

from project_guardian.document_ingestion import DocumentLibrary
from project_guardian.local_memory_chat import (
    EVIDENCE_BYTE_CAP,
    EVIDENCE_ITEM_CAP,
    LocalOllama,
    ManualAuthorization,
    _context_tokens,
    build_context_from_adapter,
    canonical,
    converse_bundle,
)
from project_guardian.restricted_runtime_adapter import (
    LocalPrincipal,
    OPERATOR_FACT_PERMISSIONS,
    RestrictedRuntimeAdapter,
)


class MissingAssociativeEvidence(AssertionError):
    """Only the measured acceptance gap, not a fixture/runtime failure."""


STATEMENT = "Client selected water-based deck finish."
PARAPHRASE = "Which coating did we decide on?"
LEXICAL = "What deck finish was selected?"
CURRENT = "Larkspur deck finish is water-based acrylic."
OLD = "Larkspur deck finish is oil."
OTHER = "Juniper deck finish is oil."


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text("[]", encoding="utf-8")
    principal = LocalPrincipal(
        "synthetic-operator", "fixture-only", OPERATOR_FACT_PERMISSIONS
    )
    headers = {"X-Elysia-Identity": "synthetic-operator",
               "X-Elysia-Token": "fixture-only"}

    def open_adapter():
        return RestrictedRuntimeAdapter(
            principals=[principal], memory_filepath=str(path)
        )

    return path, headers, open_adapter


def teach(adapter, headers, statement):
    response = adapter.handle(
        "POST", "/api/restricted/v1/facts",
        headers=headers, body={"statement": statement},
    )
    assert response.status == 201, response.body
    return response.body["fact"]["fact_id"]


def correct(adapter, headers, source_id, statement):
    response = adapter.handle(
        "POST", f"/api/restricted/v1/facts/{source_id}/corrections",
        headers=headers, body={"statement": statement},
    )
    assert response.status in (200, 201), response.body


def select(store, adapter, question, expected, label):
    path, headers, _ = store
    before = path.read_bytes()
    start = perf_counter_ns()
    bundle = build_context_from_adapter(adapter, question, headers)
    elapsed_ms = (perf_counter_ns() - start) / 1e6
    assert path.read_bytes() == before
    assert bundle == build_context_from_adapter(adapter, question, headers)
    assert path.read_bytes() == before
    assert bundle["schema"] == "elysia.local-context.v1"
    assert bundle["evidence_trust"] == "untrusted_data"
    assert bundle["selection"] == "current_revision_only"
    evidence = bundle["evidence"]
    ids = {row["source_id"] for row in evidence}
    nbytes = len(canonical(evidence).encode("utf-8"))
    assert len(evidence) <= EVIDENCE_ITEM_CAP
    assert nbytes <= EVIDENCE_BYTE_CAP
    assert bundle["no_memory_support"] == (not evidence)
    unsigned = {k: v for k, v in bundle.items() if k != "bundle_sha256"}
    assert bundle["bundle_sha256"] == hashlib.sha256(
        canonical(unsigned).encode("utf-8")
    ).hexdigest()
    assert all(row["source_id"] and row["chunk_id"] and row["revision"] >= 1
               and len(row["source_sha256"]) == 64 for row in evidence)
    print(json.dumps({
        "fixture": label, "expected": sorted(expected), "observed": sorted(ids),
        "recall": len(ids & expected) / len(expected) if expected else None,
        "precision": len(ids & expected) / len(ids) if ids else None,
        "evidence_bytes": nbytes, "items": len(evidence), "elapsed_ms": elapsed_ms,
        "no_memory_support": bundle["no_memory_support"],
    }, sort_keys=True))
    return bundle


def assert_source(row, text, revision):
    assert row["revision"] == revision
    assert row["highlights"][0]["text"] == text
    assert row["source_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.xfail(strict=True, raises=MissingAssociativeEvidence,
                   reason="EA-11A-A observed zero lexically disjoint recall")
@pytest.mark.parametrize("kind", ["fact", "document"])
def test_t01_meaning_only_fresh_retrieval(store, kind):
    _, headers, open_adapter = store
    adapter = open_adapter()
    assert not set(_context_tokens(STATEMENT)) & set(_context_tokens(PARAPHRASE))
    if kind == "fact":
        expected = teach(adapter, headers, STATEMENT)
    else:
        receipt = DocumentLibrary(adapter.memory).import_bytes(
            "synthetic-decision.txt", STATEMENT.encode("utf-8")
        )
        assert receipt["status"] == "completed"
        expected = receipt["source_id"]
    # Fresh adapter; no conversation history and no enabled vector index.
    adapter = open_adapter()
    assert adapter.memory.vector_search is None
    # Require lexical control first: real write/import/recall must work.
    control = select(store, adapter, LEXICAL, {expected}, "T01-control-" + kind)
    assert [row["source_id"] for row in control["evidence"]] == [expected]
    bundle = select(store, adapter, PARAPHRASE, {expected}, "T01-" + kind)
    if {row["source_id"] for row in bundle["evidence"]} != {expected}:
        raise MissingAssociativeEvidence("T01 missing only relevant semantic source")
    row = bundle["evidence"][0]
    assert_source(row, STATEMENT, 1)
    if kind == "document":
        assert row["trust"] == "untrusted_document"


def test_t03_current_revision_and_fresh_local_model_payload(store, monkeypatch):
    path, headers, open_adapter = store
    adapter = open_adapter()
    source_id = teach(adapter, headers, OLD)
    correct(adapter, headers, source_id, CURRENT)
    adapter = open_adapter()
    history = adapter.handle(
        "GET", f"/api/restricted/v1/facts/{source_id}/history", headers=headers
    )
    assert history.status == 200
    assert [r["revision"] for r in history.body["revisions"]] == [1, 2]
    assert history.body["revisions"][0]["statement"] == OLD
    q = "What is the Larkspur deck finish?"
    before = path.read_bytes()
    bundle = select(store, adapter, q, {source_id}, "T03-current")
    assert len(bundle["evidence"]) == 1
    row = bundle["evidence"][0]
    assert row["source_id"] == source_id
    assert_source(row, CURRENT, 2)
    captured = []

    def fake_generate(model, messages, *, json_mode=False):
        assert json_mode
        payload = json.loads(messages[-1]["content"])
        captured.append((model.model, payload))
        return json.dumps({"answer": "Synthetic response."})

    monkeypatch.setattr(LocalOllama, "generate", fake_generate)
    for name in ("fixture-model-a", "fixture-model-b"):
        fresh = select(store, open_adapter(), q, {source_id}, "T03-" + name)
        result = converse_bundle(
            fresh, q, ManualAuthorization(
                "fixture-" + name, True, True, frozenset({"local.chat", "memory.read"})
            ), LocalOllama(name), recent=(),
        )
        assert result["tools_executed"] == []
        assert result["memory_written"] is False
    assert [name for name, _ in captured] == ["fixture-model-a", "fixture-model-b"]
    for _, payload in captured:
        assert payload["recent_conversation"] == []
        assert payload["context_bundle"] == bundle
        assert OLD not in canonical(payload["context_bundle"])
    assert path.read_bytes() == before


@pytest.mark.xfail(strict=True, raises=MissingAssociativeEvidence,
                   reason="EA-11A-A observed unrelated project's evidence in explicit query")
def test_t04_explicit_project_excludes_other_project(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    target = teach(adapter, headers, CURRENT)
    distractor = teach(adapter, headers, OTHER)
    assert target != distractor
    bundle = select(store, open_adapter(), "What is the Larkspur deck finish?",
                    {target}, "T04-explicit")
    if {r["source_id"] for r in bundle["evidence"]} != {target}:
        raise MissingAssociativeEvidence("T04 unrelated project or omitted target")
    assert_source(bundle["evidence"][0], CURRENT, 1)


def test_t04_ambiguous_project_retains_distinct_sources(store):
    _, headers, open_adapter = store
    adapter = open_adapter()
    first = teach(adapter, headers, CURRENT)
    second = teach(adapter, headers, OTHER)
    bundle = select(store, open_adapter(), "What is the deck finish?",
                    {first, second}, "T04-ambiguous")
    # Both are relevant to this underspecified question. No answer-generation
    # confidence is asserted; later disambiguation must clarify or abstain.
    rows = {r["source_id"]: r for r in bundle["evidence"]}
    assert set(rows) == {first, second}
    assert_source(rows[first], CURRENT, 1)
    assert_source(rows[second], OTHER, 1)


def test_t05_absent_evidence_and_real_document_source(store):
    path, headers, open_adapter = store
    adapter = open_adapter()
    teach(adapter, headers, CURRENT)
    receipt = DocumentLibrary(adapter.memory).import_bytes(
        "synthetic-survey.txt", b"Zircon survey beacon rests at Cedar Pier."
    )
    assert receipt["status"] == "completed"
    source_id = receipt["source_id"]
    managed = DocumentLibrary(adapter.memory).root / receipt["managed_copy"]
    raw = managed.read_bytes()
    assert raw == b"Zircon survey beacon rests at Cedar Pier."
    adapter = open_adapter()
    before = path.read_bytes()
    empty = select(store, adapter, "Where are the lunar telescopes?", set(), "T05-negative")
    assert empty["no_memory_support"] is True
    assert empty["evidence"] == []
    result = select(store, adapter, "Where is the Zircon survey beacon?",
                    {source_id}, "T05-document")
    assert len(result["evidence"]) == 1
    row = result["evidence"][0]
    assert row["source_id"] == source_id
    assert row["trust"] == "untrusted_document"
    assert row["filename"] == "synthetic-survey.txt"
    assert_source(row, raw.decode("utf-8"), 1)
    assert managed.read_bytes() == raw
    assert path.read_bytes() == before
