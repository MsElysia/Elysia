"""Deterministic retrieval benchmark: current facts and completed documents compete.

All data fictional. No model, personal memory, files, provider or network needed.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from project_guardian.document_ingestion import DocumentLibrary
from project_guardian.local_memory_chat import (
    ChatBoundaryError, EVIDENCE_BYTE_CAP, EVIDENCE_ITEM_CAP,
    build_context_from_adapter, canonical,
)


class FakeAdapter:
    def __init__(self, facts):
        self._facts = list(facts)
        self.memory = SimpleNamespace(filepath="unused-synthetic-memory.json")

    def current_fact_snapshots(self):
        return list(self._facts)

    def store_identity(self):
        return {"module": "synthetic", "filepath": "unused-synthetic-memory.json"}


def _fact(name, statement, revision=1):
    return {"fact_id": name, "statement": statement, "revision": revision}


def _doc(key, text, score=0.9):
    return {
        "source_id": "doc_" + key, "chunk_id": "chunk_" + key,
        "content_sha256": "0" * 64, "filename": key + ".txt", "page": 1,
        "score": score, "text": text,
    }


def _context(facts, docs, query):
    with patch.object(DocumentLibrary, "search", return_value=docs), patch(
        "project_guardian.capability_awareness.record_capability_success"
    ):
        return build_context_from_adapter(FakeAdapter(facts), query, {})


@pytest.mark.parametrize("subject", [
    f"{place}-{thing}"
    for place in ("Veridia", "Torvyn", "Lanthor", "Ombera", "Cavira")
    for thing in ("compass", "lantern", "sundial", "telescope", "banner",
                  "mapcase", "blueprint", "journal", "pedestal", "weatherstone")
])
def test_retrieval_top_four_finds_specific_document_over_generic_facts(subject):
    place, thing = subject.split("-")
    query = f"Which archive holds the {place} {thing} inventory record?"
    facts = [
        _fact(f"fact_{place}_{i}", f"The {place} archive has a general inventory record for visitor {i}.")
        for i in range(5)
    ]
    target = _doc(subject, f"The {place} {thing} inventory record is held at Amber Observatory archive.")
    result = _context(facts, [target], query)
    assert len(result["evidence"]) <= EVIDENCE_ITEM_CAP
    assert "doc_" + subject in [e["source_id"] for e in result["evidence"]]
    assert result["no_memory_support"] is False
    assert len(canonical(result["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP


def test_current_correction_keeps_revision_and_never_reintroduces_old_claim():
    facts = [
        _fact("fact_city", "The fictional Veridia harbor is Glasshaven.", revision=2),
        _fact("fact_noise", "The fictional Veridia city has yellow lanterns."),
    ]
    result = _context(facts, [], "What is the Veridia harbor city called?")
    current = next(e for e in result["evidence"] if e["source_id"] == "fact_city")
    assert current["revision"] == 2
    assert "Glasshaven" in current["highlights"][0]["text"]
    assert "Lumenport" not in canonical(result)


def test_relevant_fact_not_replaced_by_weak_document_keyword_match():
    facts = [_fact("fact_compass", "The fictional Veridia compass is kept inside the southern vault.")]
    docs = [_doc("weak", "Travel guide advertising a generic compass.", score=0.25)]
    result = _context(facts, docs, "Where is the Veridia compass kept?")
    assert result["evidence"][0]["source_id"] == "fact_compass"


def test_large_top_hit_does_not_hide_small_relevant_hit():
    facts = [_fact("fact_oversized", "Veridia compass observatory vault " + "oversize " * 3000)]
    docs = [_doc("small", "The Veridia compass is stored in the observatory vault.")]
    result = _context(facts, docs, "Where is the Veridia compass observatory vault?")
    assert any(e["source_id"] == "doc_small" for e in result["evidence"])
    assert len(canonical(result["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP


def test_absent_evidence_never_fabricated():
    result = _context(
        [_fact("fact_other", "The fictional Veridia lanterns are purple.")],
        [],
        "Where is the Orbleth weatherstone stored?",
    )
    assert result["evidence"] == []
    assert result["no_memory_support"] is True


def test_selection_is_deterministic_and_does_not_touch_source_data():
    facts = [_fact("fact_city", "The fictional Veridia compass is kept in the vault.")]
    docs = [_doc("map", "The fictional Veridia compass vault map is posted at the entrance.")]
    before = canonical(facts) + canonical(docs)
    a = _context(facts, docs, "Where is the Veridia compass vault?")
    b = _context(facts, docs, "Where is the Veridia compass vault?")
    assert a["bundle_sha256"] == b["bundle_sha256"]
    assert a["evidence"] == b["evidence"]
    assert canonical(facts) + canonical(docs) == before
    assert any(e.get("trust") == "untrusted_document" for e in a["evidence"])


def test_question_validation_preserved():
    with pytest.raises(ChatBoundaryError):
        _context([], [], "and the please")
    with pytest.raises(ChatBoundaryError):
        _context([], [], "x" * 801)


def test_oversized_best_source_keeps_cited_excerpt_and_original_provenance():
    import hashlib

    needle = "The Nahlia chronometer serial NX-441 is sealed in the east annex vault."
    padding = "background inventory filler note " * 400
    doc = _doc("huge", padding + needle + " " + padding)
    original = canonical(doc)
    result = _context([], [doc], "Where is the Nahlia chronometer serial NX-441 sealed?")
    assert result["evidence"], "the only strong source must not silently disappear"
    hit = result["evidence"][0]
    assert hit["source_id"] == "doc_huge"
    assert hit["source_sha256"] == "0" * 64, "do not relabel excerpts as original bytes"
    highlight = hit["highlights"][0]
    assert "NX-441" in highlight["text"] and "east annex" in highlight["text"]
    assert highlight["excerpted"] is True
    assert highlight["original_chars"] == len(doc["text"])
    assert highlight["excerpt_sha256"] == hashlib.sha256(
        highlight["text"].encode("utf-8")
    ).hexdigest()
    assert len(canonical(result["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP
    assert canonical(doc) == original


def test_buried_tail_passage_keeps_relevant_source_without_false_hash():
    text = ("routine telemetry for passive observers\n" * 230)
    text += "The Kestrel relay codebook is filed on shelf R-17 in Harbor Stack."
    doc = _doc("buried", text)
    result = _context([], [doc], "Where is the Kestrel relay codebook filed?")
    assert result["evidence"][0]["source_id"] == "doc_buried"
    assert "shelf R-17" in result["evidence"][0]["highlights"][0]["text"]
    assert result["evidence"][0]["source_sha256"] == doc["content_sha256"]


def test_oversized_fact_preserves_authoritative_statement_hash():
    import hashlib

    fact = _fact(
        "fact_long",
        "Veridia compass vault " + "irrelevant inventory filler " * 1200
        + "The Veridia compass is stored at the eastern watchtower.",
    )
    result = _context([fact], [], "Where is the Veridia compass stored?")
    hit = result["evidence"][0]
    assert hit["source_sha256"] == hashlib.sha256(
        fact["statement"].encode("utf-8")
    ).hexdigest()
    assert "eastern watchtower" in hit["highlights"][0]["text"]
    assert hit["highlights"][0]["excerpted"] is True


def test_diagnostic_and_malformed_document_rows_are_not_evidence():
    diag = _doc("diag", "Veridia compass stored at north tower diagnostic traceback.")
    diag["trust"], diag["collection"] = "diagnostic_log", "diagnostic_logs"
    malformed = _doc("bad", "Veridia compass stored at north tower.")
    malformed["trust"] = ["diagnostic_log"]
    casefold_diag = _doc("case", "Veridia compass stored at north tower.")
    casefold_diag["collection"] = "Diagnostic_Logs"
    safe = _doc("safe", "The Veridia compass is stored at the eastern watchtower.")
    result = _context([], [diag, malformed, casefold_diag, safe],
                      "Where is the Veridia compass stored?")
    assert [x["source_id"] for x in result["evidence"]] == ["doc_safe"]


def test_unicode_heavy_evidence_stays_within_utf8_byte_cap():
    doc = _doc("unicode", "Veridia compass vault " + "☃" * 9000
               + " The Veridia compass is at the eastern watchtower.")
    result = _context([], [doc], "Where is the Veridia compass?")
    assert result["evidence"]
    assert len(canonical(result["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP
    assert result["evidence"][0]["source_sha256"] == doc["content_sha256"]


@pytest.mark.parametrize("subject", ["Nahlia beacon", "Torvyn telescope", "Veridia atlas"])
def test_repeated_question_only_memories_cannot_crowd_out_document_answer(subject):
    """Four question echoes are not four independent answers to a location query."""
    question = f"Where is the {subject} stored?"
    facts = [
        _fact(f"fact_pending_{i}",
              f"Where is the {subject} stored? Answer still pending confirmation, note {i}.")
        for i in range(5)
    ]
    document = _doc("located", f"The {subject} is located at Cedar Pier.")
    first = _context(facts, [document], question)
    second = _context(facts, [document], question)
    assert "doc_located" in [e["source_id"] for e in first["evidence"]]
    assert len(first["evidence"]) <= EVIDENCE_ITEM_CAP
    assert first["evidence"] == second["evidence"]


def test_distinct_conflicting_facts_are_not_deduplicated_by_similarity():
    facts = [
        _fact("fact_east", "The Nahlia beacon is located at Cedar Pier."),
        _fact("fact_west", "The Nahlia beacon is located at Willow Cove."),
    ]
    result = _context(facts, [], "Where is the Nahlia beacon located?")
    ids = {item["source_id"] for item in result["evidence"]}
    assert {"fact_east", "fact_west"}.issubset(ids)
