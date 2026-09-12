"""Shared safe-stack response helper tests (offline, no Flask server start)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from project_guardian.safe_stack import responses as helpers
from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.conversation_store import ConversationStore
from project_guardian.self_improvement.proposal_queue import (
    ProposalQueue,
    create_proposal,
)


HELPER_PATH = Path(__file__).resolve().parents[1] / "safe_stack" / "responses.py"


def _proposal(**overrides):
    base = dict(
        source="helper_test",
        source_trace_id="trace-helper",
        title="Improve helper redaction token=title-secret",
        problem_summary="Problem has api_key=problem-secret and should be redacted.",
        evidence={
            "note": "Bearer evidence-secret",
            "think_decide_act_trace": {"raw": "not exported"},
        },
        proposed_change="Use shared safe-stack response helpers.",
        affected_files=["project_guardian/safe_stack/responses.py"],
        expected_benefit="Less API host drift.",
        risk_level="medium",
        priority_score=0.74,
        confidence=0.81,
        metadata={"raw_trace": {"secret": True}},
    )
    base.update(overrides)
    return create_proposal(**base)


def test_prompt_export_helper_returns_normalized_success_payload(tmp_path):
    queue = ProposalQueue(tmp_path / "proposals.jsonl")
    proposal = _proposal()
    queue.append(proposal)

    body, status = helpers.build_self_improvement_prompt_export_response(
        queue,
        proposal.proposal_id,
        target="codex",
    )

    assert status == 200
    assert body["success"] is True
    assert body["proposal_id"] == proposal.proposal_id
    assert body["target"] == "codex"
    assert body["copy_safe"] is True
    assert isinstance(body["warnings"], list)
    assert "Codex agent instructions" in body["prompt"]


def test_proposal_list_and_detail_helpers_return_sanitized_fields(tmp_path):
    queue = ProposalQueue(tmp_path / "proposals.jsonl")
    proposal = _proposal()
    queue.append(proposal)

    list_body, list_status = helpers.build_self_improvement_proposals_list_response(queue, limit=10)
    detail_body, detail_status = helpers.build_self_improvement_proposal_detail_response(
        queue,
        proposal.proposal_id,
    )

    assert list_status == 200
    assert detail_status == 200
    row = list_body["proposals"][0]
    detail = detail_body["proposal"]
    for payload in (row, detail):
        assert payload.keys() >= {
            "proposal_id",
            "title",
            "problem_summary",
            "proposed_change",
            "affected_files",
            "risk_level",
            "priority_score",
        }
    blob = json.dumps([list_body, detail_body]).lower()
    assert "title-secret" not in blob
    assert "problem-secret" not in blob
    assert "evidence-secret" not in blob
    assert "think_decide_act_trace" not in blob
    assert "raw_trace" not in blob


def test_invalid_proposal_status_update_returns_safe_error_without_rewrite(tmp_path):
    path = tmp_path / "proposals.jsonl"
    queue = ProposalQueue(path)
    proposal = _proposal()
    queue.append(proposal)
    before = path.read_text(encoding="utf-8")

    body, status = helpers.build_self_improvement_proposal_status_update_response(
        queue,
        proposal.proposal_id,
        "execute-now",
        note="should not matter",
    )

    assert status == 400
    assert body["success"] is False
    assert body["error"].startswith("invalid_status")
    assert path.read_text(encoding="utf-8") == before


def test_brain_trace_helper_does_not_expose_raw_tda_trace(tmp_path):
    trace_path = tmp_path / "brain_last_pipeline.json"
    trace_path.write_text(
        json.dumps(
            {
                "brain_pipeline_id": "brain-helper",
                "started_at": "2026-05-17T12:00:00Z",
                "input_source": "operator_chat",
                "risk": "low",
                "execution_ok": True,
                "think_decide_act_trace": {"raw": "hidden"},
                "tda_trace": {"raw": "hidden"},
                "unified_export": {"think_decide_act_trace": {"raw": "hidden"}},
                "transitions": ["observation_received"],
            }
        ),
        encoding="utf-8",
    )

    body, status = helpers.build_brain_trace_latest_response(
        config=BrainPipelineConfig(trace_path=trace_path)
    )
    blob = json.dumps(body).lower()

    assert status == 200
    assert body["trace_exists"] is True
    assert body["tda_used"] is True
    assert '"think_decide_act_trace"' not in blob
    assert '"tda_trace"' not in blob
    assert '"raw_trace"' not in blob


def test_memory_ranking_helper_is_read_only(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    store.append_message("c1", role="user", content="Important preference: keep memory ranking advisory only.")

    body, status = helpers.build_memory_ranking_summary_response(conversation_store=store, limit=5)

    assert status == 200
    assert body["available"] is True
    assert body["mutation_allowed"] is False
    assert body["delete_allowed"] is False
    assert "proposal_counts" in body


def test_prompt_contract_status_helper_omits_raw_prompt_and_model_output(tmp_path):
    trace_path = tmp_path / "brain_last_pipeline.json"
    trace_path.write_text(
        json.dumps(
            {
                "prompt_contract_validation": {
                    "planner": {
                        "module_name": "planner",
                        "contract_id": "planner.v1",
                        "valid": False,
                        "blocked": False,
                        "mode": "warn",
                        "raw_prompt": "full system prompt",
                        "raw_model_output": {"chain_of_thought": "hidden"},
                        "scratchpad": "private notes",
                        "errors": ["forbidden_key:chain_of_thought"],
                        "warnings": ["scratchpad omitted"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    body, status = helpers.build_prompt_contracts_status_response(
        config=BrainPipelineConfig(trace_path=trace_path)
    )
    blob = json.dumps(body).lower()

    assert status == 200
    assert body["available"] is True
    assert "latest_validation" in body
    for forbidden in ("raw_prompt", "raw_model_output", "chain_of_thought", "scratchpad"):
        assert forbidden not in blob


def test_conversation_helper_returns_sanitized_messages(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    store.append_message(
        "c1",
        role="user",
        content="Remember this but redact token=chat-secret and sk-12345678901234567890.",
    )

    body, status = helpers.build_conversation_detail_response(store, "c1", message_limit=10)
    history, history_status = helpers.build_chat_history_response(store, "c1", limit=10)

    assert status == 200
    assert history_status == 200
    assert body["messages"][0]["content"]
    blob = json.dumps([body, history])
    assert "chat-secret" not in blob
    assert "sk-12345678901234567890" not in blob
    assert "[REDACTED]" in blob


def test_helpers_contain_no_execution_or_autonomy_command_behavior():
    text = HELPER_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "apply_patch",
        "run_command",
        "run_autonomous_cycle",
        "operator_chat_live_execution",
        "/api/proposals/",
        "/implement",
        "shell=true",
        "subprocess",
        "os.system",
    ):
        assert forbidden not in text

    tree = ast.parse(HELPER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            assert func.attr not in {"Popen", "call"}
