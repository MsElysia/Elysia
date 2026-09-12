from pathlib import Path
from unittest.mock import MagicMock, patch

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import project_guardian.auto_learning as auto_learning

from project_guardian.auto_learning import (
    CHAINED_EMPTY_PLAN_REDDIT_SEEDS,
    _append_opportunity_extractions,
    OPPORTUNITY_EXTRACTIONS_FILENAME,
    _build_learning_query_terms,
    _canonicalize_reddit_subreddit,
    _chained_social_item_signal_score,
    learning_run_duplicate_saturated,
    run_mistral_chained_learning_session,
    sanitize_chained_learning_plan,
)


class _EmptyPlanMistral:
    def __init__(self, model: str):
        self.model = model

    def suggest_learning_targets(self, context, round_index, already_tried=None, *, module_name, agent_name=None):
        return {}


class _CaptureContextMistral:
    contexts: list[str] = []

    def __init__(self, model: str):
        self.model = model

    def suggest_learning_targets(self, context, round_index, already_tried=None, *, module_name, agent_name=None):
        self.__class__.contexts.append(context)
        if round_index == 0:
            return {
                "twitter_queries": [],
                "reddit_subreddits_new": ["LocalLLaMA"],
                "reddit_searches": [],
                "wikipedia_titles": [],
                "reasoning": "focus on recent local planner discussions",
            }
        return {}


class _BadTargetPlanMistral:
    def __init__(self, model: str):
        self.model = model

    def suggest_learning_targets(self, context, round_index, already_tried=None, *, module_name, agent_name=None):
        return {
            "twitter_queries": ["Elysia AI development roadmap"],
            "reddit_subreddits_new": ["elysiaai", "LocalLLaMA"],
            "reddit_searches": [
                {"subreddit": "selfawarenessai", "q": "latest discussions"},
                {"subreddit": "MachineLearning", "q": "customer complaint automation"},
            ],
            "wikipedia_titles": ["Project Guardian (AI)", "Self-aware artificial intelligence"],
            "reasoning": "Look for Elysia development chatter and self-aware AI threads.",
        }


class _GroundedPlanMistral:
    def __init__(self, model: str):
        self.model = model

    def suggest_learning_targets(self, context, round_index, already_tried=None, *, module_name, agent_name=None):
        return {
            "twitter_queries": ["customer complaint automation"],
            "reddit_subreddits_new": ["MachineLearning"],
            "reddit_searches": [],
            "wikipedia_titles": [],
            "reasoning": "Look for concrete complaint and automation pain signals.",
        }


class _AlternatingTwitterPlanMistral:
    run_counter = 0

    def __init__(self, model: str):
        self.model = model

    def suggest_learning_targets(self, context, round_index, already_tried=None, *, module_name, agent_name=None):
        query = (
            "automation pain point"
            if self.__class__.run_counter == 0
            else "customer complaint automation"
        )
        self.__class__.run_counter += 1
        return {
            "twitter_queries": [query],
            "reddit_subreddits_new": [],
            "reddit_searches": [],
            "wikipedia_titles": [],
            "reasoning": "Use grounded demand queries.",
        }


class _AlternatingRedditPlanMistral:
    run_counter = 0

    def __init__(self, model: str):
        self.model = model

    def suggest_learning_targets(self, context, round_index, already_tried=None, *, module_name, agent_name=None):
        self.__class__.run_counter += 1
        if self.__class__.run_counter == 1:
            return {
                "twitter_queries": [],
                "reddit_subreddits_new": ["MachineLearning"],
                "reddit_searches": [],
                "wikipedia_titles": [],
                "reasoning": "Check the latest ML discussions.",
            }
        return {
            "twitter_queries": [],
            "reddit_subreddits_new": [],
            "reddit_searches": [{"subreddit": "MachineLearning", "q": "customer complaint automation"}],
            "wikipedia_titles": [],
            "reasoning": "Search the same area more specifically.",
        }


