"""Independent evidence required before a self-task is verified successful.

Synthetic files only. The former acceptance rule is copied here so the
adversarial case shows what the previous outcome check treated as success.
"""
import hashlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.self_task_execution_outcome import evaluate_execution_outcome
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
