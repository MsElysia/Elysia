"""Synthetic cleanup durability contract for the integrated Windows MemoryCore.

A failed primary JSON commit must never discard in-process history or publish
derived vector work. No real memories, external services, or device access.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from project_guardian.memory import MemoryCore
from project_guardian.memory_cleanup import MemoryCleanup


def seeded(tmp_path):
    path = tmp_path / "synthetic_guardian_memory.json"
    rows = [
        {"time": "2021-01-05T09:00:00", "thought": f"Synthetic archived item {i}",
         "priority": 0.1, "category": "synthetic", "metadata": {}}
        for i in range(4)
    ] + [{"time": "2026-11-03T09:00:00",
          "thought": "Synthetic important recent record", "priority": 0.9,
          "category": "synthetic", "metadata": {}}]
    path.write_text(json.dumps(rows), encoding="utf-8")
    core = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    return path, rows, core


def test_failed_consolidation_preserves_memory_and_original_disk(tmp_path, monkeypatch):
    path, before, core = seeded(tmp_path)
    before_bytes = path.read_bytes()
    with monkeypatch.context() as faults:
        faults.setattr(core, "_save", lambda: (_ for _ in ()).throw(OSError("synthetic no disk space")))
        result = MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=7)
    assert result["action"] == "error"
    assert result["action_taken"] is False
    assert core.dump_all() == before
    assert path.read_bytes() == before_bytes
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == before
    core.remember("Synthetic later safe write after failed consolidation", priority=0.9)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert len(stored) == len(before) + 1


def test_failed_cleanup_old_memories_does_not_lose_in_memory_entries(tmp_path, monkeypatch):
    path, before, core = seeded(tmp_path)
    before_bytes = path.read_bytes()
    with monkeypatch.context() as faults:
        faults.setattr(core, "_save", lambda: (_ for _ in ()).throw(OSError("synthetic denied write")))
        result = MemoryCleanup(core).cleanup_old_memories(days=90, min_priority=0.3)
    assert "error" in result
    assert core.dump_all() == before
    assert path.read_bytes() == before_bytes
    core.remember("Synthetic later save must preserve original history", priority=0.9)
    assert len(json.loads(path.read_text(encoding="utf-8"))) == len(before) + 1


def test_failed_primary_commit_does_not_degrade_or_touch_vector_copy(tmp_path, monkeypatch):
    path, before, core = seeded(tmp_path)
    vector = SimpleNamespace(metadata=[], index=None, degraded=False, rebuild_pending=False)
    enhanced = SimpleNamespace(json_memory=core, vector_memory=vector)
    with monkeypatch.context() as faults:
        faults.setattr(core, "_save", lambda: (_ for _ in ()).throw(OSError("synthetic disk full")))
        result = MemoryCleanup(enhanced).consolidate_memories(max_memories=2, keep_recent_days=7)
    assert result["action"] == "error"
    assert core.dump_all() == before
    assert vector.degraded is False
    assert vector.rebuild_pending is False


def test_successful_cleanup_still_commits_and_survives_restart(tmp_path):
    path, before, core = seeded(tmp_path)
    result = MemoryCleanup(core).cleanup_old_memories(days=90, min_priority=0.3)
    assert result["action"] == "cleaned"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == core.dump_all()
    assert len(saved) < len(before)
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == saved


def test_successful_consolidation_still_commits_and_survives_restart(tmp_path):
    path, before, core = seeded(tmp_path)
    result = MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=7)
    assert result["action"] == "consolidated"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == core.dump_all()
    assert len(saved) < len(before)
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == saved
