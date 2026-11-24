"""Snapshot restore must recover a fenced (unreadable) primary without replaying writes.

Exercises ``MemorySnapshot.restore_from_snapshot`` -- the method
``GuardianCore.restore_memory_from_snapshot`` delegates to -- against the real
``MemoryCore`` on disposable JSON stores only. Fictional example: the Saltmarsh
Ferry Company winter timetable.
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(_ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.memory import MemoryCore
import project_guardian.memory_snapshot as snapshot_module
from project_guardian.memory_snapshot import MemorySnapshot

PRE_RESTORE_SUFFIX = getattr(snapshot_module, "PRE_RESTORE_SUFFIX", ".pre-restore.")

SOURCE = "saltmarsh-timetable-2026.pdf"
FACTS = [
    ("Saltmarsh ferry first departure from Quay Street is 06:10 on weekdays.", 0.7, {"source": SOURCE, "page": 2}),
    ("Saltmarsh ferry crossing to Gull Island takes 25 minutes.", 0.6, {"source": SOURCE, "page": 2}),
    ("Saltmarsh ferry does not run on Christmas Day.", 0.8, {"source": SOURCE, "page": 4}),
    (
        "Correction: first weekday departure from Quay Street is 06:25, not 06:10 (winter timetable).",
        0.9,
        {"source": SOURCE, "page": 7, "revision": 2, "supersedes": "departure#1"},
    ),
]


class _CountingTimeline:
    def __init__(self):
        self.events = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)


def _core(path: Path, **kwargs) -> MemoryCore:
    kwargs.setdefault("enable_timeline_logging", False)
    return MemoryCore(str(path), **kwargs)


def _sidecars(primary: Path):
    return sorted(p for p in primary.parent.iterdir() if PRE_RESTORE_SUFFIX in p.name)


@pytest.fixture
def store(tmp_path):
    """Populated primary + snapshot of it. Returns (primary, snapshot_mgr, snapshot_path, entries)."""
    primary = tmp_path / "store" / "guardian_memory.json"
    primary.parent.mkdir()
    mem = _core(primary)
    for thought, priority, metadata in FACTS:
        mem.remember(thought, "fact", priority, metadata)
    entries = json.loads(primary.read_bytes())
    assert len(entries) == 4
    mgr = MemorySnapshot(snapshot_dir=str(tmp_path / "snapshots"), backup_shards=1)
    snapshot_path = mgr.create_snapshot(mem.dump_all(), metadata={"store": "saltmarsh"})
    assert snapshot_path
    return primary, mgr, snapshot_path, entries


def _corrupt(primary: Path) -> bytes:
    good = primary.read_bytes()
    primary.write_bytes(good[: len(good) // 2])
    return primary.read_bytes()


def test_fenced_primary_is_recovered_and_original_bytes_preserved(store):
    primary, mgr, snapshot_path, entries = store
    corrupt = _corrupt(primary)

    restarted = _core(primary)
    assert restarted.persistence_blocked is True
    assert restarted.memory_log == []

    assert mgr.restore_from_snapshot(snapshot_path, restarted) is True
    report = mgr.last_restore_report
    assert report["restored"] == 4 and report["skipped"] == 0 and report["truncated"] == 0
    assert report["changed"] is True and report["persisted"] is True and report["error"] is None

    assert restarted.persistence_blocked is False
    assert restarted.memory_log == entries
    assert json.loads(primary.read_bytes()) == entries

    sidecars = _sidecars(primary)
    assert len(sidecars) == 1
    assert Path(report["preserved_original"]) == sidecars[0]
    assert sidecars[0].read_bytes() == corrupt
    assert not list(primary.parent.glob(".guardian_memory_restore_*.tmp"))


def test_restart_recalls_restored_history_with_provenance_and_accepts_new_writes(store):
    primary, mgr, snapshot_path, entries = store
    _corrupt(primary)
    assert mgr.restore_from_snapshot(snapshot_path, _core(primary)) is True

    again = _core(primary)
    assert again.persistence_blocked is False
    assert len(again.memory_log) == 4
    correction = entries[-1]
    kept = [e for e in again.memory_log if e["thought"] == correction["thought"]]
    assert kept == [correction]

    hits = again.search_memories("departure")
    assert hits[0]["metadata"]["supersedes"] == "departure#1"
    assert all(h["metadata"]["source"] == SOURCE for h in hits)

    again.remember("Saltmarsh ferry fares rise to 4.50 on 1 January.", "fact", 0.6, {"source": SOURCE, "page": 9})
    assert len(json.loads(primary.read_bytes())) == 5


def test_missing_snapshot_leaves_target_and_primary_untouched(store):
    primary, mgr, _, _ = store
    corrupt = _corrupt(primary)
    target = _core(primary)

    assert mgr.restore_from_snapshot(str(primary.parent / "nope.json"), target) is False
    assert mgr.last_restore_report["error"] == "snapshot unreadable"
    assert primary.read_bytes() == corrupt
    assert target.persistence_blocked is True and target.memory_log == []
    assert _sidecars(primary) == []


def test_malformed_snapshot_json_is_rejected(store, tmp_path):
    primary, mgr, _, entries = store
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    target = _core(primary)
    before = primary.read_bytes()

    assert mgr.restore_from_snapshot(str(bad), target) is False
    assert primary.read_bytes() == before
    assert target.memory_log == entries
    assert _sidecars(primary) == []


def test_snapshot_without_memory_list_is_rejected(store, tmp_path):
    primary, mgr, _, entries = store
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"memories": {"thought": "not a list"}}), encoding="utf-8")
    target = _core(primary)
    before = primary.read_bytes()

    assert mgr.restore_from_snapshot(str(bad), target) is False
    assert "not a list" in mgr.last_restore_report["error"]
    assert primary.read_bytes() == before
    assert target.memory_log == entries


def test_malformed_entries_skipped_and_defaults_filled_verbatim_otherwise(store, tmp_path):
    primary, mgr, _, _ = store
    snap = tmp_path / "mixed.json"
    snap.write_text(json.dumps({
        "timestamp": "2026-01-02T03:04:05",
        "memories": [
            "just a string",
            {"category": "fact"},
            {"thought": 42},
            {"thought": "Gull Island pier closes at dusk.", "time": "", "priority": "high", "metadata": "nope"},
            {"thought": "Dogs travel free on the Saltmarsh ferry.", "time": "2025-12-01T08:00:00",
             "category": "fact", "priority": 0.4, "metadata": {"source": SOURCE, "page": 3}},
        ],
    }), encoding="utf-8")
    target = _core(primary)

    assert mgr.restore_from_snapshot(str(snap), target) is True
    report = mgr.last_restore_report
    assert report["restored"] == 2 and report["skipped"] == 3
    assert target.memory_log == [
        {"thought": "Gull Island pier closes at dusk.", "time": "2026-01-02T03:04:05",
         "category": "general", "priority": 0.5, "metadata": {}},
        {"thought": "Dogs travel free on the Saltmarsh ferry.", "time": "2025-12-01T08:00:00",
         "category": "fact", "priority": 0.4, "metadata": {"source": SOURCE, "page": 3}},
    ]
    assert json.loads(primary.read_bytes()) == target.memory_log


def test_restore_is_idempotent(store):
    primary, mgr, snapshot_path, entries = store
    _corrupt(primary)
    target = _core(primary)
    assert mgr.restore_from_snapshot(snapshot_path, target) is True
    after_first = primary.read_bytes()

    assert mgr.restore_from_snapshot(snapshot_path, target) is True
    report = mgr.last_restore_report
    assert report["changed"] is False and report["persisted"] is True and report["restored"] == 4
    assert report["preserved_original"] is None
    assert primary.read_bytes() == after_first
    assert len(_sidecars(primary)) == 1
    assert target.memory_log == entries


def test_failed_replace_reports_false_and_leaves_primary_unchanged(store, monkeypatch):
    primary, mgr, snapshot_path, _ = store
    corrupt = _corrupt(primary)
    target = _core(primary)

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(snapshot_module.os, "replace", boom)
    assert mgr.restore_from_snapshot(snapshot_path, target) is False
    report = mgr.last_restore_report
    assert "disk full" in report["error"]
    assert report["persisted"] is False and report["changed"] is False and report["restored"] == 0
    assert primary.read_bytes() == corrupt
    assert target.persistence_blocked is True and target.memory_log == []
    assert not list(primary.parent.glob(".guardian_memory_restore_*.tmp"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX flock contention")
def test_lock_held_by_another_writer_blocks_restore_without_touching_primary(store):
    import fcntl

    primary, mgr, snapshot_path, _ = store
    corrupt = _corrupt(primary)
    target = _core(primary)
    target._primary_lock_timeout_seconds = 0.2

    lock_path = os.path.normcase(os.path.realpath(str(primary))) + ".memorycore.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert mgr.restore_from_snapshot(snapshot_path, target) is False
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert "lock" in mgr.last_restore_report["error"].lower()
    assert primary.read_bytes() == corrupt
    assert target.memory_log == []
    assert _sidecars(primary) == []

    assert mgr.restore_from_snapshot(snapshot_path, target) is True
    assert len(target.memory_log) == 4


def test_max_memories_keeps_most_recent_entries(store):
    primary, mgr, snapshot_path, entries = store
    _corrupt(primary)
    target = _core(primary, max_memories=2)

    assert mgr.restore_from_snapshot(snapshot_path, target) is True
    assert mgr.last_restore_report["truncated"] == 2
    assert target.memory_log == entries[2:]
    assert json.loads(primary.read_bytes()) == entries[2:]


def test_healthy_primary_restore_preserves_previous_content_in_sidecar(store):
    primary, mgr, snapshot_path, entries = store
    target = _core(primary)
    target.remember("Saltmarsh ferry added a 22:40 sailing on Fridays.", "fact", 0.6, {"source": SOURCE, "page": 8})
    before = primary.read_bytes()
    assert len(json.loads(before)) == 5

    assert mgr.restore_from_snapshot(snapshot_path, target) is True
    assert target.memory_log == entries
    sidecars = _sidecars(primary)
    assert len(sidecars) == 1 and sidecars[0].read_bytes() == before

    target.remember("Saltmarsh ferry office opens at 08:00.", "fact", 0.5, {"source": SOURCE, "page": 1})
    assert len(json.loads(primary.read_bytes())) == 5
    assert target.persistence_blocked is False


def test_lazy_target_is_marked_loaded_after_restore(store):
    primary, mgr, snapshot_path, entries = store
    _corrupt(primary)
    target = _core(primary, lazy_load=True)
    assert target.is_loaded() is False

    assert mgr.restore_from_snapshot(snapshot_path, target) is True
    assert target.is_loaded() is True
    assert target.get_memory_count() == 4
    assert target.get_memory_state()["persistence_blocked"] is False


def test_restore_does_not_replay_through_remember(store):
    primary, mgr, snapshot_path, entries = store
    _corrupt(primary)
    timeline = _CountingTimeline()
    target = MemoryCore(str(primary), timeline_memory=timeline, enable_timeline_logging=True)

    assert mgr.restore_from_snapshot(snapshot_path, target) is True
    assert timeline.events == []
    assert [e["time"] for e in target.memory_log] == [e["time"] for e in entries]
    assert target._vector_index_built is False


def test_stale_writer_fenced_by_peer_can_still_restore(store):
    primary, mgr, snapshot_path, entries = store
    ours = _core(primary)
    peer = _core(primary)
    peer.remember("Peer process: Saltmarsh ferry suspended for storm Imogen.", "fact", 0.9, {"source": "ops-log"})
    peer_bytes = primary.read_bytes()

    with pytest.raises(RuntimeError):
        ours.remember("Stale writer attempt.", "fact", 0.5, {"source": SOURCE})
    assert ours.persistence_blocked is True

    assert mgr.restore_from_snapshot(snapshot_path, ours) is True
    assert ours.persistence_blocked is False
    assert ours.memory_log == entries
    sidecars = _sidecars(primary)
    assert len(sidecars) == 1 and sidecars[0].read_bytes() == peer_bytes


def test_enhanced_memory_core_wrapper_is_unwrapped(store):
    from project_guardian.memory_vector import EnhancedMemoryCore

    primary, mgr, snapshot_path, entries = store
    _corrupt(primary)
    wrapper = EnhancedMemoryCore(json_filepath=str(primary), enable_vector=False)
    assert wrapper.json_memory.persistence_blocked is True

    assert mgr.restore_from_snapshot(snapshot_path, wrapper) is True
    assert wrapper.json_memory.persistence_blocked is False
    assert wrapper.memory_log == entries
    assert wrapper.get_memory_count() == 4


def test_unsupported_target_is_rejected_without_side_effects(store):
    primary, mgr, snapshot_path, _ = store
    before = primary.read_bytes()

    class NoPrimary:
        pass

    assert mgr.restore_from_snapshot(snapshot_path, NoPrimary()) is False
    assert "filepath" in mgr.last_restore_report["error"]
    assert primary.read_bytes() == before
    assert _sidecars(primary) == []
