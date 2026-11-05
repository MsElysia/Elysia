"""Synthetic provider sentinels: never contact a service or download a model."""
from types import SimpleNamespace
import socket

import numpy as np
import pytest

from project_guardian import memory_vector as mv
from project_guardian import memory_noise, startup_runtime_guard, openai_degraded


TEXT = "Synthetic lighthouse survey equipment is stored inside Cedar Pier vault."


def test_optional_memorycore_vector_search_loader_is_offline_and_reports_fallback(monkeypatch):
    from project_guardian import memory_vector_search as search

    calls = []

    def missing_model(model, **options):
        calls.append(options)
        raise OSError("synthetic empty model cache")

    monkeypatch.setattr(search, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(search, "SentenceTransformer", missing_model)
    monkeypatch.setattr(search, "_ST_SHARED", None)
    vector_search = search.MemoryVectorSearch(use_faiss=False)
    assert calls == [{"local_files_only": True, "trust_remote_code": False}]
    stats = vector_search.get_statistics()
    assert stats["using_sentence_transformers"] is False
    assert stats["embedding_degraded"] is True


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("test attempted real network access")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-real-credential")
    monkeypatch.setattr(memory_noise, "is_embedding_entirely_skipped", lambda text: False)
    monkeypatch.setattr(memory_noise, "is_low_value_memory_text", lambda *a, **k: False)
    monkeypatch.setattr(startup_runtime_guard, "defer_sentence_transformers_for_embed", lambda: False)
    monkeypatch.setattr(startup_runtime_guard, "should_defer_vector_add_during_startup", lambda *a: False)
    monkeypatch.setattr(openai_degraded, "skip_openai_embeddings", lambda: False)


def vector(tmp_path):
    return mv.VectorMemory(vector_dim=8, index_path=str(tmp_path / "v/index.faiss"),
                           metadata_path=str(tmp_path / "v/metadata.json"))


@pytest.mark.parametrize("legacy_index", [False, True])
def test_default_search_recalls_primary_memory_offline_after_restart(tmp_path, monkeypatch, legacy_index):
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", False)
    config = {
        "vector_dim": 8,
        "index_path": str(tmp_path / "v/index.faiss"),
        "metadata_path": str(tmp_path / "v/metadata.json"),
    }
    primary = tmp_path / "primary.json"
    engine = mv.EnhancedMemoryCore(json_filepath=str(primary), vector_config=config)
    engine.remember(TEXT, category="fact", priority=0.9)
    if legacy_index:
        engine.vector_memory.add_memory("Vector-only stale entry", embedding=np.ones(8, dtype=np.float32))
        (tmp_path / "v/metadata.json.generation.json").unlink()

    restarted = mv.EnhancedMemoryCore(json_filepath=str(primary), vector_config=config)
    assert restarted.semantic_search(TEXT) == []
    assert [row["thought"] for row in restarted.search_memories(TEXT)] == [TEXT]
    assert restarted.search_memories("Vector-only stale entry") == []


@pytest.mark.parametrize("operation", ["generate", "add", "rebuild", "search"])
def test_environment_key_cannot_authorize_cloud_embedding(tmp_path, monkeypatch, operation):
    attempts = []
    def create(**kwargs):
        attempts.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * 8)])
    monkeypatch.setattr(mv, "OPENAI_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mv, "openai", SimpleNamespace(OpenAI=lambda **k:
                       SimpleNamespace(embeddings=SimpleNamespace(create=create))), raising=False)
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", False)
    v = vector(tmp_path)
    if operation == "generate":
        v.generate_embedding(TEXT)
    elif operation == "add":
        v.add_memory(TEXT, priority=0.9)
    elif operation == "rebuild":
        v.rebuild_from_memories([{"thought": TEXT}])
    else:
        v.add_memory(TEXT, embedding=np.ones(8, dtype=np.float32))
        v.search(TEXT)
    assert attempts == [], "environment key triggered an unauthorized outbound embedding request"


def test_local_loader_never_allows_implicit_download(tmp_path, monkeypatch):
    attempts = []
    def loader(*args, **kwargs):
        if kwargs.get("local_files_only") is not True or kwargs.get("trust_remote_code") is not False:
            attempts.append((args, kwargs))
        raise OSError("synthetic model absent from local cache")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(mv, "SentenceTransformer", loader, raising=False)
    result = vector(tmp_path).generate_embedding(TEXT)
    assert attempts == [], "local fallback attempted a potentially downloading model load"
    assert result is None, "unavailable model must not be replaced by successful-looking hash vectors"


