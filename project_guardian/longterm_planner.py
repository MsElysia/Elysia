# project_guardian/longterm_planner.py
# LongTermPlanner: Break Down Objectives Into Executable Tasks
# Based on Conversation 3 (elysia 4 sub a) design specifications

import logging
import json
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path

try:
    from .runtime_loop_core import RuntimeLoop
    from .ask_ai import AskAI, AIProvider
except ImportError:
    from runtime_loop_core import RuntimeLoop
    try:
        from ask_ai import AskAI, AIProvider
    except ImportError:
        AskAI = None
        AIProvider = None

logger = logging.getLogger(__name__)


class ObjectiveStatus(Enum):
    """Objective status enumeration."""
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


def _planner_task_status_from_runtime(
    status: Any,
    *,
    runtime_bound: bool = False,
) -> Optional["TaskStatus"]:
    """Map runtime-loop task status objects/strings into planner task states."""
    raw = ""
    if hasattr(status, "value"):
        raw = str(getattr(status, "value", "") or "").strip().lower()
    else:
        raw = str(status or "").strip().lower()
    if not raw:
        return None
    if raw == "failed":
        return TaskStatus.BLOCKED
    if runtime_bound and raw in {"pending", "in_progress"}:
        # Once a planner task is submitted to the runtime loop, both queued and
        # active runtime states mean "already in flight" from the planner's point of view.
        return TaskStatus.IN_PROGRESS
    for candidate in TaskStatus:
        if candidate.value == raw:
            return candidate
    return None


@dataclass
class Objective:
    """
    Represents a long-term objective with metadata.
    """
    objective_id: str
    name: str
    description: str
    priority: int = 5  # 1-10, higher = more important
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    status: ObjectiveStatus = ObjectiveStatus.ACTIVE
    tasks: List[str] = field(default_factory=list)  # Task IDs
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "objective_id": self.objective_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status.value,
            "tasks": self.tasks,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Objective":
        """Create Objective from dictionary."""
        return cls(
            objective_id=data["objective_id"],
            name=data["name"],
            description=data["description"],
            priority=data.get("priority", 5),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            status=ObjectiveStatus(data.get("status", "active")),
            tasks=data.get("tasks", []),
            metadata=data.get("metadata", {})
        )


@dataclass
class PlannedTask:
    """
    Represents a task derived from an objective.
    """
    task_id: str
    objective_id: str
    name: str
    description: str
    priority: int = 5
    dependencies: List[str] = field(default_factory=list)
    estimated_duration: Optional[float] = None  # Hours
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "objective_id": self.objective_id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "dependencies": self.dependencies,
            "estimated_duration": self.estimated_duration,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlannedTask":
        """Create PlannedTask from dictionary."""
        return cls(
            task_id=data["task_id"],
            objective_id=data["objective_id"],
            name=data["name"],
            description=data["description"],
            priority=data.get("priority", 5),
            dependencies=data.get("dependencies", []),
            estimated_duration=data.get("estimated_duration"),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            status=TaskStatus(data.get("status", "pending")),
            metadata=data.get("metadata", {})
        )


