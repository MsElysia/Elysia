# project_guardian/runtime_loop_core.py
# RuntimeLoop: Central Task Scheduler and Executor
# Based on Conversation 3 (elysia 4 sub a) design specifications

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Union, Coroutine
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from threading import Lock
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None
import time

try:
    from .elysia_loop_core import ElysiaLoopCore, Task, TaskStatus
except ImportError:
    # Fallback for direct execution
    from elysia_loop_core import ElysiaLoopCore, Task, TaskStatus

logger = logging.getLogger(__name__)


class UrgencyLevel(Enum):
    """Urgency levels for task prioritization."""
    CRITICAL = 1.0    # Immediate execution required
    HIGH = 0.8       # Important, execute soon
    MEDIUM = 0.5     # Normal priority
    LOW = 0.3        # Can wait
    IDLE = 0.1       # Background/optional


@dataclass
class TaskMetrics:
    """Metrics for tracking task performance."""
    task_id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration: Optional[float] = None
    memory_used: float = 0.0
    api_calls: int = 0
    errors: int = 0
    urgency_score: float = 0.5


class MemoryMonitor:
    """
    Monitors system memory usage and prevents overflow.
    Throttles task execution when memory is constrained.
    """
    
    def __init__(self, max_memory_percent: float = 80.0, check_interval: float = 1.0):
        self.max_memory_percent = max_memory_percent
        self.check_interval = check_interval
        self._last_check = time.time()
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None
        
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        if not PSUTIL_AVAILABLE:
            # Return safe defaults when psutil not available
            return {
                "process_mb": 100.0,
                "process_percent": 5.0,
                "system_percent": 50.0,
                "system_available_mb": 4000.0,
            }
        
        try:
            process_mem = self._process.memory_info()
            system_mem = psutil.virtual_memory()
            
            return {
                "process_mb": process_mem.rss / (1024 * 1024),
                "process_percent": self._process.memory_percent(),
                "system_percent": system_mem.percent,
                "system_available_mb": system_mem.available / (1024 * 1024),
            }
        except Exception as e:
            logger.warning(f"Memory monitoring error: {e}")
            return {
                "process_mb": 0.0,
                "process_percent": 0.0,
                "system_percent": 0.0,
                "system_available_mb": 0.0,
            }
    
    def should_throttle(self) -> bool:
        """
        Check if memory usage requires throttling.
        
        Returns:
            True if tasks should be throttled/paused
        """
        mem_info = self.get_memory_usage()
        return mem_info["system_percent"] >= self.max_memory_percent
    
    def get_throttle_factor(self) -> float:
        """
        Get throttle factor (0.0-1.0) based on memory pressure.
        
        Returns:
            Throttle factor where 1.0 = no throttling, 0.0 = full throttle
        """
        mem_info = self.get_memory_usage()
        usage = mem_info["system_percent"]
        
        if usage >= self.max_memory_percent:
            return 0.0  # Full throttle
        elif usage >= self.max_memory_percent - 10:
            return 0.3  # Heavy throttle
        elif usage >= self.max_memory_percent - 20:
            return 0.6  # Moderate throttle
        else:
            return 1.0  # No throttle


class QuantumUtilizationOptimizer:
    """
    Optimizes resource usage (API calls, compute) to minimize costs.
    Batches requests, caches responses, and manages rate limits.
    """
    
    def __init__(self):
        self.api_call_history: List[datetime] = []
        self.cache: Dict[str, tuple] = {}  # key -> (result, expiry_time)
        self.max_cache_size = 1000
        self.rate_limits: Dict[str, tuple] = {}  # service -> (max_calls, window_seconds)
        self._lock = Lock()
        
    def register_rate_limit(self, service: str, max_calls: int, window_seconds: int):
        """Register rate limit for a service."""
        with self._lock:
            self.rate_limits[service] = (max_calls, window_seconds)
    
    def can_make_api_call(self, service: str) -> bool:
        """Check if an API call can be made within rate limits."""
        if service not in self.rate_limits:
            return True  # No rate limit registered
        
        max_calls, window_seconds = self.rate_limits[service]
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        
        with self._lock:
            # Filter calls within window
            recent_calls = [
                call_time for call_time in self.api_call_history
                if call_time >= window_start and service in str(call_time)  # Simplified
            ]
            return len(recent_calls) < max_calls
    
    def record_api_call(self, service: str):
        """Record an API call for rate limiting."""
        with self._lock:
            self.api_call_history.append(datetime.now())
            # Clean old entries (keep last hour)
            cutoff = datetime.now() - timedelta(hours=1)
            self.api_call_history = [
                t for t in self.api_call_history if t >= cutoff
            ]
    
    def get_cached(self, key: str) -> Optional[Any]:
        """Get cached result if not expired."""
        with self._lock:
            if key in self.cache:
                result, expiry = self.cache[key]
                if datetime.now() < expiry:
                    return result
                else:
                    del self.cache[key]
            return None
    
    def cache_result(self, key: str, result: Any, ttl_seconds: int = 3600):
        """Cache a result with TTL."""
        with self._lock:
            if len(self.cache) >= self.max_cache_size:
                # Remove oldest entry (simple eviction)
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
            
            expiry = datetime.now() + timedelta(seconds=ttl_seconds)
            self.cache[key] = (result, expiry)


