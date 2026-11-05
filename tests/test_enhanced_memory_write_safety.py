"""Primary-write verification with real disposable JSON and real offline FAISS."""
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import numpy as np
import pytest

from project_guardian.memory import MemoryCore
from project_guardian.memory_vector import EnhancedMemoryCore, VectorMemory
from project_guardian import memory_noise, startup_runtime_guard


TEXT = "Synthetic Cedar Pier beacon inspection record belongs in the east archive."


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("write safety test attempted network access")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(memory_noise, "routine_autonomy_remember_suppressed", lambda *a: False)
    monkeypatch.setattr(memory_noise, "is_low_value_memory_text", lambda *a, **k: False)
    monkeypatch.setattr(memory_noise, "is_embedding_entirely_skipped", lambda *a: False)
    monkeypatch.setattr(startup_runtime_guard, "should_skip_nonessential_remember", lambda *a: False)
    monkeypatch.setattr(startup_runtime_guard, "should_defer_vector_add_during_startup", lambda *a: False)
    monkeypatch.setattr(VectorMemory, "generate_embedding", lambda self, text: np.ones(8, dtype=np.float32))


def engine(tmp_path, *, max_memories=None):
    e = EnhancedMemoryCore.__new__(EnhancedMemoryCore)
    e.json_memory = MemoryCore(str(tmp_path / "primary.json"), enable_timeline_logging=False,
                               enable_vector_search=False, max_memories=max_memories)
    e.vector_memory = VectorMemory(vector_dim=8, index_path=str(tmp_path / "v/index.faiss"),
                                    metadata_path=str(tmp_path / "v/metadata.json"))
    return e


@pytest.mark.parametrize("reason", ["suppressed", "duplicate_suppressed"])
def test_suppressed_primary_never_indexes_existing_or_vector_only_entry(tmp_path, monkeypatch, reason):
    e = engine(tmp_path)
    if reason == "duplicate_suppressed":
        e.remember(TEXT, "fact", 0.9, {"source": "original"})
    before = list(e.vector_memory.metadata)
    monkeypatch.setattr(memory_noise, "routine_autonomy_remember_suppressed", lambda *a: True)
    assert e.remember(TEXT, "fact", 0.9, {"source": "new"}) is None
    assert e.vector_memory.metadata == before


@pytest.mark.parametrize("failure", ["false", "none", "raise", "false_success"])
def test_rejected_or_failed_commit_never_indexes_or_loses_history(tmp_path, monkeypatch, failure):
    e = engine(tmp_path, max_memories=1)
    e.remember(TEXT, "fact", 0.9, {"source": "old"})
    path = tmp_path / "primary.json"
    before_bytes = path.read_bytes()
    before_rows = list(e.json_memory.memory_log)
    before_vectors = list(e.vector_memory.metadata)
    def save():
        if failure == "raise":
            raise OSError("synthetic disk full")
        return {"false": False, "none": None, "false_success": True}[failure]
    monkeypatch.setattr(e.json_memory, "_save", save)
    with pytest.raises((RuntimeError, OSError)):
        e.remember(TEXT + " amended", "fact", 0.9, {"source": "new"})
    assert e.json_memory.memory_log == before_rows
    assert path.read_bytes() == before_bytes
    assert e.vector_memory.metadata == before_vectors
    restarted = engine(tmp_path)
    assert restarted.json_memory.dump_all() == before_rows
    assert restarted.vector_memory.metadata == before_vectors


def test_metadata_and_duplicate_content_round_trip_restart(tmp_path):
    e = engine(tmp_path)
    for revision in (1, 2):
        meta = {"source_id": "synthetic-beacon", "revision": revision,
                "nested": {"citations": ["星空", "Cedar Pier"]}}
        assert e.remember(TEXT, "fact", 0.9, meta) is None
    rows = json.loads((tmp_path / "primary.json").read_text(encoding="utf-8"))
    assert [r["metadata"]["revision"] for r in rows] == [1, 2]
    assert [r["metadata"] for r in rows] == [r["metadata"] for r in e.vector_memory.metadata]
    restarted = engine(tmp_path)
    assert restarted.json_memory.dump_all() == rows
    assert restarted.vector_memory.metadata == e.vector_memory.metadata


def test_disk_read_failure_cannot_be_reported_as_verified_index_write(tmp_path, monkeypatch):
    e = engine(tmp_path)
    original = e.json_memory.remember
    def write_then_hide(*args, **kwargs):
        original(*args, **kwargs)
        # The committed primary bytes remain intact, but verification cannot read them.
        e.json_memory.filepath = str(tmp_path / "unreadable-or-missing.json")
    monkeypatch.setattr(e.json_memory, "remember", write_then_hide)
    with pytest.raises((RuntimeError, OSError)):
        e.remember(TEXT, "fact", 0.9)
    assert e.vector_memory.metadata == []
    assert json.loads((tmp_path / "primary.json").read_text())[0]["thought"] == TEXT


def test_concurrent_identical_content_keeps_own_metadata_and_no_suppressed_vector(tmp_path, monkeypatch):
    e = engine(tmp_path)
    start = threading.Barrier(5)
    def write(i):
        start.wait(timeout=10)
        e.remember(TEXT, "fact", 0.9, {"request": i})
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(write, i) for i in range(4)]
        start.wait(timeout=10)
        for task in tasks:
            task.result(timeout=15)
    primary = json.loads((tmp_path / "primary.json").read_text())
    assert sorted(r["metadata"]["request"] for r in primary) == list(range(4))
    assert sorted(r["metadata"]["request"] for r in e.vector_memory.metadata) == list(range(4))
    before = list(e.vector_memory.metadata)
    monkeypatch.setattr(e.json_memory, "remember", lambda *a, **k: None)
    e.remember(TEXT, "fact", 0.9, {"request": 3})
    assert e.vector_memory.metadata == before


def test_primary_receipt_is_not_confused_by_reentrant_unrelated_write(tmp_path, monkeypatch):
    e = engine(tmp_path)
    original = e.json_memory.remember
    def unrelated(*a, **k):
        original(TEXT + " unrelated", "fact", 0.9, {"request": "other"})
    monkeypatch.setattr(e.json_memory, "remember", unrelated)
    e.remember(TEXT, "fact", 0.9, {"request": "intended"})
    assert e.vector_memory.metadata == []
    assert e.json_memory.dump_all()[0]["metadata"] == {"request": "other"}


def test_memorycore_public_return_contract_stays_none(tmp_path):
    core = engine(tmp_path).json_memory
    assert core.remember(TEXT, "fact", 0.9, {"source": "synthetic"}) is None
    assert core.dump_all()[0]["metadata"] == {"source": "synthetic"}
