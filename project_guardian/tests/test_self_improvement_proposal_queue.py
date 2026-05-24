# project_guardian/tests/test_self_improvement_proposal_queue.py
"""Canonical self-improvement proposal queue (no shell, no patch application, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.contracts import BrainPipelineTrace, LearningOutcome
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.brain.self_improvement_module import JsonlSelfImprovementQueue
from project_guardian.self_improvement.proposal_queue import (
    ProposalQueue,
    append_proposal,
    create_proposal,
    get_proposal,
    rank_proposals,
    sanitize_proposal,
    update_proposal_status,
)


def test_create_proposal_has_required_fields():
    p = create_proposal(
        source="test",
        source_trace_id="tid-1",
        title="T",
        problem_summary="P",
    )
    assert p.proposal_id.startswith("prop_")
    assert len(p.proposal_id) >= 10
    assert p.created_at.endswith("Z")
    assert p.status == "proposed"
    assert p.requires_human_review is True
    assert p.category == "unknown"


def test_proposal_ids_unique():
    a = create_proposal(source="a", source_trace_id="1", title="x", problem_summary="y")
    b = create_proposal(source="a", source_trace_id="1", title="x", problem_summary="y")
    assert a.proposal_id != b.proposal_id


def test_append_list_survives_new_queue_instance(tmp_path):
    path = tmp_path / "q.jsonl"
    p = create_proposal(source="s", source_trace_id="t1", title="hi", problem_summary="body")
    append_proposal(p, path=path)
    rows = ProposalQueue(path).list_latest(limit=10)
    assert len(rows) == 1
    assert rows[0].title == "hi"


def test_secrets_redacted_in_sanitize():
    p = create_proposal(
        source="s",
        source_trace_id="t",
        title="ok",
        problem_summary="token=supersecret12345",
    )
    d = sanitize_proposal(p, for_api=True)
    assert "supersecret12345" not in json.dumps(d)


def test_raw_traces_not_in_evidence_metadata():
    p = create_proposal(
        source="s",
        source_trace_id="t",
        title="x",
        problem_summary="y",
        evidence={"think_decide_act_trace": {"nested": 1}, "ok": True},
        metadata={"raw_trace": {"x": 1}, "note": "fine"},
    )
    d = sanitize_proposal(p, for_api=False)
    assert "think_decide_act_trace" not in d.get("evidence", {})
    assert "raw_trace" not in d.get("metadata", {})


def test_rank_orders_high_priority_first(tmp_path):
    path = tmp_path / "q.jsonl"
    low = create_proposal(
        source="s",
        source_trace_id="a",
        title="l",
        problem_summary="p",
        priority_score=0.2,
    )
    high = create_proposal(
        source="s",
        source_trace_id="b",
        title="h",
        problem_summary="p",
        priority_score=0.95,
    )
    append_proposal(low, path=path)
    append_proposal(high, path=path)
    ranked = rank_proposals(ProposalQueue(path).read_all())
    assert ranked[0].priority_score >= ranked[-1].priority_score


def test_status_update_allowed(tmp_path):
    path = tmp_path / "q.jsonl"
    p = create_proposal(source="s", source_trace_id="t", title="x", problem_summary="y")
    append_proposal(p, path=path)
    ok, msg = update_proposal_status(p.proposal_id, "accepted", note="lgtm", path=path)
    assert ok and msg == "ok"
    row = get_proposal(p.proposal_id, path=path)
    assert row and row["status"] == "accepted"


def test_invalid_status_rejected(tmp_path):
    path = tmp_path / "q.jsonl"
    p = create_proposal(source="s", source_trace_id="t", title="x", problem_summary="y")
    append_proposal(p, path=path)
    ok, msg = update_proposal_status(p.proposal_id, "proposed", path=path)
    assert ok is False
    assert "invalid" in msg


def test_api_list_sanitized(tmp_path):
    path = tmp_path / "q.jsonl"
    append_proposal(
        create_proposal(
            source="api",
            source_trace_id="tr",
            title="t",
            problem_summary="Bearer abcdef1234567890",
        ),
        path=path,
    )
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        self_improvement_queue=ProposalQueue(path),
    )
    r = server._app.test_client().get("/api/self-improvement/proposals")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert "abcdef1234567890" not in json.dumps(body)


def test_api_detail_and_status(tmp_path):
    path = tmp_path / "q.jsonl"
    p = create_proposal(source="s", source_trace_id="z", title="one", problem_summary="p")
    append_proposal(p, path=path)
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        self_improvement_queue=ProposalQueue(path),
    )
    c = server._app.test_client()
    r1 = c.get(f"/api/self-improvement/proposals/{p.proposal_id}")
    assert r1.status_code == 200
    assert r1.get_json()["proposal"]["proposal_id"] == p.proposal_id
    r2 = c.post(
        f"/api/self-improvement/proposals/{p.proposal_id}/status",
        json={"status": "rejected", "note": "no"},
    )
    assert r2.status_code == 200
    assert r2.get_json()["proposal"]["status"] == "rejected"


def test_api_status_does_not_execute_shell(tmp_path, monkeypatch):
    path = tmp_path / "q.jsonl"
    p = create_proposal(source="s", source_trace_id="z", title="one", problem_summary="p")
    append_proposal(p, path=path)

    def boom(*a, **k):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr("subprocess.run", boom)
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        self_improvement_queue=ProposalQueue(path),
    )
    r = server._app.test_client().post(
        f"/api/self-improvement/proposals/{p.proposal_id}/status",
        json={"status": "deferred"},
    )
    assert r.status_code == 200


def test_brain_pipeline_enqueue_writes_canonical_only_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE", raising=False)
    leg = tmp_path / "legacy.jsonl"
    can = tmp_path / "canonical.jsonl"
    si = JsonlSelfImprovementQueue(leg, canonical_path=can)
    trace = BrainPipelineTrace()
    trace.brain_pipeline_id = "abc123"
    trace.transitions = ["a", "self_improvement_enqueued"]
    out = LearningOutcome(worked=False, lesson="lesson text", improvement_hints=["hint1"])
    si.enqueue(out, trace)
    assert can.exists() and can.stat().st_size > 0
    assert not leg.exists()
    rows = ProposalQueue(can).read_all()
    assert any(r.source_trace_id == "abc123" for r in rows)


def test_brain_pipeline_enqueue_dual_write_when_legacy_env_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE", "1")
    leg = tmp_path / "legacy.jsonl"
    can = tmp_path / "canonical.jsonl"
    si = JsonlSelfImprovementQueue(leg, canonical_path=can)
    trace = BrainPipelineTrace()
    trace.brain_pipeline_id = "dual123"
    out = LearningOutcome(worked=True, lesson="ok", improvement_hints=[])
    si.enqueue(out, trace)
    assert leg.exists() and leg.stat().st_size > 0
    assert can.exists() and can.stat().st_size > 0
    rows = ProposalQueue(can).read_all()
    assert any(r.source_trace_id == "dual123" for r in rows)


def test_default_pipe_does_not_create_proposals_without_run(tmp_path):
    """No proposals from merely constructing BrainPipeline."""
    can = tmp_path / "empty.jsonl"
    assert not can.exists()
    _ = BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        self_improvement=JsonlSelfImprovementQueue(tmp_path / "leg.jsonl", canonical_path=can),
    )
    assert not can.exists()


def test_trace_summary_includes_proposal_count(tmp_path, monkeypatch):
    from project_guardian.brain.trace_visibility import load_latest_brain_trace_summary
    from project_guardian.tests.test_brain_trace_visibility import _cfg, _valid_trace

    can = tmp_path / "prop.jsonl"
    trace_path = tmp_path / "brain.json"
    tid = "brain-123"
    trace_path.write_text(json.dumps(_valid_trace(brain_pipeline_id=tid)), encoding="utf-8")
    append_proposal(
        create_proposal(
            source="brain_pipeline",
            source_trace_id=tid,
            title="x",
            problem_summary="y",
        ),
        path=can,
    )
    monkeypatch.setattr(
        "project_guardian.self_improvement.proposal_queue.DEFAULT_PROPOSALS_PATH",
        can,
    )
    out = load_latest_brain_trace_summary(config=_cfg(trace_path))
    assert out.get("self_improvement_proposal_count") == 1
