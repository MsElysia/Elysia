"""Finite local-chat vocabulary; no model, provider, or operational data.

Adapted from #190/#204, with literal search isolation and real import/reopen.
"""
from __future__ import annotations

import hashlib
from unittest.mock import patch

import pytest

from project_guardian.document_ingestion import DocumentLibrary
from project_guardian.local_memory_chat import (
    EVIDENCE_BYTE_CAP, EVIDENCE_ITEM_CAP, _context_tokens,
    build_context_from_adapter, canonical,
)
from tests.test_retrieval_evidence_ranking import _context, _doc, _fact


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_bundle(bundle):
    assert len(bundle["evidence"]) <= EVIDENCE_ITEM_CAP
    assert len(canonical(bundle["evidence"]).encode("utf-8")) <= EVIDENCE_BYTE_CAP
    payload = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    assert bundle["bundle_sha256"] == _sha(canonical(payload))
    assert bundle["evidence_trust"] == "untrusted_data"


@pytest.mark.parametrize("query_word,stored_word", [
    ("costs", "pricing"), ("keeping", "stored"), ("photographs", "picture"),
    ("fixed", "repair"), ("buying", "purchased"), ("vaults", "vault"),
])
def test_held_out_variants_rank_corrected_fact_before_generic_records(query_word, stored_word):
    question = f"Opaline mosaic {query_word}"
    text = f"Opaline mosaic {stored_word}: record at Cedar Pier."
    target = _fact("z_target", text, revision=4)
    distractors = [
        _fact(f"a_{i}", f"Opaline mosaic generic catalog record {i}.")
        for i in range(8)
    ]
    facts = distractors + [target]
    before = canonical(facts)
    bundle = _context(facts, [], question)
    hit = bundle["evidence"][0]
    assert hit["source_id"] == hit["chunk_id"] == "z_target"
    assert hit["revision"] == 4
    assert hit["source_sha256"] == _sha(text)
    assert hit["highlights"][0]["text"] == text
    assert canonical(facts) == before
    assert _context(list(reversed(facts)), [], question) == bundle
    _assert_bundle(bundle)


@pytest.mark.parametrize("question,text", [
    ("photographs", "A picture hangs here."),
    ("buying", "Bought yesterday."),
    ("kept", "Stored securely."),
    ("fixes", "Repair completed."),
    ("prices vaults", "Cost vault inspection."),
])
def test_alias_only_overlap_meets_existing_relevance_threshold(question, text):
    # Each source shares no raw lexical word with the question.
    bundle = _context([_fact("target", text, revision=4)], [], question)
    assert len(bundle["evidence"]) == 1
    hit = bundle["evidence"][0]
    assert hit["source_id"] == "target" and hit["revision"] == 4
    assert hit["source_sha256"] == _sha(text)
    assert hit["highlights"][0]["text"] == text
    _assert_bundle(bundle)


@pytest.mark.parametrize("source_kind", ["fact", "document"])
def test_oversized_tail_uses_original_unicode_window_and_aliases(source_kind):
    text = "Straße routine " * 1200 + "A photograph waits at Cedar Pier."
    document = _doc("tail", text)
    document["content_sha256"] = _sha(text)
    facts = [_fact("tail", text, revision=4)] if source_kind == "fact" else []
    docs = [document] if source_kind == "document" else []
    before = canonical([facts, docs])
    query = "STRASSE pictures"
    bundle = _context(facts, docs, query)
    hit = bundle["evidence"][0]
    highlight = hit["highlights"][0]
    assert highlight["excerpted"] is True
    assert "Cedar Pier" in highlight["text"] and "photograph" in highlight["text"]
    assert highlight["text"].strip("…") in text
    assert hit["source_sha256"] == _sha(text)
    assert highlight["excerpt_sha256"] == _sha(highlight["text"])
    assert highlight["excerpt_sha256"] != hit["source_sha256"]
    assert hit["source_id"] == ("tail" if source_kind == "fact" else "doc_tail")
    assert hit["chunk_id"] == ("tail" if source_kind == "fact" else "chunk_tail")
    assert hit["revision"] == (4 if source_kind == "fact" else 1)
    assert canonical([facts, docs]) == before
    assert _context(facts, docs, query) == bundle
    _assert_bundle(bundle)


