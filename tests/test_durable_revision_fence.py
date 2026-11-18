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


def _seed_bound_calculator(store: ConversationStore) -> tuple[str, str, int]:
    conv = store.create(
        objective="Estimate fictional labor for a paint job",
        constraints=["Stay fictional", "No network"],
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
        arguments={
            "hourly_rate_usd": "35",
            "painters": 2,
            "days": 3,
            "hours_per_day": 8,
        },
    )
    return cid, step_id, int(bound["conversation"]["checkpoint_revision"])


def test_calculator_second_write_restore_blocks_replay(
    store: ConversationStore, monkeypatch, tmp_path: Path
):
    """Executed-but-uncommitted calculator must not reopen after matched restore."""
    import project_guardian.local_memory_chat as lmc

    cid, step_id, rev = _seed_bound_calculator(store)
    eid = "exec_" + "c" * 16
    calls = {"n": 0}
    real_calc = lmc.calculate_local

    def spy_calc(*a, **k):
        calls["n"] += 1
        return real_calc(*a, **k)

    monkeypatch.setattr(lmc, "calculate_local", spy_calc)
    real_write = mod._atomic_write_json

    def boom(path, payload):
        if Path(path).name == "conversation.json":
            raise OSError("simulated interrupt on conversation write")
        return real_write(path, payload)

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(RecoveryRequiredError, match="unresolved pending"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id=eid,
        )
    monkeypatch.setattr(mod, "_atomic_write_json", real_write)
    assert calls["n"] == 1
    pending = store._conv_dir(cid) / f"{eid}.pending.json"
    assert pending.is_file()
    original_pending = pending.read_text(encoding="utf-8")
    pending_payload = json.loads(original_pending)
    assert pending_payload["schema"] == "elysia.execution-pending.v1"
    assert pending_payload["receipt"]["result"] == "1680"

    again = ConversationStore(resolve_conversation_root(tmp_path))
    with pytest.raises(RecoveryRequiredError, match="unresolved pending"):
        again.get(cid)
    with pytest.raises(RecoveryRequiredError):
        again.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id=eid,
        )
    with pytest.raises(RecoveryRequiredError):
        again.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id="exec_" + "d" * 16,
        )
    with pytest.raises(RecoveryRequiredError):
        again.complete_operator_step(
            cid, step_id=step_id, expected_revision=rev
        )
    assert calls["n"] == 1
    assert pending.read_text(encoding="utf-8") == original_pending


def test_matched_completed_execution_idempotent_still_works(
    store: ConversationStore, monkeypatch
):
    import project_guardian.local_memory_chat as lmc

    cid, step_id, rev = _seed_bound_calculator(store)
    eid = "exec_" + "e" * 16
    calls = {"n": 0}
    real_calc = lmc.calculate_local

    def spy_calc(*a, **k):
        calls["n"] += 1
        return real_calc(*a, **k)

    monkeypatch.setattr(lmc, "calculate_local", spy_calc)
    first = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
        execution_id=eid,
    )
    second = store.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
        execution_id=eid,
    )
    assert first["saved"] is True
    assert second["idempotent"] is True
    assert calls["n"] == 1
    assert not (store._conv_dir(cid) / f"{eid}.pending.json").exists()


def test_pre_admission_write_failure_zero_calls(store: ConversationStore, monkeypatch):
    """Admission write fails before capability: zero calls, matched state usable."""
    import project_guardian.local_memory_chat as lmc

    cid, step_id, rev = _seed_bound_calculator(store)
    eid = "exec_" + "f" * 16
    calls = {"n": 0}
    real_calc = lmc.calculate_local

    def spy_calc(*a, **k):
        calls["n"] += 1
        return real_calc(*a, **k)

    monkeypatch.setattr(lmc, "calculate_local", spy_calc)
    real = mod._atomic_write_json

    def boom(path, payload):
        if str(path).endswith(".pending.json") and (
            isinstance(payload, dict) and payload.get("phase") == "ADMITTED"
        ):
            raise OSError("admission write failed")
        return real(path, payload)

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(ContinuityError, match="durably admit"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id=eid,
        )
    monkeypatch.setattr(mod, "_atomic_write_json", real)
    assert calls["n"] == 0
    assert list(store._conv_dir(cid).glob("*.pending.json")) == []
    assert store.get(cid)["task_steps"][0]["status"] == "pending"