def test_seed_fallback_skips_twitter_queries_when_plan_is_empty(tmp_path):
    captured = {}
    twitter_mock = MagicMock()

    def _fake_finalize(collected, storage_path, topics, memory, sources_count=1):
        captured["sources"] = [item.get("source") for item in collected]
        captured["titles"] = [item.get("title") for item in collected]
        return {
            "fetched": len(collected),
            "archived": len(collected),
            "admitted": 0,
            "rejected": len(collected),
            "cross_session_duplicates": 0,
            "file": "",
            "memory_count": 0,
        }

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _EmptyPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 2,
            "mistral_chained_per_source_cap": 2,
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_reddit", side_effect=lambda sub, limit=2: [{
            "source": "reddit",
            "title": f"{sub} thread",
            "text": "AI runtime operations and automation notes.",
            "url": "",
        }]),
        patch("project_guardian.auto_learning.fetch_twitter", twitter_mock),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", side_effect=lambda title: {
            "source": "wikipedia",
            "title": title,
            "text": f"{title} summary about AI systems and automation.",
            "url": "",
        }),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch("project_guardian.auto_learning.finalize_learned_collection", side_effect=_fake_finalize),
    ):
        result = run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["AI", "automation"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token="token",
            default_reddit_subs=["MachineLearning", "ArtificialIntelligence"],
            seed_twitter_queries=["artificial intelligence", "machine learning"],
        )

    assert result["fetched"] == 4
    assert twitter_mock.call_count == 0
    assert captured["sources"].count("reddit") == 2
    assert captured["sources"].count("wikipedia") == 2


def test_reddit_search_403_cooldown_skips_repeat_for_same_query():
    class _Resp:
        status_code = 403
        text = "forbidden"

        def json(self):
            return {}

    class _Client:
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            self.__class__.calls += 1
            return _Resp()

    with patch.object(auto_learning, "_REDDIT_BLOCK_UNTIL_TS_BY_KEY", {}):
        with patch("httpx.Client", _Client):
            assert auto_learning.fetch_reddit_search("MachineLearning", "automation pain point") == []
            assert _Client.calls == 1
            assert auto_learning._reddit_temporarily_blocked("MachineLearning", query="automation pain point")
            assert auto_learning.fetch_reddit_search("MachineLearning", "automation pain point") == []
            assert _Client.calls == 1


def test_reddit_alias_canonicalizes_artificial_intelligence():
    assert _canonicalize_reddit_subreddit("ArtificialIntelligence") == "artificial"


def test_empty_plan_round1_ignores_broad_config_reddit_subs_for_seeds(tmp_path):
    """General ``default_reddit_subs`` (e.g. passive_income) must not seed chained empty-plan fallback."""
    subs_requested: list[str] = []

    def capture_reddit(sub, limit=2):
        subs_requested.append(sub)
        return [{"source": "reddit", "title": sub, "text": "x." * 80, "url": ""}]

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _EmptyPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 2,
            "mistral_chained_per_source_cap": 3,
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_reddit", side_effect=capture_reddit),
        patch("project_guardian.auto_learning.fetch_twitter", MagicMock()),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch(
            "project_guardian.auto_learning.finalize_learned_collection",
            return_value={
                "fetched": 0,
                "archived": 0,
                "admitted": 0,
                "rejected": 0,
                "cross_session_duplicates": 0,
                "file": "",
                "memory_count": 0,
            },
        ),
    ):
        run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=[],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token="token",
            default_reddit_subs=["passive_income", "Entrepreneur", "SideProject"],
            seed_twitter_queries=["should_not_run"],
        )

    assert subs_requested
    assert "passive_income" not in [s.lower() for s in subs_requested]
    assert "Entrepreneur" not in subs_requested
    # First round uses tight seeds (subset of canonical list order).
    assert subs_requested[:2] == CHAINED_EMPTY_PLAN_REDDIT_SEEDS[:2]


