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


def test_duplicate_pressure_preserves_distinct_evidence():
    docs = [_doc(str(i), "Zircon beacon location Cedar Pier") for i in range(8)]
    docs.append(_doc("z_conflict", "Zircon beacon location Basalt Point"))
    result = _context([], docs, "Zircon beacon location")
    assert [e["source_id"] for e in result["evidence"]] == ["doc_0", "doc_z_conflict"]
    assert [e["highlights"][0]["text"] for e in result["evidence"]] == [
        "Zircon beacon location Cedar Pier", "Zircon beacon location Basalt Point",
    ]


@pytest.mark.xfail(strict=True, reason="Existing lexical retrieval has no semantic synonym matching")
def test_semantic_paraphrase_records_lexical_limitation():
    result = _context([], [_doc("medical", "Physician appointment begins at noon.")],
                      "When does the doctor visit start?")
    assert any(e["source_id"] == "doc_medical" for e in result["evidence"])


def test_long_near_identical_conflict_retains_source_and_exact_text():
    common = "Zircon beacon maintenance survey certified equipment " * 45
    a = _doc("a", common + "Zircon beacon is at Cedar Pier.")
    a["content_sha256"] = hashlib.sha256(a["text"].encode()).hexdigest()
    docs = [dict(a, source_id=f"doc_{i}", chunk_id=f"chunk_{i}") for i in range(8)]
    b = _doc("z_conflict", common + "Zircon beacon is NOT at Cedar Pier; it is at Basalt Point.")
    b["content_sha256"] = hashlib.sha256(b["text"].encode()).hexdigest()
    docs.append(b)
    before = canonical(docs)
    result = _context([], docs, "Zircon beacon maintenance location")
    evidence = result["evidence"]
    assert [e["source_id"] for e in evidence] == ["doc_0", "doc_z_conflict"]
    assert evidence[0]["highlights"][0]["text"] == a["text"]
    assert evidence[1]["highlights"][0]["text"] == b["text"]
    assert evidence[1]["source_sha256"] == b["content_sha256"]
    assert canonical(docs) == before
    assert len(canonical(evidence).encode()) <= EVIDENCE_BYTE_CAP


def _crowded_conflict(subject, facet, original_place, conflicting_place, suffix,
                      fact_id, conflict_key):
    """A strong distinct pair versus three lower-coverage distractors."""
    first = f"{subject} {facet} is {original_place}. " + suffix
    second = f"{subject} {facet} is not {original_place}; it is {conflicting_place}. " + suffix
    fact = _fact(fact_id, first, revision=4)
    conflict = _doc(conflict_key, second)
    conflict["content_sha256"] = hashlib.sha256(second.encode()).hexdigest()
    docs = [
        _doc("copy", first),
        conflict,
        _doc("admin", f"{subject} procurement contract tender vendor invoice accounting budget payment expense purchase approval receipt financial audit."),
        _doc("training", f"{subject} classroom demonstration student lesson curriculum educator handbook exam instruction workshop attendance certificate."),
        _doc("weather", f"{subject} seasonal rainfall thunderstorm temperature cloud humidity wind forecast lightning precipitation climate records."),
    ]
    return [fact], docs, f"{subject} {facet}", conflict


_SURVEY_SUFFIX = (
    "Annual field survey certified instrument inspection maintenance equipment "
    "inventory operation calibration battery casing signal frequency antenna mounting "
    "access safety checklist report."
)


@pytest.mark.parametrize("subject,facet,first,second,suffix,fact_id,conflict_key", [
    ("Zircon beacon", "location", "Cedar Pier", "Basalt Point",
     _SURVEY_SUFFIX, "fact_A", "conflict"),
    ("Amber sextant", "storage", "West Atrium", "North Gallery",
     (_SURVEY_SUFFIX + " ") * 7, "z_current", "z_alt_survey"),
], ids=["independent-counterexample", "held-out-long-conflict"])
def test_diversity_preserves_high_relevance_conflict_under_competition(
    subject, facet, first, second, suffix, fact_id, conflict_key
):
    facts, docs, query, conflict = _crowded_conflict(
        subject, facet, first, second, suffix, fact_id, conflict_key
    )
    before = canonical(facts) + canonical(docs)
    result = _context(facts, docs, query)
    evidence = result["evidence"]
    assert len(evidence) == 4
    assert [row["source_id"] for row in evidence[:2]] == [fact_id, conflict["source_id"]]
    assert evidence[0]["revision"] == 4
    assert evidence[0]["highlights"][0]["text"] == facts[0]["statement"]
    assert evidence[0]["source_sha256"] == hashlib.sha256(facts[0]["statement"].encode()).hexdigest()
    assert evidence[1]["revision"] == 1
    assert evidence[1]["chunk_id"] == conflict["chunk_id"]
    assert evidence[1]["highlights"][0]["text"] == conflict["text"]
    assert evidence[1]["source_sha256"] == conflict["content_sha256"]
    assert evidence[1]["trust"] == "untrusted_document"
    assert evidence[0]["score"] == evidence[1]["score"] == 1.0
    assert "doc_copy" not in {row["source_id"] for row in evidence}
    assert len(canonical(evidence).encode()) <= EVIDENCE_BYTE_CAP
    assert _context(facts, list(reversed(docs)), query) == result
    assert canonical(facts) + canonical(docs) == before


@pytest.mark.parametrize("position", ["before-first", "before-second"])
def test_unfittable_high_ranked_item_does_not_consume_relevance_slot(position):
    facts, docs, query, conflict = _crowded_conflict(
        "Zircon beacon", "location", "Cedar Pier", "Basalt Point",
        _SURVEY_SUFFIX, "fact_A", "conflict"
    )
    # Force a genuine fit failure even after excerpting: oversized synthetic
    # identity/metadata, rather than data that the normal excerpt can shrink.
    impossible_text = "Zircon beacon location is Quartz Gate."
    if position == "before-first":
        impossible_id = "0_" + "x" * (EVIDENCE_BYTE_CAP + 1)
        facts.insert(0, _fact(impossible_id, impossible_text))
    else:
        impossible = _doc("00_unfittable", impossible_text)
        impossible["filename"] = "x" * (EVIDENCE_BYTE_CAP + 1)
        docs.insert(0, impossible)
        impossible_id = impossible["source_id"]
    evidence = _context(facts, docs, query)["evidence"]
    assert len(evidence) == 4
    assert [row["source_id"] for row in evidence[:2]] == ["fact_A", conflict["source_id"]]
    assert impossible_id not in {row["source_id"] for row in evidence}
    assert len(canonical(evidence).encode()) <= EVIDENCE_BYTE_CAP
