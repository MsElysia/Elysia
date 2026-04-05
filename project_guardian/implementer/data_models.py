"""
Data models for the Implementer Agent
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class TaskStatus(str, Enum):
    """Status of a single task"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ImplementationStatus(str, Enum):
    """Status of overall implementation"""
    IN_IMPLEMENTATION = "in_implementation"
    IMPLEMENTED = "implemented"
    IMPLEMENTATION_FAILED = "implementation_failed"
    IMPLEMENTATION_PARTIAL = "implementation_partial"
    ROLLED_BACK = "rolled_back"
    REWORK_REQUIRED = "rework_required"


@dataclass
class ImplementationStep:
    """A single step in the implementation plan"""
    id: str
    description: str
    type: str  # "code_add", "code_modify", "config_update", "test_add", "doc_update", etc.
    targets: List[str]  # filenames / modules
    acceptance_criteria: List[str]
    estimated_effort: Optional[str] = None  # "low", "medium", "high"
    dependencies: List[str] = field(default_factory=list)  # step ids this depends on


@dataclass
class ImplementationPlan:
    """Complete implementation plan for a proposal"""
    proposal_id: str
    steps: List[ImplementationStep]
    assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    estimated_total_effort: Optional[str] = None
    domain: Optional[str] = None


@dataclass
class Task:
    """A concrete task to execute"""
    id: str
    step_id: str
    description: str
    command: Optional[str] = None  # e.g. "pytest tests/..." or "run_migrations"
    depends_on: List[str] = field(default_factory=list)  # task ids
    target_files: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class TaskGraph:
    """Directed acyclic graph of tasks"""
    tasks: List[Task]
    
    def topological_sort(self) -> List[Task]:
        """Return tasks in dependency order"""
        # Simple topological sort
        sorted_tasks = []
        remaining = {task.id: task for task in self.tasks}
        completed = set()
        
        while remaining:
            # Find tasks with no uncompleted dependencies
            ready = [
                task for task in remaining.values()
                if all(dep in completed for dep in task.depends_on)
            ]
            
            if not ready:
                # Circular dependency or missing dependency
                break
            
            for task in ready:
                sorted_tasks.append(task)
                completed.add(task.id)
                del remaining[task.id]
        
        # Add any remaining tasks (they have issues, but include them)
        sorted_tasks.extend(remaining.values())
        
        return sorted_tasks
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


@dataclass
class TaskResult:
    """Result of executing a single task"""
    task_id: str
    status: TaskStatus
    output: Optional[str] = None
    error: Optional[str] = None
    test_results: Optional[Dict[str, Any]] = None
    diff: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)


@dataclass
class ImplementationResult:
    """Overall result of implementing a proposal"""
    proposal_id: str
    status: ImplementationStatus
    branch_name: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_total: int = 0
    task_results: List[TaskResult] = field(default_factory=list)
    diff_summary: Optional[str] = None
    test_results: Optional[Dict[str, Any]] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    rollback_required: bool = False

