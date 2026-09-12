import importlib
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def _reload_openai_modules():
    import project_guardian.cloud_api_state as cas
    import project_guardian.openai_degraded as od

    od = importlib.reload(od)
    cas = importlib.reload(cas)
    return od, cas


def test_success_clear_removes_persisted_quota_block_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    od, _cas = _reload_openai_modules()

    od.note_openai_reasoning_rate_limit(
        "insufficient_quota",
        status_code=429,
        context="unit_test",
    )

    cache_path = tmp_path / "ElysiaGuardian" / "openai_reasoning_quota_block.json"
    assert cache_path.is_file()
    assert od.openai_insufficient_quota_reasoning_blocked() is True

    od.note_openai_reasoning_success_clear_streak(clear_insufficient_quota_block=True)

    assert od.openai_insufficient_quota_reasoning_blocked() is False
    assert not cache_path.exists()


def test_openai_quota_block_allows_timed_reprobe_for_routing(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ELYSIA_OPENAI_QUOTA_REPROBE_SEC", "60")
    od, cas = _reload_openai_modules()

    od.note_openai_reasoning_rate_limit(
        "insufficient_quota",
        status_code=429,
        context="unit_test",
    )
    base = float(od._quota_reasoning_written_at_ts)
    monkeypatch.setattr(od.time, "time", lambda: base + 61.0)
    monkeypatch.setattr(cas, "openai_key_loaded", lambda: True)
    monkeypatch.setattr(cas, "openai_routing_disabled_by_policy", lambda: False)

    assert od.openai_insufficient_quota_reasoning_blocked() is True
    assert od.openai_insufficient_quota_reasoning_blocked(allow_reprobe=True) is False
    assert cas.openai_usable_for_routing() is False
    assert cas.openai_usable_for_routing(allow_quota_reprobe=True) is True
