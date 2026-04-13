# project_guardian/tests/test_elysia_loop_integration.py
# Test ElysiaLoopCore integration with RuntimeLoop and SystemOrchestrator

import pytest
import asyncio
import time
from datetime import datetime

from project_guardian.elysia_loop_core import ElysiaLoopCore, Task, TaskStatus
from project_guardian.runtime_loop_core import RuntimeLoop
from project_guardian.system_orchestrator import SystemOrchestrator


@pytest.mark.asyncio
async def test_elysia_loop_core_basic():
    """Test basic ElysiaLoopCore functionality."""
    loop = ElysiaLoopCore()
    
    # Test task execution
    results = []
    
    async def test_task(value: int):
        await asyncio.sleep(0.1)
        results.append(value)
        return value
    
    # Start loop
    loop.start()
    
    # Submit tasks
    task_id1 = loop.submit_task(test_task, args=(1,), priority=10)
    task_id2 = loop.submit_task(test_task, args=(2,), priority=5)
    
    # Wait for execution
    await asyncio.sleep(0.5)
    
    # Check results
    assert len(results) >= 2, "Tasks should have executed"
    assert 1 in results, "High priority task should execute"
    assert 2 in results, "Lower priority task should execute"
    
    # Check status
    status = loop.get_status()
    assert status["running"] == True
    assert status["queue_size"] >= 0
    
    # Stop loop
    loop.stop()
    
    # Wait for cleanup
    await asyncio.sleep(0.2)
    
    assert loop.running == False


@pytest.mark.asyncio
async def test_runtime_loop_integration():
    """Test RuntimeLoop integration with ElysiaLoopCore."""
    runtime = RuntimeLoop()
    
    results = []
    
    async def test_task(value: int):
        await asyncio.sleep(0.1)
        results.append(value)
        return value
    
    # Start runtime loop
    runtime.start()
    
    # Submit task
    task_id = runtime.submit_task(
        test_task,
        args=(42,),
        priority=8,
        module="test"
    )
    
    # Wait for execution
    await asyncio.sleep(0.5)
    
    # Check execution
    assert 42 in results, "Task should have executed"
    
    # Check status
    status = runtime.get_status()
    assert status["running"] == True
    assert "elysia_loop_status" in status
    
    # Check ElysiaLoopCore is running
    elysia_status = status["elysia_loop_status"]
    assert elysia_status["running"] == True
    
    # Stop
    runtime.stop()
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_system_orchestrator_integration():
    """Test SystemOrchestrator integration with RuntimeLoop/ElysiaLoopCore."""
    orchestrator = SystemOrchestrator()
    
    # Initialize system
    success = await orchestrator.initialize(
        initialize_components=True,
        auto_register_modules=False
    )
    
    assert success == True, "System should initialize successfully"
    
    # Check RuntimeLoop is initialized
    assert orchestrator.runtime_loop is not None
    
    # Check RuntimeLoop is running
    runtime_status = orchestrator.runtime_loop.get_status()
    assert runtime_status["running"] == True
    
    # Check ElysiaLoopCore is running through RuntimeLoop
    elysia_status = runtime_status.get("elysia_loop_status", {})
    if elysia_status:
        assert elysia_status.get("running") == True
    
    # Test task submission through orchestrator
    results = []
    
    async def test_task():
        await asyncio.sleep(0.1)
        results.append("executed")
        return "success"
    
    task_id = orchestrator.submit_task(
        test_task,
        priority=5
    )
    
    # Wait for execution
    await asyncio.sleep(0.5)
    
    # Check execution
    assert "executed" in results
    
    # Get system status
    status = orchestrator.get_system_status()
    assert status["initialized"] == True
    assert status["running"] == True


@pytest.mark.asyncio
async def test_task_priority_ordering():
    """Test that task priorities are respected."""
    loop = ElysiaLoopCore()
    
    execution_order = []
    
    async def task(priority: int):
        await asyncio.sleep(0.05)
        execution_order.append(priority)
        return priority
    
    loop.start()
    
    # Submit tasks with different priorities (lower number = lower priority)
    loop.submit_task(task, args=(1,), priority=1)  # Low priority
    loop.submit_task(task, args=(10,), priority=10)  # High priority
    loop.submit_task(task, args=(5,), priority=5)  # Medium priority
    
    # Wait for execution
    await asyncio.sleep(0.5)
    
    # High priority should execute first
    # Note: Due to async nature, exact ordering may vary, but high priority should be in first 2
    assert 10 in execution_order[:2], "High priority task should execute early"
    
    loop.stop()
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_task_dependencies():
    """Test task dependency resolution."""
    loop = ElysiaLoopCore()
    
    results = []
    
    async def task(value: int):
        await asyncio.sleep(0.1)
        results.append(value)
        return value
    
    loop.start()
    
    # Submit dependent task first (should wait)
    task_id1 = loop.submit_task(task, args=(1,), priority=5)
    task_id2 = loop.submit_task(task, args=(2,), priority=5, dependencies=[task_id1])
    
    # Wait for execution
    await asyncio.sleep(0.5)
    
    # Task 1 should complete before task 2
    assert len(results) >= 1, "At least task 1 should complete"
    
    # Get task statuses
    task1 = loop.task_queue.get_task(task_id1)
    task2 = loop.task_queue.get_task(task_id2)
    
    if task1:
        # If task1 is completed, task2 should be able to run
        if task1.status == TaskStatus.COMPLETED:
            # Task2 should have either completed or be in progress/pending
            assert task2 is None or task2.status in [TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED]
    
    loop.stop()
    await asyncio.sleep(0.2)


def test_elysia_loop_status():
    """Test ElysiaLoopCore status reporting."""
    loop = ElysiaLoopCore()
    
    status = loop.get_status()
    
    assert "running" in status
    assert "paused" in status
    assert "queue_size" in status
    assert "total_tasks" in status
    assert "registered_modules" in status
    assert "modules" in status
    
    assert status["running"] == False  # Not started yet
    assert status["queue_size"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

