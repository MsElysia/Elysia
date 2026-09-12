# project_guardian/tests/test_auto_learning_session.py
# End-to-end auto-learning session test: fetched, archived, admitted, rejected,
# rejection_breakdown, archived_only metadata, and memory.remember calls.
# Uses temp storage and stubs only; no network access.

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.auto_learning import (
    AutoLearningScheduler,
    run_learning_session,
    _fingerprint,
    _normalize_title,
    _snippet_norm,
    DEDUP_INDEX_FILENAME,
)
import project_guardian.auto_learning as auto_learning


# --- Test data mix ---
# Item 1 (rss): ADMIT - good content, topic relevance
GOOD_RSS_1 = {
    "source": "rss",
    "title": "AI Advances 2025",
    "text": "AI and machine learning developments. " * 10,
    "url": "",
}
# Item 2 (rss): REJECT too_short
TOO_SHORT = {
    "source": "rss",
    "title": "x",
    "text": "y",
    "url": "",
}
# Item 3 (rss): REJECT generic_title
GENERIC_TITLE = {
    "source": "rss",
    "title": "[spam]",
    "text": "A" * 100,
    "url": "",
}
# Item 4 (reddit): REJECT low_trust (allow_reddit=False)
LOW_TRUST = {
    "source": "reddit",
    "title": "Reddit AI Discussion",
    "text": "A thoughtful post about AI and machine learning. " * 5,
    "url": "",
}
# Item 5 (rss): REJECT cross_session_duplicate (same content as GOOD_RSS_1)
DUP_RSS = {
    "source": "rss",
    "title": "AI Advances 2025",
    "text": "AI and machine learning developments. " * 10,
    "url": "",
}
# Item 6 (rss): ADMIT - good content (must classify operational/strategic for memory gate)
GOOD_RSS_2 = {
    "source": "rss",
    "title": "Machine Learning Progress",
    "text": ("Code deployment and runtime notes. " + "machine learning progress and research. ") * 10,
    "url": "",
}


def _fake_fetch_reddit(subreddit: str, limit: int = 5, max_retries: int = 2):
    """Stub: return one reddit item (low_trust)."""
    return [dict(LOW_TRUST)]


def _fake_fetch_rss(feed_url: str, limit: int = 5, max_retries: int = 2):
    """Stub: return five rss items in deterministic order."""
    return [
        dict(GOOD_RSS_1),
        dict(TOO_SHORT),
        dict(GENERIC_TITLE),
        dict(DUP_RSS),
        dict(GOOD_RSS_2),
    ]


def _fake_load_config():
    """Stub: return config with allow_reddit=False, topics for relevance."""
    return {
        "allow_reddit_into_memory": False,
        "min_relevance_score": 1,
        "max_archived_per_session": 100,
        "max_memory_per_session": 20,
        "max_per_source_memory": 5,
        "dedup_window_days": 30,
        "enable_moltbook_auto_learn": False,
    }


