# project_guardian/tests/test_control_panel_brain_visibility.py
"""Control panel HTML/JS and API routes for brain trace + self-improvement proposals."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from project_guardian.self_improvement.proposal_queue import (
    ProposalQueue,
    append_proposal,
    create_proposal,
)


def _imports():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE, UIControlPanel
    except ImportError:
        pytest.skip("UIControlPanel not available")
    return CONTROL_PANEL_TEMPLATE, UIControlPanel


def _html() -> str:
    template, _ = _imports()
    return template


@pytest.fixture
def panel_client(tmp_path, monkeypatch):
    _, UIControlPanelCls = _imports()
    qpath = tmp_path / "proposals.jsonl"
    monkeypatch.setattr(
        "project_guardian.self_improvement.proposal_queue.DEFAULT_PROPOSALS_PATH",
        qpath,
    )
    from project_guardian.self_improvement import proposal_queue as pq

    monkeypatch.setattr(pq, "_default_queue", None)
    panel = UIControlPanelCls(orchestrator=Mock())
    panel.app.config["TESTING"] = True
    return panel.app.test_client(), qpath


def test_control_panel_contains_brain_trace_panel():
    html = _html()
    assert "Brain Trace" in html
    assert "brain-trace-summary" in html
    assert "brain-visibility-panel" in html


def test_control_panel_calls_brain_trace_api():
    html = _html()
    assert "/api/brain/trace/latest" in html
    assert "refreshBrainTrace" in html or "refreshBrainTraceVisibility" in html


def test_control_panel_contains_self_improvement_proposals_panel():
    html = _html()
    assert "Self-Improvement Proposals" in html
    assert "self-improvement-proposals-list" in html or "self-improvement-proposals" in html


def test_control_panel_calls_self_improvement_proposals_api():
    html = _html()
    assert "/api/self-improvement/proposals" in html


def test_status_buttons_only_call_status_endpoint():
    html = _html()
    assert "/status" in html
    assert re.search(
        r"/api/self-improvement/proposals/['\"]\s*\+\s*encodeURIComponent",
        html,
    ) or "/api/self-improvement/proposals/' + encodeURIComponent" in html
    assert "apply_patch" not in html.lower()
    assert "run_command" not in html.lower()
    forbidden = re.findall(
        r"onclick=[\"'][^\"']*(?:apply_patch|run_command|subprocess)[^\"']*[\"']",
        html,
        re.I,
    )
    assert not forbidden


def test_review_only_safety_text_present():
    html = _html()
    assert "Review-only" in html
    assert "does not apply code" in html


def test_conversation_memory_local_storage_still_present():
    html = _html()
    assert "elysia_control_panel_conversation_id" in html
    assert "getApiChatConversationId" in html
    assert "localStorage" in html
    assert "api-chat-conv-label" in html


def test_brain_trace_endpoint_renders_without_crash(panel_client, tmp_path, monkeypatch):
    client, _ = panel_client
    trace_path = tmp_path / "brain_trace.json"
    trace_path.write_text(
        json.dumps(
            {
                "brain_pipeline_id": "brain-ui-test",
                "started_at": "2026-05-14T12:00:00+00:00",
                "input_source": "operator_chat",
                "risk": "low",
                "execution_ok": True,
                "think_decide_act_trace_present": True,
                "transitions": ["observation_received"],
                "dry_run": True,
            }
        ),
        encoding="utf-8",
    )

    from project_guardian.brain.config import BrainPipelineConfig

    ep = {
        "operator_chat": False,
        "operator_chat_live_execution": False,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }
    cfg = BrainPipelineConfig(
        enabled=False,
        use_think_decide_act=True,
        dry_run=True,
        persist_trace=True,
        trace_path=trace_path,
        entrypoints=ep,
    )
    monkeypatch.setattr(
        "project_guardian.brain.config.get_brain_pipeline_config",
        lambda **_k: cfg,
    )
    r = client.get("/api/brain/trace/latest")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("trace_exists") is True
    assert body.get("brain_pipeline_id") == "brain-ui-test" or (
        body.get("trace") or {}
    ).get("brain_pipeline_id") == "brain-ui-test"


def test_proposal_list_endpoint_renders_without_crash(panel_client):
    client, qpath = panel_client
    append_proposal(
        create_proposal(
            source="test",
            source_trace_id="t1",
            title="UI proposal",
            problem_summary="summary",
        ),
        path=qpath,
    )
    r = client.get("/api/self-improvement/proposals")
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("success") is True
    assert len(body.get("proposals") or []) >= 1


def test_proposal_status_endpoint_updates_only(panel_client, monkeypatch):
    client, qpath = panel_client
    p = create_proposal(
        source="test",
        source_trace_id="t2",
        title="Status test",
        problem_summary="p",
    )
    append_proposal(p, path=qpath)

    def boom(*_a, **_k):
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr("subprocess.run", boom)
    r = client.post(
        f"/api/self-improvement/proposals/{p.proposal_id}/status",
        json={"status": "reviewing", "note": "test"},
    )
    assert r.status_code == 200
    assert r.get_json().get("success") is True
    row = ProposalQueue(qpath).get(p.proposal_id)
    assert row is not None
    assert row.status == "reviewing"
