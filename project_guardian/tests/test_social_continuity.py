# Relationship continuity (bounded JSON store).

from __future__ import annotations

import json
from pathlib import Path

from project_guardian.social_intelligence.continuity import (
    load_continuity,
    merge_contact_after_session,
    merge_thread_after_session,
    persist_session_continuity,
    stable_thread_key,
)


def test_stable_thread_key_deterministic():
    u = ["https://moltbook.com/a", "https://moltbook.com/b"]
    assert stable_thread_key(u, "goal x") == stable_thread_key(list(reversed(u)), "goal x")


def test_merge_contact_tracks_interaction_count():
    prior = {}
    row = {"id": "@bob", "display": "@bob", "person_score": 0.55, "likely_human": 0.5}
    c, progressed = merge_contact_after_session(
        prior,
        person_row=row,
        thread_id="thr_test",
        now_ts=1000.0,
        drafted_top=True,
        cfg={"low_yield_score_threshold": 0.1, "low_yield_human_threshold": 0.1, "low_yield_streak_for_dead_end": 9},
    )
    assert c["interaction_count"] == 1
    assert c["first_seen_at"] == 1000.0
    assert c["last_thread_id"] == "thr_test"
    assert c["follow_up_status"] == "drafted"
    assert progressed is True


def test_persist_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "project_guardian.social_intelligence.continuity.ensure_social_data_dir",
        lambda: tmp_path,
    )
    state = load_continuity()
    ranked = [{"id": "@u1", "display": "@u1", "person_score": 0.7, "likely_human": 0.65, "relevance_reasons": []}]
    snap = persist_session_continuity(
        state=state,
        stable_key="tk_testkey123",
        thread_id="thr_1",
        ranked_people=ranked,
        thread_rank={"thread_score": 0.66, "likely_discussion_human_mix": 0.5, "thread_rank_reasons": ["a"]},
        modes={"draft": True, "observe": True, "speak": False},
        now_ts=2000.0,
        cfg={"followup_mix_floor": 0.3},
        human_ranking_cfg={"high_value_followup_thread_floor": 0.45},
        prioritize_ids=["@u1"],
    )
    assert snap["thread"]["revisit_count"] == 1
    p = (tmp_path / "continuity.json").read_text(encoding="utf-8")
    data = json.loads(p)
    assert data["contacts"]["@u1"]["interaction_count"] == 1
