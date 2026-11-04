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
    assert restarted.get_memory_state()["vector_count_authoritative"] is False
    assert restarted.semantic_search(RETIRED, threshold=0.0) == []
    assert restarted.vector_memory.search(RETIRED, threshold=0.0) == []

    # Recovery uses the current primary JSON, never stale vector metadata.
    restored = restarted.vector_memory.rebuild_from_memories(
        restarted.json_memory.dump_all()
    )
    assert restored["vector_rebuild_success"] is True
    assert restarted.vector_memory.degraded is False
    assert restarted.get_memory_state()["vector_count_authoritative"] is True
    assert faiss.read_index(str(index_path)).ntotal == 1
    assert [row["text"] for row in json.loads(metadata_path.read_text())] == [CURRENT]
    assert [row["text"] for row in restarted.semantic_search(CURRENT, threshold=0.0)] == [CURRENT]


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


def test_missing_vector_metadata_is_not_mistaken_for_valid_empty_index(fixture):
    engine, new_engine, primary, index_path, metadata_path = fixture
    assert faiss.read_index(str(index_path)).ntotal == 2
    metadata_path.unlink()  # Disposable test fixture only.
    restarted = new_engine()
    assert restarted.vector_memory.degraded
    assert restarted.vector_memory.rebuild_pending
    assert restarted.get_memory_state()["vector_count_authoritative"] is False
    assert restarted.vector_memory.search(RETIRED, threshold=0.0) == []
    assert restarted.semantic_search(CURRENT, threshold=0.0) == []
    # Rebuild from authoritative JSON restores both files to a healthy pair.
    repaired = restarted.vector_memory.rebuild_from_memories(
        restarted.json_memory.dump_all()
    )
    assert repaired["vector_rebuild_success"] is True
    assert restarted.vector_memory.index.ntotal == 2
    assert len(restarted.vector_memory.metadata) == 2
    assert metadata_path.is_file()
    assert restarted.get_memory_state()["vector_count_authoritative"] is True


def _generation_path(metadata_path):
    return Path(str(metadata_path) + ".generation.json")


def test_generation_manifest_binds_real_index_and_metadata(fixture):
    import hashlib
    engine, new_engine, _, index_path, metadata_path = fixture
    manifest_file = _generation_path(metadata_path)
    assert manifest_file.is_file()
    m = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert m["schema"] == "elysia.vector_generation.v1"
    assert len(m["generation_id"]) >= 16
    assert m["index_sha256"] == hashlib.sha256(index_path.read_bytes()).hexdigest()
    assert m["metadata_sha256"] == hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    assert m["count"] == 2
    assert m["vector_dim"] == DIMS
    assert new_engine().vector_memory.degraded is False


def test_same_count_index_change_is_fenced_by_generation(fixture):
    engine, new_engine, _, index_path, metadata_path = fixture
    assert _generation_path(metadata_path).is_file()
    # Synthetic same-size corruption: swap vector positions. Row counts match.
    altered = faiss.IndexFlatL2(DIMS)
    altered.add(np.stack([_embedding(None, CURRENT), _embedding(None, RETIRED)]))
    faiss.write_index(altered, str(index_path))
    assert faiss.read_index(str(index_path)).ntotal == 2
    assert len(json.loads(metadata_path.read_text())) == 2
    restarted = new_engine()
    assert restarted.vector_memory.degraded is True
    assert restarted.vector_memory.rebuild_pending is True
    assert restarted.get_memory_state()["vector_count_authoritative"] is False
    assert restarted.vector_memory.search(RETIRED, threshold=0.0) == []
    assert restarted.vector_memory.get_by_id(0) is None


def test_same_count_metadata_change_is_fenced_by_generation(fixture):
    engine, new_engine, _, index_path, metadata_path = fixture
    rows = json.loads(metadata_path.read_text())
    rows[0]["text"] = "Synthetic counterfeit text of equal count"
    metadata_path.write_text(json.dumps(rows), encoding="utf-8")
    assert faiss.read_index(str(index_path)).ntotal == len(rows) == 2
    restarted = new_engine()
    assert restarted.vector_memory.degraded is True
    assert restarted.vector_memory.search(CURRENT, threshold=0.0) == []


def test_interrupted_equal_count_rebuild_does_not_validate_mixed_generation(
    fixture, monkeypatch
):
    engine, new_engine, primary, index_path, metadata_path = fixture
    rows = engine.json_memory.dump_all()
    rows[0]["thought"] = "Synthetic amended retired ferry schedule"
    engine.json_memory.memory_log = rows
    engine.json_memory._save()
    with monkeypatch.context() as broken:
        broken.setattr(
            engine.vector_memory, "_atomic_write_faiss",
            lambda *a, **k: (_ for _ in ()).throw(OSError("synthetic FAISS replace crash"))
        )
        outcome = engine.vector_memory.rebuild_from_memories(rows)
    assert outcome["vector_rebuild_success"] is False
    assert faiss.read_index(str(index_path)).ntotal == 2
    assert len(json.loads(metadata_path.read_text())) == 2
    restarted = new_engine()
    assert restarted.vector_memory.degraded is True
    assert restarted.vector_memory.search(RETIRED, threshold=0.0) == []
    assert restarted.semantic_search(CURRENT, threshold=0.0) == []


