# tests/test_timeline_memory_cleanup.py
"""Focused tests for TimelineMemory.cleanup_old_events in project_guardian/timeline_memory.py."""

import importlib.util
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "project_guardian" / "timeline_memory.py"


@pytest.fixture
def tm():
    # Load by file path: the module is stdlib-only, and ``import project_guardian`` currently
    # fails on main at package import (tracked separately), which would mask these tests.
    spec = importlib.util.spec_from_file_location("timeline_memory_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def timeline(tm, tmp_path):
    return tm.TimelineMemory(db_path=str(tmp_path / "timeline.db"))


def _days_ago(days):
    return datetime.now() - timedelta(days=days)


def _backdate_event(timeline, event_id, when):
    conn = sqlite3.connect(str(timeline.db_path))
    try:
        conn.execute("UPDATE events SET timestamp = ? WHERE id = ?", (when.isoformat(), event_id))
        conn.commit()
    finally:
        conn.close()


class TestCleanupOldEvents:
    def test_cleanup_does_not_raise_and_deletes_old_rows(self, timeline):
        old_id = timeline.log_event("old", "stale")
        _backdate_event(timeline, old_id, _days_ago(120))
        timeline.log_event("new", "fresh")
        timeline.record_task_execution("old_task", "completed", started_at=_days_ago(120))
        timeline.record_task_execution("new_task", "completed", started_at=_days_ago(1))

        result = timeline.cleanup_old_events(older_than_days=90)

        assert result == {"events_deleted": 1, "tasks_deleted": 1}
        assert [e["event_type"] for e in timeline.get_events()] == ["new"]
        assert [t["task_id"] for t in timeline.get_task_history()] == ["new_task"]

    def test_deletes_are_durable_across_connections(self, timeline, tm):
        old_id = timeline.log_event("old", "stale")
        _backdate_event(timeline, old_id, _days_ago(200))

        timeline.cleanup_old_events(older_than_days=90)

        reopened = tm.TimelineMemory(db_path=str(timeline.db_path))
        assert reopened.get_events() == []

    def test_nothing_to_delete_returns_zero_counts(self, timeline):
        timeline.log_event("new", "fresh")
        timeline.record_task_execution("t", "completed", started_at=_days_ago(1))

        result = timeline.cleanup_old_events(older_than_days=90)

        assert result == {"events_deleted": 0, "tasks_deleted": 0}
        assert len(timeline.get_events()) == 1
        assert len(timeline.get_task_history()) == 1

    def test_cutoff_boundary_keeps_rows_at_or_after_cutoff(self, timeline):
        just_inside = timeline.log_event("inside", "kept")
        just_outside = timeline.log_event("outside", "removed")
        _backdate_event(timeline, just_inside, _days_ago(90) + timedelta(minutes=5))
        _backdate_event(timeline, just_outside, _days_ago(90) - timedelta(minutes=5))

        result = timeline.cleanup_old_events(older_than_days=90)

        assert result["events_deleted"] == 1
        assert [e["event_type"] for e in timeline.get_events()] == ["inside"]

    def test_vacuum_failure_is_non_fatal_after_deletes_commit(self, timeline, tm, monkeypatch):
        old_id = timeline.log_event("old", "stale")
        _backdate_event(timeline, old_id, _days_ago(120))

        real_connect = tm.sqlite3.connect

        class _VacuumRefusingCursor:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, *args):
                if sql.strip().upper() == "VACUUM":
                    raise sqlite3.OperationalError("database is locked")
                return self._inner.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        class _Conn:
            def __init__(self, inner):
                self._inner = inner

            def cursor(self):
                return _VacuumRefusingCursor(self._inner.cursor())

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def __setattr__(self, name, value):
                if name == "_inner":
                    object.__setattr__(self, name, value)
                else:
                    setattr(self._inner, name, value)

        monkeypatch.setattr(tm.sqlite3, "connect", lambda *a, **k: _Conn(real_connect(*a, **k)))

        result = timeline.cleanup_old_events(older_than_days=90)

        assert result == {"events_deleted": 1, "tasks_deleted": 0}
        monkeypatch.undo()
        assert timeline.get_events() == []

    def test_cleanup_reclaims_space_via_vacuum(self, timeline):
        for i in range(300):
            event_id = timeline.log_event("bulk", "x" * 2000, payload={"i": i, "blob": "y" * 2000})
            _backdate_event(timeline, event_id, _days_ago(400))
        size_before = timeline.db_path.stat().st_size

        result = timeline.cleanup_old_events(older_than_days=90)

        assert result["events_deleted"] == 300
        assert timeline.db_path.stat().st_size < size_before
