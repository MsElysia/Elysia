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
    """A second participating writer cannot commit during an in-progress save."""
    path, primary = _store(tmp_path)
    peer = MemoryCore(filepath=str(path), enable_timeline_logging=False)
    peer._primary_lock_timeout_seconds = 0.15
    original_check = primary._assert_primary_unchanged
    checks = [0]

    def interleave_peer_commit():
        checks[0] += 1
        if checks[0] == 2:
            with pytest.raises(RuntimeError, match="lock unavailable|reload"):
                peer.remember("Synthetic peer cannot pass primary active lock", priority=0.9)
            assert peer.persistence_blocked
        return original_check()

    with monkeypatch.context() as patch:
        patch.setattr(primary, "_assert_primary_unchanged", interleave_peer_commit)
        primary.remember("Synthetic primary commits while lock held", priority=0.9)
    assert checks[0] >= 2
    with pytest.raises(RuntimeError, match="blocked"):
        peer.remember("Synthetic peer must reload after lock timeout", priority=0.9)
    peer.load()
    assert not peer.persistence_blocked
    peer.remember("Synthetic peer commits after primary completes", priority=0.9)
    assert [r["thought"] for r in MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()] == [
        "Synthetic primary commits while lock held",
        "Synthetic peer commits after primary completes",
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


def test_explicit_reload_does_not_accept_missing_previously_loaded_primary(tmp_path):
    path, memory = _store(tmp_path)
    memory.remember("Synthetic durable history must not vanish on missing reload", priority=0.9)
    saved = path.read_bytes()
    path.unlink()  # Deliberate disposable fixture mutation.
    memory.load()  # An explicit reload cannot silently endorse the disappearance.
    assert memory.persistence_blocked
    assert memory.get_memory_state()["memory_count_authoritative"] is False
    with pytest.raises(RuntimeError, match="blocked"):
        memory.remember("Synthetic unsafe reload must not recreate file", priority=0.9)
    assert not path.exists()
    path.write_bytes(saved)
    memory.load()
    assert not memory.persistence_blocked
    assert len(memory.dump_all()) == 1


@pytest.mark.parametrize("repeat", [0, 1])
def test_process_race_after_last_checksum_before_replace(tmp_path, monkeypatch, repeat):
    """Real MemoryCore: child saves precisely while parent's replace is intercepted.

    Before the process-wide repair, child B finishes and A destroys its bytes.
    After the repair, B waits on the same lock, then loads A and saves both.
    """
    import os
    import subprocess

    path = tmp_path / f"synthetic_race_{repeat}.json"
    parent = MemoryCore(filepath=str(path), enable_timeline_logging=False, enable_vector_search=False)
    child_thought = f"Synthetic child concurrent protected entry {repeat}"
    parent_thought = f"Synthetic parent concurrently protected entry {repeat}"
    script = """
import sys
import types
from pathlib import Path
root = Path.cwd()
pkg = types.ModuleType("project_guardian")
pkg.__path__ = [str(root / "project_guardian")]
pkg.__package__ = "project_guardian"
sys.modules["project_guardian"] = pkg
from project_guardian.memory import MemoryCore
MemoryCore(filepath=sys.argv[1], enable_timeline_logging=False, enable_vector_search=False).remember(
    sys.argv[2], priority=0.9
)
"""
    real_replace = os.replace
    child = None
    intercepted = [0]
    child_completed_before_parent_replace = [False]

    def intercept_parent_replace(src, dst):
        nonlocal child
        if str(dst) == str(path) and intercepted[0] == 0:
            intercepted[0] += 1
            # This hook is in the REAL _save() after its last digest check.
            child = subprocess.Popen(
                [sys.executable, "-c", script, str(path), child_thought],
                cwd=str(_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                # Without a lock, B completes DURING this window and loses data.
                # With the lock, B is blocked until A finishes replacing.
                child.wait(timeout=2.5)
                child_completed_before_parent_replace[0] = True
            except subprocess.TimeoutExpired:
                pass
        return real_replace(src, dst)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", intercept_parent_replace)
            parent.remember(parent_thought, priority=0.9)
        assert intercepted[0] == 1, "Actual MemoryCore os.replace was not intercepted"
        assert child is not None
        out, err = child.communicate(timeout=20)
        assert child.returncode == 0, (out, err)
        restarted = MemoryCore(
            filepath=str(path), enable_timeline_logging=False, enable_vector_search=False,
        )
        records = [entry["thought"] for entry in restarted.dump_all()]
        assert records == [parent_thought, child_thought], (
            "Real child writer acknowledged a commit that parent overwrote; "
            f"child_completed_before_parent_replace={child_completed_before_parent_replace[0]} "
            f"records={records!r}"
        )
        assert not restarted.persistence_blocked
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def test_process_lock_sidecar_reuse_and_hardlink_rejection(tmp_path):
    """Sidecar persists across primary replacement/delete; never write through hardlinks."""
    import os

    path, memory = _store(tmp_path)
    lock_path = path.with_name(path.name + ".memorycore.lock")
    assert lock_path.is_file()
    assert lock_path.read_bytes() == bytes((0,))
    memory.remember("Synthetic sidecar stays stable after primary replace", priority=0.9)
    assert lock_path.is_file()
    assert not list(tmp_path.glob(".guardian_memory_*.tmp"))
    memory.forget()
    assert not path.exists()
    assert lock_path.is_file(), "Deleting a stable sidecar allows split-brain writers"
    memory.remember("Synthetic reuse same sidecar after legitimate forget", priority=0.9)
    assert len(MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()) == 1
    assert not list(tmp_path.glob(".guardian_memory_*.tmp"))

    # A separate primary must not open a preexisting malicious hard-linked lock.
    other = tmp_path / "other_memory.json"
    sentinel = tmp_path / "sentinel_never_modify.txt"
    sentinel.write_bytes(b"synthetic sentinel locked from accidental modifications")
    malicious_lock = other.with_name(other.name + ".memorycore.lock")
    try:
        os.link(sentinel, malicious_lock)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Hardlink unavailable on this temporary volume: {exc}")
    before = sentinel.read_bytes()
    blocked = MemoryCore(filepath=str(other), enable_timeline_logging=False)
    assert blocked.persistence_blocked
    with pytest.raises(RuntimeError, match="blocked"):
        blocked.remember("Synthetic unsafe hardlink must not be touched", priority=0.9)
    assert sentinel.read_bytes() == before
    assert not other.exists()


def test_acceptance_synthetic_snapshot_restore_and_sidecar_lifecycle(tmp_path):
    """Copy only synthetic JSON to a new root; restart and recreate a safe lock."""
    import hashlib
    import shutil

    original = tmp_path / "source"
    restored_root = tmp_path / "restored"
    original.mkdir()
    restored_root.mkdir()
    source = original / "guardian_memory.json"
    memory = MemoryCore(filepath=str(source), enable_timeline_logging=False, enable_vector_search=False)
    memory.remember("Synthetic snapshot entry before backup", priority=0.9)
    expected = source.read_bytes()
    digest = hashlib.sha256(expected).hexdigest()
    lock = source.with_name(source.name + ".memorycore.lock")
    assert lock.is_file()
    recovered_path = restored_root / source.name
    shutil.copy2(source, recovered_path)
    assert not (restored_root / lock.name).exists()
    recovered = MemoryCore(filepath=str(recovered_path), enable_timeline_logging=False,
                           enable_vector_search=False)
    assert not recovered.persistence_blocked
    assert recovered.dump_all() == memory.dump_all()
    assert hashlib.sha256(recovered_path.read_bytes()).hexdigest() == digest
    recovered.remember("Synthetic restored entry survives restart", priority=0.9)
    assert (restored_root / lock.name).is_file()
    restarted = MemoryCore(filepath=str(recovered_path), enable_timeline_logging=False,
                           enable_vector_search=False)
    assert len(restarted.dump_all()) == 2
    assert not list(restored_root.glob(".guardian_memory_*.tmp"))


def test_acceptance_existing_sidecar_permission_denial_fails_closed(tmp_path, monkeypatch):
    """Deterministic denied writable sidecar handle, not a claim about Windows ACLs."""
    import os

    path, seed = _store(tmp_path)
    seed.remember("Synthetic seed persists despite sidecar denial", priority=0.9)
    before = path.read_bytes()
    lock = path.with_name(path.name + ".memorycore.lock")
    original_open = os.open

    def deny_existing_sidecar(name, flags, *args, **kwargs):
        if os.path.normcase(os.path.abspath(os.fspath(name))) == os.path.normcase(os.path.abspath(str(lock))):
            raise PermissionError("synthetic existing sidecar denies O_RDWR")
        return original_open(name, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", deny_existing_sidecar)
        denied = MemoryCore(filepath=str(path), enable_timeline_logging=False,
                            enable_vector_search=False)
        assert denied.persistence_blocked
        with pytest.raises(RuntimeError):
            denied.remember("Synthetic refused sidecar must preserve seed", priority=0.9)
    assert path.read_bytes() == before
    denied.load()
    assert not denied.persistence_blocked
    denied.remember("Synthetic recovery after sidecar access restored", priority=0.9)
    assert len(MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()) == 2


def test_acceptance_directory_permission_denial_fails_closed(tmp_path, monkeypatch):
    """Simulate EACCES creating lock in writable-JSON/read-only DIRECTORY.

    Native Windows ACL enforcement is explicitly NOT established by this test.
    """
    import os

    path = tmp_path / "locked_directory" / "guardian_memory.json"
    path.parent.mkdir()
    seeded = [{"time": "2026-11-01T00:00:00", "thought": "Synthetic archived history",
               "category": "fact", "priority": 0.9, "metadata": {}}]
    raw = json.dumps(seeded).encode("utf-8")
    path.write_bytes(raw)
    original_open = os.open
    lock = str(path) + ".memorycore.lock"

    def deny_lock_creation(name, flags, *args, **kwargs):
        if os.path.normcase(os.path.abspath(os.fspath(name))) == os.path.normcase(os.path.abspath(lock)):
            raise PermissionError("synthetic read-only directory blocks sidecar create")
        return original_open(name, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", deny_lock_creation)
        memory = MemoryCore(filepath=str(path), enable_timeline_logging=False,
                            enable_vector_search=False)
        assert memory.persistence_blocked
        assert memory.get_memory_state()["memory_count_authoritative"] is False
        with pytest.raises(RuntimeError):
            memory.remember("Synthetic cannot write in archive-like directory", priority=0.9)
        assert path.read_bytes() == raw
    assert not (path.parent / (path.name + ".memorycore.lock")).exists()
    memory.load()
    assert not memory.persistence_blocked
    assert memory.dump_all() == seeded


def test_acceptance_independent_process_held_lock_fences_and_recovers(tmp_path):
    """Real independent process holds lock; timeout must not touch primary bytes."""
    import subprocess

    path, memory = _store(tmp_path)
    memory.remember("Synthetic pre-contention durable record", priority=0.9)
    before = path.read_bytes()
    script = """
import sys, types, contextlib, io
from pathlib import Path
root = Path.cwd()
pkg = types.ModuleType("project_guardian")
pkg.__path__ = [str(root / "project_guardian")]
pkg.__package__ = "project_guardian"
sys.modules["project_guardian"] = pkg
from project_guardian.memory import MemoryCore
with contextlib.redirect_stdout(io.StringIO()):
    holder = MemoryCore(filepath=sys.argv[1], enable_timeline_logging=False, enable_vector_search=False)
with holder._primary_process_lock():
    print("SYNTHETIC_LOCK_HELD", flush=True)
    sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-c", script, str(path)], cwd=str(_ROOT),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "SYNTHETIC_LOCK_HELD"
        memory._primary_lock_timeout_seconds = 0.20
        with pytest.raises(RuntimeError, match="lock unavailable|reload"):
            memory.remember("Synthetic busy-lock write cannot proceed", priority=0.9)
        assert memory.persistence_blocked
        assert path.read_bytes() == before
        with pytest.raises(RuntimeError, match="blocked"):
            memory.remember("Synthetic retry without reload prohibited", priority=0.9)
    finally:
        if child.poll() is None:
            child.stdin.write("\n")
            child.stdin.flush()
        out, err = child.communicate(timeout=15)
        assert child.returncode == 0, (out, err)
    memory.load()
    assert not memory.persistence_blocked
    memory.remember("Synthetic saved after contention release and explicit reload", priority=0.9)
    assert len(MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()) == 2


def test_acceptance_real_readonly_sidecar_file(tmp_path):
    """OS filesystem read-only attribute/mode, on synthetic sidecar only.

    Unlike injected PermissionError, exercises the actual Windows read-only file
    attribute and POSIX mode permission. Always restores permissions in finally.
    """
    import os
    import stat

    path, memory = _store(tmp_path)
    memory.remember("Synthetic primary survives real sidecar read-only mode", priority=0.9)
    before = path.read_bytes()
    lock = path.with_name(path.name + ".memorycore.lock")
    before_lock = lock.read_bytes()
    previous_mode = stat.S_IMODE(lock.stat().st_mode)
    try:
        lock.chmod(stat.S_IREAD)
        # POSIX root might bypass mode restrictions, which is not proof.
        # Hosted Windows/Ubuntu runners use normal unprivileged users.
        with pytest.raises(RuntimeError, match="lock unavailable|reload"):
            blocked = MemoryCore(filepath=str(path), enable_timeline_logging=False,
                                 enable_vector_search=False)
            blocked.remember("Synthetic write cannot bypass read-only sidecar", priority=0.9)
    finally:
        lock.chmod(previous_mode | stat.S_IWRITE | stat.S_IREAD)
    assert path.read_bytes() == before
    assert lock.read_bytes() == before_lock
    restarted = MemoryCore(filepath=str(path), enable_timeline_logging=False,
                           enable_vector_search=False)
    assert not restarted.persistence_blocked
    restarted.remember("Synthetic primary commits when read-only sidecar restored", priority=0.9)
    assert len(MemoryCore(filepath=str(path), enable_timeline_logging=False).dump_all()) == 2