@pytest.mark.parametrize("failure", ["missing_dependency", "missing_model", "encode", "legacy_loader", "nonfinite"])
def test_local_failure_is_unavailable_not_success(tmp_path, monkeypatch, failure):
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", failure != "missing_dependency")
    def loader(*args, **kwargs):
        if failure == "missing_model":
            raise OSError("synthetic missing cache")
        if failure == "legacy_loader":
            raise TypeError("synthetic old loader lacks local_files_only support")
        def encode(text):
            if failure == "encode":
                raise RuntimeError("synthetic local encode failure")
            return np.full(8, np.nan, dtype=np.float32)
        return SimpleNamespace(encode=encode)
    monkeypatch.setattr(mv, "SentenceTransformer", loader, raising=False)
    v = vector(tmp_path)
    assert v.generate_embedding(TEXT) is None
    assert v.get_stats()["embedding_status"]["available"] is False
    assert v.add_memory(TEXT, priority=0.9) is None
    assert v.index.ntotal == 0


def test_cached_local_model_success_and_no_cloud_fallback(tmp_path, monkeypatch):
    loads = []
    def loader(*args, **kwargs):
        loads.append(kwargs)
        return SimpleNamespace(encode=lambda text: np.arange(8, dtype=np.float32))
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(mv, "SentenceTransformer", loader, raising=False)
    v = vector(tmp_path)
    assert np.array_equal(v.generate_embedding(TEXT), np.arange(8, dtype=np.float32))
    assert loads == [{"local_files_only": True, "trust_remote_code": False}]
    assert v.get_stats()["embedding_status"] == {
        "available": True, "provider": "sentence_transformers", "reason": "local_model_ready"}


def test_missing_embedding_cannot_certify_partial_rebuild(tmp_path, monkeypatch):
    v = vector(tmp_path)
    v.add_memory(TEXT, embedding=np.ones(8, dtype=np.float32))
    paths = [v.index_path, v.metadata_path, v.generation_path]
    from pathlib import Path
    before = [Path(p).read_bytes() for p in paths]
    monkeypatch.setattr(v, "generate_embedding", lambda text: None)
    result = v.rebuild_from_memories([{"thought": TEXT}, {"thought": TEXT + " revised"}])
    assert result["vector_rebuild_success"] is False
    assert result["vector_rebuild_status"] == "failed"
    assert [Path(p).read_bytes() for p in paths] == before
    assert v.degraded and v.rebuild_pending
    assert v.search(TEXT) == []


def test_rebuild_can_skip_intentionally_non_vectorizable_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_noise, "is_embedding_entirely_skipped", lambda text: text == "noise")
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(mv, "SentenceTransformer", lambda *a, **k: SimpleNamespace(
        encode=lambda text: np.ones(8, dtype=np.float32)), raising=False)
    v = vector(tmp_path)
    result = v.rebuild_from_memories([{"thought": "noise"}, {"thought": TEXT}])
    assert result["vector_rebuild_success"] is True
    assert [row["text"] for row in v.metadata] == [TEXT]


@pytest.mark.parametrize("gate", ["non_vectorizable", "deferred", "policy_error"])
def test_local_guards_cannot_be_bypassed_by_hash_or_model_fallback(tmp_path, monkeypatch, gate):
    monkeypatch.delenv("OPENAI_API_KEY")
    attempted = []
    def loader(*a, **k):
        attempted.append(True)
        return SimpleNamespace(encode=lambda text: np.ones(8, dtype=np.float32))
    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(mv, "SentenceTransformer", loader, raising=False)
    if gate == "non_vectorizable":
        monkeypatch.setattr(memory_noise, "is_embedding_entirely_skipped", lambda text: True)
    elif gate == "deferred":
        monkeypatch.setattr(startup_runtime_guard, "defer_sentence_transformers_for_embed", lambda: True)
    else:
        def unavailable():
            raise RuntimeError("synthetic unavailable local policy")
        monkeypatch.setattr(startup_runtime_guard, "defer_sentence_transformers_for_embed", unavailable)
    v = vector(tmp_path)
    assert v.generate_embedding(TEXT) is None
    assert attempted == []
    assert v.get_stats()["embedding_status"]["available"] is False