@pytest.mark.parametrize("left,right", [
    ("Atlas", "Atla"), ("James", "Jame"), ("east", "west"),
    ("approved", "draft"), ("porch", "deck"), ("stain", "finish"),
    ("doctor", "physician"),
])
def test_distinct_words_and_names_remain_distinct(left, right):
    assert _context_tokens(left) != _context_tokens(right)
    assert _context([_fact("wrong", right)], [], left)["no_memory_support"] is True


@pytest.mark.parametrize("wrong,right", [("Atlas", "Atla"), ("James", "Jame")])
def test_proper_name_not_swallowed_under_distractor_pressure(wrong, right):
    facts = [_fact(f"a_{i}", f"{wrong} ledger is filed in the archive number {i}.")
             for i in range(8)]
    facts.append(_fact("z_target", f"{right} ledger is filed in the archive.", revision=2))
    bundle = _context(facts, [], f"{right} ledger archive")
    assert bundle["evidence"][0]["source_id"] == "z_target"
    assert bundle["evidence"][0]["revision"] == 2


def test_distinct_conflicting_sources_and_diagnostic_exclusion():
    first = _fact("fact_current", "Opaline mosaic cost is 47 credits.", revision=3)
    second = _doc("conflict", "Opaline mosaic price is 80 credits.")
    second["content_sha256"] = _sha(second["text"])
    copy = _doc("copy", first["statement"])
    diagnostic = _doc("diagnostic", "Opaline mosaic cost price pricing 999 credits.")
    diagnostic["collection"] = "diagnostic-logs"
    bundle = _context([first], [second, copy, diagnostic], "Opaline mosaic cost")
    assert [row["source_id"] for row in bundle["evidence"]] == ["fact_current", "doc_conflict"]
    assert bundle["evidence"][1]["trust"] == "untrusted_document"
    assert bundle["evidence"][1]["source_sha256"] == second["content_sha256"]
    assert bundle["evidence"][1]["highlights"][0]["text"] == second["text"]
    _assert_bundle(bundle)
    assert _context([first], [diagnostic, copy, second], "Opaline mosaic cost") == bundle


def test_unrelated_question_is_unsupported():
    assert _context(
        [_fact("unrelated", "Bellford mosaic is kept in a cabinet.")], [],
        "Zyphora weatherstone purchase invoice",
    )["no_memory_support"] is True


def test_completed_imports_normalize_before_six_candidate_cap_not_in_default_search(tmp_path):
    from tests.test_restricted_runtime_adapter import _adapter

    path = tmp_path / "memory.json"
    library = DocumentLibrary(_adapter(path).memory)
    sha_raw = lambda raw: hashlib.sha256(raw).hexdigest()
    # Ensure the target loses the literal search's deterministic ID tie-break.
    target_raw = max(
        (f"Opaline mosaic price was 47 credits. Receipt batch {i}.".encode()
         for i in range(16)), key=sha_raw,
    )
    target_sha = sha_raw(target_raw)
    generic = [
        raw for i in range(64)
        if sha_raw(raw := f"Opaline mosaic generic catalog record {i}.".encode()) < target_sha
    ][:8]
    assert len(generic) == 8
    receipts = [library.import_bytes(f"generic-{i}.txt", raw) for i, raw in enumerate(generic)]
    target = library.import_bytes("target.txt", target_raw)
    assert all(row["status"] == "completed" for row in receipts + [target])
    assert target["source_id"] == "doc_" + target_sha
    adapter = _adapter(path)
    restored = DocumentLibrary(adapter.memory)
    assert len([r for r in restored.receipts() if r["status"] == "completed"]) == 9
    before = path.read_bytes()
    question = "Opaline mosaic cost"
    literal = restored.search(question)
    assert len(literal) == 6
    assert target["source_id"] not in {row["source_id"] for row in literal}
    assert {row["score"] for row in literal} == {2 / 3}
    shortlist = restored.search(question, context_distinct=True)
    assert len(shortlist) == 6
    assert shortlist[0]["source_id"] == target["source_id"]
    with patch("project_guardian.capability_awareness.record_capability_success"):
        bundle = build_context_from_adapter(adapter, question, {})
        assert build_context_from_adapter(adapter, question, {}) == bundle
    hit = bundle["evidence"][0]
    assert hit["source_id"] == target["source_id"]
    assert hit["chunk_id"] == shortlist[0]["chunk_id"]
    assert hit["source_sha256"] == shortlist[0]["content_sha256"] == _sha(target_raw.decode())
    assert hit["revision"] == 1 and hit["trust"] == "untrusted_document"
    assert hit["filename"] == "target.txt" and hit["highlights"][0]["text"] == target_raw.decode()
    _assert_bundle(bundle)
    assert restored.search(question) == literal
    assert path.read_bytes() == before
    for receipt, raw in zip(receipts + [target], generic + [target_raw]):
        assert (restored.root / receipt["managed_copy"]).read_bytes() == raw


