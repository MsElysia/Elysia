# project_guardian/tests/test_auto_learning_admission.py
# Regression tests for auto-learning admission filters
# No network or real LLM - tests pure functions

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.auto_learning import (
    should_ingest_learned_item,
    score_learned_item,
    is_cross_session_duplicate,
    _fingerprint,
    _normalize_title,
    _snippet_norm,
    _build_dedup_lookup,
    _is_generic_title_for_dedup,
)


class TestAutoLearningAdmissionFilters:
    """Admission filters: low-quality, low-trust, cross-session dupes."""

    def test_low_quality_archived_not_admitted(self):
        """Low-quality items (too_short, generic_title) are not admitted."""
        topics = ["AI", "technology"]
        session_titles = set()
        session_fingerprints = set()
        config = {"allow_reddit_into_memory": True, "min_relevance_score": 1}
        caps = {"memory_admitted": 0, "max_memory_per_session": 20, "per_source": {}}
        # Too short
        admit, reason, _ = should_ingest_learned_item(
            {"compressed": "short", "title": "x", "source": "rss"},
            topics, config, session_titles, session_fingerprints, caps, dedup_lookup=None,
        )
        assert admit is False
        assert reason == "too_short"
        # Generic/spam title
        admit2, reason2, _ = should_ingest_learned_item(
            {"compressed": "A" * 100, "title": "[spam]", "source": "rss"},
            topics, config, session_titles, session_fingerprints, caps, dedup_lookup=None,
        )
        assert admit2 is False
        assert reason2 == "generic_title"

    def test_low_trust_blocked_when_allow_reddit_false(self):
        """Low-trust (reddit) items blocked when allow_reddit_into_memory=false."""
        topics = ["AI"]
        session_titles = set()
        session_fingerprints = set()
        config = {"allow_reddit_into_memory": False, "min_relevance_score": 1}
        caps = {"memory_admitted": 0, "max_memory_per_session": 20, "per_source": {}}
        item = {
            "compressed": "A thoughtful post about AI and machine learning. " * 3,
            "title": "Interesting AI Discussion",
            "source": "reddit",
        }
        admit, reason, _ = should_ingest_learned_item(
            item, topics, config, session_titles, session_fingerprints, caps, dedup_lookup=None,
        )
        assert admit is False
        assert reason == "low_trust"

    def test_low_trust_admitted_when_allow_reddit_true(self):
        """Low-trust items admitted when allow_reddit_into_memory=true."""
        topics = ["AI"]
        session_titles = set()
        session_fingerprints = set()
        config = {"allow_reddit_into_memory": True, "min_relevance_score": 1}
        caps = {"memory_admitted": 0, "max_memory_per_session": 20, "per_source": {}}
        # Content must classify as operational/strategic (not conversational-only) to pass category gate.
        item = {
            "compressed": (
                "A thoughtful post about AI and machine learning with a runtime fix for training stability. " * 3
            ),
            "title": "Interesting AI Discussion",
            "source": "reddit",
        }
        admit, reason, _ = should_ingest_learned_item(
            item, topics, config, session_titles, session_fingerprints, caps, dedup_lookup=None,
        )
        assert admit is True
        assert reason == "passed"

    def test_cross_session_duplicate_archived_only(self):
        """Cross-session duplicates are rejected (archived_only, not admitted)."""
        topics = ["AI"]
        session_titles = set()
        session_fingerprints = set()
        config = {"allow_reddit_into_memory": True, "min_relevance_score": 1}
        caps = {"memory_admitted": 0, "max_memory_per_session": 20, "per_source": {}}
        text = "A thoughtful post about AI and machine learning. " * 4
        fp = _fingerprint(text)
        record = {
            "compressed": text,
            "title": "AI Post",
            "source": "reddit",
            "title_norm": _normalize_title("AI Post"),
            "snippet_norm": _snippet_norm(text),
        }
        dedup_lookup = _build_dedup_lookup({fp: record})
        item = {"compressed": text, "title": "AI Post", "source": "reddit"}
        admit, reason, score_info = should_ingest_learned_item(
            item, topics, config, session_titles, session_fingerprints, caps, dedup_lookup=dedup_lookup,
        )
        assert admit is False
        assert reason == "cross_session_duplicate"

    def test_invalid_allow_reddit_normalizes_false_in_config_validator(self):
        """Invalid allow_reddit_into_memory normalizes to False - tested in test_startup_config."""
        # Config normalization is in config_validator.normalize_runtime_configs
        # Covered by test_startup_config::test_normalize_allow_reddit_invalid_to_false
        pass

    def test_session_result_counts_distinguish_admitted_vs_rejected(self):
        """score_learned_item and should_ingest return structured score_info."""
        topics = ["AI"]
        session_titles = set()
        session_fingerprints = set()
        # Admitted item
        good = {"compressed": "A" * 80, "title": "AI Advances", "source": "rss"}
        si = score_learned_item(good, topics, session_titles, session_fingerprints)
        assert si["admit"] is True
        assert "trust_tier" in si
        assert "relevance" in si
        # Rejected item
        bad = {"compressed": "x", "title": "y", "source": "reddit"}
        si2 = score_learned_item(bad, topics, session_titles, session_fingerprints)
        assert si2["admit"] is False
        assert "reason" in si2

    def test_dedup_generic_title_reduces_false_positives(self):
        """Generic titles (untitled, etc.) do not trigger title-only duplicate match."""
        assert _is_generic_title_for_dedup("untitled") is True
        assert _is_generic_title_for_dedup("no title") is True
        assert _is_generic_title_for_dedup("") is True
        # Specific title is not generic
        assert _is_generic_title_for_dedup("ai advances in machine learning 2025") is False
