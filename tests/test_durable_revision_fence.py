"""TASK ELYSIA-FOA-DURABLE-REVISION-031: split checkpoint/conversation fence.

Cloud-only disposable synthetic data. No network, providers, or PC runtime.
"""
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
    RecoveryRequiredError,
    StaleTaskEditError,
    resolve_conversation_root,
)
import project_guardian.conversation_continuity as mod


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


def _seed_steps(store: ConversationStore) -> tuple[str, list[dict], int]:
    conv = store.create(
        title="Synthetic estimate",
        objective="Correct materials without losing labor",
        constraints=["Stay fictional", "No network"],
    )
    cid = conv["conversation_id"]
    result = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Material A", "Subtotal B", "Draft C", "Labor D"],
        next_safe_action="Material A",
    )
    steps = result["conversation"]["task_steps"]
    store.complete_operator_step(cid, step_id=steps[0]["step_id"], expected_revision=1)
    store.complete_operator_step(cid, step_id=steps[1]["step_id"], expected_revision=2)
    rev = store.get(cid)["checkpoint_revision"]
    return cid, steps, rev


def _force_split_crash(store: ConversationStore, cid: str) -> tuple[int, int]:
    """Leave conversation behind checkpoint as if the process died mid-commit."""
    conv_path = store._conv_path(cid)
    ckpt_path = store._checkpoint_path(cid)
    conversation = json.loads(conv_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(ckpt_path.read_text(encoding="utf-8"))
    ahead = dict(checkpoint)
    ahead["revision"] = int(checkpoint.get("revision") or 0) + 1
    ahead["next_safe_action"] = "RECOVERY-REQUIRED-MARKER"
    ahead["reason"] = "synthetic_interrupted_commit"
    # Keep schema/identity valid; content hash not required for mismatch fence.
    ckpt_path.write_text(json.dumps(ahead, indent=2) + "\n", encoding="utf-8")
    return int(conversation.get("checkpoint_revision") or 0), int(ahead["revision"])


def test_matched_state_normal_complete_unchanged(store: ConversationStore):
    cid, steps, rev = _seed_steps(store)
    result = store.complete_operator_step(
        cid, step_id=steps[2]["step_id"], expected_revision=rev
    )
    assert result["saved"] is True
    assert result["idempotent"] is False
    assert store.get(cid)["checkpoint_revision"] == rev + 1
    assert store.get_checkpoint(cid)["revision"] == rev + 1


def test_second_write_failure_restores_matched_previous(
    store: ConversationStore, monkeypatch
):
    cid, steps, rev = _seed_steps(store)
    before_conv = store.get(cid)
    before_ckpt = store.get_checkpoint(cid)
    real = mod._atomic_write_json

    def boom(path, payload):
        if Path(path).name == "conversation.json":
            raise OSError("simulated interrupt on conversation write")
        return real(path, payload)

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError, match="previous matched checkpoint restored"):
        store.complete_operator_step(
            cid, step_id=steps[2]["step_id"], expected_revision=rev
        )

    monkeypatch.setattr(mod, "_atomic_write_json", real)
    again = ConversationStore(store.root)
    loaded = again.get(cid)
    ckpt = again.get_checkpoint(cid)
    assert loaded["checkpoint_revision"] == rev
    assert ckpt["revision"] == rev
    assert loaded["next_safe_action"] == before_conv["next_safe_action"]
    assert ckpt["content_sha256"] == before_ckpt["content_sha256"]

    # Legitimate retry after restore must still work exactly once.
    done = again.complete_operator_step(
        cid, step_id=steps[2]["step_id"], expected_revision=rev
    )
    assert done["saved"] is True
    assert again.get(cid)["checkpoint_revision"] == rev + 1


def test_crash_split_fails_closed_and_preserves_both_files(
    store: ConversationStore, tmp_path: Path
):
    cid, steps, rev = _seed_steps(store)
    conv_rev, ckpt_rev = _force_split_crash(store, cid)
    assert conv_rev == rev
    assert ckpt_rev == rev + 1

    conv_path = store._conv_path(cid)
    ckpt_path = store._checkpoint_path(cid)
    conv_before = conv_path.read_text(encoding="utf-8")
    ckpt_before = ckpt_path.read_text(encoding="utf-8")

    again = ConversationStore(resolve_conversation_root(tmp_path))
    with pytest.raises(RecoveryRequiredError, match="conversation revision"):
        again.get(cid)
    with pytest.raises(RecoveryRequiredError):
        again.get_checkpoint(cid)
    with pytest.raises(RecoveryRequiredError):
        again.complete_operator_step(
            cid, step_id=steps[2]["step_id"], expected_revision=conv_rev
        )
    with pytest.raises(RecoveryRequiredError):
        again.execute_verified_bound_step(
            cid,
            step_id=steps[3]["step_id"],
            expected_revision=conv_rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id="exec_" + "a" * 16,
        )

    # Evidence preserved: no overwrite of either artifact.
    assert conv_path.read_text(encoding="utf-8") == conv_before
    assert ckpt_path.read_text(encoding="utf-8") == ckpt_before


