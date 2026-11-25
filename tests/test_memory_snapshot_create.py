"""Snapshot creation must never leave a partial backup that shadows a healthy one.

Exercises ``MemorySnapshot.create_snapshot`` / ``create_daily_snapshot`` -- the
methods ``GuardianCore.create_memory_snapshot`` delegates to -- plus the
``get_latest_snapshot``/``list_snapshots`` selection the error-handler recovery
path relies on, against the real ``MemoryCore`` on disposable JSON stores only.
Fictional example: the Kestrel Ridge Apiary hive inspection log.
"""
from __future__ import annotations

import errno
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

SOURCE = "hive-log-2026.csv"
FACTS = [
    ("Kestrel Ridge hive 3 queen was marked blue on 2026-04-12.", 0.7, {"source": SOURCE, "row": 11}),
    ("Kestrel Ridge hive 3 brood pattern rated good at the May inspection.", 0.6, {"source": SOURCE, "row": 18}),
    ("Kestrel Ridge hive 5 needs a second super before the lime flow.", 0.8, {"source": SOURCE, "row": 23}),
]
CORRECTION = (
    "Correction: hive 3 queen was marked green, not blue (blue is hive 4).",
    0.9,
    {"source": SOURCE, "row": 31, "revision": 2, "supersedes": "queen-mark#1"},
)


def _core(path: Path, **kwargs) -> MemoryCore:
    kwargs.setdefault("enable_timeline_logging", False)
    return MemoryCore(str(path), **kwargs)


def _snapshot_files(mgr: MemorySnapshot):
    return sorted(p.name for p in mgr.snapshot_dir.glob("snapshot_*.json"))


def _temp_files(mgr: MemorySnapshot):
    return [str(p.relative_to(mgr.snapshot_dir)) for p in mgr.snapshot_dir.rglob(".*.tmp")]


def _fail_fsync(monkeypatch):
    def boom(fd):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(snapshot_module.os, "fsync", boom)


@pytest.fixture
def store(tmp_path):
    """Populated primary (3 facts) + manager with 3 shards. Returns (primary, core, mgr)."""
    primary = tmp_path / "store" / "guardian_memory.json"
    primary.parent.mkdir()
    mem = _core(primary)
    for thought, priority, metadata in FACTS:
        mem.remember(thought, "fact", priority, metadata)
    assert len(json.loads(primary.read_bytes())) == 3
    mgr = MemorySnapshot(snapshot_dir=str(tmp_path / "snapshots"), backup_shards=3)
    return primary, mem, mgr


def test_successful_snapshot_is_durable_and_reported(store):
    primary, mem, mgr = store
    path = mgr.create_snapshot(mem.dump_all(), metadata={"store": "kestrel"})
    assert path and Path(path).exists()
    data = mgr.load_snapshot(path)
    assert data["memory_count"] == 3
    assert data["memories"] == json.loads(primary.read_bytes())
    assert data["metadata"] == {"store": "kestrel"}
    report = mgr.last_snapshot_report
    assert report["kind"] == "snapshot" and report["path"] == path
    assert report["persisted"] is True and report["memory_count"] == 3 and report["error"] is None
    assert report["shard"] == 1 and report["shard_copied"] is True
    assert (mgr.shard_dirs[0] / Path(path).name).read_bytes() == Path(path).read_bytes()
    assert _temp_files(mgr) == []


def test_failed_write_leaves_no_partial_snapshot_and_previous_stays_latest(store, monkeypatch):
    primary, mem, mgr = store
    good = mgr.create_snapshot(mem.dump_all())
    assert good
    good_bytes = Path(good).read_bytes()
    mem.remember(*CORRECTION[:1], "fact", CORRECTION[1], CORRECTION[2])

    _fail_fsync(monkeypatch)
    assert mgr.create_snapshot(mem.dump_all()) == ""
    report = mgr.last_snapshot_report
    assert report["persisted"] is False and report["path"] is None
    assert "ENOSPC" in report["error"] or "No space left" in report["error"]

    assert _snapshot_files(mgr) == [Path(good).name]
    assert Path(good).read_bytes() == good_bytes
    assert mgr.get_latest_snapshot() == good
    assert mgr.load_snapshot(mgr.get_latest_snapshot())["memory_count"] == 3
    listing = mgr.list_snapshots()
    assert [s["path"] for s in listing] == [good]
    assert max(listing, key=lambda s: s.get("timestamp", ""))["path"] == good
    assert _temp_files(mgr) == []


