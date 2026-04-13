# Human-signal ranking heuristics (unit-level).

from __future__ import annotations

from project_guardian.social_intelligence.ranking import (
    bot_like_penalty,
    build_participant_rows,
    build_rank_context_for_draft,
    score_thread_quality,
    token_overlap,
)


def test_token_overlap_basic():
    assert token_overlap("agent retrieval debate", "learning agents retrieval") > 0.1
    assert token_overlap("", "foo") == 0.0


def test_bot_like_penalty_spam():
    assert bot_like_penalty("Nice post! Follow me for great content dm me") > 0.2
    assert bot_like_penalty("We tried this in production; however latency was an issue.") < 0.15


def test_score_thread_quality_prefers_substance():
    thin = score_thread_quality(
        all_chunks=["buy now discount"],
        step_scores=[0.3],
        topics=[],
        goal="agents",
        sponsored_skipped=0,
        total_raw_chunks=1,
        participant_count=1,
        campaign_corpus="autonomy learning agents",
    )
    rich = score_thread_quality(
        all_chunks=[
            "Alice: we tried this and it failed in practice.",
            "Bob: I disagree — the tradeoff is latency vs accuracy.",
        ],
        step_scores=[0.75, 0.8],
        topics=["retrieval", "latency"],
        goal="compare agent retrieval strategies",
        sponsored_skipped=1,
        total_raw_chunks=3,
        participant_count=3,
        campaign_corpus="autonomy learning agents execution",
    )
    assert rich["thread_score"] > thin["thread_score"]


def test_build_participant_rows_orders_by_signal():
    urls = ["https://moltbook.com/@alice"]
    chunks = [
        "Alice asks: what worked for you in production? I think we should benchmark.",
        "Spammy: great content follow me link in bio",
    ]
    rows = build_participant_rows(
        urls=urls,
        chunks=chunks,
        recurrence={"@alice": 2},
        campaign_corpus="execution autonomy agents",
        goal="learn from operators",
    )
    assert rows
    top = rows[0]
    assert top["id"] in ("@alice", "name:Alice")
    rc = build_rank_context_for_draft(
        thread_rank={"thread_score": 0.7, "likely_discussion_human_mix": 0.6},
        participants=rows,
    )
    assert rc.get("primary_contact", {}).get("display")
