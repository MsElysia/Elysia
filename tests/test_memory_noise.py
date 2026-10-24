# tests/test_memory_noise.py
"""Focused tests for project_guardian/memory_noise.py (noise heuristics + routine-memory throttle)."""

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "project_guardian" / "memory_noise.py"


@pytest.fixture
def mn():
    # Load by file path: the module is stdlib-only, and ``import project_guardian`` currently
    # fails on main at package import (tracked separately), which would mask these tests.
    spec = importlib.util.spec_from_file_location("memory_noise_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pressured(mn, monkeypatch):
    """Simulate high host RAM and a controllable clock; start from an empty throttle map."""
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(mn, "host_system_memory_fraction", lambda: 0.95)
    monkeypatch.setattr(mn.time, "time", lambda: clock["now"])
    monkeypatch.delenv("ELYSIA_ROUTINE_REMEMBER_THROTTLE_SEC", raising=False)
    monkeypatch.delenv("ELYSIA_HOST_RAM_ROUTINE_THROTTLE_FRAC", raising=False)
    mn._ROUTINE_THROTTLE_LAST.clear()
    return clock


class TestLowValueText:
    @pytest.mark.parametrize("text", [None, "", "ok", "ping", "pong.", "heartbeat tick 42"])
    def test_noise_is_low_value(self, mn, text):
        assert mn.is_low_value_memory_text(text) is True

    def test_substantive_sentence_is_kept(self, mn):
        assert mn.is_low_value_memory_text("User asked how the proposal review queue works.") is False

    def test_important_markers_block_embedding_skip(self, mn):
        text = "[Autonomy] safety_validation failed: traceback follows"
        assert mn.thought_indicates_important_memory(text) is True
        assert mn.is_embedding_entirely_skipped(text) is False

    def test_bookkeeping_line_is_entirely_skipped(self, mn):
        assert mn.is_embedding_entirely_skipped("[Autonomy] artifact-ready=false count=3") is True


class TestRoutineThrottle:
    def test_not_suppressed_when_host_fraction_unavailable(self, mn, monkeypatch):
        monkeypatch.setattr(mn, "host_system_memory_fraction", lambda: None)
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.1, "[Autonomy] no-op") is False

    def test_not_suppressed_below_pressure_threshold(self, mn, monkeypatch):
        monkeypatch.setattr(mn, "host_system_memory_fraction", lambda: 0.50)
        monkeypatch.delenv("ELYSIA_HOST_RAM_ROUTINE_THROTTLE_FRAC", raising=False)
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.1, "[Autonomy] no-op") is False

    def test_first_write_kept_duplicate_suppressed_until_ttl(self, mn, pressured):
        line = "[Autonomy] income_modules_pulse: no-op suppressed"
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.2, line) is False
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.2, line) is True
        pressured["now"] += mn._routine_throttle_ttl_sec() + 1
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.2, line) is False

    def test_important_or_high_priority_thought_never_suppressed(self, mn, pressured):
        important = "[Autonomy] no-op path hit an error: mutation blocked"
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.2, important) is False
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.2, important) is False
        routine = "[Autonomy] no-op skipped"
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.9, routine) is False
        assert mn.routine_autonomy_remember_suppressed("autonomy", 0.9, routine) is False

    def test_non_routine_category_not_suppressed(self, mn, pressured):
        line = "[Autonomy] no-op skipped"
        assert mn.routine_autonomy_remember_suppressed("conversation", 0.1, line) is False
        assert mn.routine_autonomy_remember_suppressed("conversation", 0.1, line) is False

    def test_throttle_map_is_bounded_within_single_ttl_window(self, mn, pressured):
        cap = mn._ROUTINE_THROTTLE_MAX_KEYS
        for i in range(cap * 3):
            mn.routine_autonomy_remember_suppressed("autonomy", 0.2, f"[Autonomy] no-op line {i}")
        assert len(mn._ROUTINE_THROTTLE_LAST) <= cap

    def test_eviction_drops_oldest_live_entries_first(self, mn, pressured):
        cap = mn._ROUTINE_THROTTLE_MAX_KEYS
        oldest = "[Autonomy] no-op oldest"
        mn.routine_autonomy_remember_suppressed("autonomy", 0.2, oldest)
        for i in range(cap):
            pressured["now"] += 0.001
            mn.routine_autonomy_remember_suppressed("autonomy", 0.2, f"[Autonomy] no-op line {i}")
        assert len(mn._ROUTINE_THROTTLE_LAST) <= cap
        assert mn._routine_throttle_fingerprint("autonomy", oldest) not in mn._ROUTINE_THROTTLE_LAST
        newest = mn._routine_throttle_fingerprint("autonomy", f"[Autonomy] no-op line {cap - 1}")
        assert newest in mn._ROUTINE_THROTTLE_LAST

    def test_eviction_prefers_expired_entries(self, mn, pressured):
        cap = mn._ROUTINE_THROTTLE_MAX_KEYS
        ttl = mn._routine_throttle_ttl_sec()
        stale = "[Autonomy] no-op stale"
        mn.routine_autonomy_remember_suppressed("autonomy", 0.2, stale)
        pressured["now"] += ttl + 1
        fresh_lines = [f"[Autonomy] no-op fresh {i}" for i in range(cap)]
        for line in fresh_lines:
            mn.routine_autonomy_remember_suppressed("autonomy", 0.2, line)
        assert mn._routine_throttle_fingerprint("autonomy", stale) not in mn._ROUTINE_THROTTLE_LAST
        assert all(
            mn._routine_throttle_fingerprint("autonomy", line) in mn._ROUTINE_THROTTLE_LAST
            for line in fresh_lines
        )