def test_empty_plan_respects_config_override_subs(tmp_path):
    subs_requested: list[str] = []

    def capture_reddit(sub, limit=2):
        subs_requested.append(sub)
        return [{"source": "reddit", "title": sub, "text": "y." * 80, "url": ""}]

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _EmptyPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 1,
            "mistral_chained_per_source_cap": 2,
            "mistral_chained_empty_plan_reddit_subs": ["Python", "compsci"],
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_reddit", side_effect=capture_reddit),
        patch("project_guardian.auto_learning.fetch_twitter", MagicMock()),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch(
            "project_guardian.auto_learning.finalize_learned_collection",
            return_value={
                "fetched": 0,
                "archived": 0,
                "admitted": 0,
                "rejected": 0,
                "cross_session_duplicates": 0,
                "file": "",
                "memory_count": 0,
            },
        ),
    ):
        run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=[],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token=None,
            default_reddit_subs=["passive_income"],
        )

    assert subs_requested == ["Python", "compsci"]


def test_chained_context_keeps_latest_round_summary_when_base_context_is_long(tmp_path):
    _CaptureContextMistral.contexts = []

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _CaptureContextMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 2,
            "mistral_chained_per_source_cap": 1,
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=("Elysia autonomy notes. " * 900)),
        patch("project_guardian.auto_learning.fetch_reddit", return_value=[{
            "source": "reddit",
            "title": "Planner latency thread",
            "text": "Local planner latency is a workflow bottleneck and teams keep complaining that manual retries are time-consuming." * 4,
            "url": "",
            "score": 5,
            "num_comments": 4,
        }]),
        patch("project_guardian.auto_learning.fetch_twitter", MagicMock()),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch(
            "project_guardian.auto_learning.finalize_learned_collection",
            return_value={
                "fetched": 1,
                "archived": 1,
                "admitted": 0,
                "rejected": 1,
                "cross_session_duplicates": 0,
                "file": "",
                "memory_count": 0,
            },
        ),
    ):
        run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["AI", "automation"],
            memory=None,
            llm_callback=None,
            chatlogs_path=tmp_path,
            twitter_bearer_token=None,
            default_reddit_subs=["MachineLearning"],
        )

    assert len(_CaptureContextMistral.contexts) == 2
    second_context = _CaptureContextMistral.contexts[1]
    assert "After round 1" in second_context
    assert "Planner latency thread" in second_context


def test_sanitize_chained_learning_plan_prefers_grounded_queries_and_known_subs():
    plan = sanitize_chained_learning_plan(
        {
            "twitter_queries": ["Elysia AI development roadmap"],
            "reddit_subreddits_new": ["elysiaai", "LocalLLaMA"],
            "reddit_searches": [
                {"subreddit": "selfawarenessai", "q": "latest discussions"},
                {"subreddit": "MachineLearning", "q": "customer complaint automation"},
            ],
            "wikipedia_titles": ["Project Guardian (AI)", "Self-aware artificial intelligence"],
            "reasoning": "bad raw plan",
        },
        topics=["AI", "automation", "customer complaints", "service ideas"],
        cfg={
            "twitter_search_queries": [
                "AI agents",
                "automation pain point",
                "customer complaint automation",
                "AI service idea",
            ],
            "reddit_subs": ["MachineLearning", "automation"],
        },
        seed_twitter_queries=["AI agents", "automation pain point", "customer complaint automation"],
        default_reddit_subs=["passive_income"],
        per_source_cap=2,
    )

    assert plan["twitter_queries"]
    assert "elysia" not in plan["twitter_queries"][0].lower()
    assert any(term in plan["twitter_queries"][0].lower() for term in ("pain point", "complaint", "service"))
    assert plan["reddit_subreddits_new"] == ["LocalLLaMA"]
    assert plan["reddit_searches"] == [{"subreddit": "MachineLearning", "q": "customer complaint automation"}]
    assert all("project guardian" not in title.lower() for title in plan["wikipedia_titles"])


