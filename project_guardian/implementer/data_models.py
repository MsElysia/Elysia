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


def _coerce_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def implementation_plan_from_proposal_dict(
    proposal: Dict[str, Any],
) -> Optional["ImplementationPlan"]:
    """
    Build an ImplementationPlan from JSON-ish proposal metadata when no in-memory
    plan object was passed (e.g. disk-loaded proposals with nested ``plan`` / ``implementation_plan``,
    or a top-level ``steps`` list of step dicts).
    """
    if not isinstance(proposal, dict):
        return None

    raw: Optional[Dict[str, Any]] = None
    for key in ("implementation_plan", "plan"):
        candidate = proposal.get(key)
        if isinstance(candidate, dict) and isinstance(candidate.get("steps"), list):
            raw = candidate
            break

    if raw is None:
        top_steps = proposal.get("steps")
        if isinstance(top_steps, list) and top_steps and all(
            isinstance(x, dict) for x in top_steps
        ):
            raw = {"steps": top_steps}

    if raw is None:
        return None

    steps_out: List[ImplementationStep] = []
    for idx, item in enumerate(raw.get("steps") or []):
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or item.get("step_id") or f"step-{idx + 1}").strip()
        if not sid:
            sid = f"step-{idx + 1}"
        desc = str(item.get("description") or "").strip() or sid
        stype = str(item.get("type") or "code_modify").strip() or "code_modify"
        targets = item.get("targets") or item.get("target_files") or []
        if not isinstance(targets, list):
            targets = []
        targets = [str(t).strip() for t in targets if str(t).strip()]
        ac = _coerce_str_list(item.get("acceptance_criteria"))
        deps = item.get("dependencies") or []
        if not isinstance(deps, list):
            deps = []
        deps = [str(d).strip() for d in deps if str(d).strip()]
        effort = item.get("estimated_effort")
        effort_s = str(effort).strip() if effort is not None else None
        steps_out.append(
            ImplementationStep(
                id=sid,
                description=desc,
                type=stype,
                targets=targets,
                acceptance_criteria=ac,
                estimated_effort=effort_s or None,
                dependencies=deps,
            )
        )

    if not steps_out:
        return None

    proposal_id = str(
        raw.get("proposal_id")
        or proposal.get("proposal_id")
        or "unknown"
    )
    assumptions = _coerce_str_list(raw.get("assumptions") or proposal.get("assumptions"))
    risks = _coerce_str_list(raw.get("risks") or proposal.get("risks"))
    domain = raw.get("domain") or proposal.get("domain")
    domain_s = str(domain).strip() if domain is not None else None

    return ImplementationPlan(
        proposal_id=proposal_id,
        steps=steps_out,
        assumptions=assumptions,
        risks=risks,
        estimated_total_effort=(
            str(raw.get("estimated_total_effort")).strip()
            if raw.get("estimated_total_effort") is not None
            else None
        ),
        domain=domain_s,
    )
