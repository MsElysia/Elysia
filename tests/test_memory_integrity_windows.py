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


def test_two_loaded_instances_never_erase_external_commit(tmp_path):
    """Two real MemoryCore instances; a stale save must not erase a peer's bytes."""
    path, stale = _store(tmp_path)
    peer = MemoryCore(filepath=str(path), enable_timeline_logging=False, enable_vector_search=False)
    peer.remember("Synthetic peer record must remain in authoritative history", priority=0.9)
    peer_bytes = path.read_bytes()
    peer_records = MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()

    try:
        stale.remember("Synthetic stale record must not overwrite peer history", priority=0.9)
    except RuntimeError as exc:
        assert "stale" in str(exc).lower() or "changed" in str(exc).lower() or "reload" in str(exc).lower()
    else:
        # On the test-first baseline this assertion reveals the actual lost bytes.
        assert path.read_bytes() == peer_bytes, "Stale writer overwrote peer's durable bytes"
        pytest.fail("Stale writer committed without detecting the peer's intervening write")

    assert path.read_bytes() == peer_bytes
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == peer_records
    assert stale.persistence_blocked
    assert stale.get_memory_stats()["memory_count_authoritative"] is False
    with pytest.raises(RuntimeError):
        stale.remember("Synthetic stale retry also must not overwrite peer", priority=0.9)
    assert path.read_bytes() == peer_bytes

    stale.load()
    assert not stale.persistence_blocked
    stale.remember("Synthetic fresh write after explicit reload remains durable", priority=0.9)
    restarted = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    assert len(restarted.dump_all()) == 2
    assert restarted.dump_all()[0] == peer_records[0]


def test_stale_eviction_restores_local_snapshot(tmp_path):
    path, stale = _store(tmp_path, max_memories=2)
    stale.remember("Synthetic first record retained before eviction", priority=0.9)
    stale.remember("Synthetic second record retained before eviction", priority=0.9)
    local_before = stale.dump_all()
    peer = MemoryCore(filepath=str(path), max_memories=2, enable_timeline_logging=False)
    peer.remember("Synthetic peer third record must not be deleted", priority=0.9)
    peer_bytes = path.read_bytes()
    with pytest.raises(RuntimeError, match="stale|reload|changed"):
        stale.remember("Synthetic stale eviction attempt must roll back", priority=0.9)
    assert stale.dump_all() == local_before
    assert stale.get_memory_count() is None
    assert path.read_bytes() == peer_bytes
    stale.load()
    stale.remember("Synthetic safe post-reload eviction and write", priority=0.9)
    restarted = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    assert [record["thought"] for record in restarted.dump_all()] == [
        "Synthetic peer third record must not be deleted",
        "Synthetic safe post-reload eviction and write",
    ]


def test_stale_forget_and_direct_save_cannot_erase_peer(tmp_path):
    path, stale = _store(tmp_path)
    stale.remember("Synthetic shared history is preserved", priority=0.9)
    peer = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    peer.remember("Synthetic external history must survive stale delete", priority=0.9)
    peer_bytes = path.read_bytes()
    with pytest.raises(RuntimeError, match="stale|reload|changed"):
        stale.forget()
    with pytest.raises(RuntimeError, match="blocked"):
        stale._save()
    assert path.read_bytes() == peer_bytes
    assert len(MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()) == 2


def test_missing_primary_after_load_does_not_get_recreated(tmp_path):
    path, stale = _store(tmp_path)
    stale.remember("Synthetic history initially stored before deletion", priority=0.9)
    saved = path.read_bytes()
    path.unlink()  # Only the disposable test fixture is modified.
    with pytest.raises(RuntimeError, match="stale|reload|changed"):
        stale.remember("Synthetic missing primary must not be replaced", priority=0.9)
    assert not path.exists()
    stale.load()
    assert stale.persistence_blocked
    with pytest.raises(RuntimeError, match="blocked"):
        stale.remember("Synthetic missing primary unsafe retry", priority=0.9)
    path.write_bytes(saved)  # Simulate deliberate recovery of original bytes.
    stale.load()
    assert not stale.persistence_blocked
    stale.remember("Synthetic recovered history survives restart", priority=0.9)
    assert len(MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()) == 2


def test_corrupt_primary_replacement_preserved_and_reload_required(tmp_path):
    path, stale = _store(tmp_path)
    stale.remember("Synthetic good record before external corruption", priority=0.9)
    saved = path.read_bytes()
    unreadable = b"{synthetic corrupted external primary"
    path.write_bytes(unreadable)
    with pytest.raises(RuntimeError, match="stale|reload|changed"):
        stale.remember("Synthetic corruption must remain untouched", priority=0.9)
    assert path.read_bytes() == unreadable
    stale.load()
    assert stale.persistence_blocked
    assert path.read_bytes() == unreadable
    path.write_bytes(saved)
    with pytest.raises(RuntimeError, match="blocked"):
        stale.remember("Synthetic still blocked until explicit reload", priority=0.9)
    stale.load()
    assert not stale.persistence_blocked
    assert stale.dump_all()[0]["thought"] == "Synthetic good record before external corruption"


