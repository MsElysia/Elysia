"""Task017 synthetic regressions: credentials do not authorize memory egress.

No model, external network, real memory directory or provider credentials are used.
"""
from pathlib import Path
from types import SimpleNamespace
import socket

import numpy as np
import pytest

from project_guardian import memory_vector as mv
from project_guardian import memory_vector_search as ms
from project_guardian import memory_noise, startup_runtime_guard

TEXT = "Synthetic Cedar Pier beacon is secured in the amber tower."


@pytest.fixture(autouse=True)
def offline_synthetic_guards(monkeypatch):
    def prohibited(*_args, **_kwargs):
        raise AssertionError("unexpected network attempt")
    monkeypatch.setattr(socket.socket, "connect", prohibited)
    monkeypatch.setattr(socket.socket, "connect_ex", prohibited)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-credential")
    monkeypatch.setattr(memory_noise, "is_embedding_entirely_skipped", lambda _t: False)
    monkeypatch.setattr(memory_noise, "is_low_value_memory_text", lambda *_a, **_k: False)
    monkeypatch.setattr(startup_runtime_guard, "defer_sentence_transformers_for_embed", lambda: False)
    monkeypatch.setattr(startup_runtime_guard, "should_defer_vector_add_during_startup", lambda *_a: False)


def vector(tmp_path):
    return mv.VectorMemory(
        vector_dim=8, index_path=str(tmp_path / "vec" / "index.faiss"),
        metadata_path=str(tmp_path / "vec" / "metadata.json"),
    )


@pytest.mark.parametrize("method", ["generate", "add", "search"])
def test_inherited_openai_key_never_creates_cloud_client(tmp_path, monkeypatch, method):
    attempted = []
    def cloud_client(**_kwargs):
        attempted.append("OpenAI client construction")
        raise AssertionError("cloud embedding client constructed")
    monkeypatch.setattr(mv, "OPENAI_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mv, "openai", SimpleNamespace(OpenAI=cloud_client), raising=False)
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", False)
    v = vector(tmp_path)
    if method == "generate":
        assert v.generate_embedding(TEXT) is None
    elif method == "add":
        # Force the real add path through embedding generation even without FAISS.
        v.index = SimpleNamespace(add=lambda *_a: (_ for _ in ()).throw(
            AssertionError("untrusted vector must not be indexed")))
        assert v.add_memory(TEXT, priority=0.9) is None
    else:
        v.index = SimpleNamespace(search=lambda *_args: (_ for _ in ()).throw(
            AssertionError("query must not use a pseudo embedding")))
        v.metadata = [{"text": TEXT}]
        assert v.search(TEXT) == []
    assert attempted == []


@pytest.mark.parametrize("fault", ["cache_missing", "outdated_loader", "encode_error", "nonfinite"])
def test_local_embedder_fails_closed_without_hash_or_download(tmp_path, monkeypatch, fault):
    loads = []
    def local_loader(_model, **options):
        loads.append(options)
        if fault == "cache_missing":
            raise OSError("synthetic empty local model cache")
        if fault == "outdated_loader":
            raise TypeError("synthetic loader does not support offline-only arguments")
        def encode(_text):
            if fault == "encode_error":
                raise RuntimeError("synthetic encode failure")
            return np.full(8, np.nan, dtype=np.float32)
        return SimpleNamespace(encode=encode)
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(mv, "SentenceTransformer", local_loader, raising=False)
    v = vector(tmp_path)
    assert v.generate_embedding(TEXT) is None
    assert loads == [{"local_files_only": True, "trust_remote_code": False}]
    assert v.get_stats()["embedding_status"]["available"] is False
    assert v.add_memory(TEXT) is None


def test_cached_local_embedder_uses_offline_loader_only(tmp_path, monkeypatch):
    loads = []
    def local_loader(_model, **options):
        loads.append(options)
        return SimpleNamespace(encode=lambda _text: np.arange(8, dtype=np.float32))
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(mv, "SentenceTransformer", local_loader, raising=False)
    v = vector(tmp_path)
    assert np.array_equal(v.generate_embedding(TEXT), np.arange(8, dtype=np.float32))
    assert loads == [{"local_files_only": True, "trust_remote_code": False}]
    assert v.get_stats()["embedding_status"]["provider"] == "sentence_transformers"


def test_missing_embedding_preserves_existing_vector_files_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "FAISS_AVAILABLE", False)
    v = vector(tmp_path)
    v.index = SimpleNamespace(ntotal=1)
    v.metadata = [{"id": 0, "text": "Previously indexed synthetic fact"}]
    index_file, meta_file = Path(v.index_path), Path(v.metadata_path)
    index_file.write_bytes(b"synthetic retained index witness")
    meta_file.write_bytes(b'[{"id":0,"text":"Previously indexed synthetic fact"}]')
    snapshots = (index_file.read_bytes(), meta_file.read_bytes())

    class FakeIndex:
        ntotal = 0
        def add(self, _arr):
            self.ntotal += 1
    fake_faiss = SimpleNamespace(
        IndexFlatL2=lambda _dim: FakeIndex(),
        write_index=lambda _idx, path: Path(path).write_bytes(b"WRONG REBUILD"),
    )
    monkeypatch.setattr(mv, "FAISS_AVAILABLE", True)
    monkeypatch.setattr(mv, "faiss", fake_faiss, raising=False)
    monkeypatch.setattr(v, "generate_embedding", lambda _text: None)
    result = v.rebuild_from_memories([{"thought": TEXT}])
    assert result["vector_rebuild_status"] == "failed"
    assert result["vector_rebuild_success"] is False
    assert v.degraded and v.rebuild_pending
    assert v.metadata == [{"id": 0, "text": "Previously indexed synthetic fact"}]
    assert (index_file.read_bytes(), meta_file.read_bytes()) == snapshots


