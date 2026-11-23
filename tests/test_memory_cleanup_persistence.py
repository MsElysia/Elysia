"""Consolidation/cleanup never reports unsaved removals and tolerates aware stamps.

Exercises ``MemoryCore.consolidate()`` / ``cleanup_old_memories()`` -- the exact
methods monitoring.py, runtime_health.py and ui_control_panel.py call -- over
the current MemoryCore with disposable JSON stores only. Fictional example:
the Pinecrest Allotment Society seed ledger.
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta
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
from project_guardian.memory_cleanup import MemoryCleanup, _parse_memory_time

OLD_SOURCE = "seed-ledger-2025.csv"
NEW_SOURCE = "seed-ledger-2026.csv"


def _old_stamp(days_ago, *, utc_z=False, offset=None):
    moment = (datetime.now() - timedelta(days=days_ago)).replace(microsecond=0)
    if utc_z:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    if offset:
        return moment.isoformat() + offset
    return moment.isoformat()


def _ledger_entry(index, stamp, priority=0.4):
    return {
        "time": stamp,
        "thought": f"Plot {10 + index}: sowed Pinecrest heirloom carrot row {index}",
        "category": "ledger",
        "priority": priority,
        "metadata": {"source": OLD_SOURCE, "row": index},
    }


def _seed(path, entries):
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _open(path):
    return MemoryCore(
        filepath=str(path),
        enable_timeline_logging=False,
        enable_vector_search=False,
    )


def _disk(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _recent_facts(memory):
    memory.remember(
        "Plot 7 row spacing for Pinecrest carrots is 30 cm", "ledger", 0.6,
        {"source": NEW_SOURCE, "fact_id": "spacing", "revision": 1},
    )
    memory.remember(
        "Plot 7 row spacing for Pinecrest carrots is 25 cm (corrected)", "ledger", 0.9,
        {"source": NEW_SOURCE, "fact_id": "spacing", "revision": 2, "supersedes": "spacing#1"},
    )
    memory.remember(
        "Pinecrest seed swap is on the second Saturday of March", "ledger", 0.7,
        {"source": NEW_SOURCE, "fact_id": "swap", "revision": 1},
    )


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / "guardian_memory.json"
    _seed(path, [_ledger_entry(i, _old_stamp(90 + i)) for i in range(5)])
    memory = _open(path)
    _recent_facts(memory)
    assert len(memory.memory_log) == 8
    return path, memory


# --- _parse_memory_time ----------------------------------------------------

@pytest.mark.parametrize(
    "value",
    ["2025-01-15T06:40:00Z", "2025-01-15T06:40:00+00:00", "2025-01-15T08:40:00+02:00"],
)
def test_parse_memory_time_normalizes_aware_stamps_to_naive(value):
    parsed = _parse_memory_time(value, datetime.now())
    assert parsed.tzinfo is None
    # comparable against a naive cutoff without TypeError
    assert parsed < datetime.now()


@pytest.mark.parametrize("value", ["", "   ", None, 42, "not-a-date", "2025-99-99"])
def test_parse_memory_time_falls_back_to_recent_for_malformed(value):
    fallback = datetime(2030, 1, 1, 12, 0, 0)
    assert _parse_memory_time(value, fallback) is fallback


def test_parse_memory_time_keeps_naive_local_stamp():
    stamp = "2025-03-04T05:06:07.123456"
    assert _parse_memory_time(stamp, datetime.now()) == datetime.fromisoformat(stamp)


# --- consolidate_memories: aware stamps -----------------------------------

def test_consolidate_tolerates_imported_z_stamp(tmp_path):
    path = tmp_path / "guardian_memory.json"
    entries = [_ledger_entry(i, _old_stamp(90 + i)) for i in range(5)]
    entries[2]["time"] = _old_stamp(92, utc_z=True)
    entries[3]["time"] = _old_stamp(93, offset="+00:00")
    _seed(path, entries)
    memory = _open(path)
    _recent_facts(memory)

    result = memory.consolidate(max_memories=3, keep_recent_days=30)

    assert result["action"] == "consolidated"
    assert result["action_taken"] is True
    assert result["persisted"] is True
    assert result["removed"] == 5
    assert result["final_count"] == 3
    assert len(memory.memory_log) == 3
    assert len(_disk(path)) == 3
    assert not memory.persistence_blocked


def test_consolidate_keeps_recent_aware_stamp(tmp_path):
    path = tmp_path / "guardian_memory.json"
    entries = [_ledger_entry(i, _old_stamp(90 + i)) for i in range(4)]
    entries.append(_ledger_entry(9, _old_stamp(2, utc_z=True), priority=0.2))
    _seed(path, entries)
    memory = _open(path)

    result = memory.consolidate(max_memories=2, keep_recent_days=30)

    assert result["action"] == "consolidated"
    kept = [m["metadata"]["row"] for m in memory.memory_log]
    assert kept == [9]
    assert _disk(path) == memory.memory_log


# --- consolidate_memories: persistence ------------------------------------

def test_consolidate_success_reports_persisted_and_survives_restart(ledger):
    path, memory = ledger
    before_disk = len(_disk(path))

    result = memory.consolidate(max_memories=3, keep_recent_days=30)

    assert before_disk == 8
    assert result["action"] == "consolidated"
    assert result["persisted"] is True
    assert result["removed"] == 5
    restarted = _open(path)
    assert len(restarted.memory_log) == 3
    hits = restarted.search_memories("row spacing", limit=5)
    assert hits[0]["thought"].endswith("25 cm (corrected)")
    assert hits[0]["metadata"]["source"] == NEW_SOURCE
    assert hits[0]["metadata"]["supersedes"] == "spacing#1"


def test_consolidate_failed_save_restores_memory_and_leaves_disk_untouched(ledger, monkeypatch):
    path, memory = ledger
    before_log = list(memory.memory_log)
    before_bytes = path.read_bytes()

    def failing_save():
        raise OSError("synthetic full disk")

    monkeypatch.setattr(memory, "_save", failing_save)
    result = memory.consolidate(max_memories=3, keep_recent_days=30)

    assert result["action"] == "error"
    assert result["action_taken"] is False
    assert result["no_op_reason"] == "save_failed"
    assert result["persisted"] is False
    assert result["removed"] == 0
    assert result["final_count"] == 8
    assert result["vector_rebuild_status"] == "not_attempted"
    assert "5 removals not persisted" in result["error"]
    assert memory.memory_log == before_log
    assert path.read_bytes() == before_bytes
    assert len(_open(path).memory_log) == 8


def test_consolidate_fenced_stale_writer_keeps_full_live_history(ledger):
    """Another MemoryCore (e.g. the pilot adapter process) committed first."""
    path, memory = ledger
    peer = _open(path)
    peer.remember(
        "Pinecrest compost bay 2 was turned on 2026-11-20", "ledger", 0.7,
        {"source": NEW_SOURCE, "fact_id": "compost", "revision": 1},
    )
    assert len(_disk(path)) == 9
    live_before = list(memory.memory_log)

    result = memory.consolidate(max_memories=3, keep_recent_days=30)

    assert result["action"] == "error"
    assert result["persisted"] is False
    assert result["removed"] == 0
    assert memory.memory_log == live_before
    assert memory.persistence_blocked is True
    assert len(_disk(path)) == 9
    # the live session can still answer from everything it had loaded
    hits = [m["thought"] for m in memory.search_memories("seed swap", limit=3)]
    assert any("second Saturday" in h for h in hits)
    # explicit reload is the documented recovery, after which consolidation works
    memory.load()
    assert memory.persistence_blocked is False
    assert len(memory.memory_log) == 9
    again = memory.consolidate(max_memories=3, keep_recent_days=30)
    assert again["action"] == "consolidated"
    assert again["persisted"] is True
    assert len(_disk(path)) == 3
    assert any("compost bay 2" in m["thought"] for m in _open(path).memory_log)


def test_consolidate_on_blocked_store_is_noop_without_touching_log(ledger):
    path, memory = ledger
    memory.persistence_blocked = True
    memory.last_load_error = "synthetic fence"
    before_log = list(memory.memory_log)
    before_bytes = path.read_bytes()

    result = memory.consolidate(max_memories=3, keep_recent_days=30)

    assert result["action"] == "error"
    assert result["no_op_reason"] == "persistence_blocked"
    assert result["persisted"] is False
    assert result["removed"] == 0
    assert result["error"] == "synthetic fence"
    assert memory.memory_log == before_log
    assert path.read_bytes() == before_bytes


def test_consolidate_on_unreadable_primary_removes_nothing(tmp_path):
    path = tmp_path / "guardian_memory.json"
    path.write_bytes(b"{broken synthetic ledger")
    memory = _open(path)
    assert memory.persistence_blocked

    result = memory.consolidate(max_memories=1, keep_recent_days=30)

    assert result["action_taken"] is False
    assert result["removed"] == 0
    assert path.read_bytes() == b"{broken synthetic ledger"


def test_consolidate_below_threshold_reports_unknown_persistence(ledger):
    path, memory = ledger
    result = memory.consolidate(max_memories=100, keep_recent_days=30)
    assert result["action"] == "no_action_needed"
    assert result["persisted"] is None
    assert len(_disk(path)) == 8


def test_consolidate_legacy_save_returning_none_is_not_reported_as_success(ledger, monkeypatch):
    path, memory = ledger
    monkeypatch.setattr(memory, "_save", lambda: None)
    result = memory.consolidate(max_memories=3, keep_recent_days=30)
    assert result["action"] == "consolidated"
    assert result["persisted"] is None


def test_consolidate_result_keys_are_superset_of_previous_contract(ledger):
    path, memory = ledger
    result = memory.consolidate(max_memories=3, keep_recent_days=30)
    expected = {
        "action", "attempted", "action_taken", "no_op_reason", "original_count", "final_count",
        "removed", "metadata_before", "metadata_after", "faiss_before", "faiss_after",
        "rss_before_mb", "rss_after_mb", "vector_rebuild_status", "vector_rebuild_success",
        "persisted", "error",
    }
    assert expected <= set(result)


# --- cleanup_old_memories ---------------------------------------------------

def test_cleanup_old_memories_tolerates_z_stamp_and_persists(tmp_path):
    path = tmp_path / "guardian_memory.json"
    entries = [_ledger_entry(i, _old_stamp(120 + i), priority=0.1) for i in range(3)]
    entries[1]["time"] = _old_stamp(121, utc_z=True)
    entries.append(_ledger_entry(8, _old_stamp(121), priority=0.9))
    _seed(path, entries)
    memory = _open(path)

    result = memory.cleanup_old_memories(days=90, min_priority=0.3)

    assert result["action"] == "cleaned"
    assert result["removed"] == 3
    assert result["persisted"] is True
    assert [m["metadata"]["row"] for m in memory.memory_log] == [8]
    assert _disk(path) == memory.memory_log


def test_cleanup_old_memories_failed_save_restores_memory(ledger, monkeypatch):
    path, memory = ledger
    before_log = list(memory.memory_log)
    before_bytes = path.read_bytes()
    monkeypatch.setattr(memory, "_save", lambda: (_ for _ in ()).throw(OSError("synthetic")))

    result = memory.cleanup_old_memories(days=30, min_priority=0.5)

    assert result["action"] == "error"
    assert result["persisted"] is False
    assert result["removed"] == 0
    assert memory.memory_log == before_log
    assert path.read_bytes() == before_bytes


def test_cleanup_old_memories_blocked_store_is_noop(ledger):
    path, memory = ledger
    memory.persistence_blocked = True
    before_bytes = path.read_bytes()
    result = memory.cleanup_old_memories(days=30, min_priority=0.5)
    assert result["action"] == "error"
    assert result["no_op_reason"] == "persistence_blocked"
    assert len(memory.memory_log) == 8
    assert path.read_bytes() == before_bytes


# --- normal runtime path: monitoring.SystemMonitor._perform_cleanup ---------

def _monitor(memory):
    monitoring = pytest.importorskip("project_guardian.monitoring")

    class MockGuardian:
        config = {}
        memory = None
        web_reader = None
        proposal_system = None

    guardian = MockGuardian()
    guardian.memory = memory
    return monitoring, monitoring.SystemMonitor(memory, guardian)


def _large_ledger(path, n_old=60):
    entries = [_ledger_entry(i, _old_stamp(100 + i, utc_z=(i % 7 == 0))) for i in range(n_old)]
    _seed(path, entries)
    memory = _open(path)
    memory.remember(
        "Plot 7 row spacing for Pinecrest carrots is 25 cm (corrected)", "ledger", 0.9,
        {"source": NEW_SOURCE, "fact_id": "spacing", "revision": 2, "supersedes": "spacing#1"},
    )
    return memory


def test_monitor_count_threshold_cleanup_consolidates_with_z_stamps(tmp_path):
    path = tmp_path / "guardian_memory.json"
    memory = _large_ledger(path)
    monitoring, monitor = _monitor(memory)

    result = monitor._perform_cleanup(
        memory_threshold=20, reason=monitoring.CLEANUP_REASON_MEMORY_COUNT_THRESHOLD
    )

    assert result["outcome"] == monitoring.CLEANUP_OUTCOME_CONSOLIDATED
    assert result["action_taken"] is True
    assert result["memory_after"] <= 20
    assert len(_disk(path)) == len(memory.memory_log) == result["memory_after"]
    assert _open(path).search_memories("row spacing", limit=1)[0]["metadata"]["supersedes"] == "spacing#1"


def test_monitor_cleanup_with_fenced_writer_does_not_force_trim_live_log(tmp_path):
    path = tmp_path / "guardian_memory.json"
    memory = _large_ledger(path)
    monitoring, monitor = _monitor(memory)
    peer = _open(path)
    peer.remember("Pinecrest compost bay 2 was turned on 2026-11-20", "ledger", 0.7,
                  {"source": NEW_SOURCE, "fact_id": "compost", "revision": 1})
    live_before = list(memory.memory_log)
    disk_before = path.read_bytes()

    result = monitor._perform_cleanup(
        memory_threshold=20, reason=monitoring.CLEANUP_REASON_MEMORY_COUNT_THRESHOLD
    )

    assert result["action_taken"] is False
    assert result["no_op_reason"] == "save_failed"
    assert result["outcome"] == monitoring.CLEANUP_OUTCOME_FAILED
    # neither consolidation nor monitoring's force-trim may truncate the live log
    assert memory.memory_log == live_before
    assert path.read_bytes() == disk_before
    assert memory.persistence_blocked is True
    memory.load()
    assert len(memory.memory_log) == len(live_before) + 1


def test_memory_cleanup_direct_consolidate_matches_core_wrapper(ledger):
    path, memory = ledger
    result = MemoryCleanup(memory).consolidate_memories(max_memories=3, keep_recent_days=30)
    assert result["action"] == "consolidated"
    assert result["persisted"] is True
    assert len(_disk(path)) == 3