def test_sanitize_chained_learning_plan_uses_reddit_seed_fallback_when_all_subs_are_invalid():
    plan = sanitize_chained_learning_plan(
        {
            "twitter_queries": ["customer complaint automation"],
            "reddit_subreddits_new": ["elysiaai", "selfawarenessai"],
            "reddit_searches": [{"subreddit": "ai", "q": "latest discussions"}],
            "wikipedia_titles": [],
            "reasoning": "bad reddit targets",
        },
        topics=["AI", "automation"],
        cfg={"reddit_subs": ["MachineLearning", "automation"]},
        seed_twitter_queries=["customer complaint automation"],
        default_reddit_subs=["passive_income"],
        per_source_cap=2,
    )

    assert plan["reddit_subreddits_new"] == CHAINED_EMPTY_PLAN_REDDIT_SEEDS[:2]
    assert plan["reddit_searches"] == []


def test_external_learning_query_terms_ignore_chatlog_goal_terms():
    terms = _build_learning_query_terms(
        ["automation"],
        {
            "topics": ["AI", "customer complaints"],
            "chatlog_goal_terms": ["income stream", "revenue plan", "personal finance"],
            "learning_target_terms": ["API grants", "compute credits"],
            "twitter_search_queries": ["automation pain point"],
        },
        ["customer complaint automation"],
    )

    lower = {term.lower() for term in terms}
    assert "income stream" not in lower
    assert "revenue plan" not in lower
    assert "personal finance" not in lower
    assert "api grants" in lower
    assert "compute credits" in lower
    assert "automation pain point" in lower


def test_chained_learning_sanitizes_bad_targets_before_fetch(tmp_path):
    twitter_queries: list[str] = []
    reddit_new: list[str] = []
    reddit_searches: list[tuple[str, str]] = []
    wiki_titles: list[str] = []

    def capture_twitter(query, token, limit=2):
        twitter_queries.append(query)
        return [{"source": "twitter", "title": query, "text": "Demand signal.", "url": ""}]

    def capture_reddit(sub, limit=2):
        reddit_new.append(sub)
        return [{"source": "reddit", "title": sub, "text": "Discussion text." * 10, "url": ""}]

    def capture_reddit_search(sub, query, limit=2):
        reddit_searches.append((sub, query))
        return [{"source": "reddit", "title": query, "text": "Search result text." * 10, "url": ""}]

    def capture_wiki(title):
        wiki_titles.append(title)
        return None

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _BadTargetPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 1,
            "mistral_chained_per_source_cap": 2,
            "twitter_search_queries": [
                "AI agents",
                "automation pain point",
                "customer complaint automation",
            ],
            "reddit_subs": ["MachineLearning", "automation"],
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_twitter", side_effect=capture_twitter),
        patch("project_guardian.auto_learning.fetch_reddit", side_effect=capture_reddit),
        patch("project_guardian.auto_learning.fetch_reddit_search", side_effect=capture_reddit_search),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", side_effect=capture_wiki),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch(
            "project_guardian.auto_learning.finalize_learned_collection",
            return_value={
                "fetched": 0,
                "archived": 0,
                "admitted": 0,
                "rejected": 0,
                "cross_session_duplicates": 0,
                "file": "",
                "memory_count": 0,
            },
        ),
    ):
        run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["AI", "automation", "customer complaints", "service ideas"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token="token",
            default_reddit_subs=["passive_income"],
            seed_twitter_queries=["AI agents", "automation pain point", "customer complaint automation"],
        )

    assert twitter_queries
    assert all("elysia" not in q.lower() for q in twitter_queries)
    assert any(any(term in q.lower() for term in ("pain point", "complaint", "service")) for q in twitter_queries)
    assert reddit_new == ["LocalLLaMA"]
    assert reddit_searches == [("MachineLearning", "customer complaint automation")]
    assert all("project guardian" not in title.lower() for title in wiki_titles)


