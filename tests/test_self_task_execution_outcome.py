"""Independent evidence required before a self-task is verified successful.

Synthetic files only. The former acceptance rule is copied here so the
adversarial case shows what the previous outcome check treated as success.
"""
import hashlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.self_task_execution_outcome import (
    caller_execution_success,
    capture_host_directory_state,
    evaluate_execution_outcome,
    host_effect_root,
)
from project_guardian.self_task_objectives import ObjectiveStore
from project_guardian.self_task_queue import SelfTaskQueue
from project_guardian.self_task_value_verification import evaluate_execution_value


def former_accepted_false_success(payload, artifact_path, memory_written):
    """Former _has_state_change_evidence rule: path, flag, or dry run was enough."""
    if artifact_path is not None:
        return True
    if memory_written:
        return True
    if isinstance(payload, dict):
        for key in (
            "state_changed",
            "applied",
            "dry_run_result",
            "files_written",
            "files_updated",
            "registry_updated",
            "patch_applied",
            "downstream_result",
            "external_result",
        ):
            value = payload.get(key)
            if value and value not in (False, [], {}, ""):
                return True
    return False


def evaluate(**kwargs):
    base = dict(
        archetype="execute_best_opportunity",
        execution_ready=True,
        execution_tier="strong",
        capability_attempted=True,
        capability_ok=True,
        last_result={},
        artifact_path=None,
        memory_written=False,
        last_capability_ex=None,
        detail="",
    )
    base.update(kwargs)
    return evaluate_execution_outcome(**base)


def test_false_success_flags_dry_run_and_missing_path_are_not_verified(tmp_path):
    missing = tmp_path / "not-written.json"
    payload = {
        "state_changed": True,
        "applied": True,
        "dry_run_result": {"status": "success"},
    }
    assert former_accepted_false_success(payload, missing, True) is True
    result = evaluate(
        last_result=payload,
        artifact_path=missing,
        memory_written=True,
        last_capability_ex={"result": {"state_changed": True}},
        detail="model said the task completed",
    )
    assert result["execution_outcome"] != "succeeded"
    assert result["verification_status"] == "partial"
    assert result["execution_reason"] == "dry_run_not_production_action"
    assert result["execution_followup_needed"] is True
    assert set(result) == {
        "execution_attempted",
        "execution_outcome",
        "execution_reason",
        "execution_artifact",
        "execution_followup_needed",
        "verification_status",
    }


def test_self_reported_state_without_a_file_is_not_verified():
    payload = {"state_changed": True, "applied": True, "files_written": ["invented.txt"]}
    assert former_accepted_false_success(payload, None, False) is True
    result = evaluate(last_result=payload, memory_written=True)
    assert result["execution_outcome"] == "partial"
    assert result["verification_status"] == "partial"
    assert result["execution_reason"] == "self_reported_state_without_corroboration"


def test_plan_is_not_execution():
    result = evaluate(
        archetype="generate_execution_plan",
        last_result={"execution_plan": {"steps": ["describe work"], "state_changed": True}},
    )
    assert result["execution_outcome"] == "readiness_only"
    assert result["verification_status"] == "proposed"
    assert result["execution_attempted"] is True


