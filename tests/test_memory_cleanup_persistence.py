"""
Tests for project_guardian/memory_cleanup.py consolidation honesty.

Covers two defects reproduced on main:

1. A single memory whose ``time`` carries a UTC ``Z`` / ``+HH:MM`` offset
   (imported or merged records) raised ``TypeError`` when compared against the
   naive cutoff, so every consolidation/cleanup pass returned ``action=error``
   and nothing was ever removed.
2. ``consolidate_memories`` / ``cleanup_old_memories`` truncated the in-memory
   log, then reported ``consolidated`` / ``cleaned`` with ``removed=N`` even
   when ``_save()`` failed. The disk still held the full history, so the live
   session recalled nothing until restart while the report claimed success.

Modules are loaded by file path with a stub ``project_guardian`` package
because ``import project_guardian`` fails on main (``module_activity``
missing). ``project_guardian.memory_vector`` is stubbed because the real
module needs NumPy; only ``VECTOR_REBUILD_SAFE_MAX`` and ``VectorMemory`` are
referenced by the consolidation path.
"""

import importlib.util
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PG_DIR = PROJECT_ROOT / "project_guardian"


def _install_stub_package():
    if "project_guardian" not in sys.modules or not hasattr(sys.modules["project_guardian"], "__path__"):
        pkg = types.ModuleType("project_guardian")
        pkg.__path__ = [str(PG_DIR)]
        sys.modules["project_guardian"] = pkg
    if "project_guardian.memory_vector" not in sys.modules:
        mv = types.ModuleType("project_guardian.memory_vector")
        mv.VECTOR_REBUILD_SAFE_MAX = 10000

        class VectorMemory:  # pragma: no cover - placeholder type only
            pass

        mv.VectorMemory = VectorMemory
        sys.modules["project_guardian.memory_vector"] = mv


def _load(name: str):
    _install_stub_package()
    full = f"project_guardian.{name}"
    if full in sys.modules and getattr(sys.modules[full], "__file__", None):
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PG_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cleanup_mod():
    return _load("memory_cleanup")


@pytest.fixture(scope="module")
def memory_mod():
    return _load("memory")


class FakeCore:
    """Minimal MemoryCore stand-in with a controllable ``_save`` outcome."""

    def __init__(self, log, save_outcome=True):
        self.memory_log = log
        self.save_outcome = save_outcome
        self.save_calls = 0

    def _save(self):
        self.save_calls += 1
        if isinstance(self.save_outcome, Exception):
            raise self.save_outcome
        return self.save_outcome