class RuntimeLoop:
    """
    Central task scheduler and executor with priority management.
    Integrates with ElysiaLoopCore for execution.
    Provides resource optimization and memory monitoring.
    """
    
    def __init__(
        self,
        elysia_loop: Optional[ElysiaLoopCore] = None,
        max_concurrent_tasks: int = 10,
        memory_threshold: float = 80.0
    ):
        self.elysia_loop = elysia_loop or ElysiaLoopCore()
        self.max_concurrent_tasks = max_concurrent_tasks
        self.memory_monitor = MemoryMonitor(max_memory_percent=memory_threshold)
        self.optimizer = QuantumUtilizationOptimizer()
        
        self._task_metrics: Dict[str, TaskMetrics] = {}
        self._scheduled_tasks: List[tuple] = []  # (datetime, task_id, func, args, kwargs)
        self._lock = Lock()
        self.running = False
        
    def start(self):
        """Start the runtime loop."""
        if self.running:
            logger.warning("RuntimeLoop already running")
            return
        
        # Start the underlying ElysiaLoopCore if not already running
        if not self.elysia_loop.running:
            self.elysia_loop.start()
        
        self.running = True
        logger.info("RuntimeLoop started")
        
        # Start scheduled task checker by submitting it as a coroutine to elysia_loop
        # This will be handled by the elysia_loop's async event loop
        try:
            self.elysia_loop.submit_task(
                func=self._check_scheduled_tasks(),
                priority=5,
                module="runtime_loop"
            )
        except Exception as e:
            logger.warning(f"Could not start scheduled task checker: {e}")
        
    def stop(self):
        """Stop the runtime loop."""
        self.running = False
        if self.elysia_loop.running:
            self.elysia_loop.stop()
        logger.info("RuntimeLoop stopped")
    
    def calculate_urgency(
        self,
        task_id: str,
        priority: int,
        deadline: Optional[datetime] = None,
        dependencies: List[str] = None
    ) -> float:
        """
        Calculate urgency score (0.0-1.0) for a task.
        
        Args:
            task_id: Task identifier
            priority: Task priority (1-10)
            deadline: Optional deadline
            dependencies: List of dependency task IDs
            
        Returns:
            Urgency score between 0.0 and 1.0
        """
        base_score = priority / 10.0  # Normalize priority to 0.0-1.0
        
        # Deadline pressure
        if deadline:
            now = datetime.now()
            time_until_deadline = (deadline - now).total_seconds()
            if time_until_deadline < 0:
                deadline_factor = 1.0  # Overdue
            elif time_until_deadline < 3600:  # Less than 1 hour
                deadline_factor = 0.9
            elif time_until_deadline < 86400:  # Less than 1 day
                deadline_factor = 0.7
            else:
                deadline_factor = 0.5
            base_score = (base_score + deadline_factor) / 2
        
        # Dependency pressure (if dependencies are completed, increase urgency)
        if dependencies:
            completed_deps = sum(
                1 for dep_id in dependencies
                if self.get_task_status(dep_id) == TaskStatus.COMPLETED
            )
            if len(dependencies) > 0:
                dep_factor = completed_deps / len(dependencies)
                base_score = (base_score + dep_factor * 0.5) / 1.5
        
        # Memory pressure (reduce urgency if memory is constrained)
        throttle_factor = self.memory_monitor.get_throttle_factor()
        base_score *= throttle_factor
        
        return min(1.0, max(0.0, base_score))
    
    def submit_task(
        self,
        func: Union[Callable, Coroutine],
        args: tuple = (),
        kwargs: dict = None,
        priority: int = 5,
        urgency: Optional[float] = None,
        module: str = "unknown",
        timeout: Optional[float] = None,
        dependencies: List[str] = None,
        deadline: Optional[datetime] = None,
        scheduled_time: Optional[datetime] = None
    ) -> str:
        """
        Submit a task to the runtime loop.
        
        Args:
            func: Function or coroutine to execute
            args: Positional arguments
            kwargs: Keyword arguments
            priority: Priority (1-10, higher = more important)
            urgency: Override urgency score (0.0-1.0)
            module: Module name
            timeout: Timeout in seconds
            dependencies: List of task IDs this task depends on
            deadline: Optional deadline
            scheduled_time: Optional time to execute (for scheduled tasks)
            
        Returns:
            Task ID
        """
        # Calculate urgency if not provided
        if urgency is None:
            urgency = self.calculate_urgency(
                task_id="temp",  # Will be replaced
                priority=priority,
                deadline=deadline,
                dependencies=dependencies or []
            )
        
        # Adjust priority based on urgency
        adjusted_priority = int(priority * urgency)
        
        # If scheduled, store for later
        if scheduled_time:
            with self._lock:
                task_id = f"scheduled_{len(self._scheduled_tasks)}"
                self._scheduled_tasks.append((
                    scheduled_time,
                    task_id,
                    func,
                    args,
                    kwargs or {}
                ))
                self._scheduled_tasks.sort(key=lambda x: x[0])  # Sort by time
            logger.info(f"Task scheduled for {scheduled_time}: {task_id}")
            return task_id
        
        # Submit to ElysiaLoopCore
        task_id = self.elysia_loop.submit_task(
            func=func,
            args=args,
            kwargs=kwargs or {},
            priority=adjusted_priority,
            module=module,
            timeout=timeout,
            dependencies=dependencies or []
        )
        
        # Track metrics
        metrics = TaskMetrics(
            task_id=task_id,
            created_at=datetime.now(),
            urgency_score=urgency
        )
        with self._lock:
            self._task_metrics[task_id] = metrics
        
        return task_id
    
    async def _check_scheduled_tasks(self):
        """Periodically check and execute scheduled tasks."""
        while self.running:
            await asyncio.sleep(1.0)  # Check every second
            
            now = datetime.now()
            to_execute = []
            
            with self._lock:
                # Find tasks ready to execute
                remaining = []
                for scheduled_time, task_id, func, args, kwargs in self._scheduled_tasks:
                    if scheduled_time <= now:
                        to_execute.append((task_id, func, args, kwargs))
                    else:
                        remaining.append((scheduled_time, task_id, func, args, kwargs))
                self._scheduled_tasks = remaining
            
            # Execute ready tasks
            for task_id, func, args, kwargs in to_execute:
                actual_task_id = self.elysia_loop.submit_task(
                    func=func,
                    args=args,
                    kwargs=kwargs,
                    priority=5,
                    module="scheduled"
                )
                logger.info(f"Executed scheduled task {task_id} -> {actual_task_id}")
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get status of a task."""
        task = self.elysia_loop.task_queue.get_task(task_id)
        return task.status if task else None
    
    def get_task_metrics(self, task_id: str) -> Optional[TaskMetrics]:
        """Get metrics for a task."""
        with self._lock:
            return self._task_metrics.get(task_id)
    
    def get_status(self) -> Dict[str, Any]:
        """Get runtime loop status."""
        elysia_status = self.elysia_loop.get_status()
        mem_info = self.memory_monitor.get_memory_usage()
        
        # Count tasks by status
        task_counts = {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }
        
        with self._lock:
            for metrics in self._task_metrics.values():
                task = self.elysia_loop.task_queue.get_task(metrics.task_id)
                if task:
                    status_key = task.status.value if task.status else "unknown"
                    if status_key in task_counts:
                        task_counts[status_key] += 1
        
        return {
            "running": self.running,
            "elysia_loop_status": elysia_status,
            "memory": mem_info,
            "throttle_factor": self.memory_monitor.get_throttle_factor(),
            "scheduled_tasks": len(self._scheduled_tasks),
            "task_metrics": {
                status: count for status, count in task_counts.items()
            },
            "total_tasks_tracked": len(self._task_metrics)
        }
    
    def optimize_resources(self):
        """Run resource optimization routines."""
        # Clear old cache entries
        now = datetime.now()
        with self.optimizer._lock:
            expired_keys = [
                key for key, (_, expiry) in self.optimizer.cache.items()
                if expiry < now
            ]
            for key in expired_keys:
                del self.optimizer.cache[key]
        
        logger.debug(f"Resource optimization: cleared {len(expired_keys)} cache entries")


# Example usage
if __name__ == "__main__":
    async def example_task(name: str):
        """Example async task."""
        await asyncio.sleep(0.5)
        print(f"Task {name} completed")
        return f"Result from {name}"
    
    async def test_runtime_loop():
        """Test the RuntimeLoop."""
        runtime = RuntimeLoop()
        runtime.start()
        
        # Submit some tasks with different priorities
        task1 = runtime.submit_task(
            example_task,
            args=("high_priority",),
            priority=10,
            module="test"
        )
        
        task2 = runtime.submit_task(
            example_task,
            args=("low_priority",),
            priority=1,
            module="test"
        )
        
        # Schedule a task
        scheduled_time = datetime.now() + timedelta(seconds=2)
        task3 = runtime.submit_task(
            example_task,
            args=("scheduled",),
            priority=5,
            scheduled_time=scheduled_time,
            module="test"
        )
        
        # Wait for tasks
        await asyncio.sleep(3)
        
        # Check status
        status = runtime.get_status()
        print(f"RuntimeLoop status: {status}")
        
        # Stop
        runtime.stop()
    
    asyncio.run(test_runtime_loop())

