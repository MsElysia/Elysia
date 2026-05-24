# project_guardian/tests/test_self_improvement_legacy_queue_retirement.py
"""Legacy brain_self_improvement_queue.jsonl write retirement (canonical default)."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.contracts import BrainPipelineTrace, LearningOutcome
from project_guardian.brain.self_improvement_module import JsonlSelfImprovementQueue
from project_guardian.self_improvement.prompt_export import build_proposal_prompt
from project_guardian.self_improvement.proposal_queue import (
    LEGACY_BRAIN_QUEUE_PATH,
    LEGACY_QUEUE_WRITE_ENV,
    ProposalQueue,
    append_proposal,
    count_jsonl_rows,
    create_proposal,
    legacy_queue_write_enabled,
)


@pytest.fixture(autouse=True)
def _clear_legacy_env(monkeypatch):
    monkeypatch.delenv(LEGACY_QUEUE_WRITE_ENV, raising=False)


def test_legacy_queue_write_disabled_by_default():
    assert legacy_queue_write_enabled() is False


def test_legacy_queue_write_enabled_with_env(monkeypatch):
    monkeypatch.setenv(LEGACY_QUEUE_WRITE_ENV, "1")
    assert legacy_queue_write_enabled() is True


def test_default_enqueue_writes_canonical_only(tmp_path):
    leg = tmp_path / "legacy.jsonl"
    can = tmp_path / "canonical.jsonl"
    si = JsonlSelfImprovementQueue(leg, canonical_path=can)
    trace = BrainPipelineTrace()
    trace.brain_pipeline_id = "retire-canonical"
    out = LearningOutcome(worked=False, lesson="L", improvement_hints=["h"])
    si.enqueue(out, trace)
    assert can.exists() and can.stat().st_size > 0
    assert not leg.exists()
    rows = ProposalQueue(can).read_all()
    assert len(rows) == 1
    assert rows[0].source_trace_id == "retire-canonical"


def test_default_enqueue_does_not_touch_existing_legacy_file(tmp_path):
    leg = tmp_path / "legacy.jsonl"
    can = tmp_path / "canonical.jsonl"
    original = '{"historical": true}\n'
    leg.write_text(original, encoding="utf-8")
    before = leg.read_bytes()
    si = JsonlSelfImprovementQueue(leg, canonical_path=can)
    trace = BrainPipelineTrace()
    trace.brain_pipeline_id = "no-legacy-touch"
    si.enqueue(
        LearningOutcome(worked=True, lesson="x", improvement_hints=[]),
        trace,
    )
    assert leg.read_bytes() == before
    assert ProposalQueue(can).read_all()


def test_legacy_env_enables_dual_write(tmp_path, monkeypatch):
    monkeypatch.setenv(LEGACY_QUEUE_WRITE_ENV, "true")
    leg = tmp_path / "legacy.jsonl"
    can = tmp_path / "canonical.jsonl"
    si = JsonlSelfImprovementQueue(leg, canonical_path=can)
    trace = BrainPipelineTrace()
    trace.brain_pipeline_id = "dual-env"
    si.enqueue(
        LearningOutcome(worked=False, lesson="y", improvement_hints=["z"]),
        trace,
    )
    assert leg.exists() and leg.stat().st_size > 0
    assert ProposalQueue(can).read_all()


def test_api_list_still_works_from_canonical(tmp_path):
    path = tmp_path / "canonical.jsonl"
    p = create_proposal(
        source="retire-test",
        source_trace_id="t-api",
        title="API still works",
        problem_summary="body",
    )
    append_proposal(p, path=path)
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        self_improvement_queue=ProposalQueue(path),
    )
    r = server._app.test_client().get("/api/self-improvement/proposals")
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    ids = [row["proposal_id"] for row in body.get("proposals") or []]
    assert p.proposal_id in ids
    detail = server._app.test_client().get(
        f"/api/self-improvement/proposals/{p.proposal_id}"
    )
    assert detail.status_code == 200
    assert detail.get_json()["proposal"]["proposal_id"] == p.proposal_id


def test_prompt_export_from_canonical_queue(tmp_path):
    path = tmp_path / "canonical.jsonl"
    p = create_proposal(
        source="export",
        source_trace_id="t-exp",
        title="Export me",
        problem_summary="problem",
        proposed_change="do thing",
    )
    append_proposal(p, path=path)
    row = ProposalQueue(path).get(p.proposal_id)
    assert row is not None
    prompt = build_proposal_prompt(row, target="cursor")
    assert "Export me" in prompt
    assert "do thing" in prompt


def test_diagnostic_reports_legacy_file_when_present(tmp_path, monkeypatch):
    legacy = tmp_path / "brain_self_improvement_queue.jsonl"
    legacy.write_text('{"legacy": 1}\n', encoding="utf-8")
    canonical = tmp_path / "self_improvement_proposals.jsonl"
    append_proposal(
        create_proposal(
            source="diag",
            source_trace_id="d1",
            title="diag",
            problem_summary="p",
        ),
        path=canonical,
    )
    monkeypatch.setattr(
        "project_guardian.self_improvement.proposal_queue.DEFAULT_PROPOSALS_PATH",
        canonical,
    )
    monkeypatch.setattr(
        "project_guardian.self_improvement.proposal_queue.LEGACY_BRAIN_QUEUE_PATH",
        legacy,
    )
    assert count_jsonl_rows(legacy) == 1
    diag_path = Path(__file__).resolve().parents[2] / "scripts" / "self_improvement_queue_diagnostic.py"
    spec = importlib.util.spec_from_file_location("siq_diag", diag_path)
    assert spec and spec.loader
    diag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diag)

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    assert diag.main() == 0
    out = buf.getvalue()
    assert "Legacy file exists: True" in out
    assert "Legacy write enabled" in out
    assert "Legacy write enabled (ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE): False" in out


def test_no_subprocess_on_enqueue(tmp_path, monkeypatch):
    leg = tmp_path / "legacy.jsonl"
    can = tmp_path / "canonical.jsonl"
    si = JsonlSelfImprovementQueue(leg, canonical_path=can)

    def boom(*a, **k):
        raise AssertionError("subprocess should not run on enqueue")

    monkeypatch.setattr("subprocess.run", boom)
    si.enqueue(
        LearningOutcome(worked=True, lesson="safe", improvement_hints=[]),
        BrainPipelineTrace(),
    )


def test_retirement_logic_has_no_execution_mutation_or_autonomy_tokens():
    root = Path(__file__).resolve().parents[2]
    text = "\n".join(
        [
            (root / "project_guardian" / "brain" / "self_improvement_module.py").read_text(
                encoding="utf-8"
            ),
            (root / "project_guardian" / "self_improvement" / "proposal_queue.py").read_text(
                encoding="utf-8"
            ),
        ]
    )
    for forbidden in (
        "apply_patch",
        "subprocess",
        "shell=True",
        "os.system",
        "run_autonomous_cycle",
        "operator_chat_live_execution",
    ):
        assert forbidden not in text


def test_legacy_path_constant_points_at_runtime_brain_queue():
    assert LEGACY_BRAIN_QUEUE_PATH.name == "brain_self_improvement_queue.jsonl"
