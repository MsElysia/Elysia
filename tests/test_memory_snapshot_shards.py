# tests/test_memory_snapshot_shards.py
"""Focused tests for backup-shard selection in project_guardian/memory_snapshot.py."""

import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "project_guardian" / "memory_snapshot.py"


@pytest.fixture
def ms():
    # Load by file path: the module is stdlib-only, and ``import project_guardian`` currently
    # fails on main at package import (tracked separately), which would mask these tests.
    spec = importlib.util.spec_from_file_location("memory_snapshot_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ticking_clock(ms, monkeypatch):
    """Make each ``datetime.now()`` call advance one second so snapshot names never collide."""
    state = {"now": datetime(2026, 1, 1, 12, 0, 0)}

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            state["now"] = state["now"] + timedelta(seconds=1)
            return state["now"]

    monkeypatch.setattr(ms, "datetime", _FakeDateTime)
    return state


def _shard_counts(snap):
    return [len(list(d.glob("snapshot_*.json"))) for d in snap.shard_dirs]


class TestShardSelection:
    def test_empty_shards_select_in_order(self, ms, tmp_path):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=3)
        assert snap._select_backup_shard() == 0
        (snap.shard_dirs[0] / "snapshot_a.json").write_text("{}")
        assert snap._select_backup_shard() == 1
        (snap.shard_dirs[1] / "snapshot_b.json").write_text("{}")
        assert snap._select_backup_shard() == 2
        (snap.shard_dirs[2] / "snapshot_c.json").write_text("{}")
        assert snap._select_backup_shard() == 0

    def test_prefers_least_loaded_shard_after_cleanup(self, ms, tmp_path):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=3)
        for d in snap.shard_dirs:
            (d / "snapshot_x.json").write_text("{}")
            (d / "snapshot_y.json").write_text("{}")
        # Retention cleanup emptied the middle shard; the next copy should refill it.
        for f in snap.shard_dirs[1].glob("snapshot_*.json"):
            f.unlink()
        assert snap._select_backup_shard() == 1

    def test_ignores_non_snapshot_files(self, ms, tmp_path):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=2)
        (snap.shard_dirs[0] / "notes.txt").write_text("x")
        (snap.shard_dirs[0] / "daily_20260101.json").write_text("{}")
        assert snap._select_backup_shard() == 0

    def test_no_shards_returns_zero(self, ms, tmp_path):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=0)
        assert snap.shard_dirs == []
        assert snap._select_backup_shard() == 0


class TestCreateSnapshotDistribution:
    def test_six_snapshots_spread_evenly_over_three_shards(self, ms, tmp_path, ticking_clock):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=3)
        paths = [snap.create_snapshot([{"thought": f"t{i}"}]) for i in range(6)]
        assert all(paths)
        assert len(set(paths)) == 6
        # Previously this came out as [1, 5, 0]: the selector keyed off shard_1's count only.
        assert _shard_counts(snap) == [2, 2, 2]

    def test_shard_copy_is_byte_identical_to_primary(self, ms, tmp_path, ticking_clock):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=3)
        primary = Path(snap.create_snapshot([{"thought": "keep"}], metadata={"k": 1}))
        copies = [p for d in snap.shard_dirs for p in d.glob("snapshot_*.json")]
        assert len(copies) == 1
        assert copies[0].name == primary.name
        assert json.loads(copies[0].read_text()) == json.loads(primary.read_text())

    def test_every_shard_receives_a_copy(self, ms, tmp_path, ticking_clock):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=3)
        for i in range(3):
            snap.create_snapshot([{"thought": f"t{i}"}])
        assert all(c >= 1 for c in _shard_counts(snap))

    def test_zero_shards_still_writes_primary_snapshot(self, ms, tmp_path, ticking_clock):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=0)
        path = snap.create_snapshot([{"thought": "solo"}])
        assert path
        assert Path(path).is_file()
        assert snap.get_latest_snapshot() == path

    def test_cleanup_removes_expired_shard_copies(self, ms, tmp_path, ticking_clock):
        snap = ms.MemorySnapshot(snapshot_dir=str(tmp_path), backup_shards=3, retention_days=30)
        for i in range(3):
            snap.create_snapshot([{"thought": f"t{i}"}])
        # cleanup compares real file mtimes against ``now() - retention_days`` from the fake
        # clock; a negative retention pushes the cutoff far into the future so all copies expire.
        snap.retention_days = -36500
        removed = snap.cleanup_old_snapshots()
        assert removed == 6
        assert _shard_counts(snap) == [0, 0, 0]
        assert snap.get_latest_snapshot() is None
