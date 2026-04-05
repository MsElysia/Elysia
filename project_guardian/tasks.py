# project_guardian/tasks.py
# Task Management System for Project Guardian

import datetime
from typing import List, Dict, Any, Optional
from .memory import MemoryCore

class TaskEngine:
    """
    Task management system for Project Guardian.
    Provides task creation, logging, and completion tracking.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        self.tasks: List[Dict[str, Any]] = []
        self.task_history: List[Dict[str, Any]] = []
        self._on_task_complete: Optional[Any] = None  # callable(task_id, task) for closed-loop
        
    def create_task(self, name: str, description: str, priority: float = 0.5, 
                   category: str = "general", estimated_duration: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a new task.
        
        Args:
            name: Task name
            description: Task description
            priority: Task priority (0.0 to 1.0)
            category: Task category
            estimated_duration: Estimated duration in minutes
            
        Returns:
            Created task dictionary
        """
        task = {
            "id": len(self.tasks) + 1,
            "name": name,
            "description": description,
            "priority": priority,
            "category": category,
            "status": "pending",
            "created": datetime.datetime.now().isoformat(),
            "completed": False,
            "logs": [],
            "estimated_duration": estimated_duration,
            "actual_duration": None,
            "dependencies": [],
            "assigned_to": None
        }
        
        self.tasks.append(task)
        self.memory.remember(
            f"[Guardian Task] Created: {name} - {description}",
            category="task",
            priority=priority
        )
        return task
        
    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task dictionary or None if not found
        """
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None
        
    def log_task(self, task_id: int, note: str, log_type: str = "info") -> bool:
        """
        Add a log entry to a task.
        
        Args:
            task_id: Task ID
            note: Log message
            log_type: Type of log entry (info, warning, error, progress)
            
        Returns:
            True if successful
        """
        task = self.get_task(task_id)
        if not task or task["completed"]:
            self.memory.remember(
                f"[Guardian Task] Failed to log: Task {task_id} not found or completed",
                category="task",
                priority=0.6
            )
            return False
            
        log_entry = {
            "time": datetime.datetime.now().isoformat(),
            "note": note,
            "type": log_type
        }
        task["logs"].append(log_entry)
        
        self.memory.remember(
            f"[Guardian Task] {task['name']}: {note}",
            category="task",
            priority=task["priority"]
        )
        return True
        
    def update_task_status(self, task_id: int, status: str) -> bool:
        """
        Update task status.
        
        Args:
            task_id: Task ID
            status: New status (pending, in_progress, completed, cancelled)
            
        Returns:
            True if successful
        """
        task = self.get_task(task_id)
        if not task:
            return False
            
        old_status = task["status"]
        task["status"] = status
        
        self.memory.remember(
            f"[Guardian Task] {task['name']}: {old_status} -> {status}",
            category="task",
            priority=task["priority"]
        )
        return True
        
    def complete_task(self, task_id: int, actual_duration: Optional[int] = None) -> bool:
        """
        Mark a task as completed.
        
        Args:
            task_id: Task ID
            actual_duration: Actual duration in minutes
            
        Returns:
            True if successful
        """
        task = self.get_task(task_id)
        if not task:
            return False
            
        task["completed"] = True
        task["status"] = "completed"
        task["completed_time"] = datetime.datetime.now().isoformat()
        task["actual_duration"] = actual_duration
        
        # Move to history
        self.task_history.append(task)
        self.tasks.remove(task)
        
        self.memory.remember(
            f"[Guardian Task] Completed: {task['name']}",
            category="task",
            priority=task["priority"]
        )
        if self._on_task_complete:
            try:
                self._on_task_complete(task_id, task)
            except Exception:
                pass
        return True
        
    def get_active_tasks(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all active (non-completed) tasks.
        
        Args:
            category: Filter by category (optional)
            
        Returns:
            List of active tasks
        """
        active_tasks = [task for task in self.tasks if not task["completed"]]
        
        if category:
            active_tasks = [task for task in active_tasks if task["category"] == category]
            
        return active_tasks
        
    def get_tasks_by_priority(self, min_priority: float = 0.0) -> List[Dict[str, Any]]:
        """
        Get tasks above a minimum priority level.
        
        Args:
            min_priority: Minimum priority level
            
        Returns:
            List of high-priority tasks
        """
        return [task for task in self.tasks if task["priority"] >= min_priority and not task["completed"]]
        
    def get_task_stats(self) -> Dict[str, Any]:
        """
        Get task statistics.
        
        Returns:
            Task statistics dictionary
        """
        active_tasks = len([t for t in self.tasks if not t["completed"]])
        completed_tasks = len(self.task_history)
        total_tasks = active_tasks + completed_tasks
        
        categories = {}
        for task in self.tasks + self.task_history:
            cat = task.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            
        return {
            "active_tasks": active_tasks,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "categories": categories,
            "completion_rate": completed_tasks / total_tasks if total_tasks > 0 else 0
        }
        
    def cleanup_old_tasks(self, days_old: int = 30) -> int:
        """
        Remove old completed tasks from history.
        
        Args:
            days_old: Remove tasks older than this many days
            
        Returns:
            Number of tasks removed
        """
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_old)
        cutoff_iso = cutoff_date.isoformat()
        
        removed_count = 0
        tasks_to_keep = []
        
        for task in self.task_history:
            if task.get("completed_time", "") < cutoff_iso:
                removed_count += 1
            else:
                tasks_to_keep.append(task)
                
        self.task_history = tasks_to_keep
        
        if removed_count > 0:
            self.memory.remember(
                f"[Guardian Task] Cleaned up {removed_count} old tasks",
                category="task",
                priority=0.5
            )
            
        return removed_count
        
    def get_task_summary(self) -> str:
        """
        Get a human-readable task summary.
        
        Returns:
            Task summary string
        """
        stats = self.get_task_stats()
        
        summary = f"[Guardian Task] Summary: {stats['active_tasks']} active, "
        summary += f"{stats['completed_tasks']} completed, "
        summary += f"completion rate: {stats['completion_rate']:.1%}"
        
        return summary 