from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path

from project_guardian.longterm_planner import (
    LongTermPlanner,
    ObjectiveStatus,
    TaskStatus,
)


class _RuntimeStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class _FakeRuntimeLoop:
    def __init__(self) -> None:
        self._statuses = {}
        self._submitted = 0

    def submit_task(self, func, priority=5, module="unknown", dependencies=None, deadline=None):  # noqa: ANN001
        self._submitted += 1
        runtime_task_id = f"rt-{self._submitted}"
        self._statuses[runtime_task_id] = _RuntimeStatus.IN_PROGRESS
        return runtime_task_id

    def get_task_status(self, task_id: str):
        return self._statuses.get(task_id)


def _build_planner(tmp_path: Path) -> LongTermPlanner:
    planner = LongTermPlanner(runtime_loop=_FakeRuntimeLoop(), storage_path=str(tmp_path / "planner_state.json"))
    planner.objectives = {}
    planner.planned_tasks = {}
    planner.save()
    return planner


def test_runtime_sync_marks_objective_completed(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    objective_id = planner.add_objective(
        name="Runtime sync objective",
        description="Break this down. Then complete it.",
        priority=6,
    )
    created_ids = asyncio.run(planner.breakdown_objective(objective_id, strategy="hierarchical"))
    submitted = planner.submit_tasks_to_runtime(objective_id=objective_id)

    assert set(submitted.keys()) == set(created_ids)
    for task_id in created_ids:
        planned = planner.planned_tasks[task_id]
        assert planned.status == TaskStatus.IN_PROGRESS
        assert planned.metadata.get("runtime_task_id")

    fake_runtime = planner.runtime_loop
    for runtime_task_id in submitted.values():
        fake_runtime._statuses[runtime_task_id] = _RuntimeStatus.COMPLETED

    active = planner.list_active_objectives()
    assert all(obj.objective_id != objective_id for obj in active)
    assert planner.objectives[objective_id].status == ObjectiveStatus.COMPLETED

    progress = planner.get_objective_progress(objective_id)
    assert progress["completed_tasks"] == progress["total_tasks"]
    assert progress["status"] == ObjectiveStatus.COMPLETED.value


def test_runtime_sync_maps_failed_runtime_task_to_blocked(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    objective_id = planner.add_objective(
        name="Failure sync objective",
        description="Only one step",
        priority=5,
    )
    created_ids = asyncio.run(planner.breakdown_objective(objective_id, strategy="hierarchical"))
    submitted = planner.submit_tasks_to_runtime(objective_id=objective_id)
    task_id = created_ids[0]
    runtime_task_id = submitted[task_id]

    fake_runtime = planner.runtime_loop
    fake_runtime._statuses[runtime_task_id] = _RuntimeStatus.FAILED

    progress = planner.get_objective_progress(objective_id)
    assert planner.planned_tasks[task_id].status == TaskStatus.BLOCKED
    assert planner.objectives[objective_id].status == ObjectiveStatus.ACTIVE
    assert progress["task_statuses"]["blocked"] == 1


def test_submit_tasks_recovers_orphaned_in_progress_task(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    objective_id = planner.add_objective(
        name="Recovered objective",
        description="Break this down once.",
        priority=7,
    )
    created_ids = asyncio.run(planner.breakdown_objective(objective_id, strategy="hierarchical"))
    task_id = created_ids[0]
    planner.planned_tasks[task_id].status = TaskStatus.IN_PROGRESS
    planner.planned_tasks[task_id].metadata = {}
    planner.save()

    submitted = planner.submit_tasks_to_runtime(objective_id=objective_id)

    assert task_id in submitted
    planned = planner.planned_tasks[task_id]
    assert planned.status == TaskStatus.IN_PROGRESS
    assert planned.metadata.get("runtime_task_id") == submitted[task_id]
    assert planned.metadata.get("runtime_recovery_reason") == "missing_runtime_binding"


def test_submit_tasks_does_not_resubmit_live_runtime_bound_pending_task(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    objective_id = planner.add_objective(
        name="Live runtime binding objective",
        description="Only one step",
        priority=6,
    )
    created_ids = asyncio.run(planner.breakdown_objective(objective_id, strategy="hierarchical"))
    task_id = created_ids[0]
    submitted = planner.submit_tasks_to_runtime(objective_id=objective_id)
    runtime_task_id = submitted[task_id]

    fake_runtime = planner.runtime_loop
    fake_runtime._statuses[runtime_task_id] = _RuntimeStatus.PENDING
    planned = planner.planned_tasks[task_id]
    planned.status = TaskStatus.PENDING
    planner.save()

    resubmitted = planner.submit_tasks_to_runtime(objective_id=objective_id)

    assert resubmitted == {}
    assert fake_runtime._submitted == 1
    assert planned.status == TaskStatus.IN_PROGRESS
    assert planned.metadata.get("runtime_task_id") == runtime_task_id
    assert planned.metadata.get("runtime_last_status") == TaskStatus.IN_PROGRESS.value


def test_submit_tasks_recovers_stale_pending_binding_when_runtime_task_missing(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    objective_id = planner.add_objective(
        name="Missing runtime binding objective",
        description="Only one step",
        priority=6,
    )
    created_ids = asyncio.run(planner.breakdown_objective(objective_id, strategy="hierarchical"))
    task_id = created_ids[0]
    submitted = planner.submit_tasks_to_runtime(objective_id=objective_id)
    runtime_task_id = submitted[task_id]

    fake_runtime = planner.runtime_loop
    fake_runtime._statuses.pop(runtime_task_id, None)
    planned = planner.planned_tasks[task_id]
    planned.status = TaskStatus.PENDING
    planner.save()

    resubmitted = planner.submit_tasks_to_runtime(objective_id=objective_id)

    assert task_id in resubmitted
    assert fake_runtime._submitted == 2
    assert resubmitted[task_id] != runtime_task_id
    assert planned.status == TaskStatus.IN_PROGRESS
    assert planned.metadata.get("previous_runtime_task_id") == runtime_task_id
    assert planned.metadata.get("runtime_recovery_reason") == "runtime_task_missing"


def test_pick_next_actionable_objective_prefers_pending_work_over_breakdown_only(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    breakdown_only_id = planner.add_objective(
        name="Higher priority empty objective",
        description="No tasks yet.",
        priority=9,
    )
    pending_id = planner.add_objective(
        name="Submit ready objective",
        description="One step only",
        priority=5,
    )
    created_ids = asyncio.run(planner.breakdown_objective(pending_id, strategy="hierarchical"))
    task_id = created_ids[0]
    planner.planned_tasks[task_id].status = TaskStatus.IN_PROGRESS
    planner.planned_tasks[task_id].metadata = {}
    planner.save()

    picked = planner.pick_next_actionable_objective()

    assert picked is not None
    assert picked.objective_id == pending_id
    summary = planner.get_objective_actionability(pending_id)
    assert summary["pending_tasks"] == 1
    assert summary["needs_breakdown"] is False
    assert planner.get_objective(pending_id) is not None
    assert planner.get_objective(breakdown_only_id) is not None


def test_load_prunes_smoke_objectives_when_real_objectives_exist(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    real_id = planner.add_objective(
        name="Real objective",
        description="Keep me active.",
        priority=8,
    )
    smoke_ids = [
        planner.add_objective(
            name="SmokeObjective",
            description="Build something small to verify planner.",
            priority=5,
        )
        for _ in range(3)
    ]

    reloaded = LongTermPlanner(runtime_loop=_FakeRuntimeLoop(), storage_path=str(tmp_path / "planner_state.json"))

    assert reloaded.objectives[real_id].status == ObjectiveStatus.ACTIVE
    assert all(reloaded.objectives[obj_id].status == ObjectiveStatus.CANCELLED for obj_id in smoke_ids)
    assert all(
        reloaded.objectives[obj_id].metadata.get("cleanup_reason") == "smoke_test_objective_pruned"
        for obj_id in smoke_ids
    )


def test_load_keeps_latest_smoke_objective_when_no_real_objectives_exist(tmp_path: Path) -> None:
    planner = _build_planner(tmp_path)
    smoke_ids = [
        planner.add_objective(
            name="SmokeObjective",
            description="Build something small to verify planner.",
            priority=5,
        )
        for _ in range(3)
    ]

    reloaded = LongTermPlanner(runtime_loop=_FakeRuntimeLoop(), storage_path=str(tmp_path / "planner_state.json"))

    active_smoke = [
        obj.objective_id
        for obj in reloaded.objectives.values()
        if obj.status == ObjectiveStatus.ACTIVE and obj.name == "SmokeObjective"
    ]
    cancelled_smoke = [
        obj.objective_id
        for obj in reloaded.objectives.values()
        if obj.status == ObjectiveStatus.CANCELLED and obj.name == "SmokeObjective"
    ]

    assert len(active_smoke) == 1
    assert len(cancelled_smoke) == 2
    assert set(active_smoke + cancelled_smoke) == set(smoke_ids)
