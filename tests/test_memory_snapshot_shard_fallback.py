"""Backup shards must be readable for recovery, not write-only.

Exercises ``MemorySnapshot.get_latest_snapshot`` / ``load_snapshot`` /
``restore_from_snapshot`` -- the selection and recovery path
``GuardianCore.restore_memory_from_snapshot`` and
``ErrorHandler._recover_memory_error`` rely on -- against the real
``MemoryCore`` on disposable JSON stores only. A damaged ``snapshot_*.json``
in the snapshot dir must not shadow its intact copy in a backup shard.
Fictional example: the Bramblewick Lighthouse keeper's log.
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

from project_guardian.error_handler import ErrorCategory, ErrorHandler, ErrorSeverity
from project_guardian.memory import MemoryCore
from project_guardian.memory_snapshot import MemorySnapshot

SOURCE = "keeper-log-2026.csv"
FACTS = [
    ("Bramblewick light shows two white flashes every 15 seconds.", 0.7, {"source": SOURCE, "row": 4}),
    ("Bramblewick fog signal is tested on the first Monday of each month.", 0.6, {"source": SOURCE, "row": 9}),
    ("Bramblewick lamp oil delivery arrives by the Tuesday supply boat.", 0.6, {"source": SOURCE, "row": 15}),
]
CORRECTION = (
    "Correction: Bramblewick light shows THREE white flashes every 15 seconds, not two.",
    0.9,
    {"source": SOURCE, "row": 22, "revision": 2, "supersedes": "flash-pattern#1"},
)
CORRUPT_PRIMARY = '[{"thought": "Bramblewick light'


def _core(path: Path, **kwargs) -> MemoryCore:
    kwargs.setdefault("enable_timeline_logging", False)
    return MemoryCore(str(path), **kwargs)


def _reload(path: Path) -> MemoryCore:
    mem = _core(path)
    mem.load_if_needed()
    return mem


def _truncate(path: Path) -> bytes:
    data = path.read_bytes()
    damaged = data[: len(data) // 2]
    path.write_bytes(damaged)
    return damaged


def _bump_mtime(path: Path, seconds: float) -> None:
    stat = path.stat()
    os.utime(path, (stat.st_atime + seconds, stat.st_mtime + seconds))


def _shard_copy(mgr: MemorySnapshot, snapshot: Path) -> Path:
    copies = [d / snapshot.name for d in mgr.shard_dirs if (d / snapshot.name).exists()]
    assert len(copies) == 1, copies
    return copies[0]


@pytest.fixture
def store(tmp_path):
    """Primary with 3 facts + correction, one durable snapshot with a shard copy."""
    primary = tmp_path / "store" / "guardian_memory.json"
    primary.parent.mkdir()
    mem = _core(primary)
    for thought, priority, metadata in FACTS:
        mem.remember(thought, "fact", priority, metadata)
    mem.remember(CORRECTION[0], "fact", CORRECTION[1], CORRECTION[2])
    assert len(json.loads(primary.read_bytes())) == 4
    mgr = MemorySnapshot(snapshot_dir=str(tmp_path / "snapshots"), backup_shards=3)
    snapshot = Path(mgr.create_snapshot(mem.dump_all(), metadata={"source": SOURCE}))
    assert mgr.last_snapshot_report["shard_copied"] is True
    return primary, mem, mgr, snapshot


# --- selection -----------------------------------------------------------------


def test_intact_snapshot_is_selected_from_snapshot_dir(store):
    _primary, _mem, mgr, snapshot = store
    assert mgr.get_latest_snapshot() == str(snapshot)


def test_damaged_newest_copy_yields_its_intact_shard_copy(store):
    _primary, _mem, mgr, snapshot = store
    shard = _shard_copy(mgr, snapshot)
    _truncate(snapshot)

    assert mgr.get_latest_snapshot() == str(shard)
    # The damaged original is left in place for inspection, never deleted or rewritten.
    assert snapshot.exists()


def test_malformed_json_copy_is_treated_like_unreadable(store):
    _primary, _mem, mgr, snapshot = store
    shard = _shard_copy(mgr, snapshot)
    snapshot.write_text(json.dumps({"timestamp": "x", "memories": "not-a-list"}), encoding="utf-8")

    assert mgr.get_latest_snapshot() == str(shard)
    assert mgr.load_snapshot(str(snapshot))["memory_count"] == 4


def test_snapshot_with_no_readable_copy_falls_back_to_older_snapshot(store):
    _primary, mem, mgr, older = store
    newer = Path(mgr.create_snapshot(mem.dump_all()))
    assert newer != older
    _bump_mtime(newer, 60)
    _bump_mtime(_shard_copy(mgr, newer), 60)
    _truncate(newer)
    _truncate(_shard_copy(mgr, newer))

    assert mgr.get_latest_snapshot() == str(older)


def test_no_readable_snapshot_anywhere_returns_none(store):
    _primary, _mem, mgr, snapshot = store
    _truncate(snapshot)
    _truncate(_shard_copy(mgr, snapshot))

    assert mgr.get_latest_snapshot() is None
    assert mgr.load_snapshot(str(snapshot)) is None


def test_shard_only_snapshot_is_still_recoverable(store):
    _primary, _mem, mgr, snapshot = store
    shard = _shard_copy(mgr, snapshot)
    snapshot.unlink()

    assert mgr.get_latest_snapshot() == str(shard)


def test_latest_daily_snapshot_skips_unreadable_file(store):
    _primary, mem, mgr, _snapshot = store
    daily = Path(mgr.create_daily_snapshot(mem.dump_all()))
    assert mgr.get_latest_daily_snapshot() == str(daily)
    _truncate(daily)
    assert mgr.get_latest_daily_snapshot() is None


def test_no_snapshots_at_all_returns_none(tmp_path):
    mgr = MemorySnapshot(snapshot_dir=str(tmp_path / "empty"), backup_shards=3)
    assert mgr.get_latest_snapshot() is None
    assert mgr.get_latest_daily_snapshot() is None


# --- load fallback ---------------------------------------------------------------


def test_load_snapshot_uses_shard_copy_when_primary_copy_damaged(store):
    _primary, _mem, mgr, snapshot = store
    damaged = _truncate(snapshot)

    data = mgr.load_snapshot(str(snapshot))

    assert data is not None and data["memory_count"] == 4
    assert [m["thought"] for m in data["memories"]][-1] == CORRECTION[0]
    assert snapshot.read_bytes() == damaged


def test_load_snapshot_given_shard_path_falls_back_to_snapshot_dir_copy(store):
    _primary, _mem, mgr, snapshot = store
    shard = _shard_copy(mgr, snapshot)
    _truncate(shard)

    data = mgr.load_snapshot(str(shard))
    assert data is not None and data["memory_count"] == 4


def test_load_snapshot_unknown_path_returns_none(store):
    _primary, _mem, mgr, _snapshot = store
    assert mgr.load_snapshot(str(mgr.snapshot_dir / "snapshot_never_written.json")) is None


# --- restore through the fallback -------------------------------------------------


def test_restore_from_damaged_snapshot_path_recovers_via_shard(store):
    primary, _mem, mgr, snapshot = store
    shard = _shard_copy(mgr, snapshot)
    damaged = _truncate(snapshot)
    primary.write_text(CORRUPT_PRIMARY, encoding="utf-8")

    fenced = _reload(primary)
    assert fenced.persistence_blocked is True and fenced.memory_log == []

    assert mgr.restore_from_snapshot(str(snapshot), fenced) is True
    report = mgr.last_restore_report
    assert report["snapshot_path"] == str(snapshot)
    assert report["source_path"] == str(shard)
    assert report["restored"] == 4 and report["persisted"] is True and report["error"] is None
    assert Path(report["preserved_original"]).read_text(encoding="utf-8") == CORRUPT_PRIMARY
    assert snapshot.read_bytes() == damaged

    restarted = _reload(primary)
    assert restarted.persistence_blocked is False
    assert len(restarted.memory_log) == 4
    hits = restarted.search_memories("flashes")
    assert hits and hits[0]["thought"] == CORRECTION[0]
    assert hits[0]["metadata"] == CORRECTION[2]

    restarted.remember("Bramblewick keeper rota changes on 1 December.", "fact", 0.5, {"source": SOURCE, "row": 30})
    assert len(json.loads(primary.read_bytes())) == 5


def test_restore_with_no_readable_copy_leaves_target_untouched(store):
    primary, _mem, mgr, snapshot = store
    _truncate(snapshot)
    _truncate(_shard_copy(mgr, snapshot))
    primary.write_text(CORRUPT_PRIMARY, encoding="utf-8")
    fenced = _reload(primary)

    assert mgr.restore_from_snapshot(str(snapshot), fenced) is False
    report = mgr.last_restore_report
    assert report["error"].startswith("snapshot unreadable (unreadable: JSONDecodeError")
    assert report["source_path"] is None
    assert primary.read_text(encoding="utf-8") == CORRUPT_PRIMARY
    assert fenced.persistence_blocked is True
    assert not list(primary.parent.glob("*.pre-restore.*"))


def test_restore_from_intact_snapshot_reports_itself_as_source(store):
    primary, _mem, mgr, snapshot = store
    primary.write_text(CORRUPT_PRIMARY, encoding="utf-8")
    fenced = _reload(primary)

    assert mgr.restore_from_snapshot(str(snapshot), fenced) is True
    assert mgr.last_restore_report["source_path"] == str(snapshot)


def test_error_handler_restore_instruction_recovers_via_shard(store):
    """The real ErrorHandler picks the newest listed snapshot; a damaged one must still restore."""
    primary, _mem, mgr, snapshot = store
    shard = _shard_copy(mgr, snapshot)
    _truncate(snapshot)
    primary.write_text(CORRUPT_PRIMARY, encoding="utf-8")
    fenced = _reload(primary)

    handler = ErrorHandler(memory_snapshot=mgr)
    # The message MemoryCore raises for a fenced primary ("JSONDecodeError: ...").
    assert fenced.last_load_error and fenced.last_load_error.startswith("JSONDecodeError")
    instruction = handler.handle_error(
        RuntimeError(fenced.last_load_error),
        ErrorCategory.MEMORY,
        ErrorSeverity.ERROR,
        component="MemoryCore",
        operation="load",
    )
    assert instruction["action"] == "restore_snapshot"
    assert instruction["snapshot_path"] == str(snapshot)

    assert mgr.restore_from_snapshot(instruction["snapshot_path"], fenced) is True
    assert mgr.last_restore_report["source_path"] == str(shard)
    assert len(_reload(primary).memory_log) == 4
