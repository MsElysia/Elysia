"""Operator-authoritative task state edits for conversation continuity."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(_ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.conversation_continuity import (
    ContinuityError,
    ConversationStore,
    StaleTaskEditError,
    resolve_conversation_root,
)


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


def test_operator_edit_advances_checkpoint(store: ConversationStore, tmp_path: Path):
    conv = store.create(
        title="Fictional lab tidy",
        objective="Tidy a fictional lab bench",
        constraints=["Stay fictional"],
    )
    cid = conv["conversation_id"]
    store.update_task_fields(
        cid,
        {
            "completed_work": ["Cleared beakers"],
            "outstanding_steps": ["Label jars", "Wipe surface"],
            "next_safe_action": "Label jars",
        },
    )
    first = store.write_checkpoint(cid, reason="operator")
    assert first["revision"] == 1

    result = store.commit_operator_task_state(
        cid,
        expected_revision=1,
        outstanding_steps=["Wipe surface", "Log inventory"],
        next_safe_action="Wipe surface",
    )
    assert result["saved"] is True
    assert result["idempotent"] is False
    ckpt = result["checkpoint"]
    assert ckpt["revision"] == 2
    assert ckpt["next_safe_action"] == "Wipe surface"
    assert ckpt["outstanding_steps"] == ["Wipe surface", "Log inventory"]
    assert ckpt["task_state_source"] == "operator"
    assert ckpt["authorization_state"] == "none"
    assert "token" not in ckpt
    assert "credential" not in str(ckpt).lower() or ckpt.get("authorization_state") == "none"

    # Restart recovery
    again = ConversationStore(resolve_conversation_root(tmp_path))
    loaded = again.get(cid)
    assert loaded["next_safe_action"] == "Wipe surface"
    assert loaded["checkpoint_revision"] == 2
    assert again.get_checkpoint(cid)["next_safe_action"] == "Wipe surface"


def test_stale_competing_edit_rejected(store: ConversationStore):
    conv = store.create(objective="Stale race fiction")
    cid = conv["conversation_id"]
    store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Step A"],
        next_safe_action="Step A",
    )
    with pytest.raises(StaleTaskEditError):
        store.commit_operator_task_state(
            cid,
            expected_revision=0,
            outstanding_steps=["Step B"],
            next_safe_action="Step B",
        )
    assert store.get(cid)["next_safe_action"] == "Step A"


def test_idempotent_operator_retry(store: ConversationStore):
    conv = store.create(objective="Idempotent fiction")
    cid = conv["conversation_id"]
    a = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Pack maps"],
        next_safe_action="Pack maps",
    )
    b = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Pack maps"],
        next_safe_action="Pack maps",
    )
    assert a["checkpoint"]["revision"] == 1
    assert b["idempotent"] is True
    assert b["checkpoint"]["revision"] == 1
    assert store.get(cid)["checkpoint_revision"] == 1


def test_failed_checkpoint_preserves_previous(store: ConversationStore, monkeypatch):
    conv = store.create(objective="Preserve prior")
    cid = conv["conversation_id"]
    good = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Keep me"],
        next_safe_action="Keep me",
    )
    import project_guardian.conversation_continuity as mod

    def boom(*_a, **_k):
        raise OSError("simulated interrupt")

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError):
        store.commit_operator_task_state(
            cid,
            expected_revision=1,
            outstanding_steps=["Should not land"],
            next_safe_action="Should not land",
        )
    # Monkeypatch breaks all writes including restore; re-open store path via raw file.
    # The previous checkpoint file should still exist from before the failed attempt
    # because boom raised before replace — but conversation update may have run first.
    # Restore monkeypatch effect: read checkpoint path directly without going through
    # commit (which needs atomic write). Use json via Path.
    import json

    path = store._checkpoint_path(cid)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["content_sha256"] == good["checkpoint"]["content_sha256"]
    assert loaded["next_safe_action"] == "Keep me"


def test_operator_lock_blocks_summary_overwrite(store: ConversationStore):
    conv = store.create(objective="Lock fiction")
    cid = conv["conversation_id"]
    store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Operator next"],
        next_safe_action="Operator next",
    )
    # Simulated model/host summary attempt
    store.update_task_fields(
        cid,
        {
            "outstanding_steps": ["Generated wrong step"],
            "next_safe_action": "Generated wrong step",
            "confirmed_facts": ["Model said otherwise"],
        },
    )
    record = store.get(cid)
    assert record["next_safe_action"] == "Operator next"
    assert record["outstanding_steps"] == ["Operator next"]
    assert record["confirmed_facts"] == ["Model said otherwise"]

    assembled = store.assemble_model_context(cid, "What is next?")
    assert assembled["operator_task_state"]["authoritative"] is True
    assert assembled["operator_task_state"]["next_safe_action"] == "Operator next"
    assert "operator" in assembled["continuity_note"].casefold()