def test_first_write_failure_preserves_previous_good_state(
    store: ConversationStore, monkeypatch
):
    cid, steps, rev = _seed_steps(store)
    good = store.get_checkpoint(cid)

    def boom(*_a, **_k):
        raise OSError("simulated interrupt")

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError):
        store.complete_operator_step(
            cid, step_id=steps[2]["step_id"], expected_revision=rev
        )
    loaded = json.loads(store._checkpoint_path(cid).read_text(encoding="utf-8"))
    assert loaded["content_sha256"] == good["content_sha256"]
    assert store.get(cid)["checkpoint_revision"] == rev


def test_idempotent_same_edit_preserved(store: ConversationStore):
    cid, steps, rev = _seed_steps(store)
    a = store.complete_operator_step(
        cid, step_id=steps[2]["step_id"], expected_revision=rev
    )
    b = store.complete_operator_step(
        cid, step_id=steps[2]["step_id"], expected_revision=rev
    )
    assert a["checkpoint"]["revision"] == rev + 1
    assert b["idempotent"] is True
    assert store.get(cid)["checkpoint_revision"] == rev + 1


def test_index_failure_after_matching_commit_is_distinct(
    store: ConversationStore, monkeypatch
):
    cid, steps, rev = _seed_steps(store)
    real = mod._atomic_write_json

    def boom(path, payload):
        if Path(path).name == "index.json":
            raise OSError("simulated index interrupt")
        return real(path, payload)

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError, match="index write failed"):
        store.complete_operator_step(
            cid, step_id=steps[2]["step_id"], expected_revision=rev
        )
    monkeypatch.setattr(mod, "_atomic_write_json", real)
    # Matching committed state: conversation and checkpoint advanced together.
    assert store.get(cid)["checkpoint_revision"] == rev + 1
    assert store.get_checkpoint(cid)["revision"] == rev + 1


def test_stale_competing_edit_still_rejected(store: ConversationStore):
    cid, steps, rev = _seed_steps(store)
    store.complete_operator_step(
        cid, step_id=steps[2]["step_id"], expected_revision=rev
    )
    with pytest.raises(StaleTaskEditError):
        store.complete_operator_step(
            cid, step_id=steps[3]["step_id"], expected_revision=rev
        )


def test_http_read_and_execute_blocked_on_split(tmp_path: Path):
    """Contained Flask test-client: split state fails closed with no execution."""
    if "project_guardian.ui_control_panel" not in sys.modules:
        if "project_guardian" not in sys.modules:
            package = types.ModuleType("project_guardian")
            package.__path__ = [str(_ROOT / "project_guardian")]
            package.__package__ = "project_guardian"
            sys.modules["project_guardian"] = package

    from project_guardian.ui_control_panel import UIControlPanel

    disposable = tmp_path / "disposable"
    disposable.mkdir()
    store = ConversationStore(resolve_conversation_root(disposable))
    cid, steps, rev = _seed_steps(store)
    _force_split_crash(store, cid)

    class _Orch:
        def __init__(self):
            self.config = {
                "contained_startup": True,
                "disposable_root": str(disposable),
            }
            self.execute_calls = 0

        def run_autonomous_cycle(self):
            self.execute_calls += 1
            return {"executed": False}

    orch = _Orch()
    panel = UIControlPanel(orchestrator=orch, host="127.0.0.1", port=5000)
    client = panel.app.test_client()

    read_resp = client.get(f"/api/conversations/{cid}/task-state")
    assert read_resp.status_code == 400
    read_body = read_resp.get_json()
    assert read_body["success"] is False
    assert "recovery required" in (read_body.get("error") or "").lower()

    exec_resp = client.post(
        f"/api/conversations/{cid}/task-steps/{steps[3]['step_id']}/execute",
        json={
            "expected_revision": rev,
            "authorize_calculator": True,
            "authorize_record_completion": True,
            "execution_id": "exec_" + "b" * 16,
        },
    )
    assert exec_resp.status_code in {400, 409}
    exec_body = exec_resp.get_json()
    assert exec_body.get("success") is False
    # No-action witness: orchestrator autonomy path untouched; store still split.
    assert orch.execute_calls == 0
    with pytest.raises(RecoveryRequiredError):
        ConversationStore(resolve_conversation_root(disposable)).get(cid)
