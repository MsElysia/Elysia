# project_guardian/tests/test_self_improvement_prompt_export.py
"""Self-improvement proposal prompt export (review-only; no execution)."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.self_improvement.prompt_export import (
    build_proposal_prompt,
    normalize_target,
    proposal_prompt_to_dict,
    sanitize_prompt_text,
)
from project_guardian.self_improvement.proposal_queue import (
    ProposalQueue,
    append_proposal,
    create_proposal,
)

PROMPT_EXPORT_PATH = (
    Path(__file__).resolve().parents[1] / "self_improvement" / "prompt_export.py"
)


def _sample_proposal(**overrides):
    base = dict(
        source="brain_pipeline",
        source_trace_id="trace-abc",
        title="Improve conversation redaction",
        problem_summary="Secrets may leak in stored messages.",
        evidence={"observation": "token=supersecret12345", "think_decide_act_trace": {"x": 1}},
        proposed_change="Extend redact_sensitive coverage in conversation store.",
        affected_files=["project_guardian/conversation_store.py"],
        expected_benefit="Safer persisted chat history.",
        risk_level="medium",
        priority_score=0.72,
    )
    base.update(overrides)
    return create_proposal(**base)


def test_cursor_export_includes_title_problem_proposed_change():
    p = _sample_proposal()
    prompt = build_proposal_prompt(p, target="cursor")
    assert "Improve conversation redaction" in prompt
    assert "Secrets may leak" in prompt
    assert "Extend redact_sensitive" in prompt
    assert "Cursor agent instructions" in prompt


def test_codex_export_includes_focused_tests_and_deliverables():
    p = _sample_proposal()
    prompt = build_proposal_prompt(p, target="codex")
    assert "Codex agent instructions" in prompt
    assert "test-driven" in prompt.lower()
    assert "python -m pytest" in prompt
    assert "Deliverables" in prompt


def test_export_redacts_secrets():
    p = _sample_proposal(problem_summary="api_key=abcdefghijklmnop")
    out = proposal_prompt_to_dict(p, target="cursor")
    assert "abcdefghijklmnop" not in out["prompt"]
    assert "supersecret12345" not in out["prompt"]


def test_export_omits_raw_brain_tda_traces():
    p = _sample_proposal(
        evidence={
            "think_decide_act_trace": {"transitions": ["a", "b"]},
            "tda_trace": {"nested": True},
            "note": "safe line",
        }
    )
    out = proposal_prompt_to_dict(p, target="cursor")
    assert "think_decide_act_trace" not in out["prompt"]
    assert '"transitions"' not in out["prompt"]
    assert "safe line" in out["prompt"]
    assert any("omitted" in w.lower() or "trace" in w.lower() for w in out["warnings"])


def test_unknown_target_rejected_safely():
    with pytest.raises(ValueError, match="unknown_target"):
        normalize_target("openai")
    with pytest.raises(ValueError):
        build_proposal_prompt(_sample_proposal(), target="invalid")


def test_api_endpoint_returns_prompt_json(tmp_path):
    path = tmp_path / "q.jsonl"
    p = _sample_proposal()
    append_proposal(p, path=path)
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        self_improvement_queue=ProposalQueue(path),
    )
    client = server._app.test_client()
    r = client.get(f"/api/self-improvement/proposals/{p.proposal_id}/export_prompt?target=cursor")
    assert r.status_code == 200
    body = r.get_json()
    assert body["proposal_id"] == p.proposal_id
    assert body["target"] == "cursor"
    assert body["copy_safe"] is True
    assert "Improve conversation redaction" in body["prompt"]
    assert isinstance(body["warnings"], list)

    bad = client.get(f"/api/self-improvement/proposals/{p.proposal_id}/export_prompt?target=unknown")
    assert bad.status_code == 400


def test_control_panel_contains_export_buttons_and_text():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    html = CONTROL_PANEL_TEMPLATE
    assert "Export Cursor Prompt" in html
    assert "Export Codex Prompt" in html
    assert "export_prompt" in html
    assert "Export only. This does not apply code or run commands." in html
    assert "self-improvement-proposal-prompt-export" in html


def test_export_ui_has_no_apply_run_patch_commands():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    html = CONTROL_PANEL_TEMPLATE
    start = html.find("self-improvement-prompt-export-start")
    end = html.find("self-improvement-prompt-export-end")
    assert start >= 0 and end > start
    block = html[start:end]
    assert "apply_patch" not in block.lower()
    assert "implement" not in block.lower()
    assert "execute" not in block.lower()
    assert re.search(r"exportSelfImprovementProposalPrompt\('cursor'\)", block)
    assert "copySelfImprovementExportedPrompt" in block


def test_export_prompt_includes_safety_constraints():
    prompt = build_proposal_prompt(_sample_proposal(), target="cursor")
    assert "Do not wire autonomy" in prompt
    assert "Do not enable live execution" in prompt
    assert "Do not apply unrelated changes" in prompt


def test_export_prompt_includes_implementation_report_request():
    prompt = build_proposal_prompt(_sample_proposal(), target="codex")
    assert "implementation report" in prompt.lower()
    assert "Files changed" in prompt


def test_prompt_export_module_has_no_execution_or_autonomy():
    text = PROMPT_EXPORT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "subprocess",
        "run_autonomous_cycle",
        "operator_chat_live_execution",
        "os.system",
        "shell=True",
    ):
        assert forbidden not in text
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("run", "Popen", "call"):
                raise AssertionError("prompt_export must not invoke subprocess-like calls")


def test_export_does_not_mutate_proposal_queue(tmp_path, monkeypatch):
    path = tmp_path / "q.jsonl"
    p = _sample_proposal()
    append_proposal(p, path=path)
    before = path.read_text(encoding="utf-8")
    proposal_prompt_to_dict(p, target="cursor")
    assert path.read_text(encoding="utf-8") == before


def test_sanitize_prompt_text_strips_nulls():
    assert "\x00" not in sanitize_prompt_text("a\x00b")
