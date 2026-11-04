"""Enhanced cleanup must not serve removed memories from semantic results.

Exercises the EXACT EnhancedMemoryCore method AST from project_guardian/memory_vector.py
without loading its optional NumPy/FAISS/cloud imports. Synthetic vector double:
this checks caller contracts and fail-closed read behavior, NOT real FAISS durability.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from project_guardian.memory import MemoryCore
from project_guardian.memory_cleanup import MemoryCleanup


_SOURCE = Path(__file__).resolve().parents[1] / "project_guardian" / "memory_vector.py"


def _enhanced_method(name: str):
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"), filename=str(_SOURCE))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "EnhancedMemoryCore")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, copy.deepcopy(method)], type_ignores=[]))
    scope = {"__package__": "project_guardian"}
    exec(compile(module, str(_SOURCE), "exec"), scope)
    return scope[name]


class SyntheticVector:
    def __init__(self, values):
        self.values = [dict(v) for v in values]
        self.degraded = False
        self.rebuild_pending = False
        self.rebuilt = []
        self.rebuild_mode = "rebuilt"

    def load_if_needed(self):
        return None

    def rebuild_from_memories(self, kept_memories, safe_max=250):
        self.rebuilt.append([x["thought"] for x in kept_memories])
        if self.rebuild_mode == "deferred":
            return {"vector_rebuild_status": "deferred", "vector_rebuild_success": False,
                    "error": "Synthetic rebuild deferred"}
        self.values = [
            {"text": x["thought"], "category": x.get("category", "general")}
            for x in kept_memories
        ]
        return {"vector_rebuild_status": "rebuilt", "vector_rebuild_success": True,
                "error": None}

    def search(self, query, limit=10, threshold=0.7, category=None):
        return [dict(x) for x in self.values if category is None or x.get("category") == category][:limit]


def seeded(tmp_path):
    path = tmp_path / "synthetic_history.json"
    rows = [
        {"time": "2021-01-05T09:00:00", "thought": "Synthetic retired lantern route",
         "category": "fact", "priority": 0.1, "metadata": {}},
        {"time": "2026-11-03T09:00:00", "thought": "Synthetic active lantern route",
         "category": "fact", "priority": 0.9, "metadata": {}},
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")
    memory = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    vector = SyntheticVector([
        {"text": x["thought"], "category": x["category"]} for x in rows
    ])
    enhanced = SimpleNamespace(json_memory=memory, vector_memory=vector)
    enhanced.load_if_needed = memory.load_if_needed
    return path, rows, enhanced


def _cleanup(enhanced):
    return _enhanced_method("cleanup_old_memories")(
        enhanced, days=90, min_priority_to_keep=0.7,
    )


def _search(enhanced, query="lantern"):
    return _enhanced_method("semantic_search")(enhanced, query, limit=10, threshold=0.7)


def test_enhanced_cleanup_accepts_priority_and_reconciles_vector(tmp_path):
    path, rows, enhanced = seeded(tmp_path)
    result = _cleanup(enhanced)
    assert result["action"] == "cleaned"
    assert result["vector_rebuild_success"] is True
    assert result["vector_rebuild_status"] == "rebuilt"
    assert enhanced.vector_memory.rebuilt == [[rows[1]["thought"]]]
    assert json.loads(path.read_text(encoding="utf-8")) == [rows[1]]
    assert _search(enhanced) == [{"text": rows[1]["thought"], "category": "fact"}]


def test_removed_memory_is_never_returned_if_vector_index_stays_stale(tmp_path):
    path, rows, enhanced = seeded(tmp_path)
    result = MemoryCleanup(enhanced.json_memory).cleanup_old_memories(days=90, min_priority=0.7)
    assert result["action"] == "cleaned"
    # Stale index survives intentionally: simulate rebuild interruption/restart.
    assert len(enhanced.vector_memory.values) == 2
    results = _search(enhanced)
    assert rows[0]["thought"] not in [r.get("text") for r in results]
    assert [r["text"] for r in results] == [rows[1]["thought"]]


def test_deferred_vector_rebuild_does_not_expose_removed_text(tmp_path):
    path, rows, enhanced = seeded(tmp_path)
    enhanced.vector_memory.rebuild_mode = "deferred"
    result = _cleanup(enhanced)
    assert result["action"] == "cleaned"
    assert result["vector_rebuild_success"] is False
    assert result["vector_rebuild_status"] == "deferred"
    assert enhanced.vector_memory.degraded or enhanced.vector_memory.rebuild_pending
    assert rows[0]["thought"] not in [r["text"] for r in _search(enhanced)]
    assert json.loads(path.read_text(encoding="utf-8")) == [rows[1]]


def test_primary_failure_does_not_rebuild_vector_or_drop_json(tmp_path, monkeypatch):
    path, rows, enhanced = seeded(tmp_path)
    before = path.read_bytes()
    with monkeypatch.context() as faulty:
        faulty.setattr(enhanced.json_memory, "_save", lambda: (_ for _ in ()).throw(OSError("synthetic full disk")))
        result = _cleanup(enhanced)
    assert "error" in result
    assert path.read_bytes() == before
    assert enhanced.json_memory.dump_all() == rows
    assert enhanced.vector_memory.rebuilt == []


def test_unreadable_authoritative_json_yields_no_semantic_results(tmp_path):
    path, rows, enhanced = seeded(tmp_path)
    path.write_bytes(b"{broken synthetic history")
    unreadable = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    enhanced.json_memory = unreadable
    enhanced.load_if_needed = unreadable.load_if_needed
    assert unreadable.get_memory_state()["persistence_blocked"] is True
    assert _search(enhanced) == []


def test_restarted_json_filters_old_vector_results(tmp_path):
    path, rows, enhanced = seeded(tmp_path)
    result = MemoryCleanup(enhanced.json_memory).cleanup_old_memories(days=90, min_priority=0.7)
    assert result["action"] == "cleaned"
    enhanced.json_memory = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    enhanced.load_if_needed = enhanced.json_memory.load_if_needed
    # Simulated separately persisted vector still contains retired text.
    assert len(enhanced.vector_memory.values) == 2
    assert [r["text"] for r in _search(enhanced)] == [rows[1]["thought"]]


def test_no_vector_enhanced_cleanup_keeps_json_functionality(tmp_path):
    path, rows, enhanced = seeded(tmp_path)
    enhanced.vector_memory = None
    result = _cleanup(enhanced)
    assert result["action"] == "cleaned"
    assert json.loads(path.read_text(encoding="utf-8")) == [rows[1]]