def test_failed_primary_read_fences_until_explicit_reload(tmp_path, monkeypatch):
    import builtins
    path, stale = _store(tmp_path)
    stale.remember("Synthetic before denied checksum read", priority=0.9)
    before = path.read_bytes()
    real_open = builtins.open

    def deny_primary_read(filename, mode="r", *args, **kwargs):
        if str(filename) == str(path) and mode == "rb":
            raise OSError("synthetic checksum read denied")
        return real_open(filename, mode, *args, **kwargs)

    with monkeypatch.context() as bad:
        bad.setattr(builtins, "open", deny_primary_read)
        with pytest.raises(RuntimeError, match="read failed|reload"):
            stale.remember("Synthetic unreadable checksum must block save", priority=0.9)
    assert stale.persistence_blocked
    assert path.read_bytes() == before
    with pytest.raises(RuntimeError, match="blocked"):
        stale.remember("Synthetic retry must remain blocked", priority=0.9)
    stale.load()
    stale.remember("Synthetic read restored and committed after reload", priority=0.9)
    assert len(MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()) == 2


def test_primary_path_switch_to_identical_bytes_requires_reload(tmp_path):
    path, stale = _store(tmp_path)
    stale.remember("Synthetic primary originally written under first path", priority=0.9)
    other = tmp_path / "other_memory.json"
    other.write_bytes(path.read_bytes())
    original_bytes = other.read_bytes()
    stale.filepath = str(other)
    with pytest.raises(RuntimeError, match="path changed|reload"):
        stale.remember("Synthetic identical other file must be preserved", priority=0.9)
    assert other.read_bytes() == original_bytes
    assert stale.persistence_blocked
    stale.load()
    assert not stale.persistence_blocked
    stale.remember("Synthetic explicitly loaded target now accepts write", priority=0.9)
    assert len(json.loads(other.read_text(encoding="utf-8"))) == 2
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1


def test_non_stale_replace_failure_allows_safe_retry(tmp_path, monkeypatch):
    import os
    path, memory = _store(tmp_path, max_memories=1)
    memory.remember("Synthetic preserved record before failed disk replace", priority=0.9)
    before = memory.dump_all()
    bytes_before = path.read_bytes()
    real_replace = os.replace

    def fail_replace(*_args, **_kwargs):
        raise OSError("synthetic disk replace failure")

    with monkeypatch.context() as bad:
        bad.setattr(os, "replace", fail_replace)
        with pytest.raises(RuntimeError, match="durable save failed"):
            memory.remember("Synthetic failed save must roll back eviction", priority=0.9)
    assert memory.persistence_blocked is False
    assert memory.dump_all() == before
    assert path.read_bytes() == bytes_before
    memory.remember("Synthetic valid retry after replace restored", priority=0.9)
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all() == memory.dump_all()
    assert memory.dump_all()[0]["thought"] == "Synthetic valid retry after replace restored"


def test_stale_rejection_never_publishes_vector_or_timeline(tmp_path):
    path, stale = _store(tmp_path)
    vector_published, timeline_published = [], []
    stale.vector_search = types.SimpleNamespace(
        add_memory=lambda *args, **kwargs: vector_published.append((args, kwargs))
    )
    stale._embeddings_enabled = True
    stale._vector_index_built = True
    stale.timeline = types.SimpleNamespace(
        log_event=lambda **kwargs: timeline_published.append(kwargs)
    )
    stale.enable_timeline_logging = True
    peer = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    peer.remember("Synthetic peer must remain before secondary publish", priority=0.9)
    saved = path.read_bytes()
    with pytest.raises(RuntimeError, match="stale|reload|changed"):
        stale.remember("Synthetic no vector or timeline for rejected write", priority=0.9)
    assert path.read_bytes() == saved
    assert vector_published == []
    assert timeline_published == []


def test_external_commit_during_temp_write_rechecked_before_replace(tmp_path, monkeypatch):
    path, stale = _store(tmp_path)
    peer = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    original_check = stale._assert_primary_unchanged
    checks = [0]

    def interleave_peer_commit():
        checks[0] += 1
        if checks[0] == 2:
            peer.remember("Synthetic peer saved while stale temporary file staged", priority=0.9)
        return original_check()

    with monkeypatch.context() as patch:
        patch.setattr(stale, "_assert_primary_unchanged", interleave_peer_commit)
        with pytest.raises(RuntimeError, match="stale|reload|changed"):
            stale.remember("Synthetic staging race must not erase peer", priority=0.9)
    assert checks[0] >= 2
    assert [r["thought"] for r in MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()] == [
        "Synthetic peer saved while stale temporary file staged"
    ]


def test_separate_process_writer_commit_survives_stale_parent(tmp_path):
    """Real child Python process, not just threads sharing a process lock."""
    import subprocess
    path, stale = _store(tmp_path)
    script = """
import sys
import types
from pathlib import Path
root = Path.cwd()
package = types.ModuleType("project_guardian")
package.__path__ = [str(root / "project_guardian")]
package.__package__ = "project_guardian"
sys.modules["project_guardian"] = package
from project_guardian.memory import MemoryCore
worker = MemoryCore(filepath=sys.argv[1], enable_timeline_logging=False, enable_vector_search=False)
worker.remember("Synthetic independently launched child process record must survive", priority=0.9)
"""
    subprocess.run(
        [sys.executable, "-c", script, str(path)],
        cwd=str(_ROOT),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    committed_bytes = path.read_bytes()
    with pytest.raises(RuntimeError, match="stale|changed|reload"):
        stale.remember("Synthetic parent stale after child process", priority=0.9)
    assert path.read_bytes() == committed_bytes
    assert MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()[0]["thought"] == (
        "Synthetic independently launched child process record must survive"
    )
