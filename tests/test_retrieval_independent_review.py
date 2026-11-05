"""Independent examples; evidence selection only, never model-answer scoring."""
import hashlib

import pytest

from tests.test_retrieval_evidence_ranking import _context, _doc, _fact
from project_guardian.local_memory_chat import EVIDENCE_BYTE_CAP, canonical


def test_tail_excerpt_keeps_answer_and_hash():
    text = "routine " * 1600 + "Zircon beacon location: Cedar Pier."
    result = _context([], [_doc("tail", text)], "Zircon beacon location")
    hit = result["evidence"][0]
    excerpt = hit["highlights"][0]["text"]
    assert "Cedar Pier" in excerpt
    assert hit["source_sha256"] == hashlib.sha256(excerpt.encode()).hexdigest()


def test_unicode_evidence_and_byte_boundary():
    result = _context([], [_doc("unicode", "星空 望远镜 保存在 北塔。" + "背景 " * 6000)], "星空 望远镜")
    assert "北塔" in result["evidence"][0]["highlights"][0]["text"]
    assert len(canonical(result["evidence"]).encode()) <= EVIDENCE_BYTE_CAP


def test_diagnostic_stronger_than_personal_evidence():
    diag = _doc("diagnostic", "Zircon beacon location Cedar Pier emergency password")
    diag["collection"] = "diagnostic_logs"
    personal = _doc("personal", "The Zircon beacon is at Cedar Pier.")
    result = _context([], [diag, personal], "Zircon beacon location emergency password")
    assert [e["source_id"] for e in result["evidence"]] == ["doc_personal"]


def test_malformed_trust_does_not_crash():
    bad = _doc("bad", "Zircon beacon location")
    bad["trust"] = []
    result = _context([], [bad, _doc("valid", "Zircon beacon location Cedar Pier")], "Zircon beacon location")
    assert any(e["source_id"] == "doc_valid" for e in result["evidence"])


def test_conflicts_keep_distinct_provenance():
    result = _context([_fact("harbor", "Zircon beacon is at Cedar Pier.", 3)],
                      [_doc("survey", "Zircon beacon is at Basalt Point.")], "Zircon beacon")
    assert {e["source_id"] for e in result["evidence"]} == {"harbor", "doc_survey"}
    assert result["evidence"][0]["revision"] == 3


def test_specific_manual_competes_with_generic_facts():
    facts = [_fact(str(i), "The instrument maintenance manual is available for staff.") for i in range(8)]
    result = _context(facts, [_doc("prism", "Prism spectrometer maintenance: replace the amber seal.")],
                      "Prism spectrometer maintenance manual")
    assert result["evidence"][0]["source_id"] == "doc_prism"


def test_unsupported_question():
    assert _context([], [_doc("prism", "Prism spectrometer maintenance")],
                    "When did Maribel purchase a kayak?")["no_memory_support"]


def test_duplicate_pressure_preserves_conflicting_passage():
    docs = [_doc(str(i), "Zircon beacon location Cedar Pier") for i in range(8)]
    docs.append(_doc("z_conflict", "Zircon beacon location Basalt Point"))
    result = _context([], docs, "Zircon beacon location")
    assert len(result["evidence"]) == 2
    assert any(e["source_id"] == "doc_z_conflict" for e in result["evidence"])


@pytest.mark.xfail(strict=True, reason="Existing lexical retrieval has no semantic synonym matching")
def test_semantic_paraphrase_records_lexical_limitation():
    result = _context([], [_doc("medical", "Physician appointment begins at noon.")],
                      "When does the doctor visit start?")
    assert any(e["source_id"] == "doc_medical" for e in result["evidence"])