def test_post_call_verified_receipt_write_failure_retains_marker(
    store: ConversationStore, monkeypatch
):
    """After capability returns, VERIFIED_RECEIPT write failure keeps ADMITTED marker."""
    import project_guardian.local_memory_chat as lmc

    cid, step_id, rev = _seed_bound_calculator(store)
    eid = "exec_" + "a" * 16
    calls = {"n": 0}
    real_calc = lmc.calculate_local
    seen_admit = {"ok": False}

    def spy_calc(*a, **k):
        calls["n"] += 1
        pending = store._conv_dir(cid) / f"{eid}.pending.json"
        assert pending.is_file()
        payload = json.loads(pending.read_text(encoding="utf-8"))
        assert payload.get("phase") == "ADMITTED"
        seen_admit["ok"] = True
        return real_calc(*a, **k)

    monkeypatch.setattr(lmc, "calculate_local", spy_calc)
    real = mod._atomic_write_json

    def boom(path, payload):
        if str(path).endswith(".pending.json") and (
            isinstance(payload, dict) and payload.get("phase") == "VERIFIED_RECEIPT"
        ):
            raise OSError("verified receipt write failed")
        return real(path, payload)

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    with pytest.raises(RecoveryRequiredError, match="verified receipt"):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id=eid,
        )
    monkeypatch.setattr(mod, "_atomic_write_json", real)
    assert calls["n"] == 1
    assert seen_admit["ok"] is True
    pending = store._conv_dir(cid) / f"{eid}.pending.json"
    assert pending.is_file()
    retained = json.loads(pending.read_text(encoding="utf-8"))
    assert retained.get("phase") == "ADMITTED"
    with pytest.raises(RecoveryRequiredError, match="unresolved pending"):
        store.get(cid)
    with pytest.raises(RecoveryRequiredError):
        store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_calculator=True,
            authorize_record_completion=True,
            execution_id=eid,
        )
    assert calls["n"] == 1


def test_missing_checkpoint_when_revision_nonzero_fails_closed(store: ConversationStore):
    cid, steps, rev = _seed_steps(store)
    assert rev >= 1
    store._checkpoint_path(cid).unlink()
    with pytest.raises(RecoveryRequiredError, match="checkpoint missing"):
        store.get(cid)


def test_malformed_checkpoint_fails_closed(store: ConversationStore):
    cid, _steps, _rev = _seed_steps(store)
    store._checkpoint_path(cid).write_text("{not-json", encoding="utf-8")
    with pytest.raises(RecoveryRequiredError, match="checkpoint unreadable"):
        store.get(cid)


def test_http_bound_calculator_second_write_blocks_replay(tmp_path: Path, monkeypatch):
    """Contained Flask route: positive control once, then no replay after interrupt."""
    if "project_guardian" not in sys.modules:
        package = types.ModuleType("project_guardian")
        package.__path__ = [str(_ROOT / "project_guardian")]
        package.__package__ = "project_guardian"
        sys.modules["project_guardian"] = package

    from project_guardian.ui_control_panel import UIControlPanel
    import project_guardian.local_memory_chat as lmc

    disposable = tmp_path / "disposable"
    disposable.mkdir()
    store = ConversationStore(resolve_conversation_root(disposable))
    cid, step_id, rev = _seed_bound_calculator(store)

    class _Orch:
        def __init__(self):
            self.config = {
                "contained_startup": True,
                "disposable_root": str(disposable),
            }

    panel = UIControlPanel(orchestrator=_Orch(), host="127.0.0.1", port=5000)
    client = panel.app.test_client()
    calls = {"n": 0}
    real_calc = lmc.calculate_local

    def spy_calc(*a, **k):
        calls["n"] += 1
        return real_calc(*a, **k)

    monkeypatch.setattr(lmc, "calculate_local", spy_calc)

    # Positive control: authorized bound execute through the real HTTP route.
    ok = client.post(
        f"/api/conversations/{cid}/task-steps/{step_id}/execute",
        json={
            "expected_revision": rev,
            "authorize_calculator": True,
            "authorize_record_completion": True,
            "execution_id": "exec_" + "1" * 16,
        },
    )
    assert ok.status_code == 200
    ok_body = ok.get_json()
    assert ok_body["success"] is True
    assert ok_body["verified"] is True
    assert ok_body["receipt"]["result"] == "1680"
    assert calls["n"] == 1
    rev_after = int(ok_body["conversation"]["checkpoint_revision"])

    # Re-bind a fresh pending labor step for interrupt scenario on a new conversation.
    store2 = ConversationStore(resolve_conversation_root(disposable))
    cid2, step2, rev2 = _seed_bound_calculator(store2)
    eid2 = "exec_" + "2" * 16
    real_write = mod._atomic_write_json

    def boom(path, payload):
        if Path(path).name == "conversation.json":
            raise OSError("simulated interrupt on conversation write")
        return real_write(path, payload)

    monkeypatch.setattr(mod, "_atomic_write_json", boom)
    blocked = client.post(
        f"/api/conversations/{cid2}/task-steps/{step2}/execute",
        json={
            "expected_revision": rev2,
            "authorize_calculator": True,
            "authorize_record_completion": True,
            "execution_id": eid2,
        },
    )
    monkeypatch.setattr(mod, "_atomic_write_json", real_write)
    assert blocked.status_code == 409
    blocked_body = blocked.get_json()
    assert blocked_body["success"] is False
    assert blocked_body.get("recovery_required") is True
    assert blocked_body.get("executed_this_request") is False
    assert "recovery required" in (blocked_body.get("error") or "").lower()
    assert calls["n"] == 2  # positive control + one interrupted attempt

    pending = store2._conv_dir(cid2) / f"{eid2}.pending.json"
    assert pending.is_file()
    original = pending.read_text(encoding="utf-8")

    retry_same = client.post(
        f"/api/conversations/{cid2}/task-steps/{step2}/execute",
        json={
            "expected_revision": rev2,
            "authorize_calculator": True,
            "authorize_record_completion": True,
            "execution_id": eid2,
        },
    )
    retry_diff = client.post(
        f"/api/conversations/{cid2}/task-steps/{step2}/execute",
        json={
            "expected_revision": rev2,
            "authorize_calculator": True,
            "authorize_record_completion": True,
            "execution_id": "exec_" + "3" * 16,
        },
    )
    assert retry_same.status_code == 409
    assert retry_diff.status_code == 409
    assert retry_same.get_json().get("recovery_required") is True
    assert retry_diff.get_json().get("recovery_required") is True
    assert calls["n"] == 2
    assert pending.read_text(encoding="utf-8") == original

    # First conversation remains healthy / matched after successful commit.
    healthy = ConversationStore(resolve_conversation_root(disposable)).get(cid)
    assert healthy["checkpoint_revision"] == rev_after
    assert healthy["task_steps"][0]["status"] == "completed"


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
    assert read_resp.status_code == 409
    read_body = read_resp.get_json()
    assert read_body["success"] is False
    assert read_body.get("recovery_required") is True
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
    assert exec_resp.status_code == 409
    exec_body = exec_resp.get_json()
    assert exec_body.get("success") is False
    assert exec_body.get("recovery_required") is True
    # No-action witness: orchestrator autonomy path untouched; store still split.
    assert orch.execute_calls == 0
    with pytest.raises(RecoveryRequiredError):
        ConversationStore(resolve_conversation_root(disposable)).get(cid)


