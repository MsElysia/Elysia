# enhanced_task_engine.py
# Enhanced Task Engine with Project Guardian features

import datetime
import json
import os
from typing import List, Dict, Optional, Any
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    LOW = 0.3
    MEDIUM = 0.5
    HIGH = 0.7
    CRITICAL = 0.9

class EnhancedTaskEngine:
    def __init__(self, memory, task_file="tasks.json"):
        self.memory = memory
        self.tasks = []
        self.task_file = task_file
        self.task_id_counter = 0
        self.load()

    def create_task(self, name, description, priority=0.5, category="general", deadline=None, tags=None):
        """
        Enhanced task creation with priority, category, deadline, and tags
        Maintains backward compatibility with original create_task()
        """
        self.task_id_counter += 1
        task = {
            "id": self.task_id_counter,
            "name": name,
            "description": description,
            "priority": priority,
            "category": category,
            "status": TaskStatus.PENDING.value,
            "created": datetime.datetime.now().isoformat(),
            "deadline": deadline,
            "tags": tags or [],
            "logs": [],
            "completed": False,
            "completed_time": None
        }
        self.tasks.append(task)
        
        self.memory.remember(
            f"[Task Created] {name}: {description}",
            category="task",
            priority=priority
        )
        
        self._save()
        print(f"[Task] Created: {name} (Priority: {priority}, Category: {category})")
        return task

    def get_task(self, task_id: int) -> Optional[Dict]:
        """Get task by ID"""
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None

    def update_task_status(self, task_id: int, status: str, note: str = ""):
        """Update task status with logging"""
        task = self.get_task(task_id)
        if not task:
            print(f"[Task] Task {task_id} not found")
            return False
        
        old_status = task["status"]
        task["status"] = status
        
        log_entry = {
            "time": datetime.datetime.now().isoformat(),
            "action": "status_update",
            "old_status": old_status,
            "new_status": status,
            "note": note
        }
        task["logs"].append(log_entry)
        
        # Update completion status
        if status == TaskStatus.COMPLETED.value:
            task["completed"] = True
            task["completed_time"] = datetime.datetime.now().isoformat()
        
        self.memory.remember(
            f"[Task Status] {task['name']}: {old_status} → {status}",
            category="task",
            priority=task["priority"]
        )
        
        self._save()
        print(f"[Task] {task['name']}: {old_status} → {status}")
        return True

    def log_task(self, name, note):
        """Backward compatibility method"""
        for task in self.tasks:
            if task["name"] == name and not task["completed"]:
                log_entry = {
                    "time": datetime.datetime.now().isoformat(),
                    "action": "log",
                    "note": note
                }
                task["logs"].append(log_entry)
                self.memory.remember(f"[Task Log] {name}: {note}")
                self._save()
                return
        self.memory.remember(f"[Task Log Failed] No active task: {name}")

    def complete_task(self, task_id: int, completion_note: str = ""):
        """Complete task by ID with optional note"""
        return self.update_task_status(task_id, TaskStatus.COMPLETED.value, completion_note)

    def get_active_tasks(self, category: Optional[str] = None) -> List[Dict]:
        """Get active (non-completed) tasks, optionally filtered by category"""
        active_tasks = [t for t in self.tasks if not t["completed"]]
        
        if category:
            active_tasks = [t for t in active_tasks if t["category"] == category]
        
        return active_tasks

    def get_tasks_by_priority(self, min_priority: float = 0.0, max_priority: float = 1.0) -> List[Dict]:
        """Get tasks within priority range"""
        return [
            task for task in self.tasks
            if min_priority <= task["priority"] <= max_priority
        ]

    def get_high_priority_tasks(self, threshold: float = 0.7) -> List[Dict]:
        """Get high priority tasks"""
        return self.get_tasks_by_priority(min_priority=threshold)

    def get_overdue_tasks(self) -> List[Dict]:
        """Get tasks that are past their deadline"""
        overdue = []
        now = datetime.datetime.now()
        
        for task in self.tasks:
            if task["deadline"] and not task["completed"]:
                deadline = datetime.datetime.fromisoformat(task["deadline"])
                if now > deadline:
                    overdue.append(task)
        
        return overdue

    def get_task_stats(self) -> Dict[str, Any]:
        """Get comprehensive task statistics"""
        if not self.tasks:
            return {
                "total_tasks": 0,
                "active_tasks": 0,
                "completed_tasks": 0,
                "categories": {},
                "priority_breakdown": {},
                "overdue_tasks": 0
            }
        
        stats = {
            "total_tasks": len(self.tasks),
            "active_tasks": len([t for t in self.tasks if not t["completed"]]),
            "completed_tasks": len([t for t in self.tasks if t["completed"]]),
            "categories": {},
            "priority_breakdown": {},
            "overdue_tasks": len(self.get_overdue_tasks())
        }
        
        # Category breakdown
        for task in self.tasks:
            category = task["category"]
            if category not in stats["categories"]:
                stats["categories"][category] = {"total": 0, "active": 0, "completed": 0}
            
            stats["categories"][category]["total"] += 1
            if task["completed"]:
                stats["categories"][category]["completed"] += 1
            else:
                stats["categories"][category]["active"] += 1
        
        # Priority breakdown
        for task in self.tasks:
            priority = task["priority"]
            if priority not in stats["priority_breakdown"]:
                stats["priority_breakdown"][priority] = 0
            stats["priority_breakdown"][priority] += 1
        
        return stats

    def search_tasks(self, keyword: str, category: Optional[str] = None) -> List[Dict]:
        """Search tasks by keyword"""
        results = []
        tasks_to_search = self.tasks
        
        if category:
            tasks_to_search = [t for t in self.tasks if t["category"] == category]
        
        for task in tasks_to_search:
            if (keyword.lower() in task["name"].lower() or 
                keyword.lower() in task["description"].lower()):
                results.append(task)
        
        return results

    def cleanup_old_tasks(self, days: int = 30):
        """Remove completed tasks older than specified days"""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        initial_count = len(self.tasks)
        
        self.tasks = [
            task for task in self.tasks
            if not (task["completed"] and 
                   datetime.datetime.fromisoformat(task["completed_time"]) < cutoff)
        ]
        
        removed_count = initial_count - len(self.tasks)
        if removed_count > 0:
            print(f"[Task] Cleaned up {removed_count} old completed tasks")
            self._save()

    def _save(self):
        """Save tasks to file"""
        data = {
            "tasks": self.tasks,
            "task_id_counter": self.task_id_counter,
            "last_updated": datetime.datetime.now().isoformat()
        }
        
        try:
            with open(self.task_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Task] Save failed: {e}")

    def load(self):
        """Load tasks from file"""
        if os.path.exists(self.task_file):
            try:
                with open(self.task_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                self.tasks = data.get("tasks", [])
                self.task_id_counter = data.get("task_id_counter", 0)
                
                print(f"[Task] Loaded {len(self.tasks)} tasks")
            except Exception as e:
                print(f"[Task] Load failed: {e}")

# Backward compatibility alias
TaskEngine = EnhancedTaskEngine 