class LongTermPlanner:
    """
    Breaks down long-term objectives into executable tasks.
    Integrates with RuntimeLoop for execution.
    """
    
    def __init__(
        self,
        runtime_loop: Optional[RuntimeLoop] = None,
        ask_ai: Optional[AskAI] = None,
        storage_path: str = "data/longterm_planner.json",
        prompt_evolver: Optional[Any] = None,
    ):
        self.runtime_loop = runtime_loop
        self.ask_ai = ask_ai
        self.prompt_evolver = prompt_evolver
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.objectives: Dict[str, Objective] = {}
        self.planned_tasks: Dict[str, PlannedTask] = {}
        
        # Load existing data
        self.load()

    def _refresh_objective_status(self, objective_id: str) -> None:
        """Recompute objective state from its planned tasks."""
        objective = self.objectives.get(objective_id)
        if not objective:
            return
        if objective.tasks:
            all_completed = all(
                self.planned_tasks.get(tid, PlannedTask(
                    task_id="",
                    objective_id="",
                    name="",
                    description=""
                )).status == TaskStatus.COMPLETED
                for tid in objective.tasks
            )
            if all_completed:
                objective.status = ObjectiveStatus.COMPLETED
                objective.updated_at = datetime.now()
                logger.info(f"Objective {objective.objective_id} completed")
                return
        if objective.status == ObjectiveStatus.COMPLETED:
            objective.status = ObjectiveStatus.ACTIVE
            objective.updated_at = datetime.now()

    def sync_runtime_task_states(self, objective_id: Optional[str] = None) -> int:
        """
        Reconcile planner-side planned task statuses with the runtime loop.

        Returns:
            Number of planned tasks whose status changed.
        """
        if not self.runtime_loop or not hasattr(self.runtime_loop, "get_task_status"):
            return 0

        if objective_id:
            objective = self.objectives.get(objective_id)
            task_ids = list(objective.tasks) if objective else []
        else:
            task_ids = list(self.planned_tasks.keys())

        changed = 0
        touched_objectives = set()
        for task_id in task_ids:
            planned_task = self.planned_tasks.get(task_id)
            if not planned_task:
                continue
            runtime_task_id = str((planned_task.metadata or {}).get("runtime_task_id") or "").strip()
            if not runtime_task_id:
                continue
            runtime_status = self.runtime_loop.get_task_status(runtime_task_id)
            mapped = _planner_task_status_from_runtime(runtime_status, runtime_bound=True)
            if mapped is None or mapped == planned_task.status:
                continue
            planned_task.status = mapped
            planned_task.metadata["runtime_last_status"] = mapped.value
            planned_task.metadata["runtime_last_sync_at"] = datetime.now().isoformat()
            touched_objectives.add(planned_task.objective_id)
            changed += 1

        for oid in touched_objectives:
            self._refresh_objective_status(oid)

        if changed:
            self.save()
        return changed

    @staticmethod
    def _is_smoke_objective(objective: Objective) -> bool:
        """Identify transient planner smoke-test objectives that should not stay active."""
        name = str(getattr(objective, "name", "") or "").strip().lower()
        description = str(getattr(objective, "description", "") or "").strip().lower()
        return (
            name == "smokeobjective"
            and description == "build something small to verify planner."
        )

    def prune_smoke_test_objectives(self) -> int:
        """
        Cancel stale smoke-test objectives so they do not pollute live autonomy.

        When real active objectives exist, all active smoke objectives are cancelled.
        Otherwise, keep the most recent smoke objective and cancel older duplicates.
        """
        smoke_active = [
            objective
            for objective in self.objectives.values()
            if objective.status == ObjectiveStatus.ACTIVE and self._is_smoke_objective(objective)
        ]
        if not smoke_active:
            return 0

        real_active = [
            objective
            for objective in self.objectives.values()
            if objective.status == ObjectiveStatus.ACTIVE and not self._is_smoke_objective(objective)
        ]

        keep_ids = set()
        if not real_active and smoke_active:
            newest = max(
                smoke_active,
                key=lambda objective: (
                    objective.updated_at,
                    objective.created_at,
                    objective.objective_id,
                ),
            )
            keep_ids.add(newest.objective_id)

        changed = 0
        for objective in smoke_active:
            if objective.objective_id in keep_ids:
                continue
            objective.status = ObjectiveStatus.CANCELLED
            objective.updated_at = datetime.now()
            objective.metadata["cleanup_reason"] = "smoke_test_objective_pruned"
            changed += 1

        if changed:
            logger.info("Pruned %d stale smoke-test objective(s) from planner backlog", changed)
            self.save()
        return changed

    def repair_orphaned_runtime_tasks(self, objective_id: Optional[str] = None) -> int:
        """
        Recover planner tasks that look in-progress locally but are no longer wired to
        a live runtime task after a restart or partial save.

        Returns:
            Number of planned tasks reset to PENDING.
        """
        if objective_id:
            objective = self.objectives.get(objective_id)
            task_ids = list(objective.tasks) if objective else []
        else:
            task_ids = list(self.planned_tasks.keys())

        changed = 0
        touched_objectives = set()
        for task_id in task_ids:
            planned_task = self.planned_tasks.get(task_id)
            if not planned_task:
                continue

            metadata = planned_task.metadata if isinstance(planned_task.metadata, dict) else {}
            runtime_task_id = str(metadata.get("runtime_task_id") or "").strip()
            recovery_reason = ""
            if not runtime_task_id:
                if planned_task.status != TaskStatus.IN_PROGRESS:
                    continue
                recovery_reason = "missing_runtime_binding"
            elif self.runtime_loop and hasattr(self.runtime_loop, "get_task_status"):
                try:
                    runtime_status = self.runtime_loop.get_task_status(runtime_task_id)
                except Exception:
                    runtime_status = None
                if runtime_status is None:
                    recovery_reason = "runtime_task_missing"

            if not recovery_reason:
                continue

            if not isinstance(planned_task.metadata, dict):
                planned_task.metadata = {}
            if runtime_task_id:
                planned_task.metadata["previous_runtime_task_id"] = runtime_task_id
                planned_task.metadata.pop("runtime_task_id", None)
            planned_task.status = TaskStatus.PENDING
            planned_task.metadata["runtime_last_status"] = TaskStatus.PENDING.value
            planned_task.metadata["runtime_recovered_at"] = datetime.now().isoformat()
            planned_task.metadata["runtime_recovery_reason"] = recovery_reason
            touched_objectives.add(planned_task.objective_id)
            changed += 1

        for oid in touched_objectives:
            objective = self.objectives.get(oid)
            if objective:
                objective.updated_at = datetime.now()

        if changed:
            logger.info("Recovered %d orphaned planner task(s) for runtime resubmission", changed)
            self.save()
        return changed

    def get_objective_actionability(self, objective_id: str) -> Dict[str, Any]:
        """Summarize whether an active objective can advance right now."""
        self.sync_runtime_task_states(objective_id=objective_id)
        self.repair_orphaned_runtime_tasks(objective_id=objective_id)

        objective = self.objectives.get(objective_id)
        if not objective:
            return {}

        task_statuses = {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "blocked": 0,
            "cancelled": 0,
        }
        for task_id in objective.tasks:
            task = self.planned_tasks.get(task_id)
            if not task:
                continue
            status_key = task.status.value
            if status_key in task_statuses:
                task_statuses[status_key] += 1

        total_tasks = len(objective.tasks)
        needs_breakdown = total_tasks == 0
        pending_tasks = task_statuses["pending"]
        actionable = bool(pending_tasks > 0 or needs_breakdown)
        return {
            "objective_id": objective_id,
            "name": objective.name,
            "priority": int(objective.priority or 0),
            "pending_tasks": pending_tasks,
            "total_tasks": total_tasks,
            "needs_breakdown": needs_breakdown,
            "actionable": actionable,
            "task_statuses": task_statuses,
        }

    def pick_next_actionable_objective(self, preferred_objective_id: Optional[str] = None) -> Optional[Objective]:
        """
        Choose the best active objective to advance now.

        Preference order:
        1. Preferred objective when it is still actionable.
        2. Active objectives with pending submit-ready tasks.
        3. Active objectives that need initial breakdown.
        """
        active = self.list_active_objectives()
        if not active:
            return None

        scored = []
        for objective in active:
            summary = self.get_objective_actionability(objective.objective_id)
            if not summary:
                continue
            bucket = 2 if summary["pending_tasks"] > 0 else 1 if summary["needs_breakdown"] else 0
            if preferred_objective_id and objective.objective_id == preferred_objective_id and bucket > 0:
                return objective
            scored.append((bucket, int(objective.priority or 0), objective.updated_at, objective))

        actionable = [item for item in scored if item[0] > 0]
        if not actionable:
            return None

        actionable.sort(key=lambda item: (-item[0], -item[1], item[2], item[3].objective_id))
        return actionable[0][3]
    
    def add_objective(
        self,
        name: str,
        description: str,
        priority: int = 5,
        deadline: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a new long-term objective.
        
        Args:
            name: Objective name
            description: Detailed description
            priority: Priority (1-10)
            deadline: Optional deadline
            metadata: Additional metadata
            
        Returns:
            Objective ID
        """
        objective_id = str(uuid.uuid4())
        objective = Objective(
            objective_id=objective_id,
            name=name,
            description=description,
            priority=priority,
            deadline=deadline,
            metadata=metadata or {}
        )
        
        self.objectives[objective_id] = objective
        self.save()
        
        logger.info(f"Added objective: {name} (ID: {objective_id})")
        return objective_id
    
    async def breakdown_objective(
        self,
        objective_id: str,
        strategy: str = "hierarchical"
    ) -> List[str]:
        """
        Break down an objective into executable tasks.
        
        Args:
            objective_id: Objective to break down
            strategy: Breakdown strategy ("hierarchical", "sequential", "parallel")
            
        Returns:
            List of task IDs created
        """
        objective = self.objectives.get(objective_id)
        if not objective:
            raise ValueError(f"Objective {objective_id} not found")
        
        if objective.status != ObjectiveStatus.ACTIVE:
            logger.warning(f"Objective {objective_id} is not active, skipping breakdown")
            return []
        
        # Enhanced breakdown strategy with AI integration
        import asyncio
        try:
            if asyncio.iscoroutinefunction(self._breakdown_strategy):
                tasks = await self._breakdown_strategy(objective, strategy)
            else:
                tasks = self._breakdown_strategy(objective, strategy)
        except TypeError:
            # Fallback for sync version
            tasks = self._breakdown_strategy(objective, strategy)
        
        task_ids = []
        for task_data in tasks:
            task_id = self._create_task_from_breakdown(objective_id, task_data)
            task_ids.append(task_id)
            objective.tasks.append(task_id)
        
        objective.updated_at = datetime.now()
        self.save()
        
        logger.info(f"Broke down objective {objective_id} into {len(task_ids)} tasks")
        return task_ids
    
    async def _breakdown_strategy(
        self,
        objective: Objective,
        strategy: str
    ) -> List[Dict[str, Any]]:
        """
        Apply breakdown strategy to create task structure.
        Enhanced with AI integration for intelligent task breakdown.
        """
        # Try AI-powered breakdown first if AskAI is available
        if self.ask_ai and strategy in ["hierarchical", "ai_enhanced"]:
            try:
                ai_tasks = await self._ai_breakdown(objective)
                if ai_tasks:
                    return ai_tasks
            except Exception as e:
                logger.warning(f"AI breakdown failed, falling back to heuristic: {e}")
        
        # Fallback to heuristic-based breakdown
        tasks = []
        
        # Simple heuristic: split description into logical steps
        description_parts = objective.description.split(". ")
        if len(description_parts) < 2:
            # Single task
            tasks.append({
                "name": f"Execute: {objective.name}",
                "description": objective.description,
                "priority": objective.priority,
                "estimated_duration": 1.0,  # Default 1 hour
                "dependencies": []
            })
        else:
            # Multiple subtasks
            for i, part in enumerate(description_parts[:5]):  # Max 5 tasks
                tasks.append({
                    "name": f"{objective.name} - Step {i+1}",
                    "description": part.strip(),
                    "priority": objective.priority,
                    "estimated_duration": 0.5,  # Default 30 min per step
                    "dependencies": [tasks[-1]["name"]] if i > 0 else []
                })
        
        return tasks
    
    async def _ai_breakdown(
        self,
        objective: Objective
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Use AI to intelligently break down an objective into tasks.
        
        Args:
            objective: Objective to break down
            
        Returns:
            List of task dictionaries or None if AI unavailable
        """
        if not self.ask_ai:
            return None
        
        # Use evolved prompt if available (prompt_evolver from Elysia/Guardian)
        prompt_evolver = getattr(self, "prompt_evolver", None)
        system_prompt = None
        if prompt_evolver and hasattr(prompt_evolver, "get_evolved_prompt"):
            evolved = prompt_evolver.get_evolved_prompt("planning")
            if evolved:
                system_prompt = evolved
        
        # Create prompt for AI breakdown
        prompt = f"""Break down this objective into specific, actionable tasks:

Objective: {objective.name}
Description: {objective.description}
Priority: {objective.priority}/10
Deadline: {objective.deadline.isoformat() if objective.deadline else 'None'}

Provide a JSON array of tasks, each with:
- name: Short task name
- description: Detailed description
- estimated_duration: Estimated hours (float)
- dependencies: Array of task names this depends on (can be empty)
- priority: Task priority (1-10, inherit from objective if similar)

Return ONLY valid JSON array, no markdown or explanation."""

        try:
            response = await self.ask_ai.ask_async(
                prompt=prompt,
                provider=AIProvider.OPENAI,
                temperature=0.3,  # Lower temperature for more consistent structure
                max_tokens=2000,
                system_prompt=system_prompt,
            )
            
            if not response.success:
                logger.warning(f"AI breakdown failed: {response.error}")
                return None
            
            # Parse JSON response
            import json
            import re
            
            # Extract JSON from response (handle markdown code blocks)
            content = response.content.strip()
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = content
            
            tasks_data = json.loads(json_str)
            
            # Validate and normalize tasks
            normalized_tasks = []
            for task_data in tasks_data:
                # Ensure required fields
                normalized_task = {
                    "name": task_data.get("name", "Unnamed Task"),
                    "description": task_data.get("description", ""),
                    "priority": task_data.get("priority", objective.priority),
                    "estimated_duration": float(task_data.get("estimated_duration", 1.0)),
                    "dependencies": task_data.get("dependencies", [])
                }
                normalized_tasks.append(normalized_task)
            
            logger.info(f"AI breakdown generated {len(normalized_tasks)} tasks for {objective.name}")
            return normalized_tasks
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI breakdown JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in AI breakdown: {e}")
            return None
    
    def _create_task_from_breakdown(
        self,
        objective_id: str,
        task_data: Dict[str, Any]
    ) -> str:
        """Create a PlannedTask from breakdown data."""
        task_id = str(uuid.uuid4())
        
        # Resolve dependency task IDs by name
        dependency_ids = []
        for dep_name in task_data.get("dependencies", []):
            for task in self.planned_tasks.values():
                if task.name == dep_name:
                    dependency_ids.append(task.task_id)
                    break
        
        task = PlannedTask(
            task_id=task_id,
            objective_id=objective_id,
            name=task_data["name"],
            description=task_data["description"],
            priority=task_data.get("priority", 5),
            dependencies=dependency_ids,
            estimated_duration=task_data.get("estimated_duration"),
            deadline=self.objectives[objective_id].deadline,
            metadata=task_data.get("metadata", {})
        )
        
        self.planned_tasks[task_id] = task
        return task_id

    async def _run_planned_task_body(self, ptask: PlannedTask) -> Dict[str, Any]:
        """
        Execute one planned task inside the runtime loop worker.

        Today: structured log + return completion payload. Extend here to dispatch on
        ``metadata`` (e.g. ``planner_action``, ``capability``, ``analysis_kind``).
        """
        logger.info(
            "LongTermPlanner executing task_id=%s name=%s objective=%s",
            ptask.task_id,
            ptask.name,
            ptask.objective_id,
        )
        meta = ptask.metadata if isinstance(ptask.metadata, dict) else {}
        action = str(meta.get("planner_action") or meta.get("action") or "").strip()
        if action:
            logger.info("LongTermPlanner task metadata action=%s", action[:200])
        return {
            "task_id": ptask.task_id,
            "status": "completed",
            "name": ptask.name,
            "objective_id": ptask.objective_id,
        }

    def submit_tasks_to_runtime(
        self,
        objective_id: Optional[str] = None,
        task_ids: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Submit planned tasks to RuntimeLoop for execution.
        
        Args:
            objective_id: Submit all tasks for this objective
            task_ids: Submit specific task IDs
            
        Returns:
            Dictionary mapping task_id -> runtime_task_id
        """
        if not self.runtime_loop:
            raise ValueError("RuntimeLoop not configured")

        self.sync_runtime_task_states(objective_id=objective_id)
        self.repair_orphaned_runtime_tasks(objective_id=objective_id)
        
        if objective_id:
            objective = self.objectives.get(objective_id)
            if not objective:
                raise ValueError(f"Objective {objective_id} not found")
            task_ids = objective.tasks
        
        if not task_ids:
            return {}
        
        submitted = {}
        
        for task_id in task_ids:
            planned_task = self.planned_tasks.get(task_id)
            if not planned_task:
                continue

            metadata = planned_task.metadata if isinstance(planned_task.metadata, dict) else {}
            runtime_task_id = str(metadata.get("runtime_task_id") or "").strip()
            if runtime_task_id and hasattr(self.runtime_loop, "get_task_status"):
                try:
                    runtime_status = self.runtime_loop.get_task_status(runtime_task_id)
                except Exception:
                    runtime_status = None
                mapped = _planner_task_status_from_runtime(runtime_status, runtime_bound=True)
                if mapped is not None and mapped != planned_task.status:
                    planned_task.status = mapped
                    planned_task.metadata["runtime_last_status"] = mapped.value
                    planned_task.metadata["runtime_last_sync_at"] = datetime.now().isoformat()

            if planned_task.status != TaskStatus.PENDING:
                logger.debug(f"Task {task_id} already submitted/completed")
                continue

            # Create a callable function for the task
            def make_task_func(ptask: PlannedTask):
                """Create a task function from PlannedTask."""
                planner = self

                async def task_func():
                    return await planner._run_planned_task_body(ptask)

                return task_func
            
            # Submit to runtime loop
            runtime_task_id = self.runtime_loop.submit_task(
                func=make_task_func(planned_task),
                priority=planned_task.priority,
                module="longterm_planner",
                dependencies=planned_task.dependencies,
                deadline=planned_task.deadline
            )
            
            planned_task.status = TaskStatus.IN_PROGRESS
            planned_task.metadata["runtime_task_id"] = runtime_task_id
            planned_task.metadata["runtime_last_status"] = TaskStatus.IN_PROGRESS.value
            planned_task.metadata["runtime_submitted_at"] = datetime.now().isoformat()
            submitted[task_id] = runtime_task_id
            
            logger.info(f"Submitted task {task_id} ({planned_task.name}) to RuntimeLoop")
        
        self.save()
        return submitted

    def suggest_from_introspection(
        self,
        context: Dict[str, Any],
        memory: Optional[Any] = None,
        max_active_objectives: int = 5,
    ) -> Optional[str]:
        """
        Suggest and add an objective based on introspection context (focus, pattern).
        Called by GuardianCore when introspection suggests continue_mission.
        """
        active = sum(1 for o in self.objectives.values() if o.status == ObjectiveStatus.ACTIVE)
        if active >= max_active_objectives:
            return None
        focus = context.get("focus", "general")
        pattern = context.get("pattern", "unknown")
        focus_to_objective = {
            "learning": ("Expand Knowledge", "Gather and integrate new information from learning sources"),
            "mission": ("Advance Mission", "Continue progress on active mission goals"),
            "creativity": ("Creative Exploration", "Explore creative ideas and dream cycles"),
            "safety": ("Safety Review", "Review and reinforce safety validation"),
            "task": ("Task Completion", "Complete pending high-priority tasks"),
        }
        name, desc = focus_to_objective.get(focus, ("System Improvement", f"Advance work in {focus} area"))
        objective_id = self.add_objective(name=name, description=desc, priority=6, metadata={"introspection": True, "focus": focus, "pattern": pattern})
        if memory and hasattr(memory, "remember"):
            try:
                memory.remember(
                    f"[LongTermPlanner] Suggested objective from introspection: {name}",
                    category="introspection",
                    priority=0.6,
                    metadata={"objective_id": objective_id, "focus": focus},
                )
            except Exception:
                pass
        return objective_id

    def update_task_status(self, task_id: str, status: TaskStatus):
        """Update status of a planned task."""
        task = self.planned_tasks.get(task_id)
        if task:
            task.status = status
            self._refresh_objective_status(task.objective_id)
            self.save()
    
    def get_objective(self, objective_id: str) -> Optional[Objective]:
        """Get an objective by ID."""
        return self.objectives.get(objective_id)
    
    def get_task(self, task_id: str) -> Optional[PlannedTask]:
        """Get a planned task by ID."""
        return self.planned_tasks.get(task_id)
    
    def list_objectives(
        self,
        status: Optional[ObjectiveStatus] = None
    ) -> List[Objective]:
        """List objectives, optionally filtered by status."""
        self.sync_runtime_task_states()
        if status:
            return [obj for obj in self.objectives.values() if obj.status == status]
        return list(self.objectives.values())

    def list_active_objectives(self) -> List[Objective]:
        """Convenience alias for objectives with ACTIVE status (matches simpler planner API)."""
        return self.list_objectives(status=ObjectiveStatus.ACTIVE)
    
    def get_objective_progress(self, objective_id: str) -> Dict[str, Any]:
        """Get progress information for an objective."""
        self.sync_runtime_task_states(objective_id=objective_id)
        objective = self.objectives.get(objective_id)
        if not objective:
            return {}
        
        task_statuses = {
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "blocked": 0,
            "cancelled": 0
        }
        
        for task_id in objective.tasks:
            task = self.planned_tasks.get(task_id)
            if task:
                status_key = task.status.value
                if status_key in task_statuses:
                    task_statuses[status_key] += 1
        
        total_tasks = len(objective.tasks)
        completed_tasks = task_statuses["completed"]
        progress_percent = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        return {
            "objective_id": objective_id,
            "name": objective.name,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "progress_percent": progress_percent,
            "task_statuses": task_statuses,
            "status": objective.status.value,
            "deadline": objective.deadline.isoformat() if objective.deadline else None
        }
    
    def save(self):
        """Save objectives and tasks to disk."""
        data = {
            "objectives": [obj.to_dict() for obj in self.objectives.values()],
            "tasks": [task.to_dict() for task in self.planned_tasks.values()],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.debug(f"Saved planner data to {self.storage_path}")
    
    def load(self):
        """Load objectives and tasks from disk."""
        if not self.storage_path.exists():
            logger.info(f"No existing planner data found at {self.storage_path}")
            # Initialize with default objectives if no data exists
            self._initialize_default_objectives()
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            # Load objectives
            for obj_data in data.get("objectives", []):
                objective = Objective.from_dict(obj_data)
                self.objectives[objective.objective_id] = objective
            
            # Load tasks
            for task_data in data.get("tasks", []):
                task = PlannedTask.from_dict(task_data)
                self.planned_tasks[task.task_id] = task
            
            logger.info(f"Loaded {len(self.objectives)} objectives and {len(self.planned_tasks)} tasks")

            self.prune_smoke_test_objectives()
            
            # If no objectives loaded, initialize defaults
            if len(self.objectives) == 0:
                self._initialize_default_objectives()
        except Exception as e:
            logger.error(f"Error loading planner data: {e}")
            # Initialize defaults on error
            self._initialize_default_objectives()
    
    def _initialize_default_objectives(self):
        """Initialize with default objectives if no data exists"""
        try:
            default_objectives = [
                {
                    "name": "System Optimization",
                    "description": "Continuously optimize system performance, memory usage, and response times",
                    "priority": 7
                },
                {
                    "name": "Knowledge Acquisition",
                    "description": "Actively learn from interactions, web sources, and user feedback to expand knowledge base",
                    "priority": 8
                },
                {
                    "name": "Safety & Trust Maintenance",
                    "description": "Maintain high safety standards and trust levels across all system components",
                    "priority": 9
                },
                {
                    "name": "Income Generation",
                    "description": "Explore and implement income generation strategies using available APIs and services",
                    "priority": 6
                },
                {
                    "name": "User Experience Enhancement",
                    "description": "Improve user interactions, interface responsiveness, and overall user satisfaction",
                    "priority": 7
                }
            ]
            
            for obj_data in default_objectives:
                self.add_objective(
                    name=obj_data["name"],
                    description=obj_data["description"],
                    priority=obj_data["priority"]
                )
            
            logger.info(f"Initialized {len(default_objectives)} default objectives")
        except Exception as e:
            logger.error(f"Error initializing default objectives: {e}")


# Example usage
if __name__ == "__main__":
    import asyncio
    from runtime_loop_core import RuntimeLoop
    
    async def test_planner():
        """Test the LongTermPlanner."""
        runtime = RuntimeLoop()
        runtime.start()
        
        planner = LongTermPlanner(runtime_loop=runtime)
        
        # Add an objective
        obj_id = planner.add_objective(
            name="Implement Elysia Core Features",
            description="Complete core infrastructure. Add memory system. Integrate trust evaluation.",
            priority=8,
            deadline=datetime.now() + timedelta(days=30)
        )
        
        # Break it down
        task_ids = planner.breakdown_objective(obj_id)
        print(f"Created {len(task_ids)} tasks from objective")
        
        # Submit to runtime
        submitted = planner.submit_tasks_to_runtime(objective_id=obj_id)
        print(f"Submitted {len(submitted)} tasks to RuntimeLoop")
        
        # Check progress
        progress = planner.get_objective_progress(obj_id)
        print(f"Objective progress: {progress}")
        
        await asyncio.sleep(2)
        
        # Stop
        runtime.stop()
    
    asyncio.run(test_planner())

