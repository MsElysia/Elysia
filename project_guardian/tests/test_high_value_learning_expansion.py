"""High-value learning expansion (Google CSE, Wikipedia search, Reddit/Twitter fan-out)."""

from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.auto_learning import (
    maybe_run_high_value_learning_expansion,
    sanitize_chained_learning_plan,
)


def test_sanitize_injects_empty_google_queries_when_missing():
    plan = sanitize_chained_learning_plan(
        {
            "twitter_queries": ["AI agents"],
            "reddit_subreddits_new": ["MachineLearning"],
            "reddit_searches": [],
            "wikipedia_titles": ["Machine learning"],
            "reasoning": "test",
        },
        topics=["AI"],
        cfg={"reddit_subs": ["MachineLearning"]},
        seed_twitter_queries=None,
        default_reddit_subs=["MachineLearning"],
        per_source_cap=3,
    )
    assert plan.get("google_queries") == []


def test_maybe_run_high_value_expansion_skips_below_relevance(tmp_path):
    cfg = {
        "high_value_expansion_enabled": True,
        "high_value_expansion_min_admitted": 1,
        "high_value_expansion_min_relevance": 5,
        "high_value_expansion_bulk_admitted": 99,
    }
    out = maybe_run_high_value_learning_expansion(
        session_result={
            "admitted": 1,
            "max_admitted_relevance": 2.0,
            "followup_seeds": [{"title": "x", "compressed": "y", "relevance": 2.0}],
        },
        storage_path=tmp_path,
        topics=["AI"],
        cfg=cfg,
        llm_callback=None,
        memory=None,
        twitter_bearer_token=None,
        default_reddit_sub="MachineLearning",
    )
    assert out.get("skipped") is True


def test_maybe_run_high_value_expansion_runs_when_strong_signal(tmp_path):
    cfg = {
        "high_value_expansion_enabled": True,
        "high_value_expansion_min_admitted": 1,
        "high_value_expansion_min_relevance": 3,
        "high_value_expansion_bulk_admitted": 4,
        "high_value_expansion_max_queries": 1,
        "high_value_expansion_per_branch_cap": 1,
        "google_custom_search_api_key": "",
        "google_custom_search_engine_id": "",
    }

    def _fake_google(*_a, **_k):
        return [
            {
                "source": "google",
                "title": "Example result",
                "text": "Snippet about machine learning automation.",
                "url": "https://example.com/a",
            }
        ]

    def _fake_wiki_search(*_a, **_k):
        return []

    def _fake_wiki_summary(*_a, **_k):
        return None

    def _fake_reddit_search(*_a, **_k):
        return []

    with (
        patch("project_guardian.auto_learning.fetch_google_custom_search", side_effect=_fake_google),
        patch("project_guardian.auto_learning.search_wikipedia_titles_for_query", side_effect=_fake_wiki_search),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", side_effect=_fake_wiki_summary),
        patch("project_guardian.auto_learning.fetch_reddit_search", side_effect=_fake_reddit_search),
    ):
        out = maybe_run_high_value_learning_expansion(
            session_result={
                "admitted": 1,
                "max_admitted_relevance": 4.0,
                "followup_seeds": [
                    {"title": "ML ops", "compressed": "reliability patterns", "relevance": 4.0},
                ],
            },
            storage_path=tmp_path,
            topics=["AI", "machine learning"],
            cfg=cfg,
            llm_callback=None,
            memory=None,
            twitter_bearer_token=None,
            default_reddit_sub="MachineLearning",
        )

    assert out.get("high_value_expansion") is True
    assert int(out.get("fetched", 0)) >= 1
