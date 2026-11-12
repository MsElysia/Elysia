"""Task017 real-FAISS acceptance, synthetic files and deterministic local vectors.

FAISS itself must be the installed native extension, NEVER a stub or a skip.
No SentenceTransformer/model is downloaded or loaded. No provider/network traffic.
Only pytest tmp_path directories are written.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import socket

import faiss
import numpy as np
import pytest

from project_guardian import memory_noise, startup_runtime_guard
from project_guardian import memory_vector as mv


A = "Synthetic Cedar Pier beacon is secured in the amber tower."
B = "Synthetic Birch Dock beacon is secured in the violet tower."
C = "Synthetic Elm Bay beacon is secured in the copper tower."
DIM = 8


@pytest.fixture(autouse=True)
def real_faiss_isolated(monkeypatch):
    def no_network(*_args, **_kwargs):
        raise AssertionError("No network is authorized during real-FAISS acceptance")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-credential")
    monkeypatch.setattr(memory_noise, "is_embedding_entirely_skipped", lambda _text: False)
    monkeypatch.setattr(memory_noise, "is_low_value_memory_text", lambda *_a, **_kw: False)
    monkeypatch.setattr(startup_runtime_guard, "defer_sentence_transformers_for_embed", lambda: False)
    monkeypatch.setattr(
        startup_runtime_guard, "should_defer_vector_add_during_startup",
        lambda *_a, **_kw: False,
    )

    # An in-memory deterministic encoder is not a FAISS mock.
    # It exercises FAISS persistence without an installed/cached model.
    def encode(text):
        if text == A:
            return np.ones(DIM, dtype=np.float32)
        if text == B:
            return np.zeros(DIM, dtype=np.float32)
        return np.full(DIM, 0.5, dtype=np.float32)

    monkeypatch.setattr(mv, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(
        mv, "SentenceTransformer",
        lambda _name, **options: _require_offline_encoder(options, encode),
    )

    # If FAISS import or binding fails, this test MUST fail, not skip/degrade.
    assert mv.FAISS_AVAILABLE is True
    assert mv.faiss is faiss
    assert callable(faiss.serialize_index) and callable(faiss.deserialize_index)
    assert callable(faiss.clone_index) and callable(faiss.write_index)


def _require_offline_encoder(options, encode):
    assert options == {"local_files_only": True, "trust_remote_code": False}
    return SimpleNamespace(encode=encode)


def _store(tmp_path, *, lazy=False):
    return mv.VectorMemory(
        vector_dim=DIM,
        index_path=str(tmp_path / "vec" / "index.faiss"),
        metadata_path=str(tmp_path / "vec" / "metadata.json"),
        lazy=lazy,
    )


def _pair_paths(store):
    return (
        Path(store.index_path),
        Path(store.metadata_path),
        Path(store.generation_path),
    )


def _pair_bytes(store):
    return tuple(p.read_bytes() for p in _pair_paths(store))


def test_native_faiss_serialization_deserialization_is_real():
    index = faiss.IndexFlatL2(DIM)
    vectors = np.vstack((
        np.ones(DIM, dtype=np.float32),
        np.zeros(DIM, dtype=np.float32),
    ))
    index.add(vectors)
    binary = faiss.serialize_index(index)
    decoded = faiss.deserialize_index(np.asarray(binary, dtype=np.uint8).copy())
    distances, positions = decoded.search(vectors[:1], 2)
    assert decoded.ntotal == 2 and decoded.d == DIM
    assert positions[0].tolist() == [0, 1]
    assert float(distances[0, 0]) == 0.0
    assert float(distances[0, 1]) == float(DIM)


@pytest.mark.parametrize("lazy", [False, True])
def test_real_faiss_sealed_generation_survives_restart_and_recalls_exact_fact(tmp_path, lazy):
    first = _store(tmp_path)
    assert first.add_memory(A, category="synthetic") == 0
    index_path, metadata_path, manifest_path = _pair_paths(first)
    assert faiss.read_index(str(index_path)).ntotal == 1
    assert faiss.read_index(str(index_path)).d == DIM
    receipt = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == mv.VectorMemory._SCHEMA
    assert receipt["provider"] == "sentence_transformers"
    assert receipt["model"] == "all-MiniLM-L6-v2"
    assert receipt["index_sha256"] == hashlib.sha256(index_path.read_bytes()).hexdigest()
    assert receipt["metadata_sha256"] == hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    assert len(receipt["generation"]) == 32

    loaded = _store(tmp_path, lazy=lazy)
    if lazy:
        assert loaded.loaded is False
        loaded.load_if_needed()
    assert loaded.vector_pair_verified is True
    assert loaded.index.ntotal == len(loaded.metadata) == 1
    assert [row["text"] for row in loaded.search(A, threshold=0.9)] == [A]
    assert loaded.search(B, threshold=0.9) == []
    assert loaded.embedding_status["provider"] == "sentence_transformers"
    assert _pair_bytes(loaded) == _pair_bytes(first)


def test_real_faiss_stale_writer_cannot_replace_newer_complete_generation(tmp_path):
    writer = _store(tmp_path)
    assert writer.add_memory(A) == 0
    stale = _store(tmp_path)
    assert writer.add_memory(B) == 1
    saved = _pair_bytes(writer)
    assert stale.add_memory(C) is None
    assert stale.rebuild_from_memories([{"thought": C}])["vector_rebuild_success"] is False
    assert _pair_bytes(writer) == saved
    assert stale.vector_pair_verified is False

    fresh = _store(tmp_path)
    assert fresh.vector_pair_verified is True
    assert [row["text"] for row in fresh.search(A, threshold=0.9)] == [A]
    assert [row["text"] for row in fresh.search(B, threshold=0.9)] == [B]
    assert fresh.search(C, threshold=0.9) == []
    assert [row["text"] for row in fresh.metadata] == [A, B]


def test_real_faiss_second_staging_failure_keeps_old_bytes_and_restart(tmp_path, monkeypatch):
    first = _store(tmp_path)
    assert first.add_memory(A) == 0
    old_bytes = _pair_bytes(first)

    def refuse_stage(_path, _index):
        raise OSError("synthetic disk fault during second staged-file write")

    monkeypatch.setattr(first, "_atomic_write_faiss", refuse_stage)
    result = first.rebuild_from_memories([{"thought": B}])
    assert result["vector_rebuild_success"] is False
    assert result["vector_rebuild_status"] == "failed"
    assert first.degraded and first.rebuild_pending
    assert _pair_bytes(first) == old_bytes

    restored = _store(tmp_path)
    assert restored.vector_pair_verified is True
    assert [row["text"] for row in restored.search(A, threshold=0.9)] == [A]
    assert restored.search(B, threshold=0.9) == []


def test_real_faiss_interrupted_second_publish_quarantines_original_index(tmp_path, monkeypatch):
    first = _store(tmp_path)
    assert first.add_memory(A) == 0
    before_index = Path(first.index_path).read_bytes()
    replace = mv.os.replace

    def interrupt_second_publish(source, destination):
        if (str(destination) == first.index_path and str(source).endswith(".pending")):
            raise OSError("synthetic interruption at index publish")
        return replace(source, destination)

    monkeypatch.setattr(mv.os, "replace", interrupt_second_publish)
    result = first.rebuild_from_memories([{"thought": B}])
    assert result["vector_rebuild_success"] is False
    assert first.vector_pair_verified is False
    monkeypatch.setattr(mv.os, "replace", replace)
    after_fault = _pair_bytes(first)
    assert after_fault[0] == before_index  # Old actual native FAISS bytes survive.

    reopened = _store(tmp_path)
    assert reopened.vector_pair_verified is False
    assert reopened.degraded and reopened.rebuild_pending
    assert reopened.search(A) == []
    assert reopened.search(B) == []
    assert _pair_bytes(reopened) == after_fault  # No automatic rewrite/rebuild.


def test_real_faiss_legacy_index_without_provenance_is_preserved(tmp_path):
    path = tmp_path / "vec"
    path.mkdir(parents=True)
    index = faiss.IndexFlatL2(DIM)
    index.add(np.ones((1, DIM), dtype=np.float32))
    index_path = path / "index.faiss"
    metadata_path = path / "metadata.json"
    faiss.write_index(index, str(index_path))
    metadata_path.write_text(json.dumps([{"id": 0, "text": A}]), encoding="utf-8")
    original_index = index_path.read_bytes()
    original_meta = metadata_path.read_bytes()

    legacy = _store(tmp_path)
    assert legacy.vector_pair_verified is False
    assert legacy.search(A) == []
    assert legacy.add_memory(B) is None
    assert index_path.read_bytes() == original_index
    assert metadata_path.read_bytes() == original_meta
    assert not Path(legacy.generation_path).exists()
    assert faiss.read_index(str(index_path)).ntotal == 1  # Still recoverable externally.
