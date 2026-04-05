# project_guardian/elysia_loop_core.py
# ElysiaLoop-Core Event Loop System
# Based on Conversation 5 design specifications

import asyncio
import heapq
import uuid
import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Coroutine, Union
from enum import Enum
from threading import Lock
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Task:
    """
    Task representation with priority comparison.
    Supports both sync and async callables.
    """
    
    def __init__(
        self,
        task_id: str,
        func: Union[Callable, Coroutine],
        args: tuple = (),
        kwargs: dict = None,
        priority: int = 5,
        cooperative: bool = True,
        timeout: Optional[float] = None,
        module: str = "unknown",
        dependencies: List[str] = None
    ):
        self.id = task_id
        self.func = func
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.priority = priority  # Higher number = higher priority
        self.cooperative = cooperative
        self.timeout = timeout
        self.module = module
        self.dependencies = dependencies or []
        self.status = TaskStatus.PENDING
        self.created_at = datetime.now()
        self.last_run = None
        self.attempts = 0
        self.error_count = 0
        
    def __lt__(self, other):
        """Priority comparison for heapq (inverted: higher priority = smaller number)."""
        # First compare by priority (inverted for max-heap behavior)
        if self.priority != other.priority:
            return self.priority > other.priority
        # Then by age (older tasks first)
        return self.created_at < other.created_at
        
    def __repr__(self):
        return f"Task(id={self.id}, priority={self.priority}, module={self.module}, status={self.status.value})"


class TimelineEvent:
    """Event logging structure for timeline memory."""
    
    def __init__(
        self,
        event_type: str,
        task_id: Optional[str] = None,
        summary: str = "",
        payload: Optional[Dict[str, Any]] = None
    ):
        self.timestamp = datetime.now()
        self.event_type = event_type
        self.task_id = task_id
        self.summary = summary
        self.payload = payload or {}
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "task_id": self.task_id,
            "summary": self.summary,
            "payload": json.dumps(self.payload) if self.payload else None
        }


