# project_guardian/tests/test_memory_ranking_visibility.py
"""Read-only memory ranking API and control panel visibility."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.conversation_store import ConversationStore
from project_guardian.memory_ranking.visibility import (
    build_memory_ranking_summary,
    load_memory_ranking_visibility,
    summarize_compression_proposal,
)
from project_guardian.memory_ranking import (
    MemoryCompressionProposal,
    MemoryRankingConfig,
    build_ranking_report,
    get_memory_ranking_config,
    propose_compression_from_dicts,
)


def test_summary_helper_returns_safe_empty_summary_when_no_memories_exist():
    summary = build_memory_ranking_summary(config=MemoryRankingConfig(), memories=[], limit=10)

    assert summary["available"] is True
    assert summary["sample_source"] == "none"
    assert summary["memory_count"] == 0
    assert summary["enabled"] is False
    assert summary["dry_run"] is True
    assert summary["mutation_allowed"] is False
    assert summary["delete_allowed"] is False
    assert summary["proposal_counts"] == {
        "keep_full": 0,
        "compress": 0,
        "archive": 0,
        "review_manually": 0,
    }
    assert summary["top_ranked"] == []
    assert summary["compression_proposals"] == []


def test_load_visibility_returns_safe_empty_summary_when_no_memories_exist(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    summary = load_memory_ranking_visibility(conversation_store=store, limit=10)
    assert summary["available"] is True
    assert summary["sample_source"] == "none"
    assert summary["memory_count"] == 0
    assert summary["mutation_allowed"] is False
    assert summary["delete_allowed"] is False
    assert summary["proposal_counts"]["keep_full"] == 0


def test_summary_helper_ranks_provided_conversation_messages(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    store.append_message("c1", role="user", content="Important decision: keep operator chat dry-run only.")
    store.append_message(
        "c1",
        role="assistant",
        content=("Routine heartbeat status unchanged. " * 30).strip(),
    )
    summary = build_memory_ranking_summary(conversation_store=store, config=MemoryRankingConfig(), limit=10)
    assert summary["sample_source"] == "conversation_store"
    assert summary["memory_count"] >= 2
    assert len(summary["top_ranked"]) >= 2
    assert summary["top_ranked"][0]["memory_value_score"] >= summary["top_ranked"][-1]["memory_value_score"]
    assert summary["top_ranked"][0]["text_preview"]


def test_secrets_are_redacted(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    store.append_message(
        "c1",
        role="user",
        content=(
            "api_key=alpha123 token=bravo456 password=charlie789 "
            "Authorization: Bearer delta-token sk-123456789012345678901234567890"
        ),
    )
    summary = load_memory_ranking_visibility(conversation_store=store, limit=5)
    blob = json.dumps(summary)
    assert "alpha123" not in blob
    assert "bravo456" not in blob
    assert "charlie789" not in blob
    assert "delta-token" not in blob
    assert "sk-123456789012345678901234567890" not in blob
    assert "[REDACTED]" in blob


def test_compression_proposals_are_advisory_only():
    cfg = get_memory_ranking_config()
    samples = [
        {
            "id": "long-low",
            "thought": ("Routine heartbeat. " * 50).strip(),
            "time": "2021-01-01T00:00:00+00:00",
        },
        {
            "id": "high",
            "thought": "Important decision: user prefers concise status.",
            "time": "2026-05-14T10:00:00+00:00",
            "user_important": True,
        },
    ]
    report = propose_compression_from_dicts(samples, cfg=cfg)
    summary = build_memory_ranking_summary(report, cfg=cfg, sample_source="sample")
    assert summary["compression_proposals"]
    for row in summary["compression_proposals"]:
        assert row["advisory_only"] is True
        assert row["dry_run"] is True
        assert row["action"] in {"compress", "archive", "review_manually"}
        proposal_blob = json.dumps(row).lower()
        assert "apply" not in proposal_blob
        assert "delete" not in proposal_blob
        assert "mutate" not in proposal_blob


def test_response_never_includes_mutation_controls():
    cfg = get_memory_ranking_config()
    summary = build_memory_ranking_summary(
        build_ranking_report([], cfg),
        cfg=cfg,
        sample_source="none",
    )
    blob = json.dumps(summary).lower()
    assert "apply" not in blob or "mutation_allowed" in blob
    assert summary["mutation_allowed"] is False
    assert "delete_allowed" in summary
    assert summary["delete_allowed"] is False
    prop = summarize_compression_proposal(
        MemoryCompressionProposal(
            memory_id="x",
            current_length=10,
            proposed_summary="hi",
            reason="test",
            original_value_score=0.1,
            risk_of_loss=0.2,
            action="compress",
            dry_run=True,
        )
    )
    assert "apply" not in prop
    assert prop["advisory_only"] is True


def test_control_panel_includes_memory_ranking_panel():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    html = CONTROL_PANEL_TEMPLATE
    assert "Memory Ranking" in html
    assert "memory-ranking-summary" in html
    assert "refreshMemoryRankingSummary" in html or "refreshMemoryRanking" in html


def test_control_panel_calls_ranking_summary_api():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    assert "/api/memory/ranking/summary" in CONTROL_PANEL_TEMPLATE


def test_control_panel_contains_read_only_safety_label():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    idx = CONTROL_PANEL_TEMPLATE.find('id="memory-ranking-panel"')
    assert idx >= 0
    block = CONTROL_PANEL_TEMPLATE[idx : idx + 2500]
    assert "Read-only advisory ranking" in block
    assert "No memory changes are applied" in block


def test_conversation_memory_local_storage_still_present():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    html = CONTROL_PANEL_TEMPLATE
    assert "conversation_id" in html
    assert "elysia_control_panel_conversation_id" in html
    assert "getApiChatConversationId" in html
    assert "localStorage" in html
    assert "/api/conversations" in html
    assert "/api/chat/history" in html


def test_runtime_api_memory_ranking_summary(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    store.append_message("c1", role="user", content="hello ranking")
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        conversation_store=store,
    )
    r = server._app.test_client().get("/api/memory/ranking/summary?limit=5")
    assert r.status_code == 200
    body = r.get_json()
    assert body["available"] is True
    assert "enabled" in body
    assert "dry_run" in body
    assert body["mutation_allowed"] is False
    assert body["delete_allowed"] is False
    assert "proposal_counts" in body
    assert "top_ranked" in body
    assert "compression_proposals" in body
    assert body["sample_source"] == "conversation_store"
    assert body["memory_count"] >= 1


def test_smoke_script_includes_memory_ranking_visibility_test():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_safe_stack_smoke_tests.py"
    text = script.read_text(encoding="utf-8")
    assert "project_guardian/tests/test_memory_ranking_visibility.py" in text


def test_no_llm_reviewer_invoked_by_default(monkeypatch):
    called = {"n": 0}

    def fake_reviewer(_ranked):
        called["n"] += 1
        return _ranked

    monkeypatch.setattr(
        "project_guardian.memory_ranking.ranking.review_memory_scores_with_llm",
        lambda ranked, reviewer=None: fake_reviewer(ranked) if reviewer else ranked,
    )
    cfg = get_memory_ranking_config()
    report = build_ranking_report(
        [],
        cfg,
        reviewer=None,
    )
    assert called["n"] == 0
    assert report.proposals == []


def test_no_memory_mutation_on_summary_load(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    store.append_message("c1", role="user", content="stable content")
    conv_path = store._path("c1")
    before = conv_path.read_text(encoding="utf-8") if conv_path.exists() else ""
    load_memory_ranking_visibility(conversation_store=store, limit=5)
    after = conv_path.read_text(encoding="utf-8") if conv_path.exists() else ""
    assert before == after


def test_memory_ranking_block_has_no_apply_compress_delete_buttons():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    idx = CONTROL_PANEL_TEMPLATE.find('id="memory-ranking-panel"')
    assert idx >= 0
    block = CONTROL_PANEL_TEMPLATE[idx : idx + 2500]
    assert "refreshMemoryRankingSummary" in CONTROL_PANEL_TEMPLATE
    forbidden = re.findall(
        r"onclick=[\"'][^\"']*(?:apply|compress|delete|archive|mutate)[^\"']*[\"']",
        block,
        re.I,
    )
    assert not forbidden