def test_missing_manifest_fences_legacy_pair_until_verified_rebuild(fixture):
    engine, new_engine, primary, index_path, metadata_path = fixture
    manifest_file = _generation_path(metadata_path)
    assert manifest_file.exists()
    original_index, original_metadata = index_path.read_bytes(), metadata_path.read_bytes()
    manifest_file.unlink()  # Disposable test only. No user history.
    restarted = new_engine()
    assert restarted.vector_memory.degraded is True
    assert restarted.vector_memory.rebuild_pending is True
    assert index_path.read_bytes() == original_index
    assert metadata_path.read_bytes() == original_metadata
    assert restarted.semantic_search(RETIRED, threshold=0.0) == []
    repaired = restarted.vector_memory.rebuild_from_memories(restarted.json_memory.dump_all())
    assert repaired["vector_rebuild_success"] is True
    assert manifest_file.is_file()
    assert new_engine().vector_memory.degraded is False


def test_corrupt_manifest_is_not_auto_rewritten_or_accepted(fixture):
    engine, new_engine, primary, index_path, metadata_path = fixture
    manifest_file = _generation_path(metadata_path)
    corrupt = b"{corrupt generation manifest; preserve for operator"
    manifest_file.write_bytes(corrupt)
    restarted = new_engine()
    assert restarted.vector_memory.degraded is True
    assert manifest_file.read_bytes() == corrupt
    assert restarted.vector_memory.search(CURRENT, threshold=0.0) == []


def test_generation_changes_after_successful_cleanup_and_restart(fixture):
    engine, new_engine, primary, index_path, metadata_path = fixture
    manifest_file = _generation_path(metadata_path)
    original_id = json.loads(manifest_file.read_text())["generation_id"]
    result = engine.cleanup_old_memories(days=90, min_priority_to_keep=0.7)
    assert result["vector_rebuild_success"] is True
    new_id = json.loads(manifest_file.read_text())["generation_id"]
    assert new_id != original_id
    assert new_engine().vector_memory.degraded is False


def test_unverified_generation_cannot_be_recertified_by_normal_memory_add(fixture):
    engine, new_engine, primary, index_path, metadata_path = fixture
    manifest_file = _generation_path(metadata_path)
    manifest_file.unlink()  # Simulated existing legacy/unverified pair.
    before_index, before_meta = index_path.read_bytes(), metadata_path.read_bytes()
    restarted = new_engine()
    assert restarted.vector_memory.degraded
    attempted = restarted.vector_memory.add_memory(
        "Synthetic attempted re-certification", category="fact"
    )
    assert attempted is None
    assert index_path.read_bytes() == before_index
    assert metadata_path.read_bytes() == before_meta
    assert not manifest_file.exists()
    assert new_engine().vector_memory.degraded
    # Explicit rebuild from authoritative JSON is the permitted recovery path.
    rebuilt = restarted.vector_memory.rebuild_from_memories(
        restarted.json_memory.dump_all()
    )
    assert rebuilt["vector_rebuild_success"] is True
    assert restarted.vector_memory.add_memory(
        "Synthetic verified new row", category="fact"
    ) is not None
    assert new_engine().vector_memory.degraded is False


def test_failed_vector_add_is_fenced_in_same_process_and_after_restart(fixture, monkeypatch):
    engine, new_engine, primary, index_path, metadata_path = fixture
    vector = engine.vector_memory
    manifest_file = _generation_path(metadata_path)
    original_manifest = manifest_file.read_bytes()
    before_json = primary.read_bytes()
    with monkeypatch.context() as fault:
        fault.setattr(
            vector, "_atomic_write_faiss",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("synthetic write denied"))
        )
        assert vector.add_memory(
            "Synthetic new uncommitted beacon", category="fact"
        ) is None
    assert vector.degraded is True
    assert vector.rebuild_pending is True
    assert vector.search(RETIRED, threshold=0.0) == []
    assert vector.get_by_id(0) is None
    assert vector.add_memory("Synthetic next rejected row", category="fact") is None
    assert primary.read_bytes() == before_json
    assert manifest_file.read_bytes() == original_manifest
    restarted = new_engine()
    assert restarted.vector_memory.degraded is True
    assert restarted.vector_memory.search(CURRENT, threshold=0.0) == []


def test_failed_metadata_add_does_not_claim_valid_index_or_further_writes(fixture, monkeypatch):
    engine, new_engine, primary, index_path, metadata_path = fixture
    vector = engine.vector_memory
    original_bytes = (index_path.read_bytes(), metadata_path.read_bytes())
    with monkeypatch.context() as fault:
        fault.setattr(
            vector, "_atomic_write_json",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("synthetic metadata disk full"))
        )
        assert vector.add_memory("Synthetic new uncommitted beacon", category="fact") is None
    assert vector.degraded is True
    assert vector.rebuild_pending is True
    assert vector.search(CURRENT, threshold=0.0) == []
    assert vector.get_by_id(0) is None
    assert vector.add_memory("Synthetic further unsafe add", category="fact") is None
    assert (index_path.read_bytes(), metadata_path.read_bytes()) == original_bytes
    # Rebuild solely from authoritative JSON repairs the volatile vector state.
    result = vector.rebuild_from_memories(engine.json_memory.dump_all())
    assert result["vector_rebuild_success"] is True
    assert vector.degraded is False
    assert vector.index.ntotal == len(json.loads(primary.read_text()))
    assert vector.search(CURRENT, threshold=0.0)
    assert new_engine().vector_memory.degraded is False
