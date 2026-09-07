from datetime import datetime, timedelta, timezone

from elysia_collective_seed.autopilot.task_ledger import TaskLedger


def _task(task_id="ELY-TASK-1", status="queued"):
    return {"task_id": task_id, "title": "bounded test", "status": status, "attempt": 0}


def test_claim_prevents_second_worker(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ledger.put_task(_task())
    first = ledger.claim("ELY-TASK-1", "worker-a", 60, now)
    second = ledger.claim("ELY-TASK-1", "worker-b", 60, now + timedelta(seconds=1))
    assert first.claimed is True
    assert second.claimed is False
    assert second.reason == "active_lease"
    assert ledger.get("ELY-TASK-1")["attempt"] == 1
    ledger.close()


def test_independent_connections_observe_single_lease_owner(tmp_path):
    path = tmp_path / "ledger.db"
    first_ledger = TaskLedger(path)
    second_ledger = TaskLedger(path)
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    first_ledger.put_task(_task())
    first = first_ledger.claim("ELY-TASK-1", "worker-a", 60, now)
    second = second_ledger.claim("ELY-TASK-1", "worker-b", 60, now)
    assert first.claimed is True
    assert second.claimed is False
    assert second.reason == "active_lease"
    assert second_ledger.get("ELY-TASK-1")["claimed_by"] == "worker-a"
    assert second_ledger.get("ELY-TASK-1")["attempt"] == 1
    first_ledger.close()
    second_ledger.close()


def test_same_worker_renews_without_incrementing_attempt(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ledger.put_task(_task())
    ledger.claim("ELY-TASK-1", "worker-a", 60, now)
    renewed = ledger.claim("ELY-TASK-1", "worker-a", 120, now + timedelta(seconds=10))
    assert renewed.reason == "renewed"
    assert ledger.get("ELY-TASK-1")["attempt"] == 1
    ledger.close()


def test_same_worker_reacquires_expired_lease_as_new_attempt(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ledger.put_task(_task())
    ledger.claim("ELY-TASK-1", "worker-a", 10, now)
    reacquired = ledger.claim("ELY-TASK-1", "worker-a", 60, now + timedelta(seconds=11))
    assert reacquired.reason == "claimed"
    assert ledger.get("ELY-TASK-1")["attempt"] == 2
    ledger.close()


def test_expired_lease_can_be_reaped_and_reclaimed(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ledger.put_task(_task())
    ledger.claim("ELY-TASK-1", "worker-a", 10, now)
    assert ledger.reap_expired(now + timedelta(seconds=11)) == ["ELY-TASK-1"]
    claimed = ledger.claim("ELY-TASK-1", "worker-b", 60, now + timedelta(seconds=12))
    assert claimed.claimed is True
    assert ledger.get("ELY-TASK-1")["attempt"] == 2
    ledger.close()


def test_release_requires_current_owner(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ledger.put_task(_task())
    ledger.claim("ELY-TASK-1", "worker-a", 60, now)
    assert ledger.release("ELY-TASK-1", "worker-b", now=now) is False
    assert ledger.release("ELY-TASK-1", "worker-a", "queued", now) is True
    assert ledger.get("ELY-TASK-1")["claimed_by"] is None
    ledger.close()


def test_terminal_task_cannot_be_claimed(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    ledger.put_task(_task(status="completed"))
    result = ledger.claim("ELY-TASK-1", "worker-a")
    assert result.claimed is False
    assert result.reason == "terminal_task"
    ledger.close()


def test_stale_upsert_cannot_reopen_terminal_task(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    ledger.put_task(_task(status="completed"))
    ledger.put_task(_task(status="queued"))
    assert ledger.get("ELY-TASK-1")["status"] == "completed"
    assert ledger.claim("ELY-TASK-1", "worker-a").reason == "terminal_task"
    ledger.close()


def test_events_are_auditable(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ledger.put_task(_task())
    ledger.claim("ELY-TASK-1", "worker-a", 60, now)
    ledger.release("ELY-TASK-1", "worker-a", now=now)
    event_types = [event["event_type"] for event in ledger.events("ELY-TASK-1")]
    assert event_types == ["task_upserted", "task_claimed", "task_released"]
    ledger.close()