def test_uncached_optional_memorycore_loader_is_never_online(monkeypatch):
    loads = []
    def local_loader(_model, **options):
        loads.append(options)
        raise OSError("synthetic model not cached")
    monkeypatch.setattr(ms, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(ms, "SentenceTransformer", local_loader, raising=False)
    monkeypatch.setattr(ms, "_ST_SHARED", None)
    search = ms.MemoryVectorSearch(use_faiss=False)
    assert loads == [{"local_files_only": True, "trust_remote_code": False}]
    assert search.get_statistics()["embedding_degraded"] is True
    search.add_memory("synthetic-id", TEXT)
    assert search.search_similar(TEXT) == []  # Must not masquerade as semantic search.


def test_authoritative_json_keyword_search_survives_embedding_outage(tmp_path, monkeypatch):
    from project_guardian.memory_vector import EnhancedMemoryCore
    memory = EnhancedMemoryCore(json_filepath=str(tmp_path / "primary.json"), enable_vector=False)
    memory.remember(TEXT, category="synthetic")
    assert [row["thought"] for row in memory.search_memories("Cedar Pier")] == [TEXT]
    class MissingVector:
        embedding_status = {"available": False, "provider": None, "reason": "local_model_unavailable"}
        def load_if_needed(self):
            return None
        def search(self, *_args, **_kwargs):
            return []
    memory.vector_memory = MissingVector()
    assert [row["thought"] for row in memory.search_memories("Cedar Pier", use_semantic=True)] == [TEXT]
    assert Path(memory.json_memory.filepath).exists()


def test_memorycore_semantic_route_falls_back_to_authoritative_keyword(tmp_path):
    from project_guardian.memory import MemoryCore
    memory = MemoryCore(str(tmp_path / "primary.json"))
    memory.remember(TEXT, category="synthetic")
    class Degraded:
        embedding_degraded = True
        def search_similar(self, *_args, **_kwargs):
            raise AssertionError("degraded vectors must not be queried")
    memory.vector_search = Degraded()
    memory._vector_index_built = False
    rows = memory.search_semantic("Cedar Pier")
    assert [row["thought"] for row in rows] == [TEXT]
    assert all(row.get("search_method") != "semantic" for row in rows)


def test_missing_policy_does_not_fall_back_to_untrusted_embedding(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    attempted = []
    monkeypatch.setattr(mv, "SentenceTransformer", lambda *_a, **_k: attempted.append(1),
                        raising=False)
    def missing_guard():
        raise RuntimeError("synthetic local policy unavailable")
    monkeypatch.setattr(startup_runtime_guard, "defer_sentence_transformers_for_embed", missing_guard)
    assert vector(tmp_path).generate_embedding(TEXT) is None
    assert attempted == []
