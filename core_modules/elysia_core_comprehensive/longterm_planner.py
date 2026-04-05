"""
Long Term Planner - Goal-oriented planning and task decomposition
Integrated from old modules.
"""

import datetime
import logging
from typing import Dict, List, Any, Optional


class LongTermPlanner:
    """
    Long-term planning system that breaks objectives into tasks.
    Integrates with runtime loop for task scheduling.
    """
    
    def __init__(self, runtime_loop=None, prompt_evolver=None, **kwargs):
        """
        Initialize Long Term Planner.
        
        Args:
            runtime_loop: Optional runtime loop instance for task scheduling
            prompt_evolver: Optional PromptEvolver from Guardian (reserved for future integration)
        """
        if kwargs:
            logging.debug("LongTermPlanner: ignoring unused init kwargs: %s", list(kwargs.keys()))
        self.runtime_loop = runtime_loop
        self.prompt_evolver = prompt_evolver
        self.objectives = []  # list of objective dicts (elysia_sub_modules / Guardian may use dict keyed by id elsewhere)
        self.task_history = []
    
    def add_objective(self, name: str, description: str, deadline: Optional[datetime.datetime] = None, 
                     priority: float = 0.5) -> str:
        """
        Add a new objective.
        
        Args:
            name: Objective name
            description: Objective description
            deadline: Optional deadline datetime
            priority: Priority (0.0 to 1.0)
        
        Returns:
            Status message
        """
        objective = {
            "name": name,
            "description": description,
            "deadline": deadline,
            "priority": priority,
            "created": datetime.datetime.now(),
            "status": "active"
        }
        self.objectives.append(objective)
        logging.info(f"Added objective: {name}")
        return f"Objective '{name}' added."
    
    def break_into_tasks(self, objective: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Break an objective into actionable tasks.
        
        Args:
            objective: Objective dictionary
        
        Returns:
            List of task dictionaries
        """
        name = objective["name"]
        description = objective["description"]
        priority = objective.get("priority", 0.5)
        
        # Simple task decomposition based on objective type
        tasks = []
        
        # Detect objective type from description/keywords
        desc_lower = description.lower()
        
        if any(word in desc_lower for word in ["build", "create", "develop", "make"]):
            tasks = [
                {
                    "task_type": "planning",
                    "context": {"prompt": f"Create detailed plan for: {name}"},
                    "urgency": priority,
                    "description": f"Plan {name}"
                },
                {
                    "task_type": "implementation",
                    "context": {"prompt": f"Implement: {description}"},
                    "urgency": priority * 0.9,
                    "description": f"Implement {name}"
                },
                {
                    "task_type": "testing",
                    "context": {"prompt": f"Test: {name}"},
                    "urgency": priority * 0.8,
                    "description": f"Test {name}"
                }
            ]
        elif any(word in desc_lower for word in ["research", "learn", "study", "analyze"]):
            tasks = [
                {
                    "task_type": "research",
                    "context": {"topic": description, "prompt": f"Research: {description}"},
                    "urgency": priority,
                    "description": f"Research {name}"
                },
                {
                    "task_type": "synthesis",
                    "context": {"prompt": f"Synthesize findings for: {name}"},
                    "urgency": priority * 0.9,
                    "description": f"Synthesize {name}"
                }
            ]
        elif any(word in desc_lower for word in ["write", "document", "create content"]):
            tasks = [
                {
                    "task_type": "text-gen",
                    "context": {"prompt": f"Draft content for: {name}\n{description}"},
                    "urgency": priority,
                    "description": f"Draft {name}"
                },
                {
                    "task_type": "editing",
                    "context": {"prompt": f"Edit and refine: {name}"},
                    "urgency": priority * 0.8,
                    "description": f"Edit {name}"
                }
            ]
        else:
            # Generic task breakdown
            tasks = [
                {
                    "task_type": "general",
                    "context": {"prompt": f"Work on: {name}\n{description}"},
                    "urgency": priority,
                    "description": f"Work on {name}"
                }
            ]
        
        return tasks
    
    def schedule_objective(self, name: str) -> str:
        """
        Schedule an objective by breaking it into tasks and adding to runtime loop.
        
        Args:
            name: Objective name
        
        Returns:
            Status message
        """
        target = next(
            (obj for obj in self.objectives if obj["name"] == name and obj["status"] == "active"),
            None
        )
        
        if not target:
            return f"Objective '{name}' not found or already completed."
        
        tasks = self.break_into_tasks(target)
        
        # Add tasks to runtime loop if available
        if self.runtime_loop:
            for task in tasks:
                if hasattr(self.runtime_loop, 'add_task'):
                    self.runtime_loop.add_task(
                        task["task_type"],
                        task["context"],
                        urgency=task["urgency"]
                    )
                elif hasattr(self.runtime_loop, 'enqueue_task'):
                    self.runtime_loop.enqueue_task(task)
                else:
                    logging.warning("Runtime loop doesn't support task addition")
        
        # Log task history
        for task in tasks:
            self.task_history.append({
                "objective": name,
                "task": task,
                "scheduled_at": datetime.datetime.now()
            })
        
        logging.info(f"Scheduled {len(tasks)} tasks for objective '{name}'")
        return f"Scheduled {len(tasks)} tasks for objective '{name}'."
    
    def mark_complete(self, name: str) -> str:
        """
        Mark an objective as complete.
        
        Args:
            name: Objective name
        
        Returns:
            Status message
        """
        for obj in self.objectives:
            if obj["name"] == name:
                obj["status"] = "completed"
                obj["completed_at"] = datetime.datetime.now()
                logging.info(f"Objective '{name}' marked as complete")
                return f"Objective '{name}' marked as complete."
        return f"Objective '{name}' not found."
    
    def get_objective(self, name: str) -> Optional[Dict[str, Any]]:
        """Get objective by name"""
        return next((obj for obj in self.objectives if obj["name"] == name), None)
    
    def list_active_objectives(self) -> List[Dict[str, Any]]:
        """List all active objectives"""
        return [obj for obj in self.objectives if obj["status"] == "active"]
    
    def list_completed_objectives(self) -> List[Dict[str, Any]]:
        """List all completed objectives"""
        return [obj for obj in self.objectives if obj["status"] == "completed"]
    
    def export_plan(self) -> Dict[str, Any]:
        """
        Export complete plan as dictionary.
        
        Returns:
            Plan dictionary with objectives and task history
        """
        return {
            "active_objectives": self.list_active_objectives(),
            "completed_objectives": self.list_completed_objectives(),
            "task_history": self.task_history[-50:],  # Last 50 tasks
            "total_objectives": len(self.objectives),
            "exported_at": str(datetime.datetime.now())
        }


# Example usage
if __name__ == "__main__":
    class DummyRuntime:
        """Dummy runtime loop for testing"""
        def add_task(self, task_type, context, urgency=0.5):
            print(f"[Runtime] Task added: {task_type} – Urgency: {urgency}")
            print(f"  Context: {context}")
    
    loop = DummyRuntime()
    planner = LongTermPlanner(loop)
    
    # Add objectives
    print(planner.add_objective(
        "Build Control Panel",
        "Develop user-facing UI to manage Elysia's modules.",
        priority=0.9
    ))
    
    print(planner.add_objective(
        "Research AI Safety",
        "Study best practices for AI safety and alignment.",
        priority=0.7
    ))
    
    # Schedule an objective
    print("\n" + planner.schedule_objective("Build Control Panel"))
    
    # Export plan
    print("\n=== Plan Export ===")
    import json
    print(json.dumps(planner.export_plan(), indent=2, default=str))

