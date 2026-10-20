"""Optional NumPy must not prevent importing or using lightweight local memory.

These regressions require no network, cloud model, memory store, or paid provider.
"""
from pathlib import Path

import project_guardian.memory_vector_search as vector_search


def test_hash_embedding_without_numpy(monkeypatch):
    monkeypatch.setattr(vector_search, "HAS_NUMPY", False)
    embedder = vector_search.SimpleEmbedder()
    assert isinstance(embedder.embed("synthetic text", dimension=24), list)
    assert len(embedder.embed("synthetic text", dimension=24)) == 24


def test_idf_vocab_build_does_not_need_numpy(monkeypatch):
    monkeypatch.setattr(vector_search, "HAS_NUMPY", False)
    embedder = vector_search.SimpleEmbedder()
    embedder._build_vocab(["synthetic memory", "synthetic history"])
    assert "synthetic" in embedder.idf
    assert isinstance(embedder.idf["synthetic"], float)


def test_in_memory_search_without_numpy(monkeypatch):
    monkeypatch.setattr(vector_search, "HAS_NUMPY", False)
    index = vector_search.MemoryVectorSearch(use_faiss=False)
    index.add_memory("fiction-1", "blue synthetic library artifact")
    index.add_memory("fiction-2", "green fabricated reference sample")
    matches = index.search_similar("synthetic blue", limit=2, threshold=0.5)
    assert matches
    assert matches[0][0] == "fiction-1"