def test_chained_learning_drops_low_signal_social_items_before_archive(tmp_path):
    captured = {}

    def _fake_finalize(collected, storage_path, topics, memory, sources_count=1):
        captured["titles"] = [item.get("title") for item in collected]
        captured["sources"] = [item.get("source") for item in collected]
        return {
            "fetched": len(collected),
            "archived": len(collected),
            "admitted": 0,
            "rejected": len(collected),
            "cross_session_duplicates": 0,
            "file": "",
            "memory_count": 0,
        }

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _GroundedPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 1,
            "mistral_chained_per_source_cap": 2,
            "mistral_chained_max_chatlogs": 0,
            "twitter_search_queries": ["customer complaint automation"],
            "reddit_subs": ["MachineLearning"],
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_twitter", return_value=[
            {
                "source": "twitter",
                "title": "As I work with merchant brands",
                "text": "As I work with merchant brands, data automation is key, check out my tool and follow me.",
                "url": "",
                "public_metrics": {"like_count": 0, "reply_count": 0, "retweet_count": 0},
            },
            {
                "source": "twitter",
                "title": "Customer complaint automation bottleneck",
                "text": "Teams keep complaining that manual customer complaint triage is time-consuming and needs automation.",
                "url": "",
                "public_metrics": {"like_count": 4, "reply_count": 1, "retweet_count": 0},
            },
        ]),
        patch("project_guardian.auto_learning.fetch_reddit", return_value=[
            {
                "source": "reddit",
                "title": "ML workflow bottleneck",
                "text": "Training evaluation is still manual and a workflow bottleneck for our team.",
                "url": "",
                "score": 5,
                "num_comments": 4,
            }
        ]),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch("project_guardian.auto_learning.finalize_learned_collection", side_effect=_fake_finalize),
    ):
        run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation", "customer complaints"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token="token",
            default_reddit_subs=["MachineLearning"],
            seed_twitter_queries=["customer complaint automation"],
        )

    assert captured["titles"] == [
        "Customer complaint automation bottleneck",
        "ML workflow bottleneck",
    ]


def test_chained_learning_skips_recent_twitter_repeat_between_runs(tmp_path):
    _AlternatingTwitterPlanMistral.run_counter = 0
    captured_runs: list[list[str]] = []

    def _fake_finalize(collected, storage_path, topics, memory, sources_count=1):
        captured_runs.append([item.get("title") for item in collected])
        return {
            "fetched": len(collected),
            "archived": len(collected),
            "admitted": 0,
            "rejected": len(collected),
            "cross_session_duplicates": 0,
            "file": "",
            "memory_count": 0,
        }

    def _capture_twitter(query, token, limit=2):
        return [{
            "source": "twitter",
            "query": query,
            "title": "Complaint-sorting workflow bottleneck",
            "text": "Teams keep complaining that complaint sorting is manual, time-consuming, and needs automation.",
            "url": "https://twitter.com/i/status/12345",
            "public_metrics": {"like_count": 3, "reply_count": 1, "retweet_count": 0},
        }]

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _AlternatingTwitterPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 1,
            "mistral_chained_per_source_cap": 1,
            "mistral_chained_max_chatlogs": 0,
            "mistral_chained_social_repeat_cooldown_hours": 24,
            "twitter_search_queries": ["automation pain point", "customer complaint automation"],
            "reddit_subs": ["MachineLearning"],
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_twitter", side_effect=_capture_twitter),
        patch("project_guardian.auto_learning.fetch_reddit", return_value=[]),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch("project_guardian.auto_learning.finalize_learned_collection", side_effect=_fake_finalize),
    ):
        first = run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation", "customer complaints"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token="token",
            default_reddit_subs=["MachineLearning"],
            seed_twitter_queries=["automation pain point", "customer complaint automation"],
        )
        second = run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation", "customer complaints"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token="token",
            default_reddit_subs=["MachineLearning"],
            seed_twitter_queries=["automation pain point", "customer complaint automation"],
        )

    assert first["fetched"] == 1
    assert second["fetched"] == 0
    assert captured_runs == [["Complaint-sorting workflow bottleneck"], []]


