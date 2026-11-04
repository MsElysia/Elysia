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


def test_lazy_cleanup_loads_disk_before_pruning(tmp_path):
    """An unopened but populated file is not an empty memory history."""
    path, originals, _ = seeded(tmp_path)
    deferred = MemoryCore(filepath=str(path), lazy_load=True, enable_timeline_logging=False)
    assert deferred.is_loaded() is False
    result = MemoryCleanup(deferred).cleanup_old_memories(days=90, min_priority=0.3)
    assert result["action"] == "cleaned"
    assert result["original_count"] == len(originals)
    assert deferred.get_memory_state()["memory_count_authoritative"] is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == [originals[-1]]
    assert deferred.dump_all() == saved


def test_lazy_cleanup_refuses_corrupt_file_without_overwriting_it(tmp_path):
    """Failed deferred load must fence cleanup, rather than saving empty data."""
    path = tmp_path / "synthetic_guardian_memory.json"
    original = b'{not-valid JSON; preserve these exact original bytes'
    path.write_bytes(original)
    deferred = MemoryCore(filepath=str(path), lazy_load=True, enable_timeline_logging=False)
    result = MemoryCleanup(deferred).cleanup_old_memories(days=90, min_priority=0.3)
    assert "error" in result
    assert path.read_bytes() == original
    assert deferred.get_memory_state()["persistence_blocked"] is True
    assert deferred.get_memory_state()["memory_count_authoritative"] is False


def test_corrupt_primary_consolidation_does_not_claim_healthy_noop(tmp_path):
    """A corrupt history is not an empty history below the cleanup threshold."""
    path = tmp_path / "synthetic_guardian_memory.json"
    original = b'[{"synthetic":"broken"'
    path.write_bytes(original)
    core = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    result = MemoryCleanup(core).consolidate_memories(max_memories=2000)
    assert result["action"] == "error"
    assert result["action_taken"] is False
    assert path.read_bytes() == original
    assert core.get_memory_state()["persistence_blocked"] is True


def test_lazy_consolidation_sees_original_count_below_threshold(tmp_path):
    path, originals, _ = seeded(tmp_path)
    before = path.read_bytes()
    deferred = MemoryCore(filepath=str(path), lazy_load=True, enable_timeline_logging=False)
    result = MemoryCleanup(deferred).consolidate_memories(max_memories=20)
    assert result["action"] == "no_action_needed"
    assert result["original_count"] == len(originals)
    assert path.read_bytes() == before


def test_utc_offset_timestamps_are_safe_for_manual_cleanup(tmp_path):
    """Timezone-aware imports should not make durable pruning fail or discard data."""
    from datetime import datetime, timezone
    path, originals, _ = seeded(tmp_path)
    rows = list(originals)
    rows[0] = dict(rows[0], time="2021-01-05T09:00:00+05:30")
    rows[-1] = dict(rows[-1], time=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    path.write_text(json.dumps(rows), encoding="utf-8")
    core = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    outcome = MemoryCleanup(core).cleanup_old_memories(days=90, min_priority=0.3)
    assert outcome["action"] == "cleaned"
    assert outcome["removed"] == len(rows) - 1
    assert json.loads(path.read_text(encoding="utf-8")) == [rows[-1]]
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == [rows[-1]]


def test_utc_offset_timestamps_are_safe_for_consolidation(tmp_path):
    """Consolidation must handle both legacy naive timestamps and UTC ISO stamps."""
    from datetime import datetime, timezone
    path, originals, _ = seeded(tmp_path)
    rows = list(originals)
    rows[1] = dict(rows[1], time="2021-01-05T09:00:00-04:00")
    rows[-1] = dict(rows[-1], time=datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(rows), encoding="utf-8")
    core = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    outcome = MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=90)
    assert outcome["action"] == "consolidated"
    assert outcome["removed"] == len(rows) - 1
    assert json.loads(path.read_text(encoding="utf-8")) == [rows[-1]]
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == [rows[-1]]
