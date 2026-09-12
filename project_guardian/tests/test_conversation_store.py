from __future__ import annotations

import json
from pathlib import Path

import pytest

import elysia.api.conversation_store as elysia_conversation_shim
from project_guardian import conversation_store as canonical_conversation_store
from project_guardian.conversation_store import (
    ConversationStore,
    build_recent_transcript,
    format_transcript_for_prompt,
    redact_chat_text,
    reset_default_conversation_store_for_tests,
    sanitize_conversation_id,
)

_PG_UI_PANEL_PATH = Path(__file__).resolve().parent.parent / "ui_control_panel.py"


@pytest.fixture(autouse=True)
def _reset_default_store():
    reset_default_conversation_store_for_tests()
    yield
    reset_default_conversation_store_for_tests()


def test_persists_across_new_store_instances(tmp_path):
    base = tmp_path / "c"
    s1 = ConversationStore(base)
    s1.append_message("c1", role="user", content="hello")
    s2 = ConversationStore(base)
    rows = s2.list_messages("c1", limit=10)
    assert len(rows) == 1
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "hello"


def test_redacts_secrets():
    raw = 'my api_key=sk-123456789012345678901234567890 secret'
    out = redact_chat_text(raw)
    assert "sk-123456789012345678901234567890" not in out
    assert "api_key=[REDACTED]" in out or "[REDACTED]" in out


def test_message_content_capped():
    out = redact_chat_text("x" * 200, limit=50)
    assert len(out) <= 50


def test_sanitize_conversation_id():
    assert sanitize_conversation_id("  ab/c:d  ") == "ab_c:d"


def test_format_transcript_for_prompt_respects_limits():
    msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    t = format_transcript_for_prompt(msgs, max_messages=2, max_chars=500)
    assert "User: a" in t
    assert "Assistant: b" in t


def test_malformed_jsonl_lines_skipped(tmp_path):
    p = tmp_path / "c" / "x.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"bad": nojson}\n{"message_id":"1","conversation_id":"x","role":"user","content":"ok","created_at":"t","metadata":{}}\n', encoding="utf-8")
    store = ConversationStore(tmp_path / "c")
    rows = store.list_messages("x", limit=10)
    assert len(rows) == 1
    assert rows[0]["content"] == "ok"


def test_legacy_import_once(tmp_path):
    legacy = tmp_path / "old.json"
    before = json.dumps(
        {
            "sessions": {
                "legacy_sess": [
                    {"role": "user", "content": "hi", "timestamp": "2020-01-01T00:00:00Z"},
                    {"role": "assistant", "content": "yo", "created_at": "2020-01-01T00:00:01Z"},
                ]
            }
        }
    )
    legacy.write_text(before, encoding="utf-8")
    base = tmp_path / "convos"
    s = ConversationStore(base)
    n1 = s.import_legacy_control_panel_json(legacy)
    assert n1 >= 1
    assert legacy.read_text(encoding="utf-8") == before
    n2 = s.import_legacy_control_panel_json(legacy)
    assert n2 == 0
    rows = s.list_messages("legacy_sess", limit=10)
    assert len(rows) >= 1
    assert rows[0]["created_at"] == "2020-01-01T00:00:00Z"


def test_elysia_api_conversation_shim_is_canonical():
    """Compatibility shim must re-export the same implementation objects."""
    assert elysia_conversation_shim.ConversationStore is canonical_conversation_store.ConversationStore
    assert elysia_conversation_shim.build_recent_transcript is canonical_conversation_store.build_recent_transcript
    assert elysia_conversation_shim.redact_chat_text is canonical_conversation_store.redact_chat_text


def test_elysia_api_conversation_shim_has_no_duplicate_logic():
    shim_path = Path(__file__).resolve().parent.parent.parent / "elysia" / "api" / "conversation_store.py"
    text = shim_path.read_text(encoding="utf-8")
    assert "ConversationStore(" not in text
    assert "jsonl" not in text.lower()


def test_build_recent_transcript_matches_format_transcript():
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "bye"}]
    assert build_recent_transcript(msgs, max_messages=5, max_chars=500) == format_transcript_for_prompt(
        msgs, max_messages=5, max_chars=500
    )


def test_get_messages_matches_list_messages(tmp_path):
    s = ConversationStore(tmp_path / "c")
    s.append_message("mid", role="user", content="x")
    assert s.get_messages("mid", limit=5) == s.list_messages("mid", limit=5)


def test_append_metadata_strips_traces_and_nested(tmp_path):
    s = ConversationStore(tmp_path / "c")
    msg = s.append_message(
        "t1",
        role="assistant",
        content="ok",
        metadata={
            "think_decide_act_trace": {"steps": [1, 2]},
            "trace_id": "opaque",
            "nested": {"bad": True},
            "brain_trace_path": "/tmp/trace.json",
            "safe_flag": True,
        },
    )
    meta = msg["metadata"]
    assert "think_decide_act_trace" not in meta
    assert "nested" not in meta
    assert "brain_trace_path" not in meta
    assert meta.get("trace_id") == "opaque"
    assert meta.get("safe_flag") is True


def test_control_panel_template_documents_conversation_memory_hooks():
    text = _PG_UI_PANEL_PATH.read_text(encoding="utf-8")
    assert "elysia_control_panel_conversation_id" in text or "ELYSIA_CP_CONV_LS" in text
    assert "conversation_id" in text
    assert "refreshApiChatHistory" in text
