"""Independent examples; evidence selection only, never model-answer scoring."""
import hashlib

import pytest

from tests.test_retrieval_evidence_ranking import _context, _doc, _fact
from project_guardian.local_memory_chat import (
    EVIDENCE_BYTE_CAP, EVIDENCE_ITEM_CAP, _bounded_relevant_excerpt,
    _fit_evidence_item, canonical,
)


def test_tail_excerpt_keeps_answer_and_hash():
    text = "routine " * 1600 + "Zircon beacon location: Cedar Pier."
    doc = _doc("tail", text)
    doc["content_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    before = canonical(doc)
    result = _context([], [doc], "Zircon beacon location")
    hit = result["evidence"][0]
    highlight = hit["highlights"][0]
    excerpt = highlight["text"]
    assert "Cedar Pier" in excerpt
    assert highlight["excerpted"] is True
    assert hit["source_id"] == doc["source_id"]
    assert hit["chunk_id"] == doc["chunk_id"]
    assert hit["revision"] == 1
    assert hit["trust"] == "untrusted_document"
    assert hit["source_sha256"] == doc["content_sha256"]
    assert highlight["excerpt_sha256"] == hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    assert highlight["excerpt_sha256"] != hit["source_sha256"]
    assert canonical(doc) == before


def test_unicode_evidence_and_byte_boundary():
    original = "星空 望远镜 保存在 北塔。" + "背景 " * 6000
    doc = _doc("unicode", original)
    doc["content_sha256"] = hashlib.sha256(original.encode("utf-8")).hexdigest()
    result = _context([], [doc], "星空 望远镜")
    hit = result["evidence"][0]
    highlight = hit["highlights"][0]
    assert "北塔" in highlight["text"]
    assert highlight["excerpted"] is True
    assert hit["source_sha256"] == doc["content_sha256"]
    assert highlight["excerpt_sha256"] == hashlib.sha256(highlight["text"].encode("utf-8")).hexdigest()
    assert len(canonical(result["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP


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


_BOUNDARY_FILLER = " routine material " * 1000


def _boundary_source():
    prefix = "x" * 147 + " unfixed until further notice. "
    return (prefix + _BOUNDARY_FILLER[:930-len(prefix)] +
            " harbor inspection pending. " + _BOUNDARY_FILLER +
            " Harbor fixture fixed at Cedar Pier.")


def _boundary_sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _boundary_item(text, terms=("fixed", "harbor")):
    return {
        "source_id": "fact-test", "chunk_id": "fact-test", "revision": 4,
        "source_sha256": _boundary_sha(text), "matched_tokens": list(terms),
        "score": 1., "highlights": [{"highlight_id": "fact-test:r4", "text": text}],
    }


def test_excerpt_canonical_truncated_unfixed_reproducer():
    excerpt = _bounded_relevant_excerpt(_boundary_source(), {"fixed", "harbor"})
    assert "Harbor fixture fixed at Cedar Pier." in excerpt


@pytest.mark.parametrize("false_term", ["unfixed", "fixedness", "\u0345fixed"])
def test_excerpt_ignores_substring_before_complete_term(false_term):
    text = false_term + " " + _BOUNDARY_FILLER + " fixed at Cedar Pier."
    assert "fixed at Cedar Pier." in _bounded_relevant_excerpt(text, {"fixed"})


def test_excerpt_casefolded_combining_letter_is_not_a_boundary():
    text = "x" * 149 + "\u0345fixed " + _BOUNDARY_FILLER + " fixed at Cedar Pier."
    assert "fixed at Cedar Pier." in _bounded_relevant_excerpt(text, {"fixed"})


def test_excerpt_display_drops_left_clipped_word_even_with_genuine_hit():
    prefix = "x" * 147 + " unfixed until further notice. "
    text = (prefix + _BOUNDARY_FILLER[:930-len(prefix)] +
            " harbor fixed inspection. " + _BOUNDARY_FILLER)
    excerpt = _bounded_relevant_excerpt(text, {"fixed", "harbor"})
    assert "harbor fixed inspection." in excerpt
    assert not excerpt.startswith("…fixed until")
    assert excerpt.strip("…") in text


def test_excerpt_display_drops_right_clipped_word_even_with_genuine_hit():
    prefix = "harbor fixed inspection. "
    text = (prefix + _BOUNDARY_FILLER[:894-len(prefix)] +
            " fixedness pending. " + _BOUNDARY_FILLER)
    excerpt = _bounded_relevant_excerpt(text, {"fixed", "harbor"})
    assert "harbor fixed inspection." in excerpt
    assert not excerpt.endswith("fixed…")
    assert excerpt.strip("…") in text


@pytest.mark.parametrize("word,query", [
    ("Straße", "strasse"), ("İSTANBUL", "stanbul"),
    ("harbor_fixed", "fixed"), ("harbor-fixed", "fixed"),
])
def test_excerpt_casefold_and_delimiters_use_original_text(word, query):
    text = _BOUNDARY_FILLER + " " + word + " at Cedar Pier."
    excerpt = _bounded_relevant_excerpt(text, {query})
    assert word + " at Cedar Pier." in excerpt
    assert excerpt.strip("…") in text


@pytest.mark.parametrize("cap", [900, 600, 400, 240])
def test_excerpt_original_unicode_slice_at_each_fit_size(cap):
    text = "İ Straße " + _BOUNDARY_FILLER + " Straße marker at Cedar Pier."
    excerpt = _bounded_relevant_excerpt(text, {"strasse", "marker"}, max_chars=cap)
    assert "Straße marker at Cedar Pier." in excerpt
    assert excerpt.strip("…") in text
    assert len(excerpt) <= cap + 2
    assert _bounded_relevant_excerpt(text, {"strasse", "marker"}, max_chars=cap) == excerpt


def test_excerpt_oversized_unbroken_word_is_not_fabricated_evidence():
    text = "x" * 14000
    assert _bounded_relevant_excerpt(text, {text}) == ""
    assert _fit_evidence_item([], _boundary_item(text), {text}) is None


def test_excerpt_fit_keeps_original_and_derived_hashes():
    text = _boundary_source()
    item = _boundary_item(text)
    before = canonical(item)
    fitted = _fit_evidence_item([], item, {"fixed", "harbor"})
    highlight = fitted["highlights"][0]
    assert "Harbor fixture fixed at Cedar Pier." in highlight["text"]
    assert fitted["source_sha256"] == _boundary_sha(text)
    assert highlight["excerpt_sha256"] == _boundary_sha(highlight["text"])
    assert fitted["revision"] == 4 and canonical(item) == before
    assert len(canonical([fitted]).encode()) <= EVIDENCE_BYTE_CAP
    assert _fit_evidence_item([], item, {"fixed", "harbor"}) == fitted


def test_excerpt_nonoversized_evidence_unchanged():
    text = "  unfixed at Cedar Pier.  "
    assert _bounded_relevant_excerpt(text, {"fixed"}) == text
    item = _boundary_item(text)
    assert _fit_evidence_item([], item, {"fixed"}) is item


@pytest.mark.parametrize("pad,limit", [
    (0, 900), (8900, 600), (9050, 400), (9200, 240), (9400, 0),
])
def test_excerpt_fit_budget_backoff_preserves_source(pad, limit):
    text = "routine material " * 1200 + " marker at Cedar Pier."
    item = _boundary_item(text, ("marker",))
    selected = [{"padding": "x" * pad}] if pad else []
    before = canonical([selected, item])
    fitted = _fit_evidence_item(selected, item, {"marker"})
    if not limit:
        assert fitted is None
    else:
        highlight = fitted["highlights"][0]
        assert limit - 20 < len(highlight["text"]) <= limit + 2
        assert "marker at Cedar Pier." in highlight["text"]
        assert highlight["text"].strip("…") in text
        assert fitted["source_sha256"] == _boundary_sha(text)
        assert highlight["excerpt_sha256"] == _boundary_sha(highlight["text"])
        assert len(canonical(selected + [fitted]).encode()) <= EVIDENCE_BYTE_CAP
    assert canonical([selected, item]) == before


def test_excerpt_earliest_complete_tie_and_no_complete_match():
    text = "marker at First Pier. " + _BOUNDARY_FILLER + "marker at Last Pier."
    assert "First Pier" in _bounded_relevant_excerpt(text, {"marker"})
    assert _bounded_relevant_excerpt("unfixed " + _BOUNDARY_FILLER, {"fixed"}) == ""


@pytest.mark.parametrize("kind", ["fact", "document"])
def test_context_excerpt_boundary_repair_keeps_source_identity(kind):
    text = _boundary_source()
    doc = _doc("boundary", text)
    doc["content_sha256"] = _boundary_sha(text)
    facts = [_fact("boundary", text, revision=4)] if kind == "fact" else []
    docs = [doc] if kind == "document" else []
    before = canonical([facts, docs])
    bundle = _context(facts, docs, "fixed harbor")
    assert len(bundle["evidence"]) == 1
    hit = bundle["evidence"][0]
    highlight = hit["highlights"][0]
    assert "Harbor fixture fixed at Cedar Pier." in highlight["text"]
    assert highlight["text"].strip("…") in text
    assert highlight["excerpted"] is True
    assert hit["source_sha256"] == _boundary_sha(text)
    assert highlight["excerpt_sha256"] == _boundary_sha(highlight["text"])
    assert hit["revision"] == (4 if kind == "fact" else 1)
    assert hit["source_id"] == ("boundary" if kind == "fact" else "doc_boundary")
    assert hit["chunk_id"] == ("boundary" if kind == "fact" else "chunk_boundary")
    assert len(bundle["evidence"]) <= EVIDENCE_ITEM_CAP
    assert len(canonical(bundle["evidence"]).encode()) <= EVIDENCE_BYTE_CAP
    assert _boundary_sha(canonical({k: v for k, v in bundle.items() if k != "bundle_sha256"})) == bundle["bundle_sha256"]
    assert _context(facts, docs, "fixed harbor") == bundle
    assert canonical([facts, docs]) == before