def test_real_unicode_chunk_tail_keeps_source_and_excerpt_hashes_after_reopen(tmp_path):
    from tests.test_restricted_runtime_adapter import _adapter

    path = tmp_path / "memory.json"
    # Astral characters take 12 JSON bytes each, forcing a real chunk to fit
    # through an excerpt. The keyword variant appears only at the tail.
    text = "Straße " + "\U0001f9ed" * 1100 + " Straße photograph waits at Cedar Pier."
    raw = text.encode("utf-8")
    receipt = DocumentLibrary(_adapter(path).memory).import_bytes("tail.txt", raw)
    assert receipt["status"] == "completed"
    adapter = _adapter(path)
    restored = DocumentLibrary(adapter.memory)
    before = path.read_bytes()
    query = "STRASSE pictures"
    rows = restored.search(query, context_distinct=True)
    with patch("project_guardian.capability_awareness.record_capability_success"):
        bundle = build_context_from_adapter(adapter, query, {})
        assert build_context_from_adapter(adapter, query, {}) == bundle
    hit = next(row for row in bundle["evidence"] if row["highlights"][0].get("excerpted"))
    source = next(row for row in rows if row["chunk_id"] == hit["chunk_id"])
    highlight = hit["highlights"][0]
    assert "Cedar Pier" in highlight["text"] and "photograph" in highlight["text"]
    assert highlight["text"].strip("…") in source["text"]
    assert hit["source_id"] == receipt["source_id"]
    assert hit["source_sha256"] == source["content_sha256"] == _sha(source["text"])
    assert highlight["excerpt_sha256"] == _sha(highlight["text"])
    assert hit["revision"] == 1 and hit["trust"] == "untrusted_document"
    _assert_bundle(bundle)
    assert path.read_bytes() == before
    assert (restored.root / receipt["managed_copy"]).read_bytes() == raw


def test_restricted_fact_retrieve_stays_literal_while_chat_uses_current_revision(tmp_path):
    from tests.test_restricted_runtime_adapter import _adapter, _auth

    path = tmp_path / "memory.json"
    adapter = _adapter(path)
    route = "/api/restricted/v1/facts"
    saved = adapter.handle("POST", route, headers=_auth(), body={"statement": "The picture hangs at Cedar Pier."})
    assert saved.status == 201
    fid = saved.body["fact"]["fact_id"]
    text = "The picture hangs at Basalt Point."
    corrected = adapter.handle("POST", f"{route}/{fid}/corrections", headers=_auth(), body={"statement": text})
    assert corrected.status == 200
    adapter = _adapter(path)
    before = path.read_bytes()
    direct = adapter.handle("POST", route + "/retrieve", headers=_auth(), body={"query": "photographs"})
    assert direct.status == 200 and direct.body["matches"] == []
    literal = adapter.handle("POST", route + "/retrieve", headers=_auth(), body={"query": "picture"})
    assert literal.status == 200 and literal.body["matches"][0]["revision"] == 2
    with patch("project_guardian.capability_awareness.record_capability_success"):
        bundle = build_context_from_adapter(adapter, "photographs", {})
    hit = bundle["evidence"][0]
    assert hit["source_id"] == fid and hit["revision"] == 2
    assert hit["source_sha256"] == _sha(text)
    assert hit["highlights"][0]["text"] == text
    assert "Cedar Pier" not in canonical(bundle["evidence"])
    _assert_bundle(bundle)
    assert path.read_bytes() == before
