# project_guardian/tests/test_control_panel_operator_chat_helper_integration.py
"""UIControlPanel POST /api/chat wired through safe_stack.operator_chat (no real LLMs)."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest

from project_guardian.brain.config import BrainPipelineConfig


class FakeUnifiedSystem:
    def __init__(self):
        self.calls: List[str] = []

    def chat_with_llm(self, message: str):
        self.calls.append(message)
        return f"reply-{len(self.calls)}", ""


class FakeMemory:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def remember(self, thought, category="general", priority=0.5, metadata=None):
        self.calls.append(
            {
                "thought": thought,
                "category": category,
                "priority": priority,
                "metadata": metadata or {},
            }
        )


_UNSET = object()


class FakeOrchestrator:
    def __init__(self, conversation_dir: Path, *, unified=_UNSET, memory: bool = True):
        self._unified_system = FakeUnifiedSystem() if unified is _UNSET else unified
        self.conversation_store_dir = str(conversation_dir)
        self.control_panel_chat_history_path = conversation_dir.parent / "legacy_chat_history.json"
        if memory:
            self.memory = FakeMemory()


def _brain_cfg(trace_path: Path, *, enabled: bool = True, operator_chat: bool = True) -> BrainPipelineConfig:
    return BrainPipelineConfig(
        enabled=enabled,
        use_think_decide_act=True,
        dry_run=True,
        persist_trace=True,
        trace_path=trace_path,
        entrypoints={
            "operator_chat": operator_chat,
            "operator_chat_live_execution": False,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": False,
        },
    )


def _panel(conversation_dir: Path, *, unified=_UNSET, memory: bool = True):
    try:
        from project_guardian.ui_control_panel import UIControlPanel
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    orch = FakeOrchestrator(conversation_dir, unified=unified, memory=memory)
    panel = UIControlPanel(orchestrator=orch)
    panel.app.config["TESTING"] = True
    return panel, orch


def test_panel_chat_uses_helper_with_brain_callback():
    from project_guardian.ui_control_panel import UIControlPanel

    src = inspect.getsource(UIControlPanel._handle_control_panel_operator_chat)
    assert "run_operator_chat_turn" in src
    assert "brain_trace_callback=self._maybe_run_brain_operator_chat_trace" in src


def test_ui_chat_response_envelope(tmp_path: Path):
    panel, _orch = _panel(tmp_path / "conversations")
    with panel.app.test_client() as client:
        resp = client.post("/api/chat", json={"message": "hello panel"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["reply"] == "reply-1"
    assert body["error"] is None
    assert body["conversation_id"] == "control_panel"
    assert isinstance(body["history"], list)
    assert len(body["history"]) == 2


def test_panel_reuses_conversation_id(tmp_path: Path):
    panel, _orch = _panel(tmp_path / "conversations")
    cid = "my-session"
    with panel.app.test_client() as client:
        resp = client.post(
            "/api/chat",
            json={"message": "one", "conversation_id": cid},
        )
    assert resp.status_code == 200
    assert resp.get_json()["conversation_id"] == "my-session"
    assert (tmp_path / "conversations" / "my-session.jsonl").exists()


def test_panel_persists_and_reloads_history(tmp_path: Path):
    conversation_dir = tmp_path / "conversations"
    panel, _orch = _panel(conversation_dir)
    with panel.app.test_client() as client:
        client.post("/api/chat", json={"message": "persist note"})
    assert (conversation_dir / "control_panel.jsonl").exists()

    reloaded, _ = _panel(conversation_dir)
    with reloaded.app.test_client() as client:
        hist = client.get("/api/chat/history")
    body = hist.get_json()
    assert body["success"] is True
    assert body["history"][0]["content"] == "persist note"


def test_panel_history_limit_in_prompt(tmp_path: Path):
    unified = FakeUnifiedSystem()
    panel, orch = _panel(tmp_path / "conversations", unified=unified)
    with panel.app.test_client() as client:
        client.post("/api/chat", json={"message": "My preferred launch color is teal."})
        client.post("/api/chat", json={"message": "What launch color did I mention?"})

    assert "Recent operator conversation" in unified.calls[1]
    assert "User: My preferred launch color is teal." in unified.calls[1]
    assert "Assistant: reply-1" in unified.calls[1]
    assert "Current user message:" in unified.calls[1]


def test_panel_memory_remember_side_effect(tmp_path: Path):
    panel, orch = _panel(tmp_path / "conversations")
    with panel.app.test_client() as client:
        client.post("/api/chat", json={"message": "remember this"})
    assert len(orch.memory.calls) == 1
    call = orch.memory.calls[0]
    assert call["category"] == "conversation"
    assert call["priority"] == 0.62
    assert call["metadata"]["source"] == "control_panel"
    assert call["metadata"]["conversation_id"] == "control_panel"


def test_responder_failure_returns_safe_ui_error_without_persisting(tmp_path: Path):
    unified = FakeUnifiedSystem()

    def _fail(message: str):
        unified.calls.append(message)
        return None, "model unavailable"

    unified.chat_with_llm = _fail
    panel, _orch = _panel(tmp_path / "conversations", unified=unified)

    with panel.app.test_client() as client:
        resp = client.post(
            "/api/chat",
            json={"message": "fail please", "conversation_id": "fail-conv"},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == "model unavailable"
    assert body["reply"] is None
    assert body["conversation_id"] == "fail-conv"
    assert body["history"] == []
    assert panel._conversation_store.list_messages("fail-conv", limit=10) == []


def test_runtime_api_chat_has_no_control_panel_adapter_leakage():
    root = Path(__file__).resolve().parents[2]
    runtime_source = (root / "elysia" / "api" / "server.py").read_text(encoding="utf-8")
    assert "_handle_control_panel_operator_chat" not in runtime_source
    assert "CONTROL_PANEL_CHAT_PROMPT_MESSAGES" not in runtime_source
    assert "chat_with_llm" not in runtime_source


def test_panel_brain_metadata_merged_when_trace_returns(tmp_path: Path):
    panel, _orch = _panel(tmp_path / "conversations")

    def _fake_brain(_message: str, _ctx: str) -> Dict[str, Any]:
        return {
            "brain_trace_enabled": True,
            "brain_trace_id": "panel-trace-1",
            "brain_dry_run": True,
        }

    panel._maybe_run_brain_operator_chat_trace = _fake_brain  # type: ignore[method-assign]
    with panel.app.test_client() as client:
        resp = client.post("/api/chat", json={"message": "trace merge"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("brain_trace_enabled") is True
    assert body.get("brain_trace_id") == "panel-trace-1"
    assert body.get("brain_dry_run") is True


def test_panel_brain_hook_invoked_when_config_enabled(tmp_path: Path, monkeypatch):
    trace_path = tmp_path / "brain_trace.json"
    trace_path.write_text("{}", encoding="utf-8")
    cfg = _brain_cfg(trace_path, enabled=True, operator_chat=True)
    monkeypatch.setattr(
        "project_guardian.brain.config.get_brain_pipeline_config",
        lambda **_k: cfg,
    )

    calls: List[str] = []

    def _fake_brain_run(*_a, **_k):
        calls.append("panel")
        return {"bypass": True, "reason": "test"}

    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        _fake_brain_run,
    )

    panel, orch = _panel(tmp_path / "conversations", unified=None)
    orch.ask_ai = lambda _msg: "ok"

    with panel.app.test_client() as client:
        resp = client.post("/api/chat", json={"message": "brain panel"})
    assert resp.status_code == 200
    assert calls == ["panel"]


def test_panel_brain_metadata_absent_when_config_disabled(tmp_path: Path, monkeypatch):
    trace_path = tmp_path / "brain_trace.json"
    cfg = _brain_cfg(trace_path, enabled=False, operator_chat=False)
    monkeypatch.setattr(
        "project_guardian.brain.config.get_brain_pipeline_config",
        lambda **_k: cfg,
    )

    calls: List[str] = []

    def _fake_brain_run(*_a, **_k):
        calls.append("should not run")
        return {"bypass": True}

    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        _fake_brain_run,
    )

    panel, _orch = _panel(tmp_path / "conversations")
    with panel.app.test_client() as client:
        resp = client.post("/api/chat", json={"message": "no brain"})
    assert resp.status_code == 200
    assert calls == []
    body = resp.get_json()
    assert not any(k.startswith("brain_") for k in body.keys())


def test_panel_brain_trace_fail_open_adds_error_field(tmp_path: Path, monkeypatch):
    trace_path = tmp_path / "brain_trace.json"
    cfg = _brain_cfg(trace_path, enabled=True, operator_chat=True)
    monkeypatch.setattr(
        "project_guardian.brain.config.get_brain_pipeline_config",
        lambda **_k: cfg,
    )

    def _boom(*_a, **_k):
        raise RuntimeError("trace exploded")

    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        _boom,
    )

    panel, _orch = _panel(tmp_path / "conversations")
    with panel.app.test_client() as client:
        resp = client.post("/api/chat", json={"message": "still ok"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body.get("brain_trace_error") == "trace exploded"


def test_panel_ask_ai_fallback_when_no_unified(tmp_path: Path):
    panel, orch = _panel(tmp_path / "conversations", unified=None)
    orch.ask_ai = lambda msg: f"ask:{msg[:20]}"

    with panel.app.test_client() as client:
        resp = client.post("/api/chat", json={"message": "fallback"})
    assert resp.status_code == 200
    assert resp.get_json()["reply"].startswith("ask:")


def test_panel_adapter_has_no_autonomy_live_execution_or_new_provider_tokens():
    from project_guardian.ui_control_panel import UIControlPanel

    src = "\n".join(
        inspect.getsource(obj)
        for obj in (
            UIControlPanel._make_panel_operator_chat_responder,
            UIControlPanel._jsonify_panel_operator_chat_result,
            UIControlPanel._handle_control_panel_operator_chat,
        )
    ).lower()
    for token in (
        "run_autonomous_cycle",
        "operator_chat_live_execution",
        "subprocess",
        "implementer.run_for_proposal",
    ):
        assert token not in src, token