def test_non_serializable_payload_writes_nothing(store):
    primary, mem, mgr = store
    entries = mem.dump_all()
    entries.append({"thought": "hive 7 scale reading", "metadata": {"raw": object()}})
    assert mgr.create_snapshot(entries) == ""
    report = mgr.last_snapshot_report
    assert report["persisted"] is False and "not serializable" in report["error"]
    assert _snapshot_files(mgr) == []
    assert all(not list(d.iterdir()) for d in mgr.shard_dirs)
    assert _temp_files(mgr) == []


@pytest.mark.parametrize("bad", [None, "not-a-list", {"memories": []}, 42])
def test_non_list_memory_data_is_rejected(store, bad):
    _, _, mgr = store
    assert mgr.create_snapshot(bad) == ""
    assert mgr.create_daily_snapshot(bad) == ""
    assert "must be a list" in mgr.last_snapshot_report["error"]
    assert _snapshot_files(mgr) == [] and not list(mgr.snapshot_dir.glob("daily_*.json"))


def test_snapshots_in_the_same_second_do_not_overwrite_each_other(store):
    _, _, mgr = store
    first = mgr.create_snapshot([{"thought": "first", "time": "t1"}])
    second = mgr.create_snapshot([{"thought": "second", "time": "t2"}])
    assert first and second and first != second
    assert mgr.load_snapshot(first)["memories"][0]["thought"] == "first"
    assert mgr.load_snapshot(second)["memories"][0]["thought"] == "second"
    assert len(_snapshot_files(mgr)) == 2
    shard_names = sorted(p.name for d in mgr.shard_dirs for p in d.glob("snapshot_*.json"))
    assert shard_names == _snapshot_files(mgr)


def test_shard_copies_go_to_least_loaded_shard(store):
    _, _, mgr = store
    for i in range(6):
        assert mgr.create_snapshot([{"thought": f"n{i}"}])
    assert [len(list(d.glob("snapshot_*.json"))) for d in mgr.shard_dirs] == [2, 2, 2]


def test_zero_backup_shards_is_a_clean_skip(tmp_path):
    mgr = MemorySnapshot(snapshot_dir=str(tmp_path / "snapshots"), backup_shards=0)
    path = mgr.create_snapshot([{"thought": "hive 2 swarmed"}])
    assert path and Path(path).exists()
    report = mgr.last_snapshot_report
    assert report["persisted"] is True and report["shard"] is None and report["shard_copied"] is None


def test_shard_copy_failure_keeps_primary_snapshot_and_is_reported(store, monkeypatch):
    primary, mem, mgr = store

    def boom(*args, **kwargs):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(snapshot_module.shutil, "copy2", boom)
    path = mgr.create_snapshot(mem.dump_all())
    assert path and Path(path).exists()
    assert mgr.load_snapshot(path)["memory_count"] == 3
    report = mgr.last_snapshot_report
    assert report["persisted"] is True and report["shard"] == 1 and report["shard_copied"] is False
    assert "shard copy failed" in report["error"]
    assert all(not list(d.glob("*.json")) for d in mgr.shard_dirs)
    assert _temp_files(mgr) == []


