"""Focused tests for durable conversation + continuity checkpoints."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _ensure_package():
    if "project_guardian" not in sys.modules:
        package = types.ModuleType("project_guardian")
        package.__path__ = [str(_ROOT / "project_guardian")]
        package.__package__ = "project_guardian"
        sys.modules["project_guardian"] = package


_ensure_package()

from project_guardian.conversation_continuity import (
    ContinuityError,
    ConversationStore,
    estimate_tokens,
    resolve_conversation_root,
)


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


def test_create_persist_and_recover(store: ConversationStore, tmp_path: Path):
    record = store.create(
        title="Paint plan",
        objective="Plan fictional paint task",
        constraints=["No real purchases"],
    )
    cid = record["conversation_id"]
    store.append_message(cid, role="user", content="Start with primer.")
    store.append_message(cid, role="assistant", content="Primer noted.")
    store.update_task_fields(
        cid,
        {
            "completed_work": ["Chose primer"],
            "outstanding_steps": ["Choose color"],
            "next_safe_action": "Choose color",
        },
    )
    # Fresh store instance = restart
    again = ConversationStore(resolve_conversation_root(tmp_path))
    loaded = again.get(cid)
    assert loaded["objective"] == "Plan fictional paint task"
    assert len(loaded["messages"]) == 2
    assert loaded["next_safe_action"] == "Choose color"
    assert any(r["conversation_id"] == cid for r in again.list_conversations())


def test_checkpoint_preserves_original_history(store: ConversationStore):
    record = store.create(objective="Multi-step fictional inventory")
    cid = record["conversation_id"]
    for i in range(5):
        store.append_message(cid, role="user", content=f"Step note {i} " + ("x" * 40))
        store.append_message(cid, role="assistant", content=f"Ack {i}")
    store.update_task_fields(
        cid,
        {
            "completed_work": ["Listed shelves"],
            "outstanding_steps": ["Count widgets"],
            "next_safe_action": "Count widgets",
            "confirmed_facts": ["Shelf A is empty"],
            "assumptions": ["Widgets are fictional"],
        },
    )
    before = store.get(cid)
    msg_ids = [m["message_id"] for m in before["messages"]]
    ckpt = store.write_checkpoint(cid, reason="operator")
    after = store.get(cid)
    assert [m["message_id"] for m in after["messages"]] == msg_ids
    assert ckpt["objective"] == "Multi-step fictional inventory"
    assert ckpt["next_safe_action"] == "Count widgets"
    assert ckpt["authorization_state"] == "none"
    assert "credential" not in json.dumps(ckpt).lower() or "credential" in "none"
    # No auth fields
    assert "allow_calculator" not in ckpt
    assert "token" not in ckpt


def test_checkpoint_idempotent(store: ConversationStore):
    record = store.create(objective="Idempotent task")
    cid = record["conversation_id"]
    store.update_task_fields(cid, {"next_safe_action": "Do X", "outstanding_steps": ["Do X"]})
    a = store.write_checkpoint(cid, reason="operator")
    b = store.write_checkpoint(cid, reason="operator")
    assert a["content_sha256"] == b["content_sha256"]
    assert a["revision"] == b["revision"]


def test_interrupted_checkpoint_keeps_previous(store: ConversationStore, monkeypatch):
    record = store.create(objective="Safe write")
    cid = record["conversation_id"]
    store.update_task_fields(cid, {"next_safe_action": "Keep prior", "outstanding_steps": ["Keep prior"]})
    good = store.write_checkpoint(cid, reason="operator")
    path = store._checkpoint_path(cid)
    assert path.is_file()

    def boom(*_a, **_k):
        raise OSError("simulated interrupt")

    store.update_task_fields(cid, {"next_safe_action": "Should not commit", "outstanding_steps": ["Nope"]})
    # Force a new content hash then fail atomic write
    import project_guardian.conversation_continuity as mod

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError):
        store.write_checkpoint(cid, reason="operator", force=True)
    # Previous checkpoint still recoverable
    loaded = store.get_checkpoint(cid)
    assert loaded is not None
    assert loaded["content_sha256"] == good["content_sha256"]
    assert loaded["next_safe_action"] == "Keep prior"


def test_context_rollover_builds_checkpoint(store: ConversationStore, monkeypatch):
    monkeypatch.setenv("ELYSIA_CONTEXT_BUDGET_TOKENS", "400")
    record = store.create(objective="Rollover fiction task")
    cid = record["conversation_id"]
    store.update_task_fields(
        cid,
        {
            "constraints": ["Stay fictional"],
            "completed_work": ["Opened box"],
            "outstanding_steps": ["Label jars"],
            "next_safe_action": "Label jars",
        },
    )
    for i in range(12):
        store.append_message(
            cid,
            role="user",
            content=f"Long filler message {i} about the fictional jar labeling project " + ("detail " * 30),
        )
        store.append_message(
            cid,
            role="assistant",
            content=f"Noted filler {i} " + ("ok " * 20),
        )
    assembled = store.assemble_model_context(cid, "What is the next pending step?")
    assert assembled["rolled_over"] is True
    assert assembled["checkpoint"] is not None
    assert assembled["checkpoint"]["next_safe_action"] == "Label jars"
    # Original history still present
    assert len(store.get(cid)["messages"]) >= 20


def test_conversation_isolation(store: ConversationStore):
    a = store.create(objective="Secret Alpha objective")
    b = store.create(objective="Secret Beta objective")
    store.update_task_fields(a["conversation_id"], {"next_safe_action": "Alpha next"})
    store.update_task_fields(b["conversation_id"], {"next_safe_action": "Beta next"})
    store.write_checkpoint(a["conversation_id"], reason="operator")
    store.write_checkpoint(b["conversation_id"], reason="operator")
    ca = store.get_checkpoint(a["conversation_id"])
    cb = store.get_checkpoint(b["conversation_id"])
    assert ca["conversation_id"] == a["conversation_id"]
    assert cb["conversation_id"] == b["conversation_id"]
    assert ca["objective"] != cb["objective"]
    with pytest.raises(ContinuityError):
        store.get("conv_deadbeefdeadbee")


def test_estimate_tokens_conservative():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_task_update_rejects_nothing_but_strips_are_host_side(store: ConversationStore):
    record = store.create(objective="Auth boundary")
    cid = record["conversation_id"]
    # Store itself only accepts known keys; extra auth-like keys ignored by update_task_fields
    updated = store.update_task_fields(
        cid,
        {"next_safe_action": "Ask again", "allow_calculator": True, "token": "secret"},
    )
    assert "allow_calculator" not in updated
    assert "token" not in updated
    assert updated["next_safe_action"] == "Ask again"
