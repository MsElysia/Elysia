# Bounded social-intelligence: filters + session wiring (browse mocked).

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from project_guardian.social_intelligence.filters import (
    filter_text_chunks,
    sponsored_risk_score,
)
from project_guardian.social_intelligence.service import (
    attempt_social_speak,
    load_social_config,
    run_moltbook_social_session,
)
from project_guardian.bounded_browser.schema import BrowseTaskResult, PageStepResult


def test_sponsored_risk_detects_promoted():
    assert sponsored_risk_score("Great discussion about agents") < 0.3
    spam = "Sponsored promoted post — buy now, discount code, affiliate link in bio"
    assert sponsored_risk_score(spam) >= 0.42


def test_filter_text_chunks_skips_sponsored():
    kept, skip = filter_text_chunks(
        ["Real thread about tooling", "Affiliate link — click here to buy"],
        threshold=0.4,
    )
    assert skip == 1
    assert len(kept) == 1
    assert "Real thread" in kept[0]


def test_load_social_config_has_moltbook_defaults():
    cfg = load_social_config()
    m = (cfg.get("environments") or {}).get("moltbook", {}).get("modes", {})
    assert m.get("observe") is True
    assert m.get("draft") is True
    assert m.get("speak") is False


def test_attempt_social_speak_blocked_by_default():
    out = attempt_social_speak(None, {"text": "hello", "target_url": "https://moltbook.com/x"})
    assert out.get("blocked") is True


@pytest.fixture
def fake_browse_result():
    return BrowseTaskResult(
        goal="g",
        start_url="https://moltbook.com/",
        steps=[
            PageStepResult(
                url="https://moltbook.com/feed",
                title="Feed",
                page_type="feed",
                key_findings=(
                    "Alice and Bob debate retrieval strategies.\n\n"
                    "Sponsored post: limited time offer buy now — affiliate link."
                ),
                discovered_links=[],
                relevance_score=0.72,
                continue_recommendation="stop",
            )
        ],
        visited_urls=["https://moltbook.com/feed", "https://moltbook.com/@alice"],
        stop_reason="ok",
    )


def test_run_moltbook_social_session_mocked_writes_artifact(fake_browse_result, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "project_guardian.social_intelligence.memory.SOCIAL_DATA_DIR",
        tmp_path,
    )

    with patch(
        "project_guardian.bounded_browser.moltbook.browse_moltbook",
        return_value=fake_browse_result,
    ):
        out = run_moltbook_social_session(MagicMock(), {"goal": "read community threads"})

    assert out["success"] is True
    r = out["result"]
    assert r.get("thread_id")
    assert r.get("sponsored_chunks_skipped", 0) >= 1
    assert "drafts" in r and r["drafts"]
    assert "thread_score" in r and r["thread_score"] is not None
    assert r.get("rank_context")

    threads = tmp_path / "threads.jsonl"
    assert threads.exists()
    line = threads.read_text(encoding="utf-8").strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["kind"] == "thread"
    assert rec["trust_score"] >= 0
    assert "thread_score" in rec

    ranks = tmp_path / "rankings.jsonl"
    assert ranks.exists()


def test_builtin_operator_elysia_social_intel():
    from project_guardian.capability_execution import _builtin_operator_tool_result

    g = MagicMock()
    with patch(
        "project_guardian.social_intelligence.run_social_intel_for_capability",
        return_value={"success": True, "result": {"thread_id": "x"}},
    ) as m:
        out = _builtin_operator_tool_result(
            g,
            "elysia_social_intel",
            {"goal": "social observe moltbook"},
        )
    m.assert_called_once()
    assert out["success"] is True