def test_chained_learning_skips_recent_reddit_repeat_across_modes_between_runs(tmp_path):
    _AlternatingRedditPlanMistral.run_counter = 0
    captured_runs: list[list[str]] = []

    def _fake_finalize(collected, storage_path, topics, memory, sources_count=1):
        captured_runs.append([item.get("title") for item in collected])
        return {
            "fetched": len(collected),
            "archived": len(collected),
            "admitted": 0,
            "rejected": len(collected),
            "cross_session_duplicates": 0,
            "file": "",
            "memory_count": 0,
        }

    reddit_item = {
        "source": "reddit",
        "subreddit": "MachineLearning",
        "title": "Workflow bottleneck in customer complaint triage",
        "text": "Our team still handles complaint triage manually and it remains a workflow bottleneck.",
        "url": "https://reddit.com/r/MachineLearning/comments/abc123/workflow_bottleneck",
        "score": 5,
        "num_comments": 4,
    }

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _AlternatingRedditPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": False,
            "mistral_chained_max_rounds": 1,
            "mistral_chained_per_source_cap": 1,
            "mistral_chained_max_chatlogs": 0,
            "mistral_chained_social_repeat_cooldown_hours": 24,
            "twitter_search_queries": [],
            "reddit_subs": ["MachineLearning"],
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_twitter", return_value=[]),
        patch("project_guardian.auto_learning.fetch_reddit", return_value=[dict(reddit_item)]),
        patch("project_guardian.auto_learning.fetch_reddit_search", return_value=[dict(reddit_item, reddit_mode="search", reddit_query="customer complaint automation")]),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch("project_guardian.auto_learning.finalize_learned_collection", side_effect=_fake_finalize),
    ):
        first = run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation", "customer complaints"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token=None,
            default_reddit_subs=["MachineLearning"],
        )
        second = run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation", "customer complaints"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token=None,
            default_reddit_subs=["MachineLearning"],
        )

    assert first["fetched"] == 1
    assert second["fetched"] == 0
    assert captured_runs == [["Workflow bottleneck in customer complaint triage"], []]


def test_chained_learning_skips_moltbook_during_same_day_cooldown(tmp_path):
    captured_runs: list[list[str]] = []
    moltbook_calls = {"count": 0}

    def _fake_finalize(collected, storage_path, topics, memory, sources_count=1):
        captured_runs.append([item.get("title") for item in collected])
        return {
            "fetched": len(collected),
            "archived": len(collected),
            "admitted": 0,
            "rejected": len(collected),
            "cross_session_duplicates": 0,
            "file": "",
            "memory_count": 0,
        }

    def _fake_moltbook(_topics):
        moltbook_calls["count"] += 1
        return [{
            "source": "moltbook",
            "title": "Moltbook: agent internet front page",
            "text": "Visible headlines and agent internet activity summary.",
            "url": "https://www.moltbook.com/",
        }]

    with (
        patch("project_guardian.mistral_engine.MistralEngine", _EmptyPlanMistral),
        patch("project_guardian.ollama_model_config.get_canonical_ollama_model", return_value="mistral:7b"),
        patch("project_guardian.planner_readiness.should_short_circuit_verify_ollama_for_bad_tag", return_value=(False, "")),
        patch("project_guardian.auto_learning.load_learning_config", return_value={
            "enable_moltbook_auto_learn": True,
            "mistral_chained_max_rounds": 1,
            "mistral_chained_per_source_cap": 1,
            "mistral_chained_max_chatlogs": 0,
            "mistral_chained_moltbook_cooldown_hours": 24,
        }),
        patch("project_guardian.auto_learning.fetch_chatlogs", return_value=[]),
        patch("project_guardian.auto_learning.peek_chatlogs_context", return_value=""),
        patch("project_guardian.auto_learning.fetch_moltbook_for_auto_learning", side_effect=_fake_moltbook),
        patch("project_guardian.auto_learning.fetch_reddit", return_value=[]),
        patch("project_guardian.auto_learning.fetch_twitter", return_value=[]),
        patch("project_guardian.auto_learning.fetch_wikipedia_summary", return_value=None),
        patch("project_guardian.auto_learning.compress_with_llm", side_effect=lambda text, cb, *, module_name, agent_name=None: text),
        patch("project_guardian.auto_learning.finalize_learned_collection", side_effect=_fake_finalize),
    ):
        first = run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token=None,
            default_reddit_subs=["MachineLearning"],
        )
        second = run_mistral_chained_learning_session(
            storage_path=tmp_path,
            topics=["automation"],
            memory=None,
            llm_callback=None,
            chatlogs_path=None,
            twitter_bearer_token=None,
            default_reddit_subs=["MachineLearning"],
        )

    assert moltbook_calls["count"] == 1
    assert first["fetched"] == 1
    assert second["fetched"] == 0
    assert captured_runs == [["Moltbook: agent internet front page"], []]


