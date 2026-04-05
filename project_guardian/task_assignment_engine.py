# project_guardian/task_assignment_engine.py
# TaskAssignmentEngine: Route Tasks by Trust + Specialization
# Based on extracted Elysia designs

import logging
import json
import uuid
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from collections import defaultdict

try:
    from .runtime_loop_core import RuntimeLoop
except ImportError:
    from runtime_loop_core import RuntimeLoop

logger = logging.getLogger(__name__)


class TaskCategory(Enum):
    """Categories of tasks that can be assigned."""
    MUTATION = "mutation"
    UPTIME = "uptime"
    INCOME = "income"
    COGNITIVE = "cognitive"
    NETWORK = "network"
    GENERAL = "general"


@dataclass
class TrustScore:
    """Trust score for a node/module combination."""
    node_id: str
    module_name: str
    general_trust: float = 0.5  # 0.0-1.0
    mutation_trust: float = 0.5
    uptime_trust: float = 0.5
    income_trust: float = 0.5
    cognitive_trust: float = 0.5
    network_trust: float = 0.5
    last_updated: datetime = field(default_factory=datetime.now)
    success_count: int = 0
    failure_count: int = 0
    
    def get_category_trust(self, category: TaskCategory) -> float:
        """Get trust score for a specific category."""
        mapping = {
            TaskCategory.MUTATION: self.mutation_trust,
            TaskCategory.UPTIME: self.uptime_trust,
            TaskCategory.INCOME: self.income_trust,
            TaskCategory.COGNITIVE: self.cognitive_trust,
            TaskCategory.NETWORK: self.network_trust,
            TaskCategory.GENERAL: self.general_trust,
        }
        return mapping.get(category, self.general_trust)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "module_name": self.module_name,
            "general_trust": self.general_trust,
            "mutation_trust": self.mutation_trust,
            "uptime_trust": self.uptime_trust,
            "income_trust": self.income_trust,
            "cognitive_trust": self.cognitive_trust,
            "network_trust": self.network_trust,
            "last_updated": self.last_updated.isoformat(),
            "success_count": self.success_count,
            "failure_count": self.failure_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrustScore":
        """Create TrustScore from dictionary."""
        return cls(
            node_id=data["node_id"],
            module_name=data["module_name"],
            general_trust=data.get("general_trust", 0.5),
            mutation_trust=data.get("mutation_trust", 0.5),
            uptime_trust=data.get("uptime_trust", 0.5),
            income_trust=data.get("income_trust", 0.5),
            cognitive_trust=data.get("cognitive_trust", 0.5),
            network_trust=data.get("network_trust", 0.5),
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.now().isoformat())),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0)
        )