def _old_iso(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat()


def _entry(thought, *, time, priority=0.2, source=None):
    return {
        "time": time,
        "thought": thought,
        "category": "harbor",
        "priority": priority,
        "metadata": {"source": source} if source else {},
    }


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


def test_parse_memory_time_naive_passthrough(cleanup_mod):
    now = datetime(2026, 1, 1, 12, 0, 0)
    assert cleanup_mod._parse_memory_time("2025-06-01T10:20:30", now) == datetime(2025, 6, 1, 10, 20, 30)


def test_parse_memory_time_aware_becomes_naive_and_comparable(cleanup_mod):
    now = datetime.now()
    parsed = cleanup_mod._parse_memory_time("2025-06-01T10:20:30Z", now)
    assert parsed.tzinfo is None
    assert parsed < now  # comparison with naive datetime no longer raises
    expected = datetime(2025, 6, 1, 10, 20, 30, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert parsed == expected


@pytest.mark.parametrize("bad", ["", "   ", None, 12345, "not-a-date", "2025-13-45T99:99:99"])
def test_parse_memory_time_malformed_falls_back_to_recent(cleanup_mod, bad):
    now = datetime(2026, 1, 1)
    assert cleanup_mod._parse_memory_time(bad, now) is now


# ---------------------------------------------------------------------------
# Aware timestamps no longer abort consolidation
# ---------------------------------------------------------------------------


def test_consolidate_handles_imported_utc_timestamp(cleanup_mod):
    log = [_entry(f"old {i}", time=_old_iso(400)) for i in range(5)]
    log.append(_entry("imported", time="2024-03-01T00:00:00Z", source="tide-export-2024.json"))
    log.append(_entry("recent", time=datetime.now().isoformat()))
    core = FakeCore(log)

    result = cleanup_mod.MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=30)

    assert result["action"] == "consolidated"
    assert result["error"] is None
    assert result["removed"] == 6
    assert [m["thought"] for m in core.memory_log] == ["recent"]
    assert core.save_calls == 1


def test_cleanup_old_memories_handles_imported_utc_timestamp(cleanup_mod):
    log = [
        _entry("old low", time=_old_iso(400), priority=0.1),
        _entry("imported old low", time="2024-03-01T00:00:00+00:00", priority=0.1, source="tide-export-2024.json"),
        _entry("imported old high", time="2024-03-01T00:00:00Z", priority=0.9, source="tide-export-2024.json"),
    ]
    core = FakeCore(log)

    result = cleanup_mod.MemoryCleanup(core).cleanup_old_memories(days=90, min_priority=0.3)

    assert result["action"] == "cleaned"
    assert result["removed"] == 2
    assert [m["thought"] for m in core.memory_log] == ["imported old high"]
    assert core.memory_log[0]["metadata"]["source"] == "tide-export-2024.json"


# ---------------------------------------------------------------------------
# Failed writes are never reported as successful removals
# ---------------------------------------------------------------------------


def test_consolidate_save_failure_restores_log_and_reports_failure(cleanup_mod):
    log = [_entry(f"old {i}", time=_old_iso(400)) for i in range(20)]
    original = list(log)
    core = FakeCore(log, save_outcome=False)

    result = cleanup_mod.MemoryCleanup(core).consolidate_memories(max_memories=5, keep_recent_days=30)

    assert result["action"] == "save_failed"
    assert result["action_taken"] is False
    assert result["no_op_reason"] == "save_failed"
    assert result["removed"] == 0
    assert result["final_count"] == 20
    assert result["persisted"] is False
    assert result["vector_rebuild_status"] == "not_attempted"
    assert "20 removals not persisted" in result["error"]
    assert core.memory_log == original


def test_consolidate_save_raising_is_a_failure(cleanup_mod):
    log = [_entry(f"old {i}", time=_old_iso(400)) for i in range(6)]
    core = FakeCore(log, save_outcome=OSError("disk full"))

    result = cleanup_mod.MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=30)

    assert result["action"] == "save_failed"
    assert result["action_taken"] is False
    assert len(core.memory_log) == 6


def test_cleanup_old_memories_save_failure_restores_log(cleanup_mod):
    log = [_entry(f"old {i}", time=_old_iso(400), priority=0.1) for i in range(4)]
    original = list(log)
    core = FakeCore(log, save_outcome=False)

    result = cleanup_mod.MemoryCleanup(core).cleanup_old_memories(days=90, min_priority=0.3)

    assert result["action"] == "save_failed"
    assert result["removed"] == 0
    assert result["persisted"] is False
    assert core.memory_log == original


def test_legacy_save_returning_none_is_reported_as_unknown(cleanup_mod):
    """A ``_save`` that returns None (main's MemoryCore) cannot confirm the write.

    The removal still proceeds (behaviour unchanged) but ``persisted`` is None,
    never True.
    """
    log = [_entry(f"old {i}", time=_old_iso(400)) for i in range(6)]
    core = FakeCore(log, save_outcome=None)

    result = cleanup_mod.MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=30)

    assert result["action"] == "consolidated"
    assert result["persisted"] is None
    assert len(core.memory_log) == 0


def test_consolidate_success_reports_persisted_true(cleanup_mod):
    log = [_entry(f"old {i}", time=_old_iso(400)) for i in range(6)]
    core = FakeCore(log, save_outcome=True)

    result = cleanup_mod.MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=30)

    assert result["action"] == "consolidated"
    assert result["persisted"] is True
    assert result["action_taken"] is True


