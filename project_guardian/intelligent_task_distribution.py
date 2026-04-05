# project_guardian/intelligent_task_distribution.py
# IntelligentTaskDistribution: ML-Based Task Routing to Network Nodes
# Based on Functional Elysia Network Code

import logging
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from threading import Lock
from dataclasses import dataclass, field, asdict
from enum import Enum

try:
    from .network_discovery import NetworkDiscovery, NetworkNode, NodeStatus
    from .trust_registry import TrustRegistry
    from .task_assignment_engine import TaskAssignmentEngine
except ImportError:
    from network_discovery import NetworkDiscovery, NetworkNode, NodeStatus
    from trust_registry import TrustRegistry
    from task_assignment_engine import TaskAssignmentEngine

logger = logging.getLogger(__name__)

# Optional ML dependencies
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("NumPy not available, using heuristic-based distribution")

try:
    from sklearn.ensemble import RandomForestRegressor
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn not available, using heuristic-based distribution")


@dataclass
class TaskDistribution:
    """Represents a task distribution assignment."""
    task_id: str
    task_type: str
    assigned_node_id: str
    assigned_at: datetime
    suitability_score: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "assigned_node_id": self.assigned_node_id,
            "assigned_at": self.assigned_at.isoformat(),
            "suitability_score": self.suitability_score,
            "reasoning": self.reasoning,
            "metadata": self.metadata
        }


