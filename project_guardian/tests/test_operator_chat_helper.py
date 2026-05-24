# project_guardian/tests/test_operator_chat_helper.py
"""Unit tests for project_guardian.safe_stack.operator_chat (no HTTP, no LLMs)."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from project_guardian.conversation_store import ConversationStore
from project_guardian.safe_stack import operator_chat as oc

FORBIDDEN_MODULE_TOKENS = (
    "subprocess",
    "run_autonomous_cycle",
    "apply_patch",
    "run_command",
    "implementer.run_for_proposal",
    "operator_chat_live_execution",
)


def _store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(tmp_path / "conversations")


def _ok_responder(reply: str = "assistant-ok"):
    def _inner(req: oc.OperatorChatRequest) -> oc.OperatorChatResponderResult:
        return oc.OperatorChatResponderResult(reply_text=reply, extra_fields={"source": "mock"})

    return _inner


def test_missing_conversation_id_uses_default_id(tmp_path):
    store = _store(tmp_path)
    result = oc.run_operator_chat_turn(
        "hello",
        conversation_store=store,
        responder=_ok_responder(),
    )
    assert result.ok is True
    assert result.conversation_id == "control_panel"
    assert (tmp_path / "conversations" / "control_panel.jsonl").exists()


def test_existing_conversation_id_is_sanitized(tmp_path):
    store = _store(tmp_path)
    raw = "  My Session!!  "
    result = oc.run_operator_chat_turn(
        "hi",
        conversation_id=raw,
        conversation_store=store,
        responder=_ok_responder(),
    )
    assert result.ok is True
    assert result.conversation_id == "My_Session"
    assert result.conversation_id == oc.normalize_operator_conversation_id(raw)


def test_user_and_assistant_messages_persist(tmp_path):
    store = _store(tmp_path)
    result = oc.run_operator_chat_turn(
        "persist me",
        conversation_id="persist-conv",
        conversation_store=store,
        responder=_ok_responder("saved reply"),
    )
    assert result.ok is True
    assert result.user_message_id
    assert result.assistant_message_id
    rows = store.list_messages("persist-conv")
    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "persist me"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["content"] == "saved reply"


def test_recent_history_capped_by_count(tmp_path):
    store = _store(tmp_path)
    cid = "count-cap"
    for i in range(8):
        store.append_message(cid, role="user", content=f"old-{i}")
        store.append_message(cid, role="assistant", content=f"reply-{i}")

    captured: list[oc.OperatorChatRequest] = []

    def _capture(req: oc.OperatorChatRequest) -> oc.OperatorChatResponderResult:
        captured.append(req)
        return oc.OperatorChatResponderResult(reply_text="ok")

    oc.run_operator_chat_turn(
        "new-turn",
        conversation_id=cid,
        conversation_store=store,
        responder=_capture,
        history_limit=3,
    )
    assert captured
    assert len(captured[0].history_context.history_rows) <= 3


def test_history_context_capped_by_char_budget(tmp_path):
    store = _store(tmp_path)
    cid = "char-cap"
    store.append_message(cid, role="user", content="x" * 500)
    store.append_message(cid, role="assistant", content="y" * 500)

    uncapped = oc.build_operator_history_context(
        store,
        cid,
        "next",
        history_limit=20,
        history_char_limit=8000,
    )
    ctx = oc.build_operator_history_context(
        store,
        cid,
        "next",
        history_limit=20,
        history_char_limit=80,
    )
    assert ctx.transcript_chars < uncapped.transcript_chars
    assert ("x" * 500) not in ctx.transcript


def test_responder_receives_message_and_history_context(tmp_path):
    store = _store(tmp_path)
    store.append_message("ctx-conv", role="user", content="prior question")
    store.append_message("ctx-conv", role="assistant", content="prior answer")

    seen: list[oc.OperatorChatRequest] = []

    def _capture(req: oc.OperatorChatRequest) -> oc.OperatorChatResponderResult:
        seen.append(req)
        return oc.OperatorChatResponderResult(reply_text="done")

    oc.run_operator_chat_turn(
        "follow up",
        conversation_id="ctx-conv",
        conversation_store=store,
        responder=_capture,
    )
    assert len(seen) == 1
    req = seen[0]
    assert req.message == "follow up"
    assert req.history_context.message_count == 2
    assert "prior question" in req.composed_prompt
    assert "Current user message:" in req.composed_prompt
    assert "follow up" in req.composed_prompt


def test_brain_trace_callback_optional(tmp_path):
    store = _store(tmp_path)
    calls: list[str] = []

    def _brain(msg: str, ctx: str) -> dict:
        calls.append(f"{msg}|{ctx}")
        return {"brain_trace_enabled": True, "brain_trace_id": "t-1", "brain_dry_run": True}

    result = oc.run_operator_chat_turn(
        "trace?",
        conversation_store=store,
        responder=_ok_responder(),
        brain_trace_callback=_brain,
    )
    assert result.ok is True
    assert calls == ["trace?|general"]
    assert result.brain_metadata.get("brain_trace_id") == "t-1"

    result2 = oc.run_operator_chat_turn(
        "no trace",
        conversation_store=store,
        responder=_ok_responder(),
        brain_trace_callback=None,
    )
    assert result2.ok is True
    assert not result2.brain_metadata.get("brain_trace_enabled")


def test_brain_trace_metadata_merged_and_compact(tmp_path):
    store = _store(tmp_path)

    def _brain(_msg: str, _ctx: str) -> dict:
        return {
            "brain_trace_enabled": True,
            "brain_trace_id": "compact-1",
            "brain_dry_run": True,
            "brain_raw_trace": {"secret": "hidden"},
            "think_decide_act_trace": {"nope": True},
        }

    result = oc.run_operator_chat_turn(
        "meta",
        conversation_store=store,
        responder=_ok_responder(),
        brain_trace_callback=_brain,
    )
    assert result.ok is True
    assert result.brain_metadata.get("brain_trace_id") == "compact-1"
    assert "brain_raw_trace" not in result.brain_metadata
    assert "think_decide_act_trace" not in result.brain_metadata
    assert any("dropped_nested" in w for w in result.warnings)


def test_brain_trace_failure_fail_open(tmp_path):
    store = _store(tmp_path)

    def _boom(_m: str, _c: str) -> dict:
        raise RuntimeError("trace exploded")

    result = oc.run_operator_chat_turn(
        "still chat",
        conversation_store=store,
        responder=_ok_responder("recovered"),
        brain_trace_callback=_boom,
    )
    assert result.ok is True
    assert result.reply == "recovered"
    assert result.brain_metadata.get("brain_trace_error") == "trace exploded"
    assert any("brain_trace_failed" in w for w in result.warnings)


def test_responder_failure_structured_error_no_assistant_persist(tmp_path):
    store = _store(tmp_path)

    def _fail(_req: oc.OperatorChatRequest) -> oc.OperatorChatResponderResult:
        raise oc.OperatorChatResponderError("model unavailable")

    result = oc.run_operator_chat_turn(
        "try fail",
        conversation_id="fail-conv",
        conversation_store=store,
        responder=_fail,
    )
    assert result.ok is False
    assert result.error == "model unavailable"
    assert not result.assistant_message_id
    rows = store.list_messages("fail-conv")
    assert len(rows) == 1
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "try fail"


def test_after_persist_callback_called(tmp_path):
    store = _store(tmp_path)
    calls: list[tuple] = []

    def _after(cid, user, reply, brain, extra):
        calls.append((cid, user, reply, brain, extra))

    oc.run_operator_chat_turn(
        "remember hook",
        conversation_store=store,
        responder=_ok_responder("hook-reply"),
        after_persist_callback=_after,
    )
    assert len(calls) == 1
    assert calls[0][0] == "control_panel"
    assert calls[0][1] == "remember hook"
    assert calls[0][2] == "hook-reply"


def test_secrets_redacted_from_stored_metadata(tmp_path):
    store = _store(tmp_path)

    def _brain(_m: str, _c: str) -> dict:
        return {"brain_trace_enabled": True, "brain_trace_id": "meta-1"}

    oc.run_operator_chat_turn(
        "hello",
        conversation_id="secret-conv",
        conversation_store=store,
        responder=_ok_responder("ok"),
        brain_trace_callback=_brain,
        metadata={"operator_note": "api_key=abc123secret"},
    )
    raw = (tmp_path / "conversations" / "secret-conv.jsonl").read_text(encoding="utf-8")
    assert "abc123secret" not in raw
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assistant = [r for r in rows if r.get("role") == "assistant"][-1]
    note = (assistant.get("metadata") or {}).get("operator_note", "")
    assert "abc123secret" not in note
    assert "[REDACTED]" in note or "api_key" in note


def test_helper_module_has_no_forbidden_execution_tokens():
    src = inspect.getsource(oc).lower()
    for token in FORBIDDEN_MODULE_TOKENS:
        assert token not in src, f"operator_chat must not reference {token}"


def test_no_real_llm_calls_in_tests(tmp_path):
    """Responder is mocked; turn completes without network modules."""
    store = _store(tmp_path)
    result = oc.run_operator_chat_turn(
        "offline only",
        conversation_store=store,
        responder=_ok_responder(),
    )
    assert result.ok is True
    assert result.reply == "assistant-ok"


def test_generate_conversation_id_when_missing(tmp_path):
    store = _store(tmp_path)
    cid = oc.normalize_operator_conversation_id(
        None,
        generate_if_missing=True,
        conversation_store=store,
    )
    assert cid.startswith("conv_")


def test_helper_wiring_scope_both_chat_hosts():
    root = Path(__file__).resolve().parents[2]
    runtime_source = (root / "elysia" / "api" / "server.py").read_text(encoding="utf-8")
    panel_source = (root / "project_guardian" / "ui_control_panel.py").read_text(encoding="utf-8")

    assert "run_operator_chat_turn" in runtime_source
    assert "run_operator_chat_turn" in panel_source
