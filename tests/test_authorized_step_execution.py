"""Authorized calculator-bound step execution, verification, reopen."""
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
    StaleTaskEditError,
    resolve_conversation_root,
)


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


def _seed_bound(store: ConversationStore) -> tuple[str, str, int]:
    conv = store.create(
        objective="Estimate fictional labor for a paint job",
        constraints=["Stay fictional"],
    )
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Calculate labor cost", "Review materials list"],
        next_safe_action="Calculate labor cost",
    )
    step_id = saved["conversation"]["task_steps"][0]["step_id"]
    bound = store.bind_operator_step(
        cid,
        step_id=step_id,
        expected_revision=1,
        capability="calculator.labor",
        arguments={"hourly_rate_usd": "35", "painters": 2, "days": 3, "hours_per_day": 8},
    )
    return cid, step_id, int(bound["conversation"]["checkpoint_revision"])


def test_unauthorized_execute_rejected(store: ConversationStore):
    cid, step_id, rev = _seed_bound(store)
    with pytest.raises(ContinuityError, match="not authorized"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=False,
            authorize_record_completion=True,
        )
    with pytest.raises(ContinuityError, match="not authorized"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=False,
        )
    assert store.get(cid)["task_steps"][0]["status"] == "pending"


def test_authorized_execute_verifies_and_advances(store: ConversationStore, tmp_path: Path):
    cid, step_id, rev = _seed_bound(store)
    result = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
        execution_id="exec_" + "a" * 16,
    )
    assert result["saved"] is True
    assert result["verified"] is True
    assert result["receipt"]["result"] == "1680"
    assert result["advanced"] is True
    assert result["conversation"]["next_safe_action"] == "Review materials list"
    step = next(s for s in result["conversation"]["task_steps"] if s["step_id"] == step_id)
    assert step["status"] == "completed"
    assert step["completion_source"] == "operator_verified_execution"
    assert step["verification_status"] == "verified"

    again = ConversationStore(resolve_conversation_root(tmp_path))
    loaded = again.get(cid)
    assert loaded["next_safe_action"] == "Review materials list"
    assert loaded["task_steps"][0]["result_reference"]["result"] == "1680"


def test_duplicate_execution_idempotent(store: ConversationStore):
    cid, step_id, rev = _seed_bound(store)
    eid = "exec_" + "b" * 16
    a = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
        execution_id=eid,
    )
    b = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
        execution_id=eid,
    )
    assert a["checkpoint"]["revision"] == rev + 1
    assert b["idempotent"] is True
    assert b["checkpoint"]["revision"] == rev + 1
    completed = [s for s in store.get(cid)["task_steps"] if s["status"] == "completed"]
    assert len(completed) == 1


def test_stale_execute_rejected(store: ConversationStore):
    cid, step_id, rev = _seed_bound(store)
    store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
    )
    with pytest.raises(StaleTaskEditError):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id="exec_" + "c" * 16,
        )


def test_interrupted_persist_preserves_prior(store: ConversationStore, monkeypatch):
    cid, step_id, rev = _seed_bound(store)
    good = store.get_checkpoint(cid)
    import project_guardian.conversation_continuity as mod

    calls = {"n": 0}
    real = mod._atomic_write_json

    def boom(path, payload):
        calls["n"] += 1
        # Allow pending receipt write, fail checkpoint write.
        if str(path).endswith(".pending.json"):
            return real(path, payload)
        raise OSError("simulated interrupt")

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError, match="not durably recorded"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id="exec_" + "d" * 16,
        )
    loaded = json.loads(store._checkpoint_path(cid).read_text(encoding="utf-8"))
    assert loaded["content_sha256"] == good["content_sha256"]
    assert store.get(cid)["task_steps"][0]["status"] == "pending"


def test_reopen_preserves_receipt(store: ConversationStore):
    cid, step_id, rev = _seed_bound(store)
    done = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
        execution_id="exec_" + "e" * 16,
    )
    rev2 = int(done["conversation"]["checkpoint_revision"])
    reopened = store.reopen_operator_step(cid, step_id=step_id, expected_revision=rev2)
    step = next(s for s in reopened["conversation"]["task_steps"] if s["step_id"] == step_id)
    assert step["status"] == "pending"
    assert step["execution_receipt_id"] == "exec_" + "e" * 16
    assert step["result_reference"]["result"] == "1680"
    assert any(h.get("event") == "reopened" for h in step["execution_history"])
    # Unrelated/next-list head preserved when reopen would be ambiguous.
    assert reopened["conversation"]["next_safe_action"] == "Review materials list"
    assert reopened["advancement_needs_review"] is True


def test_tool_failure_leaves_pending(store: ConversationStore, monkeypatch):
    cid, step_id, rev = _seed_bound(store)

    def boom(_expr):
        raise ValueError("forced arithmetic failure")

    monkeypatch.setattr(
        "project_guardian.local_memory_chat.calculate_local", boom
    )
    with pytest.raises(ContinuityError, match="calculator failed"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
        )
    assert store.get(cid)["task_steps"][0]["status"] == "pending"
    assert store.get(cid)["checkpoint_revision"] == rev