class TestAutoLearningSessionE2E:
    """End-to-end session: counts, metadata, memory.remember."""

    def test_session_result_counts_and_metadata_consistent(self):
        """Fetched, archived, admitted, rejected, rejection_breakdown all line up."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp)
            # Pre-populate dedup index so DUP_RSS is cross_session_duplicate
            dup_text = GOOD_RSS_1["text"]
            fp = _fingerprint(dup_text)
            now_iso = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            dedup_path = storage / DEDUP_INDEX_FILENAME
            storage.mkdir(parents=True, exist_ok=True)
            with open(dedup_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": 2,
                    "records": [{
                        "fp": fp,
                        "title_norm": _normalize_title(GOOD_RSS_1["title"]),
                        "snippet_norm": _snippet_norm(dup_text),
                        "first_seen": now_iso,
                        "last_seen": now_iso,
                        "source": "rss",
                        "admitted_to_memory": False,
                    }],
                }, f)

            memory = MagicMock()

            with (
                patch("project_guardian.auto_learning.fetch_reddit", side_effect=_fake_fetch_reddit),
                patch("project_guardian.auto_learning.fetch_rss", side_effect=_fake_fetch_rss),
                patch("project_guardian.auto_learning.load_learning_config", side_effect=_fake_load_config),
            ):
                result = run_learning_session(
                    storage_path=storage,
                    topics=["AI", "machine learning"],
                    reddit_subs=["test"],
                    rss_feeds=["http://test.local/feed"],
                    max_per_source=10,
                    memory=memory,
                )

            # --- Count consistency ---
            fetched = result["fetched"]
            archived = result["archived"]
            admitted = result["admitted"]
            rejected = result["rejected"]
            breakdown = result["rejection_breakdown"]

            assert fetched == 6
            assert archived == 6
            assert admitted + rejected == archived
            assert sum(breakdown.values()) == rejected

            # --- Expected counts (dedup pre-populated: item 1 & 5 both cross_session_duplicate) ---
            assert admitted == 1
            assert rejected == 5
            assert breakdown.get("too_short", 0) == 1
            assert breakdown.get("generic_title", 0) == 1
            assert breakdown.get("low_trust", 0) == 1
            assert breakdown.get("cross_session_duplicate", 0) == 2

            # --- Archived metadata: rejected items have archived_only + rejection_reason ---
            out_file = Path(result["file"])
            assert out_file.exists()
            lines = out_file.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 6

            archived_items = [json.loads(ln) for ln in lines]
            rejected_items = [a for a in archived_items if a.get("_arch_meta", {}).get("archived_only") is True]
            admitted_items = [a for a in archived_items if a.get("_arch_meta", {}).get("archived_only") is False]

            assert len(admitted_items) == 1
            assert len(rejected_items) == 5

            for item in rejected_items:
                meta = item.get("_arch_meta", {})
                assert meta.get("archived_only") is True
                assert "rejection_reason" in meta
                assert meta["rejection_reason"] in ("too_short", "generic_title", "low_trust", "cross_session_duplicate")

            for item in admitted_items:
                meta = item.get("_arch_meta", {})
                assert meta.get("archived_only") is False
                assert meta.get("ingestion_reason") in ("operational", "strategic")

            # --- Admitted items call memory.remember with metadata ---
            assert memory.remember.call_count == 1
            for call in memory.remember.call_args_list:
                args, kwargs = call
                assert len(args) >= 1
                assert kwargs.get("category") == "learning"
                assert "metadata" in kwargs
                md = kwargs["metadata"]
                assert "source" in md
                assert "source_trust_tier" in md
                assert "relevance_score" in md
                assert md.get("archived_only") is False
                assert md.get("ingestion_reason") in ("operational", "strategic")
                assert md.get("previously_unseen") is True


def test_wikipedia_robot_policy_block_sets_cooldown_and_skips_repeat_call():
    class _Resp:
        def __init__(self):
            self.status_code = 403
            self.text = (
                "Please respect our robot policy https://w.wiki/4wJS when crawling us. "
                "Contact bot-traffic@wikimedia.org if you need higher volumes."
            )

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

    with patch.object(auto_learning, "_WIKIPEDIA_BLOCK_UNTIL_TS", 0.0):
        with patch("httpx.Client", _Client):
            assert auto_learning.fetch_wikipedia_summary("Artificial intelligence") is None
            assert _Client.calls == 1
            assert auto_learning._WIKIPEDIA_BLOCK_UNTIL_TS > 0

            assert auto_learning.fetch_wikipedia_summary("Machine learning") is None
            assert _Client.calls == 1


def test_finalize_counts_admitted_items_even_without_memory_pipe(tmp_path):
    item = {
        "source": "rss",
        "title": "Operator-ready automation workflow",
        "text": ("Automation workflow with code deployment, runtime notes, and operator review. " * 8),
        "compressed": ("Automation workflow with code deployment, runtime notes, and operator review. " * 4),
        "url": "",
    }

    with patch(
        "project_guardian.auto_learning.load_learning_config",
        return_value={
            "allow_reddit_into_memory": True,
            "allow_strategic_into_memory": True,
            "min_relevance_score": 1,
            "min_reuse_potential": 1,
            "max_archived_per_session": 10,
            "max_memory_per_session": 10,
            "max_per_source_memory": 5,
            "dedup_window_days": 30,
        },
    ):
        result = auto_learning.finalize_learned_collection(
            [item],
            tmp_path,
            topics=["automation", "operator-ready"],
            memory=None,
            sources_count=1,
        )

    assert result["archived"] == 1
    assert result["admitted"] == 1
    assert result["memory"] == 0
    assert result["memory_count"] == 0


def test_scheduler_startup_guard_defers_without_bad_session_penalty(tmp_path):
    scheduler = AutoLearningScheduler.__new__(AutoLearningScheduler)
    scheduler.system_ref = MagicMock(guardian=MagicMock())
    scheduler.storage_path = tmp_path
    scheduler.chatlogs_path = tmp_path
    scheduler.topics = ["AI"]
    scheduler.reddit_subs = ["MachineLearning"]
    scheduler.rss_feeds = []
    scheduler.web_urls = []
    scheduler.facebook_pages = []
    scheduler.facebook_access_token = ""
    scheduler.twitter_search_queries = []
    scheduler.twitter_bearer_token = ""
    scheduler.max_per_source = 1
    scheduler.max_chatlogs = 1
    scheduler._last_run = None
    scheduler._bad_session_cooldown_until = None
    scheduler._bad_session_streak = 1

    with (
        patch("project_guardian.auto_learning.load_learning_config", return_value={"mistral_chained_learning": True}),
        patch("project_guardian.auto_learning.AutoLearningScheduler._startup_guard_reason", return_value="early_runtime_budget"),
        patch("project_guardian.auto_learning.run_mistral_chained_learning_session") as chain_mock,
        patch("project_guardian.auto_learning.run_learning_session") as flat_mock,
    ):
        scheduler._run_once()

    chain_mock.assert_not_called()
    flat_mock.assert_not_called()
    assert scheduler._bad_session_streak == 1
    assert scheduler._bad_session_cooldown_until is None
    assert scheduler._last_run is None


def test_reddit_403_sets_cooldown_and_skips_repeat_fetch():
    class _Resp:
        status_code = 403
        text = "blocked"

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
            assert auto_learning.fetch_reddit("MachineLearning") == []
            assert _Client.calls == 1
            assert auto_learning._reddit_temporarily_blocked("MachineLearning")

            assert auto_learning.fetch_reddit("MachineLearning") == []
            # second call should be skipped by cooldown (no extra network call)
            assert _Client.calls == 1