class IntelligentTaskDistribution:
    """
    Intelligently distributes tasks across network nodes.
    Uses ML-based scoring when available, falls back to heuristic-based assignment.
    """
    
    def __init__(
        self,
        network_discovery: Optional[NetworkDiscovery] = None,
        trust_registry: Optional[TrustRegistry] = None,
        task_assignment: Optional[TaskAssignmentEngine] = None,
        storage_path: str = "data/task_distribution.json",
        use_ml: bool = True
    ):
        """
        Initialize IntelligentTaskDistribution.
        
        Args:
            network_discovery: NetworkDiscovery instance
            trust_registry: TrustRegistry instance
            task_assignment: TaskAssignmentEngine instance
            storage_path: Path to distribution history storage
            use_ml: Use ML model if available
        """
        self.network_discovery = network_discovery
        self.trust_registry = trust_registry
        self.task_assignment = task_assignment
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.use_ml = use_ml and HAS_SKLEARN and HAS_NUMPY
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Distribution history
        self.distribution_history: List[TaskDistribution] = []
        
        # Performance tracking (for ML training)
        self.performance_data: List[Dict[str, Any]] = []
        
        # ML model (if available)
        self.ml_model = None
        if self.use_ml:
            try:
                self.ml_model = RandomForestRegressor(n_estimators=50, random_state=42)
                self._train_model()
                logger.info("ML model initialized for task distribution")
            except Exception as e:
                logger.warning(f"Failed to initialize ML model: {e}")
                self.use_ml = False
        
        # Load history
        self.load()
    
    def distribute_task(
        self,
        task_id: str,
        task_type: str,
        task_data: Dict[str, Any],
        required_capabilities: Optional[List[str]] = None,
        priority: int = 5
    ) -> Optional[str]:
        """
        Distribute a task to the best available node.
        
        Args:
            task_id: Unique task identifier
            task_type: Type of task
            task_data: Task data dictionary
            required_capabilities: Required node capabilities
            priority: Task priority (1-10)
            
        Returns:
            Assigned node ID or None if no suitable node found
        """
        if not self.network_discovery:
            logger.error("NetworkDiscovery not available")
            return None
        
        # Get available nodes
        available_nodes = self.network_discovery.list_nodes(
            status=NodeStatus.ACTIVE,
            min_trust=0.3
        )
        
        if not available_nodes:
            logger.warning("No active nodes available")
            return None
        
        # Filter by capabilities if specified
        if required_capabilities:
            capable_nodes = []
            for node in available_nodes:
                if all(cap in node.capabilities for cap in required_capabilities):
                    capable_nodes.append(node)
            
            if not capable_nodes:
                logger.warning(f"No nodes with required capabilities: {required_capabilities}")
                return None
            
            available_nodes = capable_nodes
        
        # Score nodes for suitability
        node_scores = []
        for node in available_nodes:
            score, reasoning = self._score_node_for_task(node, task_type, task_data, priority)
            node_scores.append((node, score, reasoning))
        
        # Sort by score (highest first)
        node_scores.sort(key=lambda x: x[1], reverse=True)
        
        if not node_scores:
            logger.warning("No suitable nodes found")
            return None
        
        # Assign to best node
        best_node, best_score, reasoning = node_scores[0]
        assigned_node_id = best_node.node_id
        
        # Create distribution record
        distribution = TaskDistribution(
            task_id=task_id,
            task_type=task_type,
            assigned_node_id=assigned_node_id,
            assigned_at=datetime.now(),
            suitability_score=best_score,
            reasoning=reasoning,
            metadata={
                "required_capabilities": required_capabilities,
                "priority": priority,
                "node_address": best_node.address,
                "node_name": best_node.name
            }
        )
        
        with self._lock:
            self.distribution_history.append(distribution)
            
            # Keep only last 10000 distributions
            if len(self.distribution_history) > 10000:
                self.distribution_history = self.distribution_history[-10000:]
            
            self.save()
        
        logger.info(f"Task {task_id} assigned to node {assigned_node_id} (score: {best_score:.2f})")
        return assigned_node_id
    
    def _score_node_for_task(
        self,
        node: NetworkNode,
        task_type: str,
        task_data: Dict[str, Any],
        priority: int
    ) -> Tuple[float, str]:
        """
        Score a node for task suitability.
        
        Args:
            node: Node to score
            task_type: Task type
            task_data: Task data
            priority: Task priority
            
        Returns:
            (score, reasoning) tuple
        """
        score = 0.0
        factors = []
        
        # Base trust score (0-1)
        trust_score = node.trust_score
        score += trust_score * 0.4
        factors.append(f"trust:{trust_score:.2f}")
        
        # Node status bonus
        if node.status == NodeStatus.ACTIVE:
            score += 0.2
            factors.append("status:active")
        
        # ML-based scoring if available
        if self.use_ml and self.ml_model:
            try:
                ml_score = self._predict_suitability(node, task_type, task_data, priority)
                score += ml_score * 0.4
                factors.append(f"ml_prediction:{ml_score:.2f}")
            except Exception as e:
                logger.debug(f"ML prediction failed: {e}")
                # Fallback to heuristic
                heuristic_score = self._heuristic_score(node, task_type, priority)
                score += heuristic_score * 0.4
                factors.append(f"heuristic:{heuristic_score:.2f}")
        else:
            # Heuristic-based scoring
            heuristic_score = self._heuristic_score(node, task_type, priority)
            score += heuristic_score * 0.4
            factors.append(f"heuristic:{heuristic_score:.2f}")
        
        # Capability match bonus
        if node.capabilities:
            score += 0.1
            factors.append("has_capabilities")
        
        # Normalize to 0-1 range
        score = min(1.0, max(0.0, score))
        
        reasoning = f"Suitability: {score:.2f} ({', '.join(factors)})"
        return score, reasoning
    
    def _heuristic_score(
        self,
        node: NetworkNode,
        task_type: str,
        priority: int
    ) -> float:
        """
        Heuristic-based node scoring (fallback).
        
        Args:
            node: Node to score
            task_type: Task type
            priority: Task priority
            
        Returns:
            Heuristic score (0-1)
        """
        score = 0.5  # Base score
        
        # Trust-based adjustment
        score = node.trust_score * 0.7 + score * 0.3
        
        # Priority matching (high priority tasks prefer high trust nodes)
        if priority >= 7:
            # Weight trust more heavily for high priority
            score = node.trust_score * 0.9 + score * 0.1
        
        return score
    
    def _predict_suitability(
        self,
        node: NetworkNode,
        task_type: str,
        task_data: Dict[str, Any],
        priority: int
    ) -> float:
        """
        Use ML model to predict node suitability.
        
        Args:
            node: Node to evaluate
            task_type: Task type
            task_data: Task data
            priority: Task priority
            
        Returns:
            Predicted suitability score (0-1)
        """
        if not self.ml_model or not HAS_NUMPY:
            return 0.5
        
        try:
            # Extract features
            features = self._extract_features(node, task_type, task_data, priority)
            features_array = np.array([features])
            
            # Predict
            prediction = self.ml_model.predict(features_array)[0]
            
            # Normalize to 0-1
            return float(max(0.0, min(1.0, prediction)))
        except Exception as e:
            logger.debug(f"ML prediction error: {e}")
            return 0.5
    
    def _extract_features(
        self,
        node: NetworkNode,
        task_type: str,
        task_data: Dict[str, Any],
        priority: int
    ) -> List[float]:
        """
        Extract features for ML model.
        
        Args:
            node: Node
            task_type: Task type
            task_data: Task data
            priority: Priority
            
        Returns:
            Feature vector
        """
        features = [
            node.trust_score,
            float(priority) / 10.0,
            float(len(node.capabilities)) / 10.0,
            1.0 if node.status == NodeStatus.ACTIVE else 0.0,
            float(hash(task_type) % 100) / 100.0,  # Task type hash
            float(len(str(task_data))) / 1000.0,  # Task size proxy
        ]
        
        return features
    
    def _train_model(self):
        """Train ML model on historical performance data."""
        if not self.use_ml or not HAS_NUMPY:
            return
        
        if len(self.performance_data) < 10:
            logger.debug("Not enough performance data for training")
            return
        
        try:
            # Prepare training data
            X = []
            y = []
            
            for record in self.performance_data[-1000:]:  # Last 1000 records
                node_id = record.get("node_id")
                node = self.network_discovery.get_node(node_id) if self.network_discovery else None
                if not node:
                    continue
                
                features = self._extract_features(
                    node,
                    record.get("task_type", ""),
                    record.get("task_data", {}),
                    record.get("priority", 5)
                )
                
                # Target: success rate or performance metric
                target = record.get("success_rate", 0.5)
                
                X.append(features)
                y.append(target)
            
            if len(X) < 10:
                return
            
            # Train model
            X_array = np.array(X)
            y_array = np.array(y)
            
            self.ml_model.fit(X_array, y_array)
            logger.info(f"ML model trained on {len(X)} samples")
            
        except Exception as e:
            logger.warning(f"ML model training failed: {e}")
    
    def record_performance(
        self,
        task_id: str,
        node_id: str,
        success: bool,
        execution_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record task execution performance for ML training.
        
        Args:
            task_id: Task ID
            node_id: Node that executed the task
            success: Whether task succeeded
            execution_time: Execution time in seconds
            metadata: Additional metadata
        """
        # Find distribution record
        distribution = None
        for dist in self.distribution_history:
            if dist.task_id == task_id and dist.assigned_node_id == node_id:
                distribution = dist
                break
        
        if not distribution:
            return
        
        # Record performance
        record = {
            "task_id": task_id,
            "node_id": node_id,
            "task_type": distribution.task_type,
            "task_data": distribution.metadata.get("task_data", {}),
            "priority": distribution.metadata.get("priority", 5),
            "success": success,
            "execution_time": execution_time,
            "success_rate": 1.0 if success else 0.0,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        with self._lock:
            self.performance_data.append(record)
            
            # Keep only last 5000 records
            if len(self.performance_data) > 5000:
                self.performance_data = self.performance_data[-5000:]
        
        # Retrain model periodically
        if len(self.performance_data) % 100 == 0:
            self._train_model()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get task distribution statistics."""
        with self._lock:
            by_node = {}
            by_task_type = {}
            total_distributions = len(self.distribution_history)
            
            for dist in self.distribution_history:
                # By node
                node_id = dist.assigned_node_id
                by_node[node_id] = by_node.get(node_id, 0) + 1
                
                # By task type
                task_type = dist.task_type
                by_task_type[task_type] = by_task_type.get(task_type, 0) + 1
            
            return {
                "total_distributions": total_distributions,
                "distributions_by_node": by_node,
                "distributions_by_task_type": by_task_type,
                "performance_records": len(self.performance_data),
                "ml_enabled": self.use_ml,
                "ml_trained": self.ml_model is not None
            }
    
    def save(self):
        """Save distribution history."""
        with self._lock:
            # Save last 1000 distributions
            recent = self.distribution_history[-1000:] if len(self.distribution_history) > 1000 else self.distribution_history
            
            data = {
                "distributions": [dist.to_dict() for dist in recent],
                "performance_data": self.performance_data[-500:],  # Last 500
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save distribution history: {e}")
    
    def load(self):
        """Load distribution history."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                distributions_data = data.get("distributions", [])
                
                for dist_dict in distributions_data:
                    try:
                        distribution = TaskDistribution(
                            task_id=dist_dict["task_id"],
                            task_type=dist_dict["task_type"],
                            assigned_node_id=dist_dict["assigned_node_id"],
                            assigned_at=datetime.fromisoformat(dist_dict["assigned_at"]),
                            suitability_score=dist_dict["suitability_score"],
                            reasoning=dist_dict["reasoning"],
                            metadata=dist_dict.get("metadata", {})
                        )
                        self.distribution_history.append(distribution)
                    except Exception as e:
                        logger.error(f"Failed to load distribution: {e}")
                
                self.performance_data = data.get("performance_data", [])
            
            logger.info(f"Loaded {len(self.distribution_history)} distribution records")
        except Exception as e:
            logger.error(f"Failed to load distribution history: {e}")


# Example usage
if __name__ == "__main__":
    async def test_distribution():
        """Test IntelligentTaskDistribution."""
        # This would require NetworkDiscovery to be set up
        distribution = IntelligentTaskDistribution()
        
        # Distribute a task
        node_id = distribution.distribute_task(
            task_id="task_1",
            task_type="ai_generation",
            task_data={"prompt": "Generate response"},
            required_capabilities=["ai_generation"],
            priority=8
        )
        
        print(f"Task assigned to node: {node_id}")
        
        # Record performance
        distribution.record_performance(
            task_id="task_1",
            node_id=node_id,
            success=True,
            execution_time=2.5
        )
        
        # Get statistics
        stats = distribution.get_statistics()
        print(f"Distribution stats: {stats}")
    
    asyncio.run(test_distribution())