def test_learning_run_duplicate_saturated_detects_cross_session_dup_spike():
    assert learning_run_duplicate_saturated(
        {
            "rejected": 10,
            "rejection_breakdown": {"cross_session_duplicate": 7},
            "cross_session_duplicates": 7,
        }
    )
    assert not learning_run_duplicate_saturated(
        {
            "rejected": 10,
            "rejection_breakdown": {"too_short": 10},
            "cross_session_duplicates": 0,
        }
    )


def test_sanitize_chained_plan_self_ref_whitelist_allows_explicit_phrase():
    phrase = "elysia automation pain point triage"
    plan = sanitize_chained_learning_plan(
        {
            "twitter_queries": [phrase, "who am I as an AI agent"],
            "reddit_subreddits_new": [],
            "reddit_searches": [],
            "wikipedia_titles": [],
            "reasoning": "x",
        },
        topics=["automation"],
        cfg={
            "reddit_subs": ["MachineLearning"],
            "mistral_chained_plan_self_ref_whitelist": [phrase],
        },
        seed_twitter_queries=["automation pain point"],
        default_reddit_subs=["MachineLearning"],
        per_source_cap=2,
    )
    assert phrase in plan["twitter_queries"]


def test_social_generic_launch_text_scores_below_complaint():
    complaint = {
        "source": "twitter",
        "title": "hiring is impossible for this stack",
        "text": "we tried recruiters and still cannot find senior infra " * 3,
        "public_metrics": {"like_count": 2, "reply_count": 1, "retweet_count": 0},
    }
    hype = {
        "source": "twitter",
        "title": "excited to announce our new ChatGPT wrapper launch",
        "text": "follow us for AI tips " * 25,
        "public_metrics": {"like_count": 40, "reply_count": 1, "retweet_count": 2},
    }
    c = _chained_social_item_signal_score(dict(complaint), ["automation"])
    h = _chained_social_item_signal_score(dict(hype), ["automation"])
    assert c > h


def test_append_opportunity_extractions_jsonl(tmp_path):
    _append_opportunity_extractions(
        tmp_path,
        [
            {
                "title": "API outage pain",
                "source": "reddit",
                "compressed": "operators discuss retries",
                "relevance": 4.0,
                "trust_tier": "low",
            }
        ],
        ["automation"],
    )
    p = tmp_path / OPPORTUNITY_EXTRACTIONS_FILENAME
    assert p.exists()
    raw = p.read_text(encoding="utf-8").strip().splitlines()[-1]
    import json

    row = json.loads(raw)
    assert row["opportunities"][0]["problem"] == "API outage pain"
    assert "confidence" in row["opportunities"][0]
