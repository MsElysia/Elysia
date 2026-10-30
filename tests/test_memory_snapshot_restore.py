"""
Tests for ``MemorySnapshot.restore_from_snapshot`` (project_guardian/memory_snapshot.py).

Defects reproduced on main:

* The restore replayed every snapshot entry through ``MemoryCore.remember()``
  with only ``thought``/``category``/``priority``. Every restored entry was
  re-stamped with the restore time and lost its ``metadata`` (provenance,
  correction links), so a source-linked answer stopped being source-linked
  after recovery.
* ``remember()`` applies the startup-thin-mode, noise and memory-pressure
  write filters, so a restore could silently drop entries and still return
  ``True``; it also rewrote the JSON file once per entry.
* ``target_memory.forget()`` deleted the live store before the snapshot
  content was validated, and success was reported without checking that the
  restored history actually reached disk.

Modules are loaded by file path with a stub ``project_guardian`` package
because ``import project_guardian`` fails on main (``module_activity``
missing). ``project_guardian.memory_vector`` is stubbed so ``memory.py`` does
not need NumPy. With the stub package in place the relative imports inside
``MemoryCore.remember`` (``startup_runtime_guard``, ``memory_noise``) resolve
to the real modules, so the write filters are live in these tests.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PG_DIR = PROJECT_ROOT / "project_guardian"

SOURCE = "dome-log-2026-10.pdf"


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
def snapshot_mod():
    return _load("memory_snapshot")


@pytest.fixture(scope="module")
def memory_mod():
    return _load("memory")


@pytest.fixture(scope="module")
def startup_guard_mod():
    return _load("startup_runtime_guard")


def _mossbank_entries():
    """Fictional Mossbank Observatory dome log: facts, a correction, a short note."""
    return [
        {
            "time": "2026-10-12T21:04:00.000001",
            "thought": "Mossbank Observatory dome motor was serviced on 2026-10-12 by the night crew.",
            "category": "facility",
            "priority": 0.7,
            "metadata": {"source": SOURCE, "page": 3},
        },
        {
            "time": "2026-10-13T02:11:00.000002",
            "thought": "The 0.6 m reflector collimation drifted 2 arcmin after the service.",
            "category": "instrument",
            "priority": 0.6,
            "metadata": {"source": SOURCE, "page": 4},
        },
        {
            "time": "2026-10-15T19:30:00.000003",
            "thought": "Correction: the dome motor service date was 2026-10-14, not 2026-10-12.",
            "category": "facility",
            "priority": 0.8,
            "metadata": {"source": SOURCE, "page": 5, "supersedes": "dome motor serviced 2026-10-12"},
            "imported_by": "mossbank-archive-sync",
        },
        {
            "time": "2026-10-15T23:58:00.000004",
            "thought": "Dome closed.",
            "category": "facility",
            "priority": 0.4,
            "metadata": {"source": SOURCE, "page": 6},
        },
    ]


def _write_snapshot(tmp_path, entries, **extra):
    snapshot_file = tmp_path / "snapshot_mossbank.json"
    data = {
        "timestamp": "2026-10-16T00:00:00",
        "memory_count": len(entries) if isinstance(entries, list) else 0,
        "memories": entries,
        "metadata": {"example": "mossbank"},
        "vector_index_path": None,
    }
    data.update(extra)
    snapshot_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return snapshot_file


class FakeCore:
    """MemoryCore stand-in recording which write paths the restore touches."""

    def __init__(self, log=None, save_outcome=True, max_memories=None):
        self.memory_log = list(log or [])
        self.save_outcome = save_outcome
        self.max_memories = max_memories
        self.save_calls = 0
        self.remember_calls = 0
        self.forget_calls = 0
        self.loaded = True
        self._vector_index_built = True

    def load_if_needed(self):
        self.loaded = True

    def _save(self):
        self.save_calls += 1
        return self.save_outcome

    def remember(self, *args, **kwargs):
        self.remember_calls += 1

    def forget(self):
        self.forget_calls += 1
        self.memory_log = []


# --------------------------------------------------------------------------- #
# Verbatim restore: provenance, history, extra keys
# --------------------------------------------------------------------------- #

def test_restore_preserves_time_metadata_and_extra_keys(tmp_path, snapshot_mod, memory_mod):
    entries = _mossbank_entries()
    snapshot_file = _write_snapshot(tmp_path, entries)
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    mem = memory_mod.MemoryCore(str(tmp_path / "guardian_memory.json"))

    assert snap.restore_from_snapshot(str(snapshot_file), mem) is True
    assert mem.memory_log == entries
    assert mem.memory_log[2]["imported_by"] == "mossbank-archive-sync"
    assert snap.last_restore_report["restored"] == 4
    assert snap.last_restore_report["persisted"] is True
    assert snap.last_restore_report["error"] is None


def test_restore_survives_restart_and_keeps_correction_source_linked(tmp_path, snapshot_mod, memory_mod):
    entries = _mossbank_entries()
    snapshot_file = _write_snapshot(tmp_path, entries)
    store = tmp_path / "guardian_memory.json"
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))

    # Live store corrupted: the case error_handler._recover_memory_error hands to restore.
    store.write_text('[{"time": "2026-', encoding="utf-8")
    broken = memory_mod.MemoryCore(str(store))
    assert broken.memory_log == []

    assert snap.restore_from_snapshot(str(snapshot_file), broken) is True

    reborn = memory_mod.MemoryCore(str(store))
    assert reborn.memory_log == entries
    hits = reborn.search_memories("service date")
    assert len(hits) == 1
    assert hits[0]["metadata"]["source"] == SOURCE
    assert hits[0]["metadata"]["supersedes"] == "dome motor serviced 2026-10-12"
    assert hits[0]["time"] == "2026-10-15T19:30:00.000003"


def test_restore_bypasses_remember_write_filters(tmp_path, snapshot_mod, memory_mod, startup_guard_mod, monkeypatch):
    """Startup thin mode would drop 'Dome closed.' (priority 0.4, short) via remember()."""
    monkeypatch.setattr(startup_guard_mod, "startup_memory_thin_mode_active", lambda: True)
    mem = memory_mod.MemoryCore(str(tmp_path / "guardian_memory.json"))
    mem.remember("Dome closed.", category="facility", priority=0.4, metadata={"source": SOURCE})
    assert mem.memory_log == [], "precondition: thin mode filters this write on remember()"

    entries = _mossbank_entries()
    snapshot_file = _write_snapshot(tmp_path, entries)
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    assert snap.restore_from_snapshot(str(snapshot_file), mem) is True
    assert [e["thought"] for e in mem.memory_log] == [e["thought"] for e in entries]
    assert snap.last_restore_report["skipped"] == 0


def test_restore_uses_single_persist_and_never_forget_or_remember(tmp_path, snapshot_mod):
    snapshot_file = _write_snapshot(tmp_path, _mossbank_entries())
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    core = FakeCore(log=[{"time": "x", "thought": "stale live entry"}], save_outcome=True)

    assert snap.restore_from_snapshot(str(snapshot_file), core) is True
    assert core.save_calls == 1
    assert core.remember_calls == 0
    assert core.forget_calls == 0
    assert len(core.memory_log) == 4
    assert core._vector_index_built is False


def test_restore_honours_max_memories_keeping_most_recent(tmp_path, snapshot_mod):
    entries = _mossbank_entries()
    snapshot_file = _write_snapshot(tmp_path, entries)
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    core = FakeCore(max_memories=2)

    assert snap.restore_from_snapshot(str(snapshot_file), core) is True
    assert core.memory_log == entries[-2:]
    assert snap.last_restore_report["truncated"] == 2
    assert snap.last_restore_report["restored"] == 2


# --------------------------------------------------------------------------- #
# Malformed input: target untouched
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("memories", ["not-a-list", {"thought": "dict instead of list"}, None])
def test_malformed_snapshot_leaves_target_untouched(tmp_path, snapshot_mod, memory_mod, memories):
    store = tmp_path / "guardian_memory.json"
    mem = memory_mod.MemoryCore(str(store))
    mem.remember("Mossbank live entry that must survive a bad restore attempt.", priority=0.9,
                 metadata={"source": SOURCE})
    before_bytes = store.read_bytes()
    before_log = list(mem.memory_log)

    snapshot_file = _write_snapshot(tmp_path, memories)
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))

    assert snap.restore_from_snapshot(str(snapshot_file), mem) is False
    assert snap.last_restore_report["error"] == "snapshot_malformed"
    assert mem.memory_log == before_log
    assert store.read_bytes() == before_bytes


def test_unreadable_snapshot_leaves_target_untouched(tmp_path, snapshot_mod):
    bad = tmp_path / "snapshot_bad.json"
    bad.write_text("{not json", encoding="utf-8")
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    core = FakeCore(log=[{"time": "x", "thought": "keep me"}])

    assert snap.restore_from_snapshot(str(bad), core) is False
    assert snap.last_restore_report["error"] == "snapshot_unreadable"
    assert core.memory_log == [{"time": "x", "thought": "keep me"}]
    assert core.save_calls == 0
    assert core.forget_calls == 0


def test_malformed_entries_are_skipped_and_counted(tmp_path, snapshot_mod):
    good = _mossbank_entries()[:2]
    entries = [good[0], "a bare string", 42, {"category": "facility"}, {"thought": "   "},
               {"thought": None}, good[1]]
    snapshot_file = _write_snapshot(tmp_path, entries)
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    core = FakeCore()

    assert snap.restore_from_snapshot(str(snapshot_file), core) is True
    assert core.memory_log == good
    assert snap.last_restore_report["skipped"] == 5
    assert snap.last_restore_report["restored"] == 2


def test_missing_standard_keys_are_filled_without_touching_payload(tmp_path, snapshot_mod):
    entries = [{"thought": "Reflector mirror recoated.", "metadata": "not-a-dict"}]
    snapshot_file = _write_snapshot(tmp_path, entries, timestamp="2026-10-16T00:00:00")
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    core = FakeCore()

    assert snap.restore_from_snapshot(str(snapshot_file), core) is True
    assert core.memory_log == [{
        "thought": "Reflector mirror recoated.",
        "metadata": {},
        "time": "2026-10-16T00:00:00",
        "category": "general",
        "priority": 0.5,
    }]


# --------------------------------------------------------------------------- #
# Failed write: never reported as success
# --------------------------------------------------------------------------- #

def test_explicit_save_failure_restores_previous_log_and_returns_false(tmp_path, snapshot_mod):
    snapshot_file = _write_snapshot(tmp_path, _mossbank_entries())
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))
    previous = [{"time": "x", "thought": "live entry before restore"}]
    core = FakeCore(log=previous, save_outcome=False)

    assert snap.restore_from_snapshot(str(snapshot_file), core) is False
    assert core.memory_log == previous
    assert core.save_calls == 1
    assert snap.last_restore_report["error"] == "persist_failed"
    assert snap.last_restore_report["persisted"] is False
    assert snap.last_restore_report["restored"] == 0


def test_save_raising_is_reported_as_failure(tmp_path, snapshot_mod):
    snapshot_file = _write_snapshot(tmp_path, _mossbank_entries())
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))

    class RaisingCore(FakeCore):
        def _save(self):
            self.save_calls += 1
            raise OSError("disk full")

    core = RaisingCore(log=[{"time": "x", "thought": "live"}])
    assert snap.restore_from_snapshot(str(snapshot_file), core) is False
    assert core.memory_log == [{"time": "x", "thought": "live"}]
    assert snap.last_restore_report["error"] == "persist_failed"


def test_legacy_save_returning_none_is_verified_on_disk(tmp_path, snapshot_mod, memory_mod):
    """main's MemoryCore._save returns None and only prints on failure."""
    snapshot_file = _write_snapshot(tmp_path, _mossbank_entries())
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))

    # Unwritable target: directory does not exist, so every open("w") attempt fails.
    missing_dir_store = tmp_path / "no_such_dir" / "guardian_memory.json"
    mem = memory_mod.MemoryCore(str(missing_dir_store))
    assert mem._save() is None, "precondition: legacy _save returns None"

    assert snap.restore_from_snapshot(str(snapshot_file), mem) is False
    assert mem.memory_log == []
    assert not missing_dir_store.exists()
    assert snap.last_restore_report["error"] == "persist_failed"

    # Writable target: the same legacy _save, verified by re-reading the file.
    good_store = tmp_path / "guardian_memory.json"
    mem_ok = memory_mod.MemoryCore(str(good_store))
    assert snap.restore_from_snapshot(str(snapshot_file), mem_ok) is True
    assert json.loads(good_store.read_text(encoding="utf-8")) == _mossbank_entries()


def test_persist_without_save_method_is_not_success(tmp_path, snapshot_mod):
    snapshot_file = _write_snapshot(tmp_path, _mossbank_entries())
    snap = snapshot_mod.MemorySnapshot(snapshot_dir=str(tmp_path / "snaps"))

    class NoSave:
        memory_log = [{"time": "x", "thought": "live"}]

    target = NoSave()
    assert snap.restore_from_snapshot(str(snapshot_file), target) is False
    assert target.memory_log == [{"time": "x", "thought": "live"}]