class TimelineMemory:
    """
    SQLite-based event logging for audit trail and system reconstruction.
    """
    
    def __init__(self, db_path: str = "elysia_timeline.db"):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS timeline_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        task_id TEXT,
                        summary TEXT,
                        payload TEXT
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON timeline_events(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON timeline_events(task_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON timeline_events(event_type)")
                conn.commit()
            logger.info(f"Timeline memory initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize timeline database: {e}")
            raise
        
    def log_event(self, event: TimelineEvent):
        """Log an event to the timeline."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                event_dict = event.to_dict()
                cursor.execute("""
                    INSERT INTO timeline_events (timestamp, event_type, task_id, summary, payload)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    event_dict["timestamp"],
                    event_dict["event_type"],
                    event_dict["task_id"],
                    event_dict["summary"],
                    event_dict["payload"]
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log event to timeline: {e}")
            # Don't raise - timeline logging failures shouldn't crash the system
            # But log the error for debugging
        
    def query_events(
        self,
        task_id: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query timeline events with filters."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM timeline_events WHERE 1=1"
                params = []
                
                if task_id:
                    query += " AND task_id = ?"
                    params.append(task_id)
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type)
                if since:
                    query += " AND timestamp >= ?"
                    params.append(since.isoformat())
                    
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [
                    {
                        "id": row[0],
                        "timestamp": row[1],
                        "event_type": row[2],
                        "task_id": row[3],
                        "summary": row[4],
                        "payload": json.loads(row[5]) if row[5] else {}
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to query timeline events: {e}")
            return []  # Return empty list on error rather than crashing


class BaseModuleAdapter(ABC):
    """
    Abstract base class for all module adapters.
    Standardizes interface for module communication.
    """
    
    @abstractmethod
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a method on the module.
        
        Args:
            method: Method name to execute
            payload: Method arguments and parameters
            
        Returns:
            Response dictionary (must include 'success' key)
        """
        pass
        
    @abstractmethod
    def get_module_name(self) -> str:
        """Get the module name."""
        pass
        
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Get list of capabilities this module provides."""
        pass


class ModuleRegistry:
    """
    Central registry for module adapters.
    Provides discovery and routing capabilities.
    """
    
    def __init__(self):
        self._adapters: Dict[str, BaseModuleAdapter] = {}
        self._lock = Lock()
        
    def register(self, name: str, adapter: BaseModuleAdapter):
        """Register a module adapter."""
        with self._lock:
            if name in self._adapters:
                logger.warning(f"Overwriting existing adapter: {name}")
            self._adapters[name] = adapter
            logger.info(f"Registered module: {name}")
            
    def get(self, name: str) -> Optional[BaseModuleAdapter]:
        """Get a module adapter by name."""
        with self._lock:
            return self._adapters.get(name)
            
    def list_modules(self) -> List[str]:
        """List all registered module names."""
        with self._lock:
            return list(self._adapters.keys())
            
    def get_module_capabilities(self, name: str) -> List[str]:
        """Get capabilities for a specific module."""
        adapter = self.get(name)
        if adapter:
            return adapter.get_capabilities()
        return []
    
    def get_registry_status(self) -> Dict[str, Any]:
        """Get status of the module registry."""
        with self._lock:
            return {
                "module_names": list(self._adapters.keys()),
                "total_modules": len(self._adapters),
                "modules": {
                    name: {
                        "name": name,
                        "capabilities": adapter.get_capabilities() if adapter else []
                    }
                    for name, adapter in self._adapters.items()
                }
            }
    
    def get_module_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific module."""
        adapter = self.get(name)
        if not adapter:
            return None
        return {
            "name": name,
            "capabilities": adapter.get_capabilities(),
            "module_name": adapter.get_module_name() if hasattr(adapter, 'get_module_name') else name
        }
    
    async def route_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Route a task to an appropriate module."""
        task_type = task_data.get("type", "")
        payload = task_data.get("payload", {})
        
        # Simple routing: find module with matching capability
        with self._lock:
            for name, adapter in self._adapters.items():
                capabilities = adapter.get_capabilities()
                if task_type in capabilities or task_type.lower() in [c.lower() for c in capabilities]:
                    try:
                        if hasattr(adapter, 'execute'):
                            result = adapter.execute(task_type, payload)
                            return {"success": True, "module": name, "result": result}
                    except Exception as e:
                        logger.error(f"Error executing task on module {name}: {e}")
                        return {"success": False, "error": str(e), "module": name}
        
        # No matching module found
        return {"success": False, "error": f"No module found for task type: {task_type}"}


class GlobalTaskQueue:
    """
    Thread-safe priority queue for task management.
    Supports dependency resolution.
    """
    
    def __init__(self):
        self._queue: List[Task] = []
        self._tasks: Dict[str, Task] = {}  # Task registry by ID
        self._lock = Lock()
        
    def add_task(self, task: Task) -> bool:
        """Add a task to the queue."""
        with self._lock:
            if task.id in self._tasks:
                logger.warning(f"Task {task.id} already exists")
                return False
            self._tasks[task.id] = task
            heapq.heappush(self._queue, task)
            logger.debug(f"Added task to queue: {task.id}")
            return True
            
    def get_next_task(self) -> Optional[Task]:
        """Get the next task from the queue (highest priority)."""
        with self._lock:
            if not self._queue:
                return None
            # Pop task with highest priority
            task = heapq.heappop(self._queue)
            return task
            
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)
            
    def update_task_status(self, task_id: str, status: TaskStatus):
        """Update task status."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                if status == TaskStatus.IN_PROGRESS:
                    task.last_run = datetime.now()
                    task.attempts += 1
                    
    def remove_task(self, task_id: str) -> bool:
        """Remove a task from the registry."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                # Remove from queue (inefficient but necessary)
                self._queue = [t for t in self._queue if t.id != task_id]
                heapq.heapify(self._queue)
                return True
            return False
            
    def requeue_task(self, task: Task):
        """Re-add a task to the queue."""
        with self._lock:
            task.status = TaskStatus.PENDING
            heapq.heappush(self._queue, task)
            
    def check_dependencies(self, task: Task) -> bool:
        """Check if all dependencies are completed."""
        if not task.dependencies:
            return True
        with self._lock:
            for dep_id in task.dependencies:
                dep_task = self._tasks.get(dep_id)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    return False
            return True
            
    def get_queue_size(self) -> int:
        """Get current queue size."""
        with self._lock:
            return len(self._queue)
            
    def get_task_count(self) -> int:
        """Get total task count (including completed)."""
        with self._lock:
            return len(self._tasks)


class ElysiaLoopCore:
    """
    Main event loop controller for Elysia.
    Non-blocking async execution with priority-based scheduling.
    """
    
    def __init__(
        self,
        timeline_memory: Optional[TimelineMemory] = None,
        module_registry: Optional[ModuleRegistry] = None,
        loop_interval: float = 0.1,
        batch_size: int = 5
    ):
        self.timeline = timeline_memory or TimelineMemory()
        self.registry = module_registry or ModuleRegistry()
        self.task_queue = GlobalTaskQueue()
        self.loop_interval = loop_interval
        self.batch_size = batch_size
        self.running = False
        self.paused = False
        self._loop_task: Optional[asyncio.Task] = None
        self._event_loop = None
        
    async def _execute_task(self, task: Task) -> bool:
        """
        Execute a single task.
        
        Returns:
            True if task completed successfully, False otherwise
        """
        try:
            self.task_queue.update_task_status(task.id, TaskStatus.IN_PROGRESS)
            
            # Check dependencies
            if not self.task_queue.check_dependencies(task):
                logger.debug(f"Task {task.id} waiting on dependencies")
                self.task_queue.requeue_task(task)
                return False
                
            # Log task start
            event = TimelineEvent(
                event_type="task_start",
                task_id=task.id,
                summary=f"Task started: {task.module}.{task.func.__name__ if callable(task.func) else 'unknown'}",
                payload={"module": task.module, "priority": task.priority}
            )
            self.timeline.log_event(event)
            
            # Route to module if it's a module method call
            if task.module != "unknown" and task.module in self.registry.list_modules():
                adapter = self.registry.get(task.module)
                if adapter:
                    result = adapter.execute(
                        method=task.func.__name__ if callable(task.func) else str(task.func),
                        payload={"args": task.args, "kwargs": task.kwargs}
                    )
                    
                    if result.get("success", False):
                        self.task_queue.update_task_status(task.id, TaskStatus.COMPLETED)
                        event = TimelineEvent(
                            event_type="task_complete",
                            task_id=task.id,
                            summary=f"Task completed successfully",
                            payload=result
                        )
                        self.timeline.log_event(event)
                        return True
                    else:
                        raise Exception(result.get("error", "Module execution failed"))
            
            # Execute as coroutine or callable
            if asyncio.iscoroutine(task.func):
                if task.timeout:
                    result = await asyncio.wait_for(task.func, timeout=task.timeout)
                else:
                    result = await task.func
            elif asyncio.iscoroutinefunction(task.func):
                if task.timeout:
                    result = await asyncio.wait_for(task.func(*task.args, **task.kwargs), timeout=task.timeout)
                else:
                    result = await task.func(*task.args, **task.kwargs)
            else:
                # Sync function - run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                if task.timeout:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, task.func, *task.args, **task.kwargs),
                        timeout=task.timeout
                    )
                else:
                    result = await loop.run_in_executor(None, task.func, *task.args, **task.kwargs)
                    
            # Task completed successfully
            self.task_queue.update_task_status(task.id, TaskStatus.COMPLETED)
            event = TimelineEvent(
                event_type="task_complete",
                task_id=task.id,
                summary=f"Task completed successfully",
                payload={"result": str(result)[:100]}  # Truncate for storage
            )
            self.timeline.log_event(event)
            logger.info(f"Task {task.id} completed successfully")
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"Task {task.id} timed out")
            task.error_count += 1
            if task.error_count < 3:  # Retry up to 3 times
                self.task_queue.requeue_task(task)
                return False
            else:
                self.task_queue.update_task_status(task.id, TaskStatus.FAILED)
                
        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}", exc_info=True)
            task.error_count += 1
            if task.error_count < 3:
                self.task_queue.requeue_task(task)
                return False
            else:
                self.task_queue.update_task_status(task.id, TaskStatus.FAILED)
                event = TimelineEvent(
                    event_type="task_error",
                    task_id=task.id,
                    summary=f"Task failed: {str(e)[:100]}",
                    payload={"error": str(e)[:200]}
                )
                self.timeline.log_event(event)
                
        return False
        
    async def _execute_idle_tasks(self):
        """Execute background tasks when queue is empty."""
        # Heartbeat task
        queue_size = self.task_queue.get_queue_size()
        event = TimelineEvent(
            event_type="heartbeat",
            summary="ElysiaLoop heartbeat",
            payload={"queue_size": queue_size}
        )
        self.timeline.log_event(event)
        
        # Log heartbeat periodically (every 60 seconds)
        if not hasattr(self, '_last_heartbeat_log'):
            self._last_heartbeat_log = datetime.now()
        
        now = datetime.now()
        if (now - self._last_heartbeat_log).total_seconds() >= 60:
            logger.debug(f"ElysiaLoop heartbeat: queue_size={queue_size}, running={self.running}, paused={self.paused}")
            self._last_heartbeat_log = now
        
        # Memory compaction task could go here
        # Dream cycle tasks could go here
        
    async def _run_loop(self):
        """Main event loop coroutine - non-blocking async execution."""
        logger.info("ElysiaLoop-Core event loop started")
        
        while self.running:
            if self.paused:
                await asyncio.sleep(1.0)
                continue
                
            # Process batch of tasks
            batch_processed = 0
            for _ in range(self.batch_size):
                task = self.task_queue.get_next_task()
                if not task:
                    break
                    
                # Execute task (non-blocking)
                await self._execute_task(task)
                batch_processed += 1
                
                # Cooperative multitasking - yield control
                if task.cooperative:
                    await asyncio.sleep(0.01)
                    
            # If no tasks, run idle tasks
            if batch_processed == 0:
                await self._execute_idle_tasks()
                
            # Loop timing
            await asyncio.sleep(self.loop_interval)
            
        logger.info("ElysiaLoop-Core event loop stopped")
        
    def start(self):
        """Start the event loop."""
        if self.running:
            logger.warning("Event loop already running")
            return
            
        self.running = True
        self.paused = False
        
        try:
            loop = asyncio.get_running_loop()
            # If we're in an existing loop, create task
            self._loop_task = asyncio.create_task(self._run_loop())
        except RuntimeError:
            # No running loop, create new one in background thread
            import threading
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(self._run_loop())
            
            self._loop_thread = threading.Thread(target=run_in_thread, daemon=True)
            self._loop_thread.start()
            self._loop_task = None
            
        logger.info("ElysiaLoop-Core started")
        
    def stop(self):
        """Stop the event loop."""
        if not self.running:
            return
            
        self.running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("ElysiaLoop-Core stopped")
        
    def pause(self):
        """Pause the event loop."""
        self.paused = True
        logger.info("ElysiaLoop-Core paused")
        
    def resume(self):
        """Resume the event loop."""
        self.paused = False
        logger.info("ElysiaLoop-Core resumed")
        
    def submit_task(
        self,
        func: Union[Callable, Coroutine],
        args: tuple = (),
        kwargs: dict = None,
        priority: int = 5,
        module: str = "unknown",
        timeout: Optional[float] = None,
        dependencies: List[str] = None
    ) -> str:
        """
        Submit a task to the queue.
        
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            func=func,
            args=args,
            kwargs=kwargs or {},
            priority=priority,
            module=module,
            timeout=timeout,
            dependencies=dependencies or []
        )
        
        if self.task_queue.add_task(task):
            return task_id
        else:
            raise ValueError(f"Failed to add task {task_id}")
            
    def get_status(self) -> Dict[str, Any]:
        """Get event loop status."""
        return {
            "running": self.running,
            "paused": self.paused,
            "queue_size": self.task_queue.get_queue_size(),
            "total_tasks": self.task_queue.get_task_count(),
            "registered_modules": len(self.registry.list_modules()),
            "modules": self.registry.list_modules()
        }


# Bootstrap/test code
if __name__ == "__main__":
    async def test_task():
        """Test async task."""
        await asyncio.sleep(0.1)
        return "Test task completed"
        
    async def test_main():
        """Test main function."""
        loop = ElysiaLoopCore()
        loop.start()
        
        # Submit some test tasks
        task_id1 = loop.submit_task(test_task, priority=10, module="test")
        task_id2 = loop.submit_task(test_task, priority=5, module="test")
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Check status
        status = loop.get_status()
        print(f"Loop status: {status}")
        
        # Stop loop
        loop.stop()
        
    # Run test
    asyncio.run(test_main())

