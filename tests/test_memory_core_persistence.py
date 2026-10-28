# tests/test_memory_core_persistence.py
"""Persistence and restart-survival tests for project_guardian/memory.py (MemoryCore JSON history)."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "project_guardian" / "memory.py"


def _load_module(name="memory_core_persistence_under_test"):
    # Load by file path: ``import project_guardian`` currently fails on main at package import
    # (tracked separately). memory.py degrades its optional relative imports to None, so the
    # JSON history path under test is exercised exactly as in the runtime.
    spec = importlib.util.spec_from_file_location(name, _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mem_mod():
    return _load_module()


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "fictional_memory.json")


def _seed_lanternfish(MemoryCore, store):
    """Fictional example: three facts about the (fictional) Lanternfish Bakery, one a correction."""
    m = MemoryCore(filepath=store)
    assert m.remember(
        "Lanternfish Bakery opens at 06:30 on weekdays",
        category="fact", priority=0.8, metadata={"source": "lf-handbook-v1#p3"},
    ) is True
    assert m.remember(
        "Lanternfish Bakery sourdough uses a 48-hour levain",
        category="fact", priority=0.7, metadata={"source": "lf-handbook-v1#p9"},
    ) is True
    assert m.remember(
        "Correction: Lanternfish Bakery opens at 07:00 on weekdays",
        category="fact", priority=0.9,
        metadata={"source": "lf-memo-2026-10-21", "supersedes": "lf-handbook-v1#p3"},
    ) is True
    return m


def _disk(store):
    return json.loads(Path(store).read_text(encoding="utf-8"))


def test_remember_persists_and_survives_restart(mem_mod, store):
    _seed_lanternfish(mem_mod.MemoryCore, store)
    assert len(_disk(store)) == 3

    restarted = mem_mod.MemoryCore(filepath=store)
    assert restarted.get_memory_count() == 3
    hits = restarted.search_memories("opens")
    assert [h["thought"] for h in hits] == [
        "Correction: Lanternfish Bakery opens at 07:00 on weekdays",
        "Lanternfish Bakery opens at 06:30 on weekdays",
    ]
    assert hits[0]["metadata"] == {"source": "lf-memo-2026-10-21", "supersedes": "lf-handbook-v1#p3"}
    assert restarted.get_memory_state()["last_load_error"] is None


def test_non_serializable_entry_is_rejected_without_touching_disk(mem_mod, store):
    m = _seed_lanternfish(mem_mod.MemoryCore, store)
    before = Path(store).read_bytes()

    ok = m.remember("Lanternfish Bakery cat is named Pilchard", category="fact", priority=0.6,
                    metadata={"obj": object()})

    assert ok is False
    assert len(m.memory_log) == 3, "rejected entry must not enter the in-memory log"
    assert Path(store).read_bytes() == before, "on-disk history must be byte-identical"
    assert "not JSON serializable" in m.get_memory_state()["last_save_error"]

    # The store is still writable afterwards (no poison-pill entry left behind).
    assert m.remember("Lanternfish Bakery cat is named Pilchard", category="fact", priority=0.6) is True
    assert m.get_memory_state()["last_save_error"] is None
    assert len(_disk(store)) == 4


def test_failed_write_leaves_previous_history_intact(mem_mod, store, monkeypatch):
    m = _seed_lanternfish(mem_mod.MemoryCore, store)
    before = Path(store).read_bytes()

    def boom(tmp, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(mem_mod.os, "replace", boom)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    ok = m.remember("Lanternfish Bakery closes Mondays", category="fact", priority=0.7)

    assert ok is False
    assert Path(store).read_bytes() == before
    assert "No space left" in m.get_memory_state()["last_save_error"]
    # Entry stays in memory and is persisted by the next successful save.
    assert len(m.memory_log) == 4
    monkeypatch.undo()
    assert m.remember("Lanternfish Bakery takes card payments", category="fact", priority=0.7) is True
    assert [e["thought"] for e in _disk(store)][-2:] == [
        "Lanternfish Bakery closes Mondays",
        "Lanternfish Bakery takes card payments",
    ]


def test_no_temp_files_left_after_save_or_failed_save(mem_mod, store, tmp_path, monkeypatch):
    m = _seed_lanternfish(mem_mod.MemoryCore, store)
    assert [p.name for p in tmp_path.iterdir()] == ["fictional_memory.json"]

    def locked(*_):
        raise OSError("locked")

    monkeypatch.setattr(mem_mod.os, "replace", locked)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert m.remember("Lanternfish Bakery has four ovens", category="fact", priority=0.7) is False
    assert [p.name for p in tmp_path.iterdir()] == ["fictional_memory.json"]


def test_truncated_history_is_quarantined_not_overwritten(mem_mod, store, tmp_path):
    _seed_lanternfish(mem_mod.MemoryCore, store)
    full = Path(store).read_text(encoding="utf-8")
    truncated = full[: len(full) // 2]
    Path(store).write_text(truncated, encoding="utf-8")

    restarted = mem_mod.MemoryCore(filepath=store)
    assert restarted.memory_log == []
    state = restarted.get_memory_state()
    assert state["last_load_error"]
    quarantined = state["quarantined_history_path"]
    assert quarantined and Path(quarantined).exists()
    assert Path(quarantined).name.startswith("fictional_memory.json.corrupt.")
    assert Path(quarantined).read_text(encoding="utf-8") == truncated, "original bytes preserved"
    assert not Path(store).exists()

    # A post-restart write creates a fresh history; the preserved copy is untouched.
    assert restarted.remember("Lanternfish Bakery reopened after the outage", category="fact", priority=0.8) is True
    assert len(_disk(store)) == 1
    assert Path(quarantined).read_text(encoding="utf-8") == truncated
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["fictional_memory.json", Path(quarantined).name])


def test_non_list_history_is_quarantined(mem_mod, store):
    Path(store).write_text(json.dumps({"thought": "not a list"}), encoding="utf-8")
    m = mem_mod.MemoryCore(filepath=store)
    assert m.memory_log == []
    assert "must be a JSON list" in m.get_memory_state()["last_load_error"]
    assert m.quarantined_history_path and os.path.exists(m.quarantined_history_path)
    assert m.remember("Lanternfish Bakery sells rye on Fridays", category="fact", priority=0.7) is True
    assert len(_disk(store)) == 1


def test_quarantine_names_do_not_collide_within_one_second(mem_mod, tmp_path):
    store = str(tmp_path / "fictional_memory.json")
    Path(store).write_text("{not json", encoding="utf-8")
    first = mem_mod.MemoryCore(filepath=store).quarantined_history_path
    Path(store).write_text("[also not json", encoding="utf-8")
    second = mem_mod.MemoryCore(filepath=store).quarantined_history_path
    assert first != second
    assert Path(first).read_text(encoding="utf-8") == "{not json"
    assert Path(second).read_text(encoding="utf-8") == "[also not json"


def test_io_load_failure_does_not_quarantine(mem_mod, store, monkeypatch):
    _seed_lanternfish(mem_mod.MemoryCore, store)
    real_open = open

    def denied(path, *a, **kw):
        if str(path) == store and (not a or "r" in a[0]):
            raise PermissionError(13, "Permission denied")
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", denied)
    m = mem_mod.MemoryCore(filepath=store)
    assert m.memory_log == []
    assert "Permission denied" in m.get_memory_state()["last_load_error"]
    assert m.quarantined_history_path is None
    assert Path(store).exists(), "a possibly-healthy file must stay in place on I/O failure"


def test_missing_file_is_a_clean_start(mem_mod, store):
    m = mem_mod.MemoryCore(filepath=store)
    assert m.memory_log == []
    st = m.get_memory_state()
    assert st["last_load_error"] is None and st["quarantined_history_path"] is None
    assert m.remember("Lanternfish Bakery was founded in a fictional 1998", category="fact", priority=0.7) is True
    assert len(_disk(store)) == 1


def test_max_memories_not_evicted_for_rejected_entry(mem_mod, store):
    m = mem_mod.MemoryCore(filepath=store, max_memories=2)
    assert m.remember("Lanternfish Bakery fact one", category="fact", priority=0.7) is True
    assert m.remember("Lanternfish Bakery fact two", category="fact", priority=0.7) is True
    assert m.remember("Lanternfish Bakery fact three", category="fact", priority=0.7,
                      metadata={"bad": object()}) is False
    assert [e["thought"] for e in m.memory_log] == ["Lanternfish Bakery fact one", "Lanternfish Bakery fact two"]


def test_lazy_load_state_reports_persistence_fields(mem_mod, store):
    m = mem_mod.MemoryCore(filepath=store, lazy_load=True)
    st = m.get_memory_state(load_if_needed=False)
    assert st["memory_count_authoritative"] is False
    assert set(st) >= {"last_save_error", "last_load_error", "quarantined_history_path"}
