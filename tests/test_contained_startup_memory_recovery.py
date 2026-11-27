"""Contained startup must survive an unreadable memory store and give recovery a producer.

Covers ``project_guardian.contained_startup.preflight_memory_store`` (runs before
GuardianCore is built, whose startup writes raise on a fenced store) and
``snapshot_memory_on_startup`` (the only routine snapshot producer), plus the
full chain through the real ``start_contained_guardian`` / ``GuardianCore`` on a
disposable root. Fictional example: the Thornfield Canal lock-keeper's logbook.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from project_guardian.contained_startup import (
    RESTORE_MARKER_NAME,
    ContainedStartupError,
    build_contained_startup_config,
    preflight_memory_store,
    snapshot_memory_on_startup,
)
from project_guardian.memory import MemoryCore
from project_guardian.memory_snapshot import MemorySnapshot

SOURCE = "lock-log-2026.csv"
FACTS = [
    ("Thornfield Lock 7 top gate paddle sticks above half; log entry 14.", 0.7, {"source": SOURCE, "row": 14}),
    ("Thornfield Lock 7 water level is held at 2.4 m during the summer schedule.", 0.6, {"source": SOURCE, "row": 19}),
    ("Thornfield Lock 9 bywash was cleared of weed on 2026-05-03.", 0.8, {"source": SOURCE, "row": 27}),
]
CORRECTION = (
    "Correction: Lock 7 summer level is 2.6 m, not 2.4 m (log entry 19 misread).",
    0.9,
    {"source": SOURCE, "row": 33, "revision": 2, "supersedes": "level#1"},
)


@pytest.fixture
def disposable(tmp_path, monkeypatch):
    root = tmp_path / "disposable"
    root.mkdir()
    temp = root / "temp"
    temp.mkdir()
    for key in ("TEMP", "TMP", "TMPDIR"):
        monkeypatch.setenv(key, str(temp))
    monkeypatch.setenv("ELYSIA_AUTO_LEARNING", "false")
    monkeypatch.delenv("ELYSIA_THUMB_DRIVE", raising=False)
    monkeypatch.delenv("ELYSIA_THUMB_DRIVE_SECONDARY", raising=False)
    for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "SMTP_PASSWORD", "ELYSIA_SMTP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    return root


@pytest.fixture
def reset_guardian():
    yield
    try:
        from project_guardian.guardian_singleton import reset_singleton

        reset_singleton()
    except Exception:
        pass
    try:
        from project_guardian.core import GuardianCore

        GuardianCore._any_instance_initialized = False
    except Exception:
        pass


def _config(root: Path):
    return build_contained_startup_config(root)


def _ingest(core: MemoryCore):
    for text, pri, md in FACTS:
        core.remember(text, "canal", pri, metadata=md)
    core.remember(CORRECTION[0], "canal", CORRECTION[1], metadata=CORRECTION[2])


def _facts(core: MemoryCore):
    return [m for m in core.memory_log if m.get("metadata", {}).get("source") == SOURCE]


def _seed_store_and_snapshot(cfg):
    """Facts + correction in the primary, one snapshot of them; returns (primary, snapshot path)."""
    primary = Path(cfg["memory_filepath"])
    core = MemoryCore(str(primary), enable_timeline_logging=False)
    _ingest(core)
    manager = MemorySnapshot(**cfg["snapshot_config"])
    snap = manager.create_snapshot(core.dump_all())
    assert snap
    return primary, snap


def _corrupt(primary: Path) -> bytes:
    good = primary.read_bytes()
    bad = good[: len(good) // 2]
    primary.write_bytes(bad)
    return bad


def _sidecars(primary: Path):
    return sorted(primary.parent.glob(f"{primary.name}.pre-restore.*"))


def _marker(cfg) -> Path:
    return Path(cfg["memory_filepath"]).parent / RESTORE_MARKER_NAME


# --- preflight_memory_store ------------------------------------------------------


def test_readable_store_is_left_alone(disposable):
    cfg = _config(disposable)
    primary, _ = _seed_store_and_snapshot(cfg)
    before = primary.read_bytes()

    report = preflight_memory_store(cfg)

    assert report["status"] == "readable"
    assert report["memory_count"] == 4
    assert report["marker"] is None
    assert primary.read_bytes() == before
    assert _sidecars(primary) == []


def test_unreadable_store_without_snapshot_fails_closed_with_instructions(disposable):
    cfg = _config(disposable)
    primary = Path(cfg["memory_filepath"])
    core = MemoryCore(str(primary), enable_timeline_logging=False)
    _ingest(core)
    bad = _corrupt(primary)

    with pytest.raises(ContainedStartupError) as exc:
        preflight_memory_store(cfg)

    msg = str(exc.value)
    assert str(primary) in msg
    assert "unreadable" in msg
    assert "No readable snapshot" in msg
    assert "persistence blocked" not in msg.lower()
    assert primary.read_bytes() == bad
    assert _sidecars(primary) == []
    assert not _marker(cfg).exists()


def test_unreadable_store_with_snapshot_names_it_and_the_opt_in(disposable):
    cfg = _config(disposable)
    primary, snap = _seed_store_and_snapshot(cfg)
    bad = _corrupt(primary)

    with pytest.raises(ContainedStartupError) as exc:
        preflight_memory_store(cfg)

    msg = str(exc.value)
    assert snap in msg
    assert "4 memories" in msg
    assert str(_marker(cfg)) in msg
    assert RESTORE_MARKER_NAME in msg
    assert primary.read_bytes() == bad, "no restore without consent"
    assert _sidecars(primary) == []


def test_marker_restores_latest_snapshot_and_preserves_original(disposable):
    cfg = _config(disposable)
    primary, snap = _seed_store_and_snapshot(cfg)
    bad = _corrupt(primary)
    _marker(cfg).touch()

    report = preflight_memory_store(cfg)

    assert report["status"] == "restored"
    assert report["memory_count"] == 4
    assert report["restore"]["source_path"] == snap
    assert not _marker(cfg).exists(), "marker is one-shot"
    assert Path(report["marker"]).name.startswith(f"{RESTORE_MARKER_NAME}.consumed-")
    sidecars = _sidecars(primary)
    assert len(sidecars) == 1 and sidecars[0].read_bytes() == bad
    assert report["preserved_original"] == str(sidecars[0])

    reloaded = MemoryCore(str(primary), enable_timeline_logging=False)
    assert not reloaded.persistence_blocked
    assert len(_facts(reloaded)) == 4
    hit = reloaded.search_memories("summer level", limit=1)[0]
    assert hit["metadata"]["source"] == SOURCE
    assert hit["metadata"]["supersedes"] == "level#1"
    assert hit["time"] == next(m["time"] for m in json.loads(Path(snap).read_text())["memories"] if m["thought"] == CORRECTION[0])


def test_restored_store_accepts_new_writes(disposable):
    cfg = _config(disposable)
    primary, _ = _seed_store_and_snapshot(cfg)
    _corrupt(primary)
    _marker(cfg).touch()
    preflight_memory_store(cfg)

    core = MemoryCore(str(primary), enable_timeline_logging=False)
    core.remember("Thornfield Lock 9 bywash re-checked after restore.", "canal", 0.5, metadata={"source": SOURCE, "row": 40})
    again = MemoryCore(str(primary), enable_timeline_logging=False)
    assert len(_facts(again)) == 5


def test_marker_with_readable_store_is_ignored_and_renamed(disposable):
    cfg = _config(disposable)
    primary, _ = _seed_store_and_snapshot(cfg)
    before = primary.read_bytes()
    _marker(cfg).touch()

    report = preflight_memory_store(cfg)

    assert report["status"] == "readable"
    assert not _marker(cfg).exists()
    assert Path(report["marker"]).name.startswith(f"{RESTORE_MARKER_NAME}.ignored-")
    assert primary.read_bytes() == before
    assert _sidecars(primary) == []


def test_marker_without_readable_snapshot_is_consumed_and_nothing_changes(disposable):
    cfg = _config(disposable)
    primary, snap = _seed_store_and_snapshot(cfg)
    # Damage every copy of the only snapshot so no readable copy remains.
    manager = MemorySnapshot(**cfg["snapshot_config"])
    for copy in [Path(snap), *(d / Path(snap).name for d in manager.shard_dirs)]:
        if copy.exists():
            copy.write_text("{not json", encoding="utf-8")
    bad = _corrupt(primary)
    _marker(cfg).touch()

    with pytest.raises(ContainedStartupError) as exc:
        preflight_memory_store(cfg)

    assert "no readable snapshot" in str(exc.value).lower()
    assert not _marker(cfg).exists()
    assert primary.read_bytes() == bad
    assert _sidecars(primary) == []


def test_fence_that_is_not_corruption_never_restores(disposable, monkeypatch):
    cfg = _config(disposable)
    primary, _ = _seed_store_and_snapshot(cfg)
    before = primary.read_bytes()
    _marker(cfg).touch()

    from contextlib import contextmanager

    @contextmanager
    def held(self):
        raise TimeoutError("MemoryCore primary lock held by pid 4242")
        yield  # pragma: no cover

    monkeypatch.setattr(MemoryCore, "_primary_process_lock", held)

    with pytest.raises(ContainedStartupError) as exc:
        preflight_memory_store(cfg)

    msg = str(exc.value)
    assert "not corruption" in msg
    assert "no restore was attempted" in msg
    assert primary.read_bytes() == before
    assert _marker(cfg).exists(), "consent was not evaluated, so it is kept for the real retry"
    assert _sidecars(primary) == []


def test_preflight_rejects_config_without_store_path():
    with pytest.raises(ContainedStartupError):
        preflight_memory_store({})


# --- snapshot_memory_on_startup --------------------------------------------------


class _FakeGuardian:
    def __init__(self, memory, manager):
        self.memory = memory
        self.memory_snapshot = manager

    def create_memory_snapshot(self, daily: bool = False):
        return self.memory_snapshot.create_snapshot(self.memory.dump_all())


def test_startup_snapshot_writes_and_applies_retention(disposable):
    cfg = _config(disposable)
    core = MemoryCore(cfg["memory_filepath"], enable_timeline_logging=False)
    _ingest(core)
    manager = MemorySnapshot(**cfg["snapshot_config"])  # contained retention is 1 day
    stale = manager.snapshot_dir / "snapshot_20200101_000000.json"
    stale.write_text(json.dumps({"timestamp": "2020-01-01T00:00:00", "memory_count": 0, "memories": []}))
    old = 1_577_836_800  # 2020-01-01 UTC
    os.utime(stale, (old, old))

    report = snapshot_memory_on_startup(_FakeGuardian(core, manager))

    assert report["persisted"] is True
    assert report["error"] is None
    assert report["removed_old"] == 1 and not stale.exists()
    data = json.loads(Path(report["path"]).read_text())
    assert [m["thought"] for m in data["memories"]] == [m["thought"] for m in core.memory_log]
    assert manager.get_latest_snapshot() == report["path"]


def test_startup_snapshot_skips_fenced_store_and_never_raises(disposable):
    cfg = _config(disposable)
    primary = Path(cfg["memory_filepath"])
    primary.write_text("{broken", encoding="utf-8")
    core = MemoryCore(str(primary), enable_timeline_logging=False)
    assert core.persistence_blocked
    manager = MemorySnapshot(**cfg["snapshot_config"])

    report = snapshot_memory_on_startup(_FakeGuardian(core, manager))

    assert report["persisted"] is False
    assert report["skipped"].startswith("memory store fenced")
    assert list(manager.snapshot_dir.glob("snapshot_*.json")) == []


def test_startup_snapshot_reports_write_failure_without_raising(disposable, monkeypatch):
    cfg = _config(disposable)
    core = MemoryCore(cfg["memory_filepath"], enable_timeline_logging=False)
    _ingest(core)
    manager = MemorySnapshot(**cfg["snapshot_config"])
    monkeypatch.setattr(MemorySnapshot, "_write_text_durably", staticmethod(lambda *_: (_ for _ in ()).throw(OSError(28, "No space left"))))

    report = snapshot_memory_on_startup(_FakeGuardian(core, manager))

    assert report["persisted"] is False
    assert report["path"] is None
    assert "No space left" in (report["error"] or "")
    assert list(manager.snapshot_dir.glob("snapshot_*.json")) == []


def test_startup_snapshot_without_snapshot_support_is_skipped():
    class Bare:
        memory = None

    report = snapshot_memory_on_startup(Bare())
    assert report["persisted"] is False and report["skipped"]


# --- full chain through the real contained GuardianCore boot --------------------


def _boot(root: Path):
    from project_guardian.contained_startup import start_contained_guardian

    return start_contained_guardian(root, ui_enabled=False)


def _stop(guardian):
    from project_guardian.guardian_singleton import reset_singleton

    try:
        guardian.shutdown()
    finally:
        reset_singleton()


def test_contained_boot_writes_startup_snapshot(disposable, reset_guardian):
    guardian, config = _boot(disposable)
    try:
        assert config["memory_preflight"]["status"] == "readable"
        snap = config["startup_snapshot"]
        assert snap["persisted"] is True, snap
        path = Path(snap["path"])
        assert path.is_relative_to(disposable.resolve())
        store = guardian.memory.json_memory if hasattr(guardian.memory, "json_memory") else guardian.memory
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["memory_count"] == len(store.memory_log) >= 1
        assert guardian.memory_snapshot.get_latest_snapshot() == str(path)
    finally:
        _stop(guardian)


def test_contained_restart_survives_corruption_only_with_consent(disposable, reset_guardian):
    # Session 1: ingest the logbook.
    guardian, _ = _boot(disposable)
    store = guardian.memory.json_memory if hasattr(guardian.memory, "json_memory") else guardian.memory
    primary = Path(store.filepath)
    _ingest(store)
    _stop(guardian)

    # Session 2: a normal restart; its startup snapshot now contains the facts.
    guardian, config = _boot(disposable)
    store = guardian.memory.json_memory if hasattr(guardian.memory, "json_memory") else guardian.memory
    assert len(_facts(store)) == 4
    snap_path = config["startup_snapshot"]["path"]
    assert snap_path
    snap_memories = json.loads(Path(snap_path).read_text(encoding="utf-8"))["memories"]
    assert sum(1 for m in snap_memories if m.get("metadata", {}).get("source") == SOURCE) == 4
    _stop(guardian)

    # The store is damaged between sessions.
    bad = _corrupt(primary)

    # Session 3: boot refuses with a diagnosis instead of a traceback from startup writes.
    with pytest.raises(ContainedStartupError) as exc:
        _boot(disposable)
    msg = str(exc.value)
    assert "unreadable" in msg and snap_path in msg and RESTORE_MARKER_NAME in msg
    assert "persistence blocked" not in msg.lower()
    assert primary.read_bytes() == bad
    assert _sidecars(primary) == []

    # Operator consents; session 4 restores and runs.
    (primary.parent / RESTORE_MARKER_NAME).touch()
    guardian, config = _boot(disposable)
    try:
        pre = config["memory_preflight"]
        assert pre["status"] == "restored"
        assert pre["restore"]["source_path"] == snap_path
        sidecars = _sidecars(primary)
        assert len(sidecars) == 1 and sidecars[0].read_bytes() == bad
        assert not (primary.parent / RESTORE_MARKER_NAME).exists()

        store = guardian.memory.json_memory if hasattr(guardian.memory, "json_memory") else guardian.memory
        assert not store.persistence_blocked
        assert len(_facts(store)) == 4
        hit = store.search_memories("summer level", limit=1)[0]
        assert hit["metadata"]["source"] == SOURCE and hit["metadata"]["supersedes"] == "level#1"

        store.remember("Thornfield Lock 9 bywash re-checked after restore.", "canal", 0.5, metadata={"source": SOURCE, "row": 40})
        assert config["startup_snapshot"]["persisted"] is True
    finally:
        _stop(guardian)

    # Session 5: the post-restore write survived a restart too.
    guardian, config = _boot(disposable)
    try:
        store = guardian.memory.json_memory if hasattr(guardian.memory, "json_memory") else guardian.memory
        assert len(_facts(store)) == 5
        assert config["memory_preflight"]["status"] == "readable"
    finally:
        _stop(guardian)