def test_vector_reconcile_not_reached_when_save_fails(cleanup_mod):
    class VectorStub:
        def __init__(self):
            self.metadata = [1, 2, 3]
            self.reconciled = False
            self.degraded = False

        def _reconcile_with_memories(self, memories, safe_max):
            self.reconciled = True
            return {"metadata_after": len(memories), "faiss_after": len(memories),
                    "vector_rebuild_status": "rebuilt", "vector_rebuild_success": True}

    class Enhanced:
        def __init__(self, json_memory, vector_memory):
            self.json_memory = json_memory
            self.vector_memory = vector_memory

    json_core = FakeCore([_entry(f"old {i}", time=_old_iso(400)) for i in range(6)], save_outcome=False)
    vec = VectorStub()
    result = cleanup_mod.MemoryCleanup(Enhanced(json_core, vec)).consolidate_memories(max_memories=2)

    assert result["action"] == "save_failed"
    assert vec.reconciled is False
    assert vec.degraded is False
    assert len(json_core.memory_log) == 6


# ---------------------------------------------------------------------------
# End to end through the real MemoryCore JSON history (disposable store)
# ---------------------------------------------------------------------------


def test_real_memory_core_consolidation_survives_restart(tmp_path, cleanup_mod, memory_mod):
    """Harbor Lantern tide tables: 6 facts (1 imported with a UTC stamp), consolidate,
    restart from disk, recall only what the report said was kept."""
    store = tmp_path / "harbor_lantern_memory.json"
    core = memory_mod.MemoryCore(filepath=str(store), enable_timeline_logging=False)

    facts = [
        ("High tide at Lantern Quay is 06:40 on spring days", 0.3),
        ("Low tide at Lantern Quay is 12:55 on spring days", 0.3),
        ("Ferry to Gull Rock skips the 07:00 run in winter", 0.3),
        ("Harbor master prefers the north mooring for dinghies", 0.9),
        ("Correction: ferry skips the 07:30 run, not 07:00", 0.5),
    ]
    for thought, priority in facts:
        core.remember(thought, category="harbor", priority=priority, metadata={"source": "tide-table-2026.pdf"})
    assert len(core.memory_log) == 5

    # Backdate everything except the correction; one entry carries an imported UTC stamp.
    core.memory_log[0]["time"] = _old_iso(400)
    core.memory_log[1]["time"] = "2025-01-15T06:40:00Z"
    core.memory_log[2]["time"] = _old_iso(200)
    core.memory_log[3]["time"] = _old_iso(300)
    core._save()
    on_disk_before = json.loads(store.read_text(encoding="utf-8"))
    assert len(on_disk_before) == 5

    result = cleanup_mod.MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=30)

    assert result["action"] == "consolidated"
    assert result["error"] is None
    assert result["removed"] == 3
    kept = [m["thought"] for m in core.memory_log]
    assert kept == [
        "Correction: ferry skips the 07:30 run, not 07:00",
        "Harbor master prefers the north mooring for dinghies",
    ]
    # Provenance travels with the kept records.
    assert all(m["metadata"]["source"] == "tide-table-2026.pdf" for m in core.memory_log)

    # Restart: a fresh core reading the same store sees exactly the kept set.
    restarted = memory_mod.MemoryCore(filepath=str(store), enable_timeline_logging=False)
    assert [m["thought"] for m in restarted.memory_log] == kept
    hits = restarted.search_memories("ferry", limit=5)
    assert len(hits) == 1
    assert hits[0]["thought"].startswith("Correction:")
    assert hits[0]["metadata"]["source"] == "tide-table-2026.pdf"


def test_real_memory_core_failed_write_keeps_disk_as_recall_source(tmp_path, cleanup_mod, memory_mod, monkeypatch):
    store = tmp_path / "harbor_lantern_memory.json"
    core = memory_mod.MemoryCore(filepath=str(store), enable_timeline_logging=False)
    for i in range(6):
        core.remember(f"Mooring note {i}", category="harbor", priority=0.3, metadata={"source": "logbook.txt"})
    for m in core.memory_log:
        m["time"] = _old_iso(400)
    core._save()
    disk_before = store.read_bytes()

    # Simulate a save that reports failure (the contract returned by a bool-returning _save).
    monkeypatch.setattr(core, "_save", lambda: False)
    result = cleanup_mod.MemoryCleanup(core).consolidate_memories(max_memories=2, keep_recent_days=30)

    assert result["action"] == "save_failed"
    assert result["removed"] == 0
    assert len(core.memory_log) == 6
    assert store.read_bytes() == disk_before

    restarted = memory_mod.MemoryCore(filepath=str(store), enable_timeline_logging=False)
    assert len(restarted.memory_log) == 6