def test_missing_or_unpermitted_or_mismatched_artifact_is_rejected(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    body = b"synthetic artifact bytes\n"
    inside = root / "receipt.bin"
    inside.write_bytes(body)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    missing = root / "missing.bin"
    assert former_accepted_false_success({}, missing, False) is True

    missing_result = evaluate(artifact_path=missing, allowed_roots=(root,), last_result={"artifact_sha256": digest})
    assert missing_result["execution_outcome"] != "succeeded"
    assert missing_result["execution_reason"] == "artifact_missing_or_unpermitted"
    assert missing_result["execution_artifact"] is None

    outside_result = evaluate(artifact_path=outside, allowed_roots=(root,), last_result={"artifact_sha256": digest})
    assert outside_result["execution_outcome"] != "succeeded"
    assert outside_result["execution_artifact"] is None

    mismatch = evaluate(artifact_path=inside, allowed_roots=(root,), last_result={"artifact_sha256": "0" * 64})
    assert mismatch["execution_outcome"] != "succeeded"
    assert mismatch["verification_status"] == "partial"


def test_matching_file_and_host_state_change_are_verified(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    body = b"synthetic verified receipt\n"
    path = root / "receipt.bin"
    path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    file_result = evaluate(
        artifact_path=path,
        allowed_roots=(root,),
        last_result={"artifact_sha256": digest, "state_changed": False},
    )
    assert file_result["execution_outcome"] == "succeeded"
    assert file_result["verification_status"] == "verified"
    assert file_result["execution_reason"] == "independent_file_integrity"
    assert file_result["execution_artifact"] == str(path.resolve())
    assert file_result["execution_followup_needed"] is False

    state_result = evaluate(
        last_result={"state_changed": False},
        observed_before={"revision": 1, "bytes": 4},
        observed_after={"revision": 2, "bytes": 9},
    )
    assert state_result["execution_outcome"] == "succeeded"
    assert state_result["verification_status"] == "verified"
    assert state_result["execution_reason"] == "independent_state_comparison"

    flags_only = evaluate(
        observed_before={"state_changed": False},
        observed_after={"state_changed": True},
        last_result={"state_changed": True},
    )
    assert flags_only["execution_outcome"] != "succeeded"


def test_valid_file_cannot_promote_a_dry_run(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    body = b"dry run output\n"
    path = root / "receipt.bin"
    path.write_bytes(body)
    result = evaluate(
        artifact_path=path,
        allowed_roots=(root,),
        last_result={
            "artifact_sha256": hashlib.sha256(body).hexdigest(),
            "dry_run_result": {"status": "success"},
        },
    )
    assert result["execution_outcome"] == "partial"
    assert result["verification_status"] == "partial"
    assert result["execution_reason"] == "dry_run_not_production_action"


def test_failure_and_blocked_keep_recovery_detail():
    failed = evaluate(
        capability_ok=False,
        last_capability_ex={"error": "disk full while writing receipt"},
        detail="disk full while writing receipt",
    )
    assert failed["execution_outcome"] == "failed"
    assert failed["verification_status"] == "failed"
    assert "disk full while writing receipt" in failed["execution_reason"]
    assert failed["execution_followup_needed"] is True

    blocked = evaluate(
        capability_attempted=False,
        capability_ok=False,
        detail="required capability unavailable: calculator",
    )
    assert blocked["execution_outcome"] == "failed"
    assert blocked["verification_status"] == "blocked"
    assert "required capability unavailable: calculator" in blocked["execution_reason"]
    assert blocked["execution_followup_needed"] is True


def test_non_execution_and_unapplied_repair_stay_unverified():
    other = evaluate(archetype="learning_recent_digest", last_result={"state_changed": True}, memory_written=True)
    assert other["execution_outcome"] == "none"
    assert other["verification_status"] == "not_applicable"

    repair = evaluate(
        archetype="repair_tool_registry_coverage",
        last_result={"proposal": {"registry_updated": True}},
    )
    assert repair["execution_outcome"] == "partial"
    assert repair["verification_status"] == "partial"
    assert repair["execution_reason"] == "patch_or_proposal_without_apply"


def test_value_check_does_not_treat_a_missing_path_as_an_artifact(tmp_path):
    missing = tmp_path / "missing.json"
    assert former_accepted_false_success({}, missing, False) is True
    result = evaluate_execution_value(
        archetype="execute_best_opportunity",
        adv_result={
            "operator_ready": True,
            "objective_advanced": False,
            "execution_ready": False,
            "advancement_reason": "",
        },
        exec_result={"execution_outcome": "partial"},
        artifact_path=missing,
        execution_tier="strong",
        payload={},
    )
    assert result["value_verified"] is False


def test_queue_records_rejected_and_verified_status(tmp_path):
    queue = SelfTaskQueue(storage_path=tmp_path / "queue.json")
    task = {
        "task_id": "st_false_success",
        "archetype": "execute_best_opportunity",
        "title": "synthetic false success",
    }
    assert queue.enqueue(task, dedupe_key="false-success", cooldown_sec=0)
    assert queue.claim("st_false_success")
    false_result = evaluate(
        last_result={"state_changed": True, "dry_run_result": {"status": "success"}},
        memory_written=True,
        detail="model said done",
    )
    queue.complete(
        "st_false_success",
        success=True,
        useful=False,
        execution_outcome=false_result["execution_outcome"],
        execution_reason=false_result["execution_reason"],
        execution_attempted=false_result["execution_attempted"],
        execution_followup_needed=false_result["execution_followup_needed"],
        verification_status=false_result["verification_status"],
    )
    stored = queue.get_by_id("st_false_success")
    assert stored["execution_outcome"] == "partial"
    assert stored["verification_status"] == "partial"
    assert stored["execution_reason"] == "dry_run_not_production_action"

    verified_task = {
        "task_id": "st_verified",
        "archetype": "execute_best_opportunity",
        "title": "synthetic verified",
    }
    assert queue.enqueue(verified_task, dedupe_key="verified", cooldown_sec=0)
    assert queue.claim("st_verified")
    verified = evaluate(
        observed_before={"revision": 1, "bytes": 4},
        observed_after={"revision": 2, "bytes": 9},
    )
    queue.complete(
        "st_verified",
        success=True,
        useful=True,
        execution_outcome=verified["execution_outcome"],
        execution_reason=verified["execution_reason"],
        execution_attempted=True,
        verification_status=verified["verification_status"],
    )
    stored_verified = queue.get_by_id("st_verified")
    assert stored_verified["execution_outcome"] == "succeeded"
    assert stored_verified["verification_status"] == "verified"


def _blob_sha1(data: bytes) -> str:
    normalized = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(normalized) + normalized).hexdigest()


def test_module_activity_is_the_historical_helper():
    data = (ROOT / "project_guardian" / "module_activity.py").read_bytes()
    assert _blob_sha1(data) == "7795b83ac5f4482deec10700980f482a11c9cb54"
    text = data.decode("utf-8")
    assert "def mark_module_activity(" in text
    assert "def get_module_last_activity(" in text
    assert "def activity_age_minutes(" in text


def test_host_snapshot_verifies_a_real_change_and_rejects_a_false_report(tmp_path):
    root = host_effect_root(tmp_path / "queue.json")
    assert root == tmp_path / "self_task_host_effects"
    before = capture_host_directory_state(root)
    false_report = evaluate(
        last_result={
            "success": True,
            "state_changed": True,
            "applied": True,
            "dry_run_result": {"status": "success"},
        },
        memory_written=True,
        observed_before=before,
        observed_after=capture_host_directory_state(root),
        detail="model said the host changed",
    )
    assert false_report["verification_status"] == "partial"
    assert false_report["execution_outcome"] != "succeeded"
    assert caller_execution_success(
        "execute_best_opportunity", True, True, false_report
    ) == (False, False)

    root.mkdir()
    (root / "receipt.txt").write_text("host-observed", encoding="utf-8")
    changed = evaluate(
        last_result={"success": True, "state_changed": True},
        observed_before=before,
        observed_after=capture_host_directory_state(root),
    )
    assert changed["verification_status"] == "verified"
    assert changed["execution_outcome"] == "succeeded"
    assert changed["execution_reason"] == "independent_state_comparison"
    assert caller_execution_success(
        "execute_best_opportunity", True, True, changed
    ) == (True, True)

    dry = evaluate(
        last_result={"dry_run_result": {"status": "success"}, "state_changed": True},
        observed_before=before,
        observed_after=capture_host_directory_state(root),
    )
    assert dry["verification_status"] == "partial"
    assert dry["execution_outcome"] == "partial"


def test_queue_and_objective_keep_the_same_verified_outcome(tmp_path):
    queue_path = tmp_path / "queue.json"
    objective_path = tmp_path / "objectives.json"
    queue = SelfTaskQueue(storage_path=queue_path)
    objectives = ObjectiveStore(storage_path=objective_path)
    objective_id = objectives.create_lightweight(title="synthetic", goal="observe a receipt")
    root = host_effect_root(queue_path)
    before = capture_host_directory_state(root)

    queue.enqueue(
        {
            "task_id": "st_false",
            "archetype": "execute_best_opportunity",
            "title": "false success",
            "objective_id": objective_id,
        },
        dedupe_key="false",
        cooldown_sec=0,
    )
    queue.claim("st_false")
    false_result = evaluate(
        last_result={"success": True, "state_changed": True, "applied": True},
        memory_written=True,
        observed_before=before,
        observed_after=capture_host_directory_state(root),
    )
    false_value = evaluate_execution_value(
        archetype="execute_best_opportunity",
        adv_result={
            "operator_ready": True,
            "objective_advanced": True,
            "execution_ready": True,
            "advancement_reason": "model said the objective moved",
        },
        exec_result=false_result,
        artifact_path=None,
        execution_tier="strong",
        payload={"state_changed": True},
    )
    assert false_value["value_verified"] is False
    queue.complete(
        "st_false",
        success=True,
        useful=True,
        execution_tier="strong",
        objective_advanced=True,
        operator_ready=True,
        execution_attempted=True,
        execution_outcome="succeeded",
        verification_status=false_result["verification_status"],
        value_verified=True,
    )
    objectives.apply_post_execution_objective(
        objective_id,
        archetype="execute_best_opportunity",
        exec_result=false_result,
        value_result={"value_verified": True, "blocker_removed": True, "value_score": 0.9},
    )

    reloaded_queue = SelfTaskQueue(storage_path=queue_path)
    reloaded_objective = ObjectiveStore(storage_path=objective_path)
    stored = reloaded_queue.get_by_id("st_false")
    objective = reloaded_objective.get(objective_id)
    assert stored["verification_status"] == "partial"
    assert stored["execution_outcome"] != "succeeded"
    assert stored["value_verified"] is False
    assert not str(stored["last_outcome"]).startswith("execution_succeeded")
    assert objective["last_execution"]["verification_status"] == "partial"
    assert objective["last_execution"]["execution_outcome"] != "succeeded"
    assert objective["value_verified"] is False
    assert objective.get("execution_completed") is False
    assert float(objective["progress"]) == 0.0
    assert objective.get("blocker_removed") is not True
    assert objective["status"] == "active"

    root.mkdir()
    (root / "receipt.txt").write_text("paid", encoding="utf-8")
    verified = evaluate(
        observed_before=before,
        observed_after=capture_host_directory_state(root),
        last_result={"success": True},
    )
    queue.enqueue(
        {
            "task_id": "st_real",
            "archetype": "execute_best_opportunity",
            "title": "real change",
            "objective_id": objective_id,
        },
        dedupe_key="real",
        cooldown_sec=0,
    )
    queue.claim("st_real")
    queue.complete(
        "st_real",
        success=True,
        useful=True,
        execution_tier="strong",
        objective_advanced=True,
        operator_ready=True,
        execution_attempted=True,
        execution_outcome=verified["execution_outcome"],
        verification_status=verified["verification_status"],
        value_verified=False,
    )
    objectives.apply_post_execution_objective(
        objective_id,
        archetype="execute_best_opportunity",
        exec_result=verified,
        value_result={"value_verified": False, "value_score": 0.2},
    )
    reloaded_queue = SelfTaskQueue(storage_path=queue_path)
    reloaded_objective = ObjectiveStore(storage_path=objective_path)
    stored = reloaded_queue.get_by_id("st_real")
    objective = reloaded_objective.get(objective_id)
    assert stored["verification_status"] == "verified"
    assert stored["execution_outcome"] == "succeeded"
    assert str(stored["last_outcome"]).startswith("execution_succeeded")
    assert objective["last_execution"]["verification_status"] == "verified"
    assert objective["last_execution"]["execution_outcome"] == "succeeded"
    assert objective["execution_completed"] is True
    assert float(objective["progress"]) == 0.12

    plan = evaluate(
        archetype="generate_execution_plan",
        last_result={"state_changed": True, "success": True},
        observed_before=before,
        observed_after=capture_host_directory_state(root),
    )
    assert plan["execution_outcome"] == "readiness_only"
    assert plan["verification_status"] == "proposed"
    assert caller_execution_success("generate_execution_plan", True, True, plan) == (True, True)
    plan_objective = objectives.create_lightweight(title="plan", goal="plan only")
    objectives.apply_post_execution_objective(
        plan_objective,
        archetype="generate_execution_plan",
        exec_result=plan,
        value_result={"value_verified": True, "value_score": 0.4},
    )
    planned = ObjectiveStore(storage_path=objective_path).get(plan_objective)
    assert planned.get("execution_completed") is not True
    assert float(planned["progress"]) == 0.0
    assert planned["last_execution"]["verification_status"] == "proposed"


def test_self_generated_task_runner_uses_host_snapshots(tmp_path):
    try:
        from project_guardian.core import GuardianCore
    except ImportError as exc:
        pytest.skip("GuardianCore startup blocked: %s" % exc)

    import project_guardian.capability_execution as capability_execution
    import project_guardian.self_task_objectives as objective_mod
    import project_guardian.self_task_queue as queue_mod

    queue_path = tmp_path / "queue.json"
    objective_path = tmp_path / "objectives.json"
    effect_root = host_effect_root(queue_path)
    original_queue = queue_mod.SelfTaskQueue
    original_objectives = objective_mod.ObjectiveStore
    original_execute = capability_execution.execute_capability_kind

    def queue_factory(*args, **kwargs):
        kwargs["storage_path"] = queue_path
        return original_queue(*args, **kwargs)

    def objective_factory(*args, **kwargs):
        kwargs["storage_path"] = objective_path
        return original_objectives(*args, **kwargs)

    objectives = original_objectives(storage_path=objective_path)
    objective_id = objectives.create_lightweight(title="runner", goal="host receipt")
    queue = original_queue(storage_path=queue_path)
    queue.enqueue(
        {
            "task_id": "st_runner_false",
            "archetype": "execute_best_opportunity",
            "title": "runner false success",
            "objective_id": objective_id,
            "recommended_capabilities": ["module:false_success"],
        },
        dedupe_key="runner-false",
        cooldown_sec=0,
    )
    queue.enqueue(
        {
            "task_id": "st_runner_real",
            "archetype": "execute_best_opportunity",
            "title": "runner real change",
            "objective_id": objective_id,
            "recommended_capabilities": ["module:write_receipt"],
        },
        dedupe_key="runner-real",
        cooldown_sec=0,
    )

    def execute(guardian, kind, name, payload):
        if name == "write_receipt":
            effect_root.mkdir(parents=True, exist_ok=True)
            (effect_root / "receipt.txt").write_text("observed-by-host", encoding="utf-8")
        return {
            "success": True,
            "result_for_governance": {
                "success": True,
                "state_changed": True,
                "applied": True,
                "dry_run_result": {"status": "success"} if name == "false_success" else None,
            },
        }

    runner = GuardianCore.__new__(GuardianCore)
    runner._load_self_tasking_config = lambda: {
        "max_queue_size": 24,
        "orchestration_bounded_capability_execution": False,
        "dedupe_cooldown_sec": 0,
    }
    runner._self_task_payload_useful = lambda result: False
    runner._self_task_has_strong_signals = lambda **kwargs: False
    runner._module_last_invoked = {}
    queue_mod.SelfTaskQueue = queue_factory
    objective_mod.ObjectiveStore = objective_factory
    capability_execution.execute_capability_kind = execute
    try:
        false_ok, false_useful, _false_detail = runner._run_self_generated_task(
            "st_runner_false", 0.0, None
        )
        stored_false = original_queue(storage_path=queue_path).get_by_id("st_runner_false")
        false_objective = original_objectives(storage_path=objective_path).get(objective_id)
        real_ok, _real_useful, _real_detail = runner._run_self_generated_task(
            "st_runner_real", 0.0, None
        )
    finally:
        queue_mod.SelfTaskQueue = original_queue
        objective_mod.ObjectiveStore = original_objectives
        capability_execution.execute_capability_kind = original_execute

    assert false_ok is False
    assert false_useful is False
    assert stored_false["verification_status"] == "partial"
    assert stored_false["execution_outcome"] != "succeeded"
    assert stored_false["last_outcome"] == "execution_partial_no_value"
    assert float(false_objective["progress"]) == 0.0
    assert false_objective.get("execution_completed") is not True

    assert real_ok is True
    stored_real = original_queue(storage_path=queue_path).get_by_id("st_runner_real")
    reloaded = original_objectives(storage_path=objective_path).get(objective_id)
    assert stored_real["verification_status"] == "verified"
    assert stored_real["execution_outcome"] == "succeeded"
    assert str(stored_real["last_outcome"]).startswith("execution_succeeded")
    assert reloaded["last_execution"]["verification_status"] == "verified"
    assert reloaded["last_execution"]["execution_outcome"] == "succeeded"
    assert reloaded["execution_completed"] is True
    assert float(reloaded["progress"]) == 0.12
