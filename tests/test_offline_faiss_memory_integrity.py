"""Offline, REAL FAISS cleanup and restart checks for Elysia.

Use actual FAISS IndexFlatL2 and real temporary index/metadata files,
deterministic local NumPy embeddings, and synthetic JSON MemoryCore history.
Network connections are forbidden. No personal data or model downloads.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import faiss
import numpy as np
import pytest

from project_guardian.memory_vector import (
    EnhancedMemoryCore,
    VectorMemory,
    FAISS_AVAILABLE,
)

assert FAISS_AVAILABLE, "Real offline FAISS test must not run with a mock or skip"


RETIRED = "Synthetic retired lighthouse ferry schedule"
CURRENT = "Synthetic current lighthouse ferry schedule"
DIMS = 8


def _embedding(self, text):
    # Non-semantic, deterministic local fixture. No HTTP, model calls or files.
    vec = np.zeros(DIMS, dtype=np.float32)
    vec[0 if "retired" in text else 1] = 1.0
    return vec


@pytest.fixture()
def fixture(tmp_path, monkeypatch):
    # A test must fail rather than accidentally use paid cloud or model downloads.
    for env in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    def deny_network(*args, **kwargs):
        raise AssertionError("offline FAISS verification attempted network access")
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(VectorMemory, "generate_embedding", _embedding)

    primary = tmp_path / "synthetic_memory.json"
    index_path = tmp_path / "faiss" / "index.faiss"
    metadata_path = tmp_path / "faiss" / "metadata.json"
    index_path.parent.mkdir()
    records = [
        {"time": "2021-01-01T08:00:00", "thought": RETIRED,
         "category": "fact", "priority": 0.1, "metadata": {}},
        {"time": "2026-11-03T08:00:00", "thought": CURRENT,
         "category": "fact", "priority": 0.9, "metadata": {}},
    ]
    primary.write_text(json.dumps(records), encoding="utf-8")
    config = {"vector_dim": DIMS, "index_path": str(index_path),
              "metadata_path": str(metadata_path)}
    def new_engine():
        return EnhancedMemoryCore(json_filepath=str(primary),
                                  enable_vector=True, vector_config=config,
                                  lazy_json=False, lazy_vector=False)
    engine = new_engine()
    assert engine.vector_memory is not None
    assert engine.vector_memory.index is not None
    for record in records:
        assert engine.vector_memory.add_memory(
            text=record["thought"], category="fact",
            priority=record["priority"]
        ) is not None
    assert engine.vector_memory.index.ntotal == 2
    assert faiss.read_index(str(index_path)).ntotal == 2
    assert len(json.loads(metadata_path.read_text(encoding="utf-8"))) == 2
    return engine, new_engine, primary, index_path, metadata_path


def _retired_search(engine):
    return engine.semantic_search(RETIRED, limit=10, threshold=0.0)


def test_real_faiss_cleanup_removes_old_row_and_survives_restart(fixture):
    engine, new_engine, primary, index_path, metadata_path = fixture
    result = engine.cleanup_old_memories(days=90, min_priority_to_keep=0.7)
    assert result["action"] == "cleaned"
    assert result["vector_rebuild_status"] == "rebuilt"
    assert result["vector_rebuild_success"] is True
    assert [m["thought"] for m in json.loads(primary.read_text())] == [CURRENT]
    assert engine.vector_memory.index.ntotal == 1
    assert faiss.read_index(str(index_path)).ntotal == 1
    assert [m["text"] for m in json.loads(metadata_path.read_text())] == [CURRENT]
    assert all(m.get("text") != RETIRED for m in _retired_search(engine))
    after = new_engine()
    assert after.vector_memory.index.ntotal == 1
    assert [m["text"] for m in after.vector_memory.metadata] == [CURRENT]
    assert [m["text"] for m in after.semantic_search(CURRENT, threshold=0.0)] == [CURRENT]
    assert all(m["text"] != RETIRED for m in _retired_search(after))


def test_interrupted_index_write_cannot_revalidate_mismatched_files_after_restart(
    fixture, monkeypatch
):
    engine, new_engine, primary, index_path, metadata_path = fixture
    # Metadata replacement succeeds; FAISS replacement fails. Startup must
    # detect the index/metadata row-count mismatch and fail closed.
    with monkeypatch.context() as failure:
        failure.setattr(
            engine.vector_memory, "_atomic_write_faiss",
            lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic index replace denied"))
        )
        result = engine.cleanup_old_memories(days=90, min_priority_to_keep=0.7)
    assert result["action"] == "cleaned"  # JSON already committed
    assert result["vector_rebuild_success"] is False
    assert [x["thought"] for x in json.loads(primary.read_text())] == [CURRENT]
    assert engine.vector_memory.degraded is True
    assert _retired_search(engine) == []

    assert faiss.read_index(str(index_path)).ntotal == 2
    assert len(json.loads(metadata_path.read_text())) == 1
    restarted = new_engine()
    assert restarted.vector_memory.degraded is True
    assert restarted.vector_memory.rebuild_pending is True
    assert restarted.semantic_search(RETIRED, threshold=0.0) == []
    assert restarted.vector_memory.search(RETIRED, threshold=0.0) == []


def test_failed_metadata_replace_does_not_reexpose_removed_memories(fixture, monkeypatch):
    engine, new_engine, primary, index_path, metadata_path = fixture
    with monkeypatch.context() as failure:
        failure.setattr(
            engine.vector_memory, "_atomic_write_json",
            lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic metadata replace denied"))
        )
        result = engine.cleanup_old_memories(days=90, min_priority_to_keep=0.7)
    assert result["vector_rebuild_success"] is False
    assert [m["thought"] for m in json.loads(primary.read_text())] == [CURRENT]
    assert engine.semantic_search(RETIRED, threshold=0.0) == []
    # A failure must not claim raw vector files have been scrubbed.
    assert faiss.read_index(str(index_path)).ntotal == 2
    restarted = new_engine()
    assert all(x.get("text") != RETIRED for x in _retired_search(restarted))


def test_real_faiss_primary_commit_failure_does_not_touch_vector_files(
    fixture, monkeypatch
):
    engine, _, primary, index_path, metadata_path = fixture
    original = primary.read_bytes()
    orig_index = index_path.read_bytes()
    orig_meta = metadata_path.read_bytes()
    with monkeypatch.context() as failure:
        failure.setattr(engine.json_memory, "_save",
                        lambda: (_ for _ in ()).throw(OSError("synthetic full primary disk")))
        result = engine.cleanup_old_memories(days=90, min_priority_to_keep=0.7)
    assert "error" in result
    assert primary.read_bytes() == original
    assert index_path.read_bytes() == orig_index
    assert metadata_path.read_bytes() == orig_meta
    assert len(engine.json_memory.dump_all()) == 2
    assert engine.vector_memory.index.ntotal == 2


def test_offline_faiss_read_after_restart_with_corrupt_json_returns_no_hits(fixture):
    engine, new_engine, primary, _, _ = fixture
    primary.write_bytes(b"{injected unreadable synthetic source")
    restarted = new_engine()
    assert restarted.json_memory.get_memory_state()["persistence_blocked"]
    assert restarted.semantic_search(RETIRED, threshold=0.0) == []
