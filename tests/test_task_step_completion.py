"""Operator step completion and safe next-action advancement."""
from __future__ import annotations

import json
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
    NO_OUTSTANDING_STEPS,
    StaleTaskEditError,
    resolve_conversation_root,
)


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


def _seed(store: ConversationStore) -> tuple[str, list[dict]]:
    conv = store.create(
        title="Garden checklist",
        objective="Complete a fictional garden maintenance checklist",
        constraints=["Stay fictional"],
    )
    cid = conv["conversation_id"]
    result = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Check soil", "Log weather", "Water plants"],
        next_safe_action="Check soil",
    )
    steps = result["conversation"]["task_steps"]
    assert len(steps) == 3
    return cid, steps


def test_complete_advances_next_action(store: ConversationStore, tmp_path: Path):
    cid, steps = _seed(store)
    first = steps[0]
    result = store.complete_operator_step(
        cid, step_id=first["step_id"], expected_revision=1
    )
    assert result["saved"] is True
    assert result["advanced"] is True
    assert result["advancement_needs_review"] is False
    assert result["checkpoint"]["revision"] == 2
    assert result["checkpoint"]["reason"] == "operator_step_complete"
    assert result["conversation"]["next_safe_action"] == "Log weather"
    assert result["conversation"]["outstanding_steps"] == ["Log weather", "Water plants"]
    completed = [s for s in result["conversation"]["task_steps"] if s["status"] == "completed"]
    assert len(completed) == 1
    assert completed[0]["completion_source"] == "operator"
    assert completed[0]["step_id"] == first["step_id"]

    again = ConversationStore(resolve_conversation_root(tmp_path))
    loaded = again.get(cid)
    assert loaded["next_safe_action"] == "Log weather"
    assert loaded["checkpoint_revision"] == 2


def test_unrelated_next_action_preserved(store: ConversationStore):
    cid, steps = _seed(store)
    # Operator sets an unrelated next action (not the head pending step).
    store.commit_operator_task_state(
        cid,
        expected_revision=1,
        next_safe_action="Call fictional nursery first",
    )
    first = steps[0]
    result = store.complete_operator_step(
        cid, step_id=first["step_id"], expected_revision=2
    )
    assert result["advanced"] is False
    assert result["advancement_needs_review"] is True
    assert result["conversation"]["next_safe_action"] == "Call fictional nursery first"
    pending = [s["description"] for s in result["conversation"]["task_steps"] if s["status"] == "pending"]
    assert "Check soil" not in pending
    assert "Log weather" in pending


def test_idempotent_completion_retry(store: ConversationStore):
    cid, steps = _seed(store)
    first = steps[0]
    a = store.complete_operator_step(cid, step_id=first["step_id"], expected_revision=1)
    b = store.complete_operator_step(cid, step_id=first["step_id"], expected_revision=1)
    assert a["checkpoint"]["revision"] == 2
    assert b["idempotent"] is True
    assert b["checkpoint"]["revision"] == 2
    assert store.get(cid)["checkpoint_revision"] == 2
    completed = [s for s in store.get(cid)["task_steps"] if s["status"] == "completed"]
    assert len(completed) == 1


def test_stale_completion_rejected(store: ConversationStore):
    cid, steps = _seed(store)
    store.complete_operator_step(cid, step_id=steps[0]["step_id"], expected_revision=1)
    with pytest.raises(StaleTaskEditError):
        store.complete_operator_step(cid, step_id=steps[1]["step_id"], expected_revision=1)


def test_failed_write_preserves_checkpoint(store: ConversationStore, monkeypatch):
    cid, steps = _seed(store)
    good = store.get_checkpoint(cid)
    import project_guardian.conversation_continuity as mod

    def boom(*_a, **_k):
        raise OSError("simulated interrupt")

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError):
        store.complete_operator_step(cid, step_id=steps[0]["step_id"], expected_revision=1)
    loaded = json.loads(store._checkpoint_path(cid).read_text(encoding="utf-8"))
    assert loaded["content_sha256"] == good["content_sha256"]
    assert store.get(cid)["next_safe_action"] == "Check soil"


def test_last_step_does_not_invent_work(store: ConversationStore):
    cid, steps = _seed(store)
    store.complete_operator_step(cid, step_id=steps[0]["step_id"], expected_revision=1)
    store.complete_operator_step(cid, step_id=steps[1]["step_id"], expected_revision=2)
    result = store.complete_operator_step(
        cid, step_id=steps[2]["step_id"], expected_revision=3
    )
    assert result["conversation"]["next_safe_action"] == NO_OUTSTANDING_STEPS
    assert result["conversation"]["outstanding_steps"] == []
    assert all(s["status"] == "completed" for s in result["conversation"]["task_steps"])


def test_model_summary_cannot_reverse_completion(store: ConversationStore):
    cid, steps = _seed(store)
    store.complete_operator_step(cid, step_id=steps[0]["step_id"], expected_revision=1)
    store.update_task_fields(
        cid,
        {
            "outstanding_steps": ["Check soil", "Log weather", "Water plants"],
            "next_safe_action": "Check soil",
            "task_steps": [],
        },
    )
    record = store.get(cid)
    assert record["next_safe_action"] == "Log weather"
    assert "Check soil" not in record["outstanding_steps"]
    completed_ids = {
        s["step_id"] for s in record["task_steps"] if s["status"] == "completed"
    }
    assert steps[0]["step_id"] in completed_ids
