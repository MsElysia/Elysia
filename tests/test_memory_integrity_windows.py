"""MemoryCore preservation and recovery regressions with disposable JSON only.

Exercises the current Windows MemoryCore; not a replacement memory subsystem.
"""
from __future__ import annotations

import json
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


def _store(tmp_path, *, max_memories=None, lazy_load=False):
    path = tmp_path / "guardian_memory.json"
    return path, MemoryCore(
        filepath=str(path),
        max_memories=max_memories,
        lazy_load=lazy_load,
        enable_timeline_logging=False,
        enable_vector_search=False,
    )


def test_write_restarts_with_authoritative_memory(tmp_path):
    path, memory = _store(tmp_path)
    memory.remember("Synthetic city Harborview has a stone lighthouse", category="fact", priority=0.9)
    fresh = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    assert fresh.dump_all() == memory.dump_all()
    assert fresh.dump_all()[-1]["thought"].endswith("stone lighthouse")
    assert fresh.get_memory_state()["memory_count_authoritative"] is True


def test_failed_write_restores_evicted_history_and_does_not_poison_retry(tmp_path, monkeypatch):
    path, memory = _store(tmp_path, max_memories=2)
    memory.remember("Synthetic cafe Lanternfish serves cinnamon biscuits", priority=0.9)
    memory.remember("Synthetic cafe Lanternfish is closed on Sundays", priority=0.9)
    before = memory.dump_all()
    before_bytes = path.read_bytes()
    with monkeypatch.context() as bad:
        bad.setattr(memory, "_save", lambda: (_ for _ in ()).throw(OSError("synthetic full disk")))
        with pytest.raises(OSError, match="synthetic full disk"):
            memory.remember("Synthetic attempt must not evict a previous memory", priority=0.9)
    assert memory.dump_all() == before
    assert path.read_bytes() == before_bytes
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == before
    memory.remember("Synthetic cafe Lanternfish now accepts payments", priority=0.9)
    assert len(memory.dump_all()) == 2
    assert memory.dump_all()[0] == before[1]
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == memory.dump_all()


@pytest.mark.parametrize("raw", [b"{broken synthetic memory", b'{"not":"a list"}', b'[1, 2]'])
def test_corrupt_or_malformed_history_never_overwritten(tmp_path, raw):
    path = tmp_path / "guardian_memory.json"
    path.write_bytes(raw)
    memory = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    state = memory.get_memory_state()
    assert state["persistence_blocked"] is True
    assert state["memory_count"] is None
    assert state["memory_count_authoritative"] is False
    assert memory.get_memory_count() is None
    with pytest.raises(RuntimeError, match="persistence blocked"):
        memory.remember("Synthetic entry must not overwrite existing broken bytes", priority=0.9)
    assert path.read_bytes() == raw
    assert memory.dump_all() == []


def test_recovery_requires_explicit_valid_reload(tmp_path):
    path = tmp_path / "guardian_memory.json"
    raw = b'{"historical":"unreadable bytes'
    path.write_bytes(raw)
    memory = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    assert memory.persistence_blocked
    with pytest.raises(RuntimeError, match="persistence blocked"):
        memory.forget()
    assert path.read_bytes() == raw
    # Simulated operator-controlled repair uses synthetic data only.
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="persistence blocked"):
        memory.remember("Synthetic repair not yet explicitly verified", priority=0.9)
    memory.load()
    assert memory.persistence_blocked is False
    assert memory.last_load_error is None
    memory.remember("Synthetic repaired memory persists after explicit reload", priority=0.9)
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == memory.dump_all()


def test_missing_unreadable_file_does_not_automatically_clear_fence(tmp_path):
    path = tmp_path / "guardian_memory.json"
    path.write_bytes(b"unreadable synthetic")
    memory = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    assert memory.persistence_blocked
    path.unlink()  # Synthetic deliberate external action, not production behavior.
    memory.load()
    assert memory.persistence_blocked
    with pytest.raises(RuntimeError, match="persistence blocked"):
        memory.remember("Synthetic missing original must not permit recreation", priority=0.9)
    assert not path.exists()


def test_lazy_load_fails_closed_and_reports_not_authoritative(tmp_path):
    path = tmp_path / "guardian_memory.json"
    raw = b"{invalid synthetic"
    path.write_bytes(raw)
    memory = MemoryCore(filepath=str(path), lazy_load=True, enable_timeline_logging=False)
    assert memory.is_loaded() is False
    assert memory.get_memory_count() is None
    memory.load_if_needed()
    assert memory.persistence_blocked
    assert memory.get_memory_state()["memory_count_authoritative"] is False
    with pytest.raises(RuntimeError, match="persistence blocked"):
        memory.remember("Synthetic deferred load must not overwrite broken history", priority=0.9)
    assert path.read_bytes() == raw


def test_optional_usb_mirror_failure_does_not_fake_primary_failure(tmp_path, monkeypatch):
    mirror = types.ModuleType("memory_storage_config")
    def failed_mirror(*_args):
        raise OSError("synthetic USB unavailable")
    mirror.notify_usb_persist_mirror = failed_mirror
    monkeypatch.setitem(sys.modules, "memory_storage_config", mirror)
    path, memory = _store(tmp_path)
    memory.remember("Synthetic primary memory must survive optional USB error", priority=0.9)
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == memory.dump_all()


def test_failed_disk_commit_does_not_publish_secondary_events(tmp_path, monkeypatch):
    path, memory = _store(tmp_path)
    timeline = types.SimpleNamespace(log_event=lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected event")))
    memory.timeline = timeline
    memory.enable_timeline_logging = True
    with monkeypatch.context() as bad:
        bad.setattr(memory, "_save", lambda: (_ for _ in ()).throw(OSError("synthetic failed commit")))
        with pytest.raises(OSError, match="synthetic failed commit"):
            memory.remember("Synthetic rejected memory must not reach timeline", priority=0.9)
    assert memory.dump_all() == []
    assert not path.exists()