def test_shared_root_lock_across_store_instances(tmp_path: Path):
    root = resolve_conversation_root(tmp_path)
    a = ConversationStore(root)
    b = ConversationStore(root)
    assert a._lock is b._lock


def test_concurrent_store_execute_serializes_one_admission(
    tmp_path: Path, monkeypatch
):
    """Two Store instances / threads: one admits; total calculator calls == 1."""
    import threading
    import project_guardian.local_memory_chat as lmc

    root = resolve_conversation_root(tmp_path)
    seed = ConversationStore(root)
    cid, step_id, rev = _seed_bound_calculator(seed)
    start = threading.Barrier(2, timeout=10)
    calls = {"n": 0}
    results = []
    lock = threading.Lock()
    real_calc = lmc.calculate_local

    def spy_calc(*a, **k):
        calls["n"] += 1
        return real_calc(*a, **k)

    monkeypatch.setattr(lmc, "calculate_local", spy_calc)

    def worker(eid: str):
        store = ConversationStore(root)
        start.wait()
        try:
            out = store.execute_verified_bound_step(
                cid,
                step_id=step_id,
                expected_revision=rev,
                authorize_calculator=True,
                authorize_record_completion=True,
                execution_id=eid,
            )
            with lock:
                results.append(("ok", out.get("executed_this_request"), eid))
        except Exception as exc:
            with lock:
                results.append(("err", type(exc).__name__, str(exc)))

    t1 = threading.Thread(target=worker, args=("exec_" + "1" * 16,))
    t2 = threading.Thread(target=worker, args=("exec_" + "2" * 16,))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)
    assert not t1.is_alive() and not t2.is_alive()
    assert calls["n"] == 1
    oks = [r for r in results if r[0] == "ok"]
    errs = [r for r in results if r[0] == "err"]
    assert len(oks) == 1
    assert len(errs) == 1
    assert oks[0][1] is True
    assert errs[0][1] in {"StaleTaskEditError", "RecoveryRequiredError", "ContinuityError"}


def test_pilot_exclusion_module_reusable():
    """Reuse existing launch claim rather than inventing a second ownership system."""
    excl_src = (_ROOT / "pilot" / "pilot_exclusion.py").read_text(encoding="utf-8")
    launch_src = (_ROOT / "pilot" / "launch_verified_pilot.py").read_text(encoding="utf-8")
    assert "def try_acquire_launch_claim" in excl_src
    assert "def launch_claim_is_held" in excl_src
    assert "def writer_exclusion_status" in excl_src
    assert "try_acquire_launch_claim" in launch_src
    assert "own_launch_claim" in launch_src
    # In-process Store serialization remains required even with launch claim.
    assert "_shared_root_lock" in (
        (_ROOT / "project_guardian" / "conversation_continuity.py").read_text(
            encoding="utf-8"
        )
    )
