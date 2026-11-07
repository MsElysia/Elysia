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


def test_oversized_best_source_keeps_bounded_excerpt_instead_of_silent_loss():
    """Independently chosen: the only strong hit is huge — keep a relevant excerpt."""
    needle = "The Nahlia chronometer serial NX-441 is sealed in the east annex vault."
    padding = ("background inventory filler note " * 400)
    docs = [_doc("huge", padding + needle + " " + padding)]
    result = _context([], docs, "Where is the Nahlia chronometer serial NX-441 sealed?")
    assert result["evidence"], "oversized best source must not disappear"
    hit = result["evidence"][0]
    assert hit["source_id"] == "doc_huge"
    text = hit["highlights"][0]["text"]
    assert "NX-441" in text and "east annex" in text
    assert hit["highlights"][0].get("excerpted") is True
    assert len(text) < len(docs[0]["text"])
    assert len(canonical(result["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP


def test_relevant_passage_inside_large_document_is_selected():
    """Independently chosen: buried passage in a long document must surface."""
    prefix = ("routine sensor heartbeat telemetry line\n" * 80)
    passage = "The Kestrel relay codebook is filed under shelf R-17 in Harbor Stack."
    suffix = ("routine sensor heartbeat telemetry line\n" * 80)
    docs = [
        _doc("noise", "Harbor Stack visitor pamphlet with no codebook details."),
        _doc("large", prefix + passage + suffix),
    ]
    result = _context([], docs, "Where is the Kestrel relay codebook filed?")
    assert any(e["source_id"] == "doc_large" for e in result["evidence"])
    blob = canonical(result["evidence"])
    assert "R-17" in blob and "Kestrel" in blob


def test_paraphrase_corrected_conflict_duplicate_and_unsupported_suite():
    # Paraphrase
    facts = [_fact("fact_harbor", "The fictional Veridia harbor city is called Glasshaven.")]
    r = _context(facts, [], "What city is Veridia's harbor known as?")
    assert "fact_harbor" in [e["source_id"] for e in r["evidence"]]
    assert "Glasshaven" in canonical(r["evidence"])
    # Corrected revision
    facts = [_fact("fact_city", "The fictional Veridia harbor is Glasshaven.", revision=2)]
    r = _context(facts, [], "What is the Veridia harbor city called?")
    assert next(e for e in r["evidence"] if e["source_id"] == "fact_city")["revision"] == 2
    # Conflicting sources remain distinguishable
    facts = [_fact("fact_a", "The Veridia compass is stored in the southern vault.")]
    docs = [_doc("b", "The Veridia compass is stored in the northern tower.")]
    r = _context(facts, docs, "Where is the Veridia compass stored?")
    ids = {e["source_id"] for e in r["evidence"]}
    assert "fact_a" in ids and "doc_b" in ids
    # Duplicates do not exceed cap
    facts = [_fact("fact_once", "The Veridia lantern is kept at Harbor Gate.")]
    docs = [
        _doc("dup1", "The Veridia lantern is kept at Harbor Gate."),
        _doc("dup2", "The Veridia lantern is kept at Harbor Gate."),
    ]
    r = _context(facts, docs, "Where is the Veridia lantern kept?")
    assert len(r["evidence"]) <= EVIDENCE_ITEM_CAP and "fact_once" in [
        e["source_id"] for e in r["evidence"]
    ]
    # Unsupported
    r = _context(
        [_fact("fact_other", "The fictional Veridia lanterns are purple.")],
        [],
        "Where is the Orbleth weatherstone stored?",
    )
    assert r["evidence"] == [] and r["no_memory_support"] is True


def test_diagnostic_log_rows_excluded_from_personal_memory_retrieval():
    diag = _doc("diag", "Traceback ProposalWatcher diagnostic runtime failure detail.")
    diag["trust"] = "diagnostic_log"
    diag["collection"] = "diagnostic_logs"
    facts = [_fact("fact_ok", "The Veridia compass is kept in the southern vault.")]
    result = _context(facts, [diag], "Where is the Veridia compass kept?")
    ids = [e["source_id"] for e in result["evidence"]]
    assert "doc_diag" not in ids
    assert "fact_ok" in ids


@pytest.mark.parametrize(("trust", "collection"), [
    (" diagnostic_log ", None),
    (" \tDiAgNoStIc\t", None),
    ("diagnostic-log", None),
    (None, " Diagnostic_Logs \t"),
    (None, "DIAGNOSTIC-logs"),
    (None, " diagnostic logs "),
    (None, ["diagnostic_logs"]),
])
def test_imported_diagnostic_label_variants_are_never_answer_evidence(trust, collection):
    """Metadata variants and malformed rows fail closed, never poisoning answers."""
    diagnostic = _doc("padded_diag", "The Veridia compass is stored at north tower.")
    if trust is not None:
        diagnostic["trust"] = trust
    if collection is not None:
        diagnostic["collection"] = collection
    safe = _doc("safe_source", "The Veridia compass is stored at south vault.")
    original_diagnostic = dict(diagnostic)
    result = _context([], [diagnostic, safe], "Where is the Veridia compass stored?")
    assert [item["source_id"] for item in result["evidence"]] == ["doc_safe_source"]
    assert diagnostic == original_diagnostic


def test_legitimate_document_with_diagnostic_word_in_body_is_retained():
    ordinary = _doc("ordinary", "The Veridia compass diagnostic manual is at south vault.")
    result = _context([], [ordinary], "Where is the Veridia compass manual?")
    assert [item["source_id"] for item in result["evidence"]] == ["doc_ordinary"]


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
