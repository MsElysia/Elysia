# project_guardian/global_task_queue.py
# GlobalTaskQueue: Priority Heap-Based Task Queue
# Based on ElysiaLoop-Core Event Loop Design

import logging
import heapq
import uuid
from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from collections import defaultdict

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Represents a task in the queue."""
    task_id: str
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: int = 5  # 1-10, higher = more important
    module: str = "unknown"
    timeout: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """Comparison for priority queue (lower priority number = higher actual priority)."""
        # Invert because heapq is min-heap, but we want max priority first
        return self.priority > other.priority
    
    def __eq__(self, other):
        """Equality check."""
        return self.task_id == other.task_id


class GlobalTaskQueue:
    """
    Priority heap-based task queue with dependency resolution.
    Thread-safe task management for ElysiaLoopCore.
    """
    
    def __init__(self):
        # Priority queue (heapq uses min-heap, so we invert priorities)
        self._queue: List[Tuple[int, int, Task]] = []  # (priority, insertion_order, task)
        self._insertion_counter = 0
        self._lock = Lock()
        
        # Task registry (task_id -> Task)
        self._tasks: Dict[str, Task] = {}
        
        # Dependency tracking
        self._dependencies: Dict[str, List[str]] = {}  # task_id -> [dependent_task_ids]
        self._reverse_dependencies: Dict[str, List[str]] = {}  # task_id -> [task_ids_this_depends_on]
        
        # Status tracking
        self._status_counts: Dict[TaskStatus, int] = defaultdict(int)
    
    def submit_task(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        priority: int = 5,
        module: str = "unknown",
        timeout: Optional[float] = None,
        dependencies: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Submit a task to the queue.
        
        Args:
            func: Function/coroutine to execute
            args: Positional arguments
            kwargs: Keyword arguments
            priority: Priority (1-10, higher = more important)
            module: Module name
            timeout: Optional timeout in seconds
            dependencies: List of task IDs this task depends on
            task_id: Optional custom task ID
            metadata: Optional task metadata
            
        Returns:
            Task ID
        """
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # Clamp priority to 1-10
        priority = max(1, min(10, priority))
        
        task = Task(
            task_id=task_id,
            func=func,
            args=args or (),
            kwargs=kwargs or {},
            priority=priority,
            module=module,
            timeout=timeout,
            dependencies=dependencies or [],
            metadata=metadata or {}
        )
        
        with self._lock:
            self._tasks[task_id] = task
            
            # Track dependencies
            if task.dependencies:
                self._reverse_dependencies[task_id] = task.dependencies.copy()
                for dep_id in task.dependencies:
                    if dep_id not in self._dependencies:
                        self._dependencies[dep_id] = []
                    self._dependencies[dep_id].append(task_id)
            
            # Check if ready to queue (dependencies met)
            if self._check_dependencies(task):
                self._enqueue(task)
            else:
                task.status = TaskStatus.PENDING
                self._status_counts[TaskStatus.PENDING] += 1
            
            logger.debug(f"Submitted task {task_id} (priority: {priority}, module: {module})")
        
        return task_id
    
    def _check_dependencies(self, task: Task) -> bool:
        """Check if all dependencies for a task are completed."""
        if not task.dependencies:
            return True
        
        for dep_id in task.dependencies:
            dep_task = self._tasks.get(dep_id)
            if not dep_task:
                logger.warning(f"Dependency {dep_id} not found for task {task.task_id}")
                return False
            
            if dep_task.status != TaskStatus.COMPLETED:
                return False
        
        return True
    
    def _enqueue(self, task: Task):
        """Add a task to the priority queue."""
        # Use negative priority for min-heap (higher priority = lower number in heap)
        # Also use insertion counter as tiebreaker
        self._insertion_counter += 1
        heapq.heappush(self._queue, (-task.priority, self._insertion_counter, task))
        task.status = TaskStatus.QUEUED
        self._status_counts[TaskStatus.QUEUED] += 1
    
    def get_next_task(self) -> Optional[Task]:
        """
        Get the next task from the queue (highest priority first).
        
        Returns:
            Task or None if queue is empty
        """
        with self._lock:
            while self._queue:
                # Pop highest priority task
                _, _, task = heapq.heappop(self._queue)
                
                # Check dependencies again (in case status changed)
                if not self._check_dependencies(task):
                    # Dependencies not met, skip for now
                    continue
                
                # Update status
                old_status = task.status
                task.status = TaskStatus.RUNNING
                self._status_counts[old_status] -= 1
                self._status_counts[TaskStatus.RUNNING] += 1
                
                return task
            
            return None
    
    def requeue_task(self, task: Task):
        """Requeue a task (e.g., after temporary failure)."""
        with self._lock:
            if task.status == TaskStatus.RUNNING:
                self._status_counts[TaskStatus.RUNNING] -= 1
            
            self._enqueue(task)
    
    def mark_completed(self, task_id: str):
        """Mark a task as completed."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found")
                return
            
            old_status = task.status
            task.status = TaskStatus.COMPLETED
            self._status_counts[old_status] -= 1
            self._status_counts[TaskStatus.COMPLETED] += 1
            
            # Check dependent tasks
            if task_id in self._dependencies:
                for dependent_id in self._dependencies[task_id]:
                    dependent = self._tasks.get(dependent_id)
                    if dependent and dependent.status == TaskStatus.PENDING:
                        if self._check_dependencies(dependent):
                            self._status_counts[TaskStatus.PENDING] -= 1
                            self._enqueue(dependent)
            
            logger.debug(f"Task {task_id} marked as completed")
    
    def mark_failed(self, task_id: str):
        """Mark a task as failed."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            
            old_status = task.status
            task.status = TaskStatus.FAILED
            self._status_counts[old_status] -= 1
            self._status_counts[TaskStatus.FAILED] += 1
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending or queued task.
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            True if cancelled, False if not found or already running
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            if task.status == TaskStatus.RUNNING:
                logger.warning(f"Cannot cancel running task {task_id}")
                return False
            
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                return False
            
            old_status = task.status
            task.status = TaskStatus.CANCELLED
            self._status_counts[old_status] -= 1
            self._status_counts[TaskStatus.CANCELLED] += 1
            
            # Remove from queue if present
            self._queue = [
                item for item in self._queue
                if item[2].task_id != task_id
            ]
            heapq.heapify(self._queue)
            
            logger.info(f"Task {task_id} cancelled")
            return True
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        with self._lock:
            return len(self._queue)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get queue statistics."""
        with self._lock:
            return {
                "queue_size": len(self._queue),
                "total_tasks": len(self._tasks),
                "status_counts": {
                    status.value: count
                    for status, count in self._status_counts.items()
                },
                "pending_dependencies": len([
                    t for t in self._tasks.values()
                    if t.status == TaskStatus.PENDING and t.dependencies
                ])
            }
    
    def clear_completed(self, older_than_hours: int = 24):
        """
        Clear completed tasks older than specified time.
        
        Args:
            older_than_hours: Remove tasks completed more than this many hours ago
        """
        cutoff = datetime.now().timestamp() - (older_than_hours * 3600)
        
        with self._lock:
            to_remove = []
            for task_id, task in self._tasks.items():
                if task.status == TaskStatus.COMPLETED:
                    # Check if old enough (using created_at as proxy)
                    if task.created_at.timestamp() < cutoff:
                        to_remove.append(task_id)
            
            for task_id in to_remove:
                task = self._tasks[task_id]
                self._status_counts[TaskStatus.COMPLETED] -= 1
                del self._tasks[task_id]
                
                # Clean up dependencies
                if task_id in self._dependencies:
                    del self._dependencies[task_id]
                if task_id in self._reverse_dependencies:
                    del self._reverse_dependencies[task_id]
            
            logger.info(f"Cleared {len(to_remove)} completed tasks")
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        module: Optional[str] = None,
        limit: int = 100
    ) -> List[Task]:
        """List tasks, optionally filtered."""
        with self._lock:
            tasks = list(self._tasks.values())
            
            if status:
                tasks = [t for t in tasks if t.status == status]
            
            if module:
                tasks = [t for t in tasks if t.module == module]
            
            # Sort by priority (descending) and creation time
            tasks.sort(key=lambda t: (-t.priority, t.created_at))
            
            return tasks[:limit]


# Example usage
if __name__ == "__main__":
    queue = GlobalTaskQueue()
    
    # Submit some tasks
    def task1():
        return "Task 1 complete"
    
    def task2():
        return "Task 2 complete"
    
    task_id1 = queue.submit_task(task1, priority=8, module="test")
    task_id2 = queue.submit_task(task2, priority=5, module="test", dependencies=[task_id1])
    
    # Get next task
    next_task = queue.get_next_task()
    if next_task:
        print(f"Next task: {next_task.task_id} (priority: {next_task.priority})")
        queue.mark_completed(next_task.task_id)
    
    # Get statistics
    stats = queue.get_statistics()
    print(f"Statistics: {stats}")

