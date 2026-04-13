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
    run_learning_session,
    _fingerprint,
    _normalize_title,
    _snippet_norm,
    DEDUP_INDEX_FILENAME,
)


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
