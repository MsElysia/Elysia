# project_guardian/runtime_bootstrap.py
# RuntimeBootstrap: Startup Tracking and Initialization
# Based on Elysia Part 3 designs

import logging
import json
import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

try:
    from .runtime_loop_core import RuntimeLoop
    from .heartbeat import Heartbeat
except ImportError:
    from runtime_loop_core import RuntimeLoop
    from heartbeat import Heartbeat

logger = logging.getLogger(__name__)


class BootstrapStatus(Enum):
    """Bootstrap status levels."""
    PENDING = "pending"
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class BootstrapStep:
    """A single bootstrap step."""
    step_id: str
    name: str
    status: BootstrapStatus = BootstrapStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "dependencies": self.dependencies,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BootstrapStep":
        """Create BootstrapStep from dictionary."""
        return cls(
            step_id=data["step_id"],
            name=data["name"],
            status=BootstrapStatus(data.get("status", "pending")),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            duration_seconds=data.get("duration_seconds"),
            error=data.get("error"),
            dependencies=data.get("dependencies", []),
            metadata=data.get("metadata", {})
        )


class RuntimeBootstrap:
    """
    Startup tracking and initialization system.
    Manages system startup sequence, tracks initialization progress, and handles dependencies.
    """
    
    def __init__(
        self,
        runtime_loop: Optional[RuntimeLoop] = None,
        heartbeat: Optional[Heartbeat] = None,
        storage_path: str = "data/runtime_bootstrap.json"
    ):
        self.runtime_loop = runtime_loop
        self.heartbeat = heartbeat
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Bootstrap steps
        self.steps: Dict[str, BootstrapStep] = {}
        self.step_functions: Dict[str, Callable] = {}
        
        # Startup tracking
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.total_duration: Optional[float] = None
        
        # Status
        self.status: BootstrapStatus = BootstrapStatus.PENDING
        
        # History
        self.startup_history: List[Dict[str, Any]] = []
        
        self.load()
    
    def register_step(
        self,
        step_id: str,
        name: str,
        step_func: Callable,
        dependencies: Optional[List[str]] = None
    ):
        """
        Register a bootstrap step.
        
        Args:
            step_id: Unique step identifier
            name: Human-readable step name
            step_func: Function/coroutine to execute
            dependencies: List of step IDs that must complete first
        """
        step = BootstrapStep(
            step_id=step_id,
            name=name,
            dependencies=dependencies or []
        )
        
        self.steps[step_id] = step
        self.step_functions[step_id] = step_func
        
        logger.info(f"Registered bootstrap step: {name} (ID: {step_id})")
    
    def _check_dependencies(self, step_id: str) -> bool:
        """Check if all dependencies for a step are complete."""
        step = self.steps.get(step_id)
        if not step:
            return False
        
        for dep_id in step.dependencies:
            dep_step = self.steps.get(dep_id)
            if not dep_step:
                logger.warning(f"Dependency {dep_id} not found for step {step_id}")
                return False
            
            if dep_step.status != BootstrapStatus.COMPLETE:
                return False
        
        return True
    
    async def _execute_step(self, step_id: str) -> bool:
        """Execute a single bootstrap step."""
        step = self.steps.get(step_id)
        if not step:
            logger.error(f"Step {step_id} not found")
            return False
        
        step_func = self.step_functions.get(step_id)
        if not step_func:
            logger.error(f"Step function for {step_id} not found")
            step.status = BootstrapStatus.FAILED
            step.error = "Step function not found"
            return False
        
        # Check dependencies
        if not self._check_dependencies(step_id):
            logger.warning(f"Dependencies not met for step {step_id}")
            return False
        
        # Execute step
        step.status = BootstrapStatus.INITIALIZING
        step.started_at = datetime.now()
        
        try:
            if asyncio.iscoroutinefunction(step_func):
                result = await step_func()
            else:
                result = step_func()
            
            step.status = BootstrapStatus.COMPLETE
            step.completed_at = datetime.now()
            
            if step.started_at:
                step.duration_seconds = (step.completed_at - step.started_at).total_seconds()
            
            logger.info(f"Bootstrap step completed: {step.name} ({step.duration_seconds:.2f}s)")
            return True
            
        except Exception as e:
            step.status = BootstrapStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.now()
            
            if step.started_at:
                step.duration_seconds = (step.completed_at - step.started_at).total_seconds()
            
            logger.error(f"Bootstrap step failed: {step.name} - {e}")
            return False
    
    def _get_ready_steps(self) -> List[str]:
        """Get list of steps that are ready to execute (dependencies met)."""
        ready = []
        
        for step_id, step in self.steps.items():
            if step.status == BootstrapStatus.PENDING:
                if self._check_dependencies(step_id):
                    ready.append(step_id)
        
        return ready
    
    async def bootstrap(self, max_concurrent: int = 3) -> bool:
        """
        Execute all bootstrap steps in dependency order.
        
        Args:
            max_concurrent: Maximum number of steps to run concurrently
            
        Returns:
            True if all steps completed successfully
        """
        self.start_time = datetime.now()
        self.status = BootstrapStatus.INITIALIZING
        
        logger.info("Starting bootstrap sequence...")
        
        # Execute steps in waves based on dependencies
        remaining_steps = set(self.steps.keys())
        completed_steps = set()
        
        while remaining_steps:
            # Get ready steps
            ready_steps = [
                step_id for step_id in remaining_steps
                if step_id in self._get_ready_steps()
            ]
            
            if not ready_steps:
                # Check if we're stuck (no ready steps but still have remaining)
                stuck_steps = [
                    self.steps[step_id].name
                    for step_id in remaining_steps
                ]
                logger.error(f"Bootstrap stuck - no ready steps. Remaining: {stuck_steps}")
                self.status = BootstrapStatus.FAILED
                self.end_time = datetime.now()
                if self.start_time:
                    self.total_duration = (self.end_time - self.start_time).total_seconds()
                self.save()
                return False
            
            # Execute ready steps (up to max_concurrent)
            concurrent_steps = ready_steps[:max_concurrent]
            
            # Execute concurrently
            tasks = [self._execute_step(step_id) for step_id in concurrent_steps]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check results
            for i, step_id in enumerate(concurrent_steps):
                if isinstance(results[i], Exception):
                    logger.error(f"Exception in step {step_id}: {results[i]}")
                    self.steps[step_id].status = BootstrapStatus.FAILED
                    self.steps[step_id].error = str(results[i])
                
                if self.steps[step_id].status == BootstrapStatus.COMPLETE:
                    completed_steps.add(step_id)
                    remaining_steps.discard(step_id)
                elif self.steps[step_id].status == BootstrapStatus.FAILED:
                    # Failed step blocks bootstrap
                    logger.error(f"Bootstrap failed due to step: {step_id}")
                    self.status = BootstrapStatus.FAILED
                    self.end_time = datetime.now()
                    if self.start_time:
                        self.total_duration = (self.end_time - self.start_time).total_seconds()
                    self.save()
                    return False
        
        # All steps completed
        self.status = BootstrapStatus.COMPLETE
        self.end_time = datetime.now()
        if self.start_time:
            self.total_duration = (self.end_time - self.start_time).total_seconds()
        
        # Record in history
        self.startup_history.append({
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.total_duration,
            "status": self.status.value,
            "steps_count": len(self.steps),
            "completed_steps": len([s for s in self.steps.values() if s.status == BootstrapStatus.COMPLETE])
        })
        
        # Keep only last 50 startup records
        if len(self.startup_history) > 50:
            self.startup_history = self.startup_history[-50:]
        
        self.save()
        
        logger.info(f"Bootstrap complete in {self.total_duration:.2f}s ({len(self.steps)} steps)")
        return True
    
    def get_progress(self) -> Dict[str, Any]:
        """Get bootstrap progress information."""
        total_steps = len(self.steps)
        completed = len([s for s in self.steps.values() if s.status == BootstrapStatus.COMPLETE])
        failed = len([s for s in self.steps.values() if s.status == BootstrapStatus.FAILED])
        pending = len([s for s in self.steps.values() if s.status == BootstrapStatus.PENDING])
        initializing = len([s for s in self.steps.values() if s.status == BootstrapStatus.INITIALIZING])
        
        progress_percent = (completed / total_steps * 100) if total_steps > 0 else 0
        
        failed_steps = [
            {"step_id": s.step_id, "name": s.name, "error": s.error}
            for s in self.steps.values()
            if s.status == BootstrapStatus.FAILED
        ]
        
        return {
            "status": self.status.value,
            "progress_percent": progress_percent,
            "total_steps": total_steps,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "initializing": initializing,
            "failed_steps": failed_steps,
            "total_duration_seconds": self.total_duration,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }
    
    def get_step_status(self, step_id: str) -> Optional[BootstrapStep]:
        """Get status of a specific step."""
        return self.steps.get(step_id)
    
    def get_startup_history(self) -> List[Dict[str, Any]]:
        """Get startup history."""
        return self.startup_history
    
    def reset(self):
        """Reset bootstrap state for a fresh start."""
        self.start_time = None
        self.end_time = None
        self.total_duration = None
        self.status = BootstrapStatus.PENDING
        
        for step in self.steps.values():
            step.status = BootstrapStatus.PENDING
            step.started_at = None
            step.completed_at = None
            step.duration_seconds = None
            step.error = None
        
        self.save()
        logger.info("Bootstrap state reset")
    
    def save(self):
        """Save bootstrap data."""
        data = {
            "steps": {step_id: step.to_dict() for step_id, step in self.steps.items()},
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration": self.total_duration,
            "status": self.status.value,
            "startup_history": self.startup_history[-20:],  # Last 20
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def load(self):
        """Load bootstrap data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            # Load steps
            for step_id, step_data in data.get("steps", {}).items():
                step = BootstrapStep.from_dict(step_data)
                self.steps[step_id] = step
            
            # Load timing
            if data.get("start_time"):
                self.start_time = datetime.fromisoformat(data["start_time"])
            if data.get("end_time"):
                self.end_time = datetime.fromisoformat(data["end_time"])
            self.total_duration = data.get("total_duration")
            
            # Load status
            if data.get("status"):
                self.status = BootstrapStatus(data["status"])
            
            # Load history
            self.startup_history = data.get("startup_history", [])
            
            logger.info(f"Loaded {len(self.steps)} bootstrap steps")
        except Exception as e:
            logger.error(f"Error loading bootstrap data: {e}")


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_bootstrap():
        """Test the RuntimeBootstrap system."""
        bootstrap = RuntimeBootstrap()
        
        # Register some steps
        async def init_memory():
            await asyncio.sleep(0.1)
            return "Memory initialized"
        
        async def init_runtime():
            await asyncio.sleep(0.1)
            return "Runtime initialized"
        
        async def init_trust():
            await asyncio.sleep(0.1)
            return "Trust system initialized"
        
        async def init_heartbeat():
            await asyncio.sleep(0.1)
            return "Heartbeat initialized"
        
        bootstrap.register_step("memory", "Initialize Memory", init_memory)
        bootstrap.register_step("runtime", "Initialize Runtime", init_runtime)
        bootstrap.register_step("trust", "Initialize Trust System", init_trust, dependencies=["memory"])
        bootstrap.register_step("heartbeat", "Initialize Heartbeat", init_heartbeat, dependencies=["runtime"])
        
        # Execute bootstrap
        success = await bootstrap.bootstrap()
        
        # Get progress
        progress = bootstrap.get_progress()
        print(f"Bootstrap success: {success}")
        print(f"Progress: {progress}")
    
    asyncio.run(test_bootstrap())

