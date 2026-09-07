from elysia_collective_seed.autopilot.completion_validator import validate_completion


def packet(**overrides):
    value = {
        "task_id": "ELY-TASK-42",
        "worker": {"provider": "dryrun", "role": "engineer"},
        "outcome": "completed",
        "summary": "bounded work completed",
        "checks": [{"name": "unit", "result": "pass"}],
        "next_recommendation": {"action": "verify"},
    }
    value.update(overrides)
    return value


def test_valid_completion_with_required_check():
    result = validate_completion(packet(), expected_task_id="ELY-TASK-42", required_checks=("unit",))
    assert result.valid
    assert result.reasons == ()


def test_rejects_task_identity_mismatch():
    result = validate_completion(packet(), expected_task_id="ELY-TASK-99")
    assert not result.valid
    assert "task_id_mismatch" in result.reasons


def test_rejects_missing_required_check():
    result = validate_completion(packet(), required_checks=("unit", "safety"))
    assert not result.valid
    assert "missing_required_check:safety" in result.reasons


def test_rejects_nonpassing_required_check():
    result = validate_completion(
        packet(checks=[{"name": "unit", "result": "skip"}]),
        required_checks=("unit",),
    )
    assert not result.valid
    assert "required_check_not_passed:unit:skip" in result.reasons


def test_completed_cannot_contain_failed_check():
    result = validate_completion(packet(checks=[{"name": "unit", "result": "fail"}]))
    assert not result.valid
    assert "completed_with_failed_check" in result.reasons


def test_rejects_duplicate_check_names():
    result = validate_completion(packet(checks=[
        {"name": "unit", "result": "pass"},
        {"name": "unit", "result": "pass"},
    ]))
    assert not result.valid
    assert "duplicate_check:unit" in result.reasons


def test_partial_outcome_may_report_failed_check():
    result = validate_completion(
        packet(outcome="partial", checks=[{"name": "unit", "result": "fail"}])
    )
    assert result.valid