def test_daily_failed_write_keeps_previous_daily_intact(store, monkeypatch):
    primary, mem, mgr = store
    first = mgr.create_daily_snapshot(mem.dump_all())
    assert first
    first_bytes = Path(first).read_bytes()
    mem.remember(*CORRECTION[:1], "fact", CORRECTION[1], CORRECTION[2])

    _fail_fsync(monkeypatch)
    assert mgr.create_daily_snapshot(mem.dump_all()) == ""
    assert mgr.last_snapshot_report["persisted"] is False
    assert [p.name for p in mgr.snapshot_dir.glob("daily_*.json")] == [Path(first).name]
    assert Path(first).read_bytes() == first_bytes
    assert mgr.load_snapshot(mgr.get_latest_daily_snapshot())["memory_count"] == 3
    assert _temp_files(mgr) == []


def test_daily_replaces_today_and_removes_earlier_dates_only_after_success(store):
    primary, mem, mgr = store
    stale = mgr.snapshot_dir / "daily_20200101.json"
    stale.write_text(json.dumps({"memories": [], "snapshot_type": "daily"}))

    first = mgr.create_daily_snapshot(mem.dump_all())
    assert first and not stale.exists()
    assert mgr.last_snapshot_report["removed_previous"] == 1

    mem.remember(*CORRECTION[:1], "fact", CORRECTION[1], CORRECTION[2])
    second = mgr.create_daily_snapshot(mem.dump_all())
    assert second == first
    assert mgr.last_snapshot_report["removed_previous"] == 0
    assert mgr.load_snapshot(second)["memory_count"] == 4
    assert [p.name for p in mgr.snapshot_dir.glob("daily_*.json")] == [Path(first).name]


def test_list_snapshots_timestamp_alias_selects_newest(store):
    _, _, mgr = store
    older = mgr.create_snapshot([{"thought": "older"}])
    newer = mgr.create_snapshot([{"thought": "newer"}])
    base = os.stat(newer).st_mtime
    os.utime(older, (base - 3600, base - 3600))
    listing = mgr.list_snapshots()
    assert listing[0]["path"] == newer
    assert all(s["timestamp"] == s["created"] for s in listing)
    assert max(listing, key=lambda s: s.get("timestamp", ""))["path"] == newer


def test_ingest_snapshot_failed_snapshot_corruption_restore_restart_recall(store, monkeypatch):
    """Kestrel Ridge end to end: the failed backup must not cost the recovery."""
    primary, mem, mgr = store
    snapshot_a = mgr.create_snapshot(mem.dump_all())
    mem.remember(*CORRECTION[:1], "fact", CORRECTION[1], CORRECTION[2])
    snapshot_b = mgr.create_snapshot(mem.dump_all())
    assert snapshot_a and snapshot_b and snapshot_b != snapshot_a
    expected = json.loads(primary.read_bytes())
    assert len(expected) == 4

    # A later snapshot attempt fails (disk/USB). It must not become "latest".
    _fail_fsync(monkeypatch)
    assert mgr.create_snapshot(mem.dump_all()) == ""
    monkeypatch.undo()
    latest = mgr.get_latest_snapshot()
    assert latest == snapshot_b

    # Primary is truncated; the restarted core fences itself.
    good = primary.read_bytes()
    primary.write_bytes(good[: len(good) // 2])
    restarted = _core(primary)
    assert restarted.persistence_blocked is True and restarted.memory_log == []

    assert mgr.restore_from_snapshot(latest, restarted) is True
    assert restarted.persistence_blocked is False

    recalled = _core(primary)
    assert recalled.memory_log == expected
    hits = recalled.search_memories("queen")
    assert hits[0]["thought"].startswith("Correction: hive 3 queen was marked green")
    assert hits[0]["metadata"]["source"] == SOURCE
    assert hits[0]["metadata"]["supersedes"] == "queen-mark#1"
    assert hits[1]["thought"] == FACTS[0][0]

    recalled.remember("Kestrel Ridge hive 4 requeened on 2026-06-02.", "fact", 0.7, {"source": SOURCE, "row": 40})
    assert len(json.loads(primary.read_bytes())) == 5
