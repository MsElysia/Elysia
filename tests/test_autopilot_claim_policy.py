"""Execution authority checks at the durable SQLite lease boundary."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.dryrun_orchestrator import dispatch_and_claim
from elysia_collective_seed.autopilot.task_ledger import TaskLedger
from tests.evidence_fixture import seed_legacy_execution_lease

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)
WORKER = Worker("worker", "test", frozenset({"implementation", "test"}),
                frozenset({"read_only", "repo_write", "sandbox_write", "deployment"}))


def task(**overrides):
    return dict(dict(task_id="task", status="queued", risk_class="repo_write",
                     task_class="implementation", required_capabilities=["test"],
                     max_attempts=3, dependencies=[]), **overrides)


def ledger_at(tmp_path, workers=(WORKER,)):
    return TaskLedger(tmp_path / "claims.db", execution_workers=workers)


@pytest.mark.parametrize("policy,reason", [
    ({"risk_class": "deployment"}, "authority_gate"),
    ({"risk_class": "external_write"}, "authority_gate"),
    ({"risk_class": "sensitive_data"}, "authority_gate"),
    ({"risk_class": "privileged"}, "authority_gate"),
    ({"human_approval_required": True}, "authority_gate"),
    ({"risk_class": None}, "unknown_risk_class"),
    ({"risk_class": "new_risk"}, "unknown_risk_class"),
    ({"dependencies": "dep"}, "invalid_execution_policy"),
    ({"dependencies": [None]}, "invalid_execution_policy"),
    ({"allowed_workers": {}}, "invalid_execution_policy"),
    ({"required_capabilities": [""]}, "invalid_execution_policy"),
    ({"human_approval_required": "false"}, "invalid_execution_policy"),
    ({"human_approval_required": 0}, "invalid_execution_policy"),
    ({"task_class": []}, "invalid_execution_policy"),
])
@pytest.mark.parametrize("stage", ["claim", "renew", "recover"])
def test_policy_denial_precedes_every_lease_success(tmp_path, policy, reason, stage):
    ledger = ledger_at(tmp_path)
    try:
        ledger.put_task(task(**policy))
        if stage != "claim":
            seed_legacy_execution_lease(ledger, "task", "worker", NOW)
        when = NOW + timedelta(minutes=16) if stage == "recover" else NOW
        before = ledger.get("task"), ledger.events("task")
        result = ledger.claim("task", "worker", now=when)
        assert not result.claimed and result.reason == reason
        assert (ledger.get("task"), ledger.events("task")) == before
    finally:
        ledger.close()


@pytest.mark.parametrize("worker,policy", [
    (None, {}),
    (replace(WORKER, available=False), {}),
    (replace(WORKER, risk_classes=frozenset({"read_only"})), {}),
    (replace(WORKER, capabilities=frozenset({"test"})), {}),
    (replace(WORKER, capabilities=frozenset({"implementation"})), {}),
    (WORKER, {"allowed_workers": ["someone_else"]}),
])
@pytest.mark.parametrize("reopen", [False, True])
def test_worker_configuration_cannot_be_omitted_or_forged(tmp_path, worker, policy, reopen):
    ledger = ledger_at(tmp_path, () if worker is None else (worker,))
    ledger.put_task(task(**policy))
    if reopen:
        ledger.close()
        ledger = ledger_at(tmp_path, () if worker is None else (worker,))
    try:
        assert not ledger.claim("task", "worker", now=NOW).claimed
        result = dispatch_and_claim(ledger, task(**policy), {}, [WORKER])
        assert result.state == "blocked"
        assert ledger.get("task")["attempt"] == 0
        assert not any(e["event_type"] == "task_claimed" for e in ledger.events("task"))
    finally:
        ledger.close()


@pytest.mark.parametrize("status", [None, "queued", "claimed", "running", "verifying", "review", "blocked", "human_review", "rejected", "archived"])
def test_dependencies_must_be_durably_completed(tmp_path, status):
    ledger = ledger_at(tmp_path)
    try:
        if status is not None:
            ledger.put_task(task(task_id="dep", status=status))
        ledger.put_task(task(dependencies=["dep"]))
        assert not ledger.claim("task", "worker", now=NOW).claimed
        forged = dispatch_and_claim(ledger, task(dependencies=["dep"]), {"dep": "completed"}, [WORKER])
        assert forged.reasons == ("dependencies_incomplete",)
        assert ledger.get("task")["attempt"] == 0
    finally:
        ledger.close()


def test_durable_completion_overrides_stale_bridge_state_and_nonpreferred_worker_is_eligible(tmp_path):
    second = replace(WORKER, worker_id="second", quality=0.1)
    ledger = ledger_at(tmp_path, (WORKER, second))
    try:
        ledger.put_task(task(task_id="dep", status="completed"))
        ledger.put_task(task(dependencies=["dep"]))
        assert ledger.claim("task", "second", now=NOW).claimed
        assert ledger.release("task", "second", now=NOW)
        result = dispatch_and_claim(ledger, task(dependencies=["dep"]), {"dep": "blocked"}, [])
        assert result.claim.claimed and result.worker_id == "worker"
    finally:
        ledger.close()


@pytest.mark.parametrize("mode", ["renew", "recover", "reap"])
def test_revoked_worker_and_dependency_rechecked_after_initial_claim(tmp_path, mode):
    ledger = ledger_at(tmp_path)
    try:
        ledger.put_task(task(task_id="dep", status="completed"))
        ledger.put_task(task(dependencies=["dep"]))
        assert ledger.claim("task", "worker", lease_seconds=5, now=NOW).claimed
        when = NOW + timedelta(seconds=6) if mode != "renew" else NOW
        if mode == "reap":
            assert ledger.reap_expired(when) == ["task"]
        ledger.execution_workers["worker"] = replace(WORKER, available=False)
        before = ledger.get("task")
        assert not ledger.claim("task", "worker", now=when).claimed
        assert ledger.get("task") == before
        ledger.execution_workers["worker"] = WORKER
        with ledger.conn:
            ledger.conn.execute("UPDATE tasks SET status='blocked' WHERE task_id='dep'")
        assert ledger.claim("task", "worker", now=when).reason == "dependencies_incomplete"
        assert ledger.get("task") == before
    finally:
        ledger.close()


def test_last_attempt_renewal_and_reopen_authority(tmp_path):
    ledger = ledger_at(tmp_path)
    ledger.put_task(task(max_attempts=1))
    assert ledger.claim("task", "worker", now=NOW).claimed
    ledger.close()
    ledger = ledger_at(tmp_path, ())
    try:
        assert not ledger.claim("task", "worker", now=NOW).claimed
        ledger.execution_workers["worker"] = WORKER
        assert ledger.claim("task", "worker", now=NOW).reason == "renewed"
        assert ledger.get("task")["attempt"] == 1
        assert not ledger.claim("task", "worker", now=NOW + timedelta(minutes=16)).claimed
        assert ledger.get("task")["status"] == "human_review"
    finally:
        ledger.close()


def test_legacy_missing_risk_and_self_dependency_fail_closed(tmp_path):
    ledger = ledger_at(tmp_path)
    try:
        missing = task(); del missing["risk_class"]
        ledger.put_task(missing)
        assert ledger.claim("task", "worker", now=NOW).reason == "unknown_risk_class"
        ledger.put_task(task(task_id="self", dependencies=["self"]))
        assert ledger.claim("self", "worker", now=NOW).reason == "dependencies_incomplete"
    finally:
        ledger.close()


def test_dependency_read_and_claim_hold_one_write_transaction(tmp_path):
    ledger = ledger_at(tmp_path)
    writer = sqlite3.connect(tmp_path / "claims.db", timeout=0)
    blocked = []
    try:
        ledger.put_task(task(task_id="dep", status="completed"))
        ledger.put_task(task(dependencies=["dep"]))
        def attempt_change(statement):
            if statement.startswith("SELECT status FROM tasks"):
                try:
                    writer.execute("UPDATE tasks SET status='blocked' WHERE task_id='dep'")
                    writer.commit()
                except sqlite3.OperationalError as error:
                    blocked.append(str(error))
                    writer.rollback()
        ledger.conn.set_trace_callback(attempt_change)
        assert ledger.claim("task", "worker", now=NOW).claimed
        assert blocked == ["database is locked"]
    finally:
        writer.close()
        ledger.close()
