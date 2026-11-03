"""Focused local vocabulary retrieval: paraphrase recall without unsafe conflation.

No cloud, model downloads, personal memory or network. Exact citation IDs and
current-revision semantics are inherited from the existing context builder.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from project_guardian.document_ingestion import DocumentLibrary
from project_guardian.local_memory_chat import _context_tokens, build_context_from_adapter
from project_guardian.memory import MemoryCore


NAMES = ("Bellford", "Veridia", "Torvyn", "Lanternia", "Ombera")
CONCEPTS = (
    ("cost", "price", "What was the {name} mosaic cost?",
     "The {name} mosaic price was 47 credits."),
    ("kept", "stored", "Where is the {name} mosaic kept?",
     "The {name} mosaic is stored inside the south atrium."),
    ("photo", "picture", "Where is the {name} mosaic photo?",
     "The {name} mosaic picture hangs in the north hall."),
    ("repair", "fix", "What repair was done to the {name} mosaic?",
     "A fix of the {name} mosaic was completed in June."),
    ("purchased", "bought", "When was the {name} mosaic purchased?",
     "The {name} mosaic was bought in June."),
    ("vaults", "vault", "Which {name} mosaic vaults are secured?",
     "The {name} mosaic vault is secured in the west wing."),
)


def _fact(fid, statement):
    return {"fact_id": fid, "revision": 2 if fid == "fact_target" else 1,
            "statement": statement}


def _query(facts, text, memory=None):
    adapter = SimpleNamespace(
        current_fact_snapshots=lambda: facts,
        store_identity=lambda: {"module": "synthetic", "filepath": None},
    )
    if memory is not None:
        adapter.memory = memory
    with patch("project_guardian.capability_awareness.record_capability_success"):
        return build_context_from_adapter(adapter, text, {})


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("query_word,stored_word,query,statement", CONCEPTS)
def test_paraphrase_returns_corrected_specific_memory_not_generic_distractors(
    name, query_word, stored_word, query, statement
):
    target = _fact("fact_target", statement.format(name=name))
    distractors = [
        _fact(f"fact_00{i}", f"The {name} mosaic has a general visitor record number {i}.")
        for i in range(5)
    ]
    # The vault case deliberately includes a shared adjective to make direct
    # lexical matching tie, so only plural normalization distinguishes it.
    if query_word == "vaults":
        distractors = [
            _fact(f"fact_00{i}", f"The {name} mosaic is secured under catalog entry {i}.")
            for i in range(5)
        ]
    result = _query(distractors + [target], query.format(name=name))
    ids = [e["source_id"] for e in result["evidence"]]
    assert "fact_target" in ids
    assert ids[0] == "fact_target"
    assert result["evidence"][0]["revision"] == 2
    assert result["evidence"][0]["source_sha256"] == hashlib.sha256(
        target["statement"].encode("utf-8")
    ).hexdigest()
    assert stored_word in result["evidence"][0]["highlights"][0]["text"].casefold()
    assert len(ids) <= 4


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("left,right", [
    ("porch", "deck"), ("stain", "finish"),
    ("approved", "draft"), ("east", "west"),
])
def test_ambiguous_or_opposite_words_never_become_equivalent(name, left, right):
    assert set(_context_tokens(f"{name} {left}")) != set(_context_tokens(f"{name} {right}"))
    assert left not in _context_tokens(right)
    assert right not in _context_tokens(left)


def test_document_search_uses_same_safe_variants_before_top_six(tmp_path: Path):
    path = tmp_path / "synthetic_memory.json"
    memory = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    # Nine completed document receipts, built with synthetic records and real
    # durable local storage. Generic documents sort ahead of the target by ID.
    for i in range(8):
        source_id = f"doc_{i:03d}"
        meta = {"source_id": source_id, "status": "completed"}
        memory.remember("Synthetic document indexed", category="document_source",
                        priority=0.9, metadata=meta)
        body = f"The Bellford mosaic has general visitor records number {i}."
        row = {"source_id": source_id, "chunk_id": f"chunk_{i:03d}",
               "filename": f"generic_{i}.txt", "page": 1,
               "content_sha256": hashlib.sha256(body.encode()).hexdigest()}
        memory.remember(body, category="document_chunk", priority=0.9, metadata=row)
    source_id = "doc_zzz"
    memory.remember("Synthetic document indexed", category="document_source",
                    priority=0.9, metadata={"source_id": source_id, "status": "completed"})
    body = "The Bellford mosaic price was 47 credits."
    memory.remember(body, category="document_chunk", priority=0.9,
                    metadata={"source_id": source_id, "chunk_id": "chunk_zzz",
                              "filename": "target.txt", "page": 1,
                              "content_sha256": hashlib.sha256(body.encode()).hexdigest()})

    restored = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    library = DocumentLibrary(restored)
    matches = library.search("What is the Bellford mosaic cost?")
    assert matches and matches[0]["source_id"] == source_id
    bundle = _query([], "What is the Bellford mosaic cost?", restored)
    assert bundle["evidence"][0]["source_id"] == source_id
    assert bundle["evidence"][0]["trust"] == "untrusted_document"
    assert bundle["evidence"][0]["filename"] == "target.txt"


def test_unrelated_facts_remain_absent_and_no_cloud_used():
    out = _query(
        [_fact("fact_unrelated", "The fictional Bellford mosaic is kept in a cabinet.")],
        "Where is the Zyphora weatherstone purchase invoice?"
    )
    assert out["evidence"] == []
    assert out["no_memory_support"] is True