@dataclass
class NodeCapability:
    """Capabilities and specialization of a node."""
    node_id: str
    specializations: List[TaskCategory] = field(default_factory=list)
    max_concurrent_tasks: int = 5
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TrustRegistry:
    """
    Simple Trust Registry implementation.
    Tracks trust scores per node per module/category.
    """
    
    def __init__(self, storage_path: str = "data/trust_registry.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.scores: Dict[Tuple[str, str], TrustScore] = {}  # (node_id, module) -> TrustScore
        self.load()
    
    def get_trust(
        self,
        node_id: str,
        module_name: str = "general",
        category: Optional[TaskCategory] = None
    ) -> float:
        """Get trust score for a node/module/category."""
        key = (node_id, module_name)
        score = self.scores.get(key)
        
        if not score:
            # Initialize with default
            score = TrustScore(node_id=node_id, module_name=module_name)
            self.scores[key] = score
        
        if category:
            return score.get_category_trust(category)
        return score.general_trust
    
    def update_trust(
        self,
        node_id: str,
        module_name: str,
        success: bool,
        category: Optional[TaskCategory] = None
    ):
        """Update trust score based on task outcome."""
        key = (node_id, module_name)
        score = self.scores.get(key)
        
        if not score:
            score = TrustScore(node_id=node_id, module_name=module_name)
            self.scores[key] = score
        
        # Update success/failure counts
        if success:
            score.success_count += 1
        else:
            score.failure_count += 1
        
        # Calculate new trust (simple weighted average)
        total = score.success_count + score.failure_count
        if total > 0:
            new_trust = score.success_count / total
            
            # Update category-specific trust if provided
            if category:
                if category == TaskCategory.MUTATION:
                    score.mutation_trust = new_trust
                elif category == TaskCategory.UPTIME:
                    score.uptime_trust = new_trust
                elif category == TaskCategory.INCOME:
                    score.income_trust = new_trust
                elif category == TaskCategory.COGNITIVE:
                    score.cognitive_trust = new_trust
                elif category == TaskCategory.NETWORK:
                    score.network_trust = new_trust
            else:
                score.general_trust = new_trust
        
        score.last_updated = datetime.now()
        self.save()
    
    def get_all_nodes(self) -> List[str]:
        """Get list of all registered node IDs."""
        return list(set(node_id for node_id, _ in self.scores.keys()))
    
    def get_node_scores(self, node_id: str) -> List[TrustScore]:
        """Get all trust scores for a node."""
        return [
            score for (nid, _), score in self.scores.items()
            if nid == node_id
        ]
    
    def save(self):
        """Save trust registry to disk."""
        data = {
            "scores": [
                score.to_dict()
                for score in self.scores.values()
            ],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load trust registry from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            for score_data in data.get("scores", []):
                score = TrustScore.from_dict(score_data)
                key = (score.node_id, score.module_name)
                self.scores[key] = score
            
            logger.info(f"Loaded {len(self.scores)} trust scores")
        except Exception as e:
            logger.error(f"Error loading trust registry: {e}")


class TaskAssignmentEngine:
    """
    Routes tasks to subnodes based on trust scores and specialization.
    Implements trial task system for low-trust nodes.
    """
    
    def __init__(
        self,
        runtime_loop: Optional[RuntimeLoop] = None,
        trust_registry: Optional[TrustRegistry] = None,
        min_trust_for_assignment: float = 0.3,
        trial_task_probability: float = 0.1  # 10% chance for low-trust nodes
    ):
        self.runtime_loop = runtime_loop
        self.trust_registry = trust_registry or TrustRegistry()
        self.min_trust_for_assignment = min_trust_for_assignment
        self.trial_task_probability = trial_task_probability
        
        # Node registry with capabilities
        self.nodes: Dict[str, NodeCapability] = {}
        
        # Assignment history
        self.assignment_history: List[Dict[str, Any]] = []
    
    def register_node(
        self,
        node_id: str,
        specializations: List[TaskCategory],
        max_concurrent_tasks: int = 5,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Register a node with its capabilities."""
        self.nodes[node_id] = NodeCapability(
            node_id=node_id,
            specializations=specializations,
            max_concurrent_tasks=max_concurrent_tasks,
            capabilities=capabilities or [],
            metadata=metadata or {}
        )
        logger.info(f"Registered node: {node_id} with specializations: {[s.value for s in specializations]}")
    
    def assign_task(
        self,
        task_func: Any,
        task_args: tuple = (),
        task_kwargs: dict = None,
        category: TaskCategory = TaskCategory.GENERAL,
        module_name: str = "unknown",
        priority: int = 5,
        required_capabilities: Optional[List[str]] = None,
        allow_trial: bool = True
    ) -> Optional[str]:
        """
        Assign a task to the best available node.
        
        Args:
            task_func: Function/coroutine to execute
            task_args: Positional arguments
            task_kwargs: Keyword arguments
            category: Task category
            module_name: Module name
            priority: Task priority (1-10)
            required_capabilities: Required node capabilities
            allow_trial: Allow trial tasks for low-trust nodes
            
        Returns:
            Task ID if assigned, None if no suitable node found
        """
        # Find suitable nodes
        candidates = self._find_candidates(
            category=category,
            required_capabilities=required_capabilities
        )
        
        if not candidates:
            logger.warning(f"No suitable nodes found for task category: {category.value}")
            return None
        
        # Select best node
        selected_node = self._select_best_node(
            candidates=candidates,
            category=category,
            module_name=module_name,
            allow_trial=allow_trial
        )
        
        if not selected_node:
            logger.warning("Failed to select node for task assignment")
            return None
        
        node_id, trust_score = selected_node
        
        # Submit task to runtime loop with node attribution
        if not self.runtime_loop:
            logger.error("RuntimeLoop not configured")
            return None
        
        task_id = self.runtime_loop.submit_task(
            func=task_func,
            args=task_args,
            kwargs=task_kwargs or {},
            priority=priority,
            module=f"{module_name}@{node_id}",  # Include node in module name
        )
        
        # Log assignment
        assignment = {
            "task_id": task_id,
            "node_id": node_id,
            "category": category.value,
            "module": module_name,
            "trust_score": trust_score,
            "timestamp": datetime.now().isoformat(),
            "priority": priority
        }
        self.assignment_history.append(assignment)
        
        logger.info(f"Assigned task {task_id} to node {node_id} (trust: {trust_score:.2f}, category: {category.value})")
        
        return task_id
    
    def _find_candidates(
        self,
        category: TaskCategory,
        required_capabilities: Optional[List[str]] = None
    ) -> List[Tuple[str, NodeCapability]]:
        """
        Find candidate nodes for a task.
        
        Returns:
            List of (node_id, NodeCapability) tuples
        """
        candidates = []
        
        for node_id, capability in self.nodes.items():
            # Check if node has required capabilities
            if required_capabilities:
                if not all(cap in capability.capabilities for cap in required_capabilities):
                    continue
            
            # Prefer nodes with matching specialization
            if category in capability.specializations:
                candidates.append((node_id, capability))
            # Also include nodes with general capability
            elif TaskCategory.GENERAL in capability.specializations:
                candidates.append((node_id, capability))
        
        return candidates
    
    def _select_best_node(
        self,
        candidates: List[Tuple[str, NodeCapability]],
        category: TaskCategory,
        module_name: str,
        allow_trial: bool
    ) -> Optional[Tuple[str, float]]:
        """
        Select the best node from candidates based on trust and specialization.
        
        Returns:
            (node_id, trust_score) tuple or None
        """
        import random
        
        scored_candidates = []
        
        for node_id, capability in candidates:
            trust = self.trust_registry.get_trust(
                node_id=node_id,
                module_name=module_name,
                category=category
            )
            
            # Check if trust is too low (unless trial allowed)
            if trust < self.min_trust_for_assignment:
                if allow_trial and random.random() < self.trial_task_probability:
                    # Trial task - give low-trust node a chance
                    logger.info(f"Trial task assignment to low-trust node {node_id} (trust: {trust:.2f})")
                else:
                    continue  # Skip this node
            
            # Calculate composite score
            # Higher trust = better
            # Specialization match = bonus
            specialization_bonus = 0.2 if category in capability.specializations else 0.0
            composite_score = trust + specialization_bonus
            
            scored_candidates.append((node_id, trust, composite_score))
        
        if not scored_candidates:
            return None
        
        # Sort by composite score (highest first)
        scored_candidates.sort(key=lambda x: x[2], reverse=True)
        
        # Select top candidate
        best_node_id, best_trust, _ = scored_candidates[0]
        return (best_node_id, best_trust)
    
    def record_task_outcome(
        self,
        task_id: str,
        success: bool,
        node_id: Optional[str] = None,
        category: Optional[TaskCategory] = None,
        module_name: Optional[str] = None
    ):
        """
        Record task outcome and update trust scores.
        
        Args:
            task_id: Task ID
            success: Whether task succeeded
            node_id: Node ID (extracted from assignment history if not provided)
            category: Task category (extracted if not provided)
            module_name: Module name (extracted if not provided)
        """
        # Find assignment in history
        assignment = None
        for assgn in reversed(self.assignment_history):
            if assgn["task_id"] == task_id:
                assignment = assgn
                break
        
        if not assignment:
            logger.warning(f"Task {task_id} not found in assignment history")
            return
        
        node_id = node_id or assignment.get("node_id")
        category_str = assignment.get("category")
        module_name = module_name or assignment.get("module")
        
        if not node_id:
            logger.warning(f"Cannot update trust: node_id not found for task {task_id}")
            return
        
        # Convert category string to enum
        category = category or TaskCategory(category_str) if category_str else None
        
        # Update trust registry
        self.trust_registry.update_trust(
            node_id=node_id,
            module_name=module_name or "unknown",
            success=success,
            category=category
        )
        
        logger.info(f"Updated trust for node {node_id}: success={success}, trust={self.trust_registry.get_trust(node_id, module_name, category):.2f}")
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Get statistics about task routing."""
        # Count assignments by node
        node_counts = defaultdict(int)
        category_counts = defaultdict(int)
        
        for assignment in self.assignment_history:
            node_counts[assignment["node_id"]] += 1
            category_counts[assignment["category"]] += 1
        
        return {
            "total_assignments": len(self.assignment_history),
            "nodes_registered": len(self.nodes),
            "assignments_by_node": dict(node_counts),
            "assignments_by_category": dict(category_counts),
            "registered_nodes": list(self.nodes.keys())
        }


# Example usage
if __name__ == "__main__":
    import asyncio
    from runtime_loop_core import RuntimeLoop
    
    async def test_assignment():
        """Test the TaskAssignmentEngine."""
        runtime = RuntimeLoop()
        runtime.start()
        
        engine = TaskAssignmentEngine(runtime_loop=runtime)
        
        # Register some nodes
        engine.register_node(
            node_id="node_alpha",
            specializations=[TaskCategory.COGNITIVE, TaskCategory.GENERAL],
            capabilities=["ai_reasoning", "text_generation"]
        )
        
        engine.register_node(
            node_id="node_beta",
            specializations=[TaskCategory.MUTATION, TaskCategory.NETWORK],
            capabilities=["code_analysis", "network_ops"]
        )
        
        # Simulate some successful tasks to build trust
        engine.trust_registry.update_trust("node_alpha", "cognitive", True, TaskCategory.COGNITIVE)
        engine.trust_registry.update_trust("node_alpha", "cognitive", True, TaskCategory.COGNITIVE)
        engine.trust_registry.update_trust("node_beta", "mutation", True, TaskCategory.MUTATION)
        
        # Assign a cognitive task
        async def cognitive_task():
            await asyncio.sleep(0.1)
            return "Cognitive task completed"
        
        task_id = engine.assign_task(
            task_func=cognitive_task,
            category=TaskCategory.COGNITIVE,
            module_name="cognitive",
            priority=7
        )
        
        print(f"Assigned cognitive task: {task_id}")
        
        await asyncio.sleep(1)
        
        # Record success
        engine.record_task_outcome(task_id, success=True)
        
        # Check stats
        stats = engine.get_routing_stats()
        print(f"Routing stats: {stats}")
        
        runtime.stop()
    
    asyncio.run(test_assignment())

