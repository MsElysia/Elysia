import types
from pathlib import Path

from project_guardian.core import GuardianCore


class _MemoryStub:
    def __init__(self):
        self.events = []

    def remember(self, thought, category="general", priority=0.5, metadata=None):
        self.events.append(
            {
                "thought": thought,
                "category": category,
                "priority": priority,
                "metadata": metadata or {},
            }
        )


def _mk_guardian_for_guidance() -> GuardianCore:
    g = GuardianCore.__new__(GuardianCore)
    g.memory = _MemoryStub()
    g._last_moltbook_guidance = None
    g._moltbook_guidance_last_at = 0.0
    g._last_chatlog_guidance = None
    g._chatlog_guidance_last_at = 0.0
    g._load_autonomy_config = lambda: {
        "enable_moltbook_direction_guidance": True,
        "moltbook_guidance_cooldown_minutes": 60,
        "moltbook_guidance_max_chars": 420,
    }
    return g


def test_moltbook_guidance_collects_and_caches(monkeypatch):
    calls = {"count": 0}

    def _fake_browse(goal, start_url=None, memory_core=None, **_kwargs):
        calls["count"] += 1
        step = types.SimpleNamespace(
            title="Operator demand signal",
            key_findings="Users request automation and concrete tool integrations.",
            url="https://www.moltbook.com/thread/123",
        )
        return types.SimpleNamespace(
            steps=[step],
            visited_urls=["https://www.moltbook.com/thread/123"],
            stop_reason="completed",
        )

    monkeypatch.setattr("project_guardian.bounded_browser.moltbook.browse_moltbook", _fake_browse)
    g = _mk_guardian_for_guidance()

    first = g._maybe_collect_moltbook_guidance(
        purpose="decision",
        action_hint="autonomy action selection",
        force_refresh=False,
    )
    second = g._maybe_collect_moltbook_guidance(
        purpose="decision",
        action_hint="autonomy action selection",
        force_refresh=False,
    )

    assert isinstance(first, dict)
    assert "automation" in str(first.get("summary", "")).lower()
    assert isinstance(second, dict)
    assert second.get("summary") == first.get("summary")
    assert calls["count"] == 1
    assert g.memory.events, "expected guidance memory event"


def test_chatlog_guidance_collects_and_caches(monkeypatch):
    g = _mk_guardian_for_guidance()
    g._load_autonomy_config = lambda: {
        "enable_chatlog_direction_guidance": True,
        "chatlog_guidance_cooldown_minutes": 60,
        "chatlog_guidance_max_files": 3,
        "chatlog_guidance_max_chars": 420,
    }

    monkeypatch.setattr(
        "project_guardian.auto_learning.get_chatlogs_path",
        lambda: "dummy",
    )
    calls = {"count": 0}

    def _fake_peek(chatlogs_path, max_files=3, search_terms=None, **_kwargs):
        calls["count"] += 1
        return [
            {
                "title": "Elysia roadmap decisions",
                "text": "Prioritize concrete operator tasks, safe mutations, and small program additions.",
            }
        ]

    monkeypatch.setattr("project_guardian.auto_learning.peek_chatlogs_context", _fake_peek)

    first = g._maybe_collect_chatlog_guidance(
        purpose="decision",
        action_hint="autonomy action selection",
        force_refresh=False,
    )
    second = g._maybe_collect_chatlog_guidance(
        purpose="decision",
        action_hint="autonomy action selection",
        force_refresh=False,
    )

    assert isinstance(first, dict)
    assert "operator tasks" in str(first.get("summary", "")).lower()
    assert isinstance(second, dict)
    assert second.get("summary") == first.get("summary")
    assert calls["count"] == 1


def test_chatlog_guidance_empty_skips_memory_remember(monkeypatch):
    """No memory spam when exports are missing or peek returns nothing."""
    g = _mk_guardian_for_guidance()
    g._load_autonomy_config = lambda: {
        "enable_chatlog_direction_guidance": True,
        "chatlog_guidance_cooldown_minutes": 60,
        "chatlog_guidance_max_files": 3,
        "chatlog_guidance_max_chars": 420,
    }
    monkeypatch.setattr(
        "project_guardian.auto_learning.get_chatlogs_path",
        lambda: Path("/nonexistent_chatlogs_dir"),
    )
    monkeypatch.setattr(
        "project_guardian.auto_learning.peek_chatlogs_context",
        lambda *a, **k: "",
    )
    out = g._maybe_collect_chatlog_guidance(
        purpose="decision",
        action_hint="",
        force_refresh=True,
    )
    assert isinstance(out, dict)
    assert out.get("items_used") == 0
    assert "No local ChatGPT direction captured." in str(out.get("summary") or "")
    assert g.memory.events == []


def test_moltbook_guidance_does_not_delegate_to_openclaw_by_default(monkeypatch):
    calls = {"openclaw_available": 0, "delegate": 0}

    def _fake_social(_guardian, _payload):
        return {
            "ok": True,
            "result": {
                "summary": "Thread signals and reply opportunities captured from MoltBook.",
                "pages_visited": 3,
                "stop_reason": "page_budget",
            },
        }

    class _OpenClawSystem:
        def delegate_to_openclaw(self, **_kwargs):
            calls["delegate"] += 1
            return {"ok": True, "task_id": "oc-1"}

    g = _mk_guardian_for_guidance()
    g._load_autonomy_config = lambda: {
        "enable_moltbook_direction_guidance": True,
        "moltbook_guidance_mode": "social",
        "moltbook_guidance_cooldown_minutes": 60,
        "moltbook_guidance_delegate_openclaw": False,
    }
    g._openclaw_available = lambda: calls.__setitem__("openclaw_available", calls["openclaw_available"] + 1) or True
    g._openclaw_system = lambda: _OpenClawSystem()
    monkeypatch.setattr("project_guardian.social_intelligence.run_moltbook_social_session", _fake_social)

    out = g._maybe_collect_moltbook_guidance(
        purpose="decision",
        action_hint="autonomy action selection",
        force_refresh=True,
    )

    assert isinstance(out, dict)
    assert "openclaw" not in out
    assert calls["delegate"] == 0


def test_openclaw_goal_requires_actuator_cues_for_moltbook():
    g = GuardianCore.__new__(GuardianCore)

    assert g._goal_requires_openclaw("Read MoltBook threads and draft a reply") is False
    assert g._goal_requires_openclaw("MoltBook browser automation: click through settings") is True
    assert g._goal_requires_openclaw("Scan GitHub repo for integration work") is True

