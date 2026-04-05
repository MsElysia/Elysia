# project_guardian/trust_registry.py
# TrustRegistry: Node Reliability and Specialty Statistics
# Based on elysia 4 (Main Consolidation) designs

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from pathlib import Path
from threading import Lock, RLock
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TrustMetrics:
    """Trust metrics for a node."""
    node_id: str
    general_trust: float = 0.5  # 0.0-1.0
    mutation_trust: float = 0.5
    uptime_trust: float = 0.5
    income_trust: float = 0.5
    cognitive_trust: float = 0.5
    network_trust: float = 0.5
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    last_active: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_category_trust(self, category: str) -> float:
        """Get trust score for a specific category."""
        category_map = {
            "mutation": self.mutation_trust,
            "uptime": self.uptime_trust,
            "income": self.income_trust,
            "cognitive": self.cognitive_trust,
            "network": self.network_trust,
            "general": self.general_trust
        }
        return category_map.get(category.lower(), self.general_trust)
    
    def calculate_success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_tasks == 0:
            return 0.5  # Default neutral trust
        return self.successful_tasks / self.total_tasks
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "general_trust": self.general_trust,
            "mutation_trust": self.mutation_trust,
            "uptime_trust": self.uptime_trust,
            "income_trust": self.income_trust,
            "cognitive_trust": self.cognitive_trust,
            "network_trust": self.network_trust,
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrustMetrics":
        """Create TrustMetrics from dictionary."""
        return cls(
            node_id=data["node_id"],
            general_trust=data.get("general_trust", 0.5),
            mutation_trust=data.get("mutation_trust", 0.5),
            uptime_trust=data.get("uptime_trust", 0.5),
            income_trust=data.get("income_trust", 0.5),
            cognitive_trust=data.get("cognitive_trust", 0.5),
            network_trust=data.get("network_trust", 0.5),
            total_tasks=data.get("total_tasks", 0),
            successful_tasks=data.get("successful_tasks", 0),
            failed_tasks=data.get("failed_tasks", 0),
            last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else None,
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
            metadata=data.get("metadata", {})
        )


class TrustRegistry:
    """
    Tracks node reliability and specialty statistics.
    Manages trust scores across different categories and provides automated trust adjustment.
    """
    
    def __init__(
        self,
        storage_path: str = "data/trust_registry.json",
        trust_decay_rate: float = 0.01,  # Decay per day of inactivity
        min_trust: float = 0.0,
        max_trust: float = 1.0
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.trust_decay_rate = trust_decay_rate
        self.min_trust = min_trust
        self.max_trust = max_trust
        
        # Thread-safe storage (use RLock for reentrant locking)
        self._lock = RLock()
        self.nodes: Dict[str, TrustMetrics] = {}
        
        self.load()
        # Don't apply decay during initialization to avoid blocking
        # Decay will be applied on first use or explicitly
        # self._apply_decay()
    
    def register_node(
        self,
        node_id: str,
        initial_trust: float = 0.5,
        initial_category_trusts: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Register a new node in the trust registry.
        
        Args:
            node_id: Unique node identifier
            initial_trust: Initial general trust score
            initial_category_trusts: Optional category-specific trust scores
            metadata: Optional node metadata
            
        Returns:
            Node ID
        """
        with self._lock:
            if node_id in self.nodes:
                logger.warning(f"Node {node_id} already registered, updating...")
            
            node = self.nodes.get(node_id)
            if not node:
                node = TrustMetrics(
                    node_id=node_id,
                    general_trust=initial_trust,
                    metadata=metadata or {}
                )
            
            # Set category trusts
            if initial_category_trusts:
                for category, trust in initial_category_trusts.items():
                    if category == "mutation":
                        node.mutation_trust = trust
                    elif category == "uptime":
                        node.uptime_trust = trust
                    elif category == "income":
                        node.income_trust = trust
                    elif category == "cognitive":
                        node.cognitive_trust = trust
                    elif category == "network":
                        node.network_trust = trust
                    elif category == "general":
                        node.general_trust = trust
            
            node.last_active = datetime.now()
            self.nodes[node_id] = node
            self.save()
        
        logger.info(f"Registered node: {node_id} (trust: {initial_trust:.2f})")
        return node_id
    
    def get_trust(
        self,
        node_id: str,
        category: str = "general"
    ) -> float:
        """
        Get trust score for a node and category.
        
        Args:
            node_id: Node ID
            category: Trust category (mutation, uptime, income, cognitive, network, general)
            
        Returns:
            Trust score (0.0-1.0)
        """
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                # Return neutral trust for unknown nodes
                return 0.5
            
            return node.get_category_trust(category)
    
    def update_trust(
        self,
        node_id: str,
        success: bool,
        category: str = "general",
        amount: Optional[float] = None
    ):
        """
        Update trust score based on task outcome.
        
        Args:
            node_id: Node ID
            success: Whether the task succeeded
            category: Trust category
            amount: Optional fixed amount to adjust (if None, uses automatic calculation)
        """
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                # Auto-register node
                node = TrustMetrics(node_id=node_id)
                self.nodes[node_id] = node
            
            # Update task counts
            node.total_tasks += 1
            if success:
                node.successful_tasks += 1
            else:
                node.failed_tasks += 1
            
            # Calculate trust adjustment
            if amount is None:
                # Automatic adjustment based on success rate
                success_rate = node.calculate_success_rate()
                
                # Adjust trust towards success rate (weighted average)
                adjustment = (success_rate - node.get_category_trust(category)) * 0.1
            else:
                adjustment = amount
            
            # Apply adjustment to appropriate category
            if category == "mutation":
                node.mutation_trust = max(self.min_trust, min(self.max_trust, node.mutation_trust + adjustment))
            elif category == "uptime":
                node.uptime_trust = max(self.min_trust, min(self.max_trust, node.uptime_trust + adjustment))
            elif category == "income":
                node.income_trust = max(self.min_trust, min(self.max_trust, node.income_trust + adjustment))
            elif category == "cognitive":
                node.cognitive_trust = max(self.min_trust, min(self.max_trust, node.cognitive_trust + adjustment))
            elif category == "network":
                node.network_trust = max(self.min_trust, min(self.max_trust, node.network_trust + adjustment))
            else:
                node.general_trust = max(self.min_trust, min(self.max_trust, node.general_trust + adjustment))
            
            node.last_active = datetime.now()
            node.updated_at = datetime.now()
            self.save()
            
            logger.debug(f"Updated trust for {node_id} ({category}): {node.get_category_trust(category):.3f}")
    
    def _apply_decay(self):
        """Apply trust decay to inactive nodes."""
        now = datetime.now()
        
        with self._lock:
            for node in self.nodes.values():
                if node.last_active:
                    days_inactive = (now - node.last_active).days
                    if days_inactive > 0:
                        decay = self.trust_decay_rate * days_inactive
                        
                        # Apply decay to all categories
                        node.general_trust = max(self.min_trust, node.general_trust - decay)
                        node.mutation_trust = max(self.min_trust, node.mutation_trust - decay)
                        node.uptime_trust = max(self.min_trust, node.uptime_trust - decay)
                        node.income_trust = max(self.min_trust, node.income_trust - decay)
                        node.cognitive_trust = max(self.min_trust, node.cognitive_trust - decay)
                        node.network_trust = max(self.min_trust, node.network_trust - decay)
                        
                        node.updated_at = now
            
            self.save()
    
    def get_node(self, node_id: str) -> Optional[TrustMetrics]:
        """Get trust metrics for a node."""
        with self._lock:
            return self.nodes.get(node_id)
    
    def list_nodes(
        self,
        min_trust: Optional[float] = None,
        category: str = "general"
    ) -> List[TrustMetrics]:
        """List nodes, optionally filtered by minimum trust."""
        with self._lock:
            nodes = list(self.nodes.values())
            
            if min_trust is not None:
                nodes = [
                    node for node in nodes
                    if node.get_category_trust(category) >= min_trust
                ]
            
            return nodes
    
    def get_top_nodes(
        self,
        category: str = "general",
        limit: int = 10
    ) -> List[TrustMetrics]:
        """Get top nodes by trust score in a category."""
        nodes = self.list_nodes(category=category)
        nodes.sort(key=lambda n: n.get_category_trust(category), reverse=True)
        return nodes[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with self._lock:
            total_nodes = len(self.nodes)
            
            # Average trusts by category
            avg_trusts = defaultdict(float)
            category_counts = defaultdict(int)
            
            for node in self.nodes.values():
                for category in ["general", "mutation", "uptime", "income", "cognitive", "network"]:
                    trust = node.get_category_trust(category)
                    avg_trusts[category] += trust
                    category_counts[category] += 1
            
            for category in avg_trusts:
                if category_counts[category] > 0:
                    avg_trusts[category] /= category_counts[category]
            
            # Total tasks
            total_tasks = sum(node.total_tasks for node in self.nodes.values())
            total_successful = sum(node.successful_tasks for node in self.nodes.values())
            total_failed = sum(node.failed_tasks for node in self.nodes.values())
            
            overall_success_rate = total_successful / total_tasks if total_tasks > 0 else 0.0
            
            # Active nodes (active in last 24 hours)
            now = datetime.now()
            active_nodes = len([
                node for node in self.nodes.values()
                if node.last_active and (now - node.last_active).total_seconds() < 86400
            ])
            
            return {
                "total_nodes": total_nodes,
                "active_nodes": active_nodes,
                "average_trusts": dict(avg_trusts),
                "total_tasks": total_tasks,
                "successful_tasks": total_successful,
                "failed_tasks": total_failed,
                "overall_success_rate": overall_success_rate
            }
    
    def export_registry(self, filepath: Optional[str] = None) -> str:
        """Export registry to JSON file."""
        path = Path(filepath) if filepath else self.storage_path.parent / "trust_registry_export.json"
        
        with self._lock:
            data = {
                "nodes": {node_id: node.to_dict() for node_id, node in self.nodes.items()},
                "statistics": self.get_statistics(),
                "exported_at": datetime.now().isoformat()
            }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported trust registry to {path}")
        return str(path)
    
    def save(self):
        """Save trust registry to disk."""
        with self._lock:
            data = {
                "nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self.nodes.items()
                },
                "trust_decay_rate": self.trust_decay_rate,
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
            
            with self._lock:
                for node_id, node_data in data.get("nodes", {}).items():
                    node = TrustMetrics.from_dict(node_data)
                    self.nodes[node_id] = node
                
                self.trust_decay_rate = data.get("trust_decay_rate", self.trust_decay_rate)
            
            logger.info(f"Loaded {len(self.nodes)} nodes from trust registry")
        except Exception as e:
            logger.error(f"Error loading trust registry: {e}")


# Example usage
if __name__ == "__main__":
    registry = TrustRegistry()
    
    # Register some nodes
    registry.register_node("node_alpha", initial_trust=0.7)
    registry.register_node("node_beta", initial_trust=0.5)
    
    # Update trust based on outcomes
    registry.update_trust("node_alpha", success=True, category="general")
    registry.update_trust("node_alpha", success=True, category="cognitive")
    registry.update_trust("node_beta", success=False, category="general")
    
    # Get trust scores
    trust_alpha = registry.get_trust("node_alpha", "general")
    trust_beta = registry.get_trust("node_beta", "general")
    
    print(f"Node Alpha trust: {trust_alpha:.3f}")
    print(f"Node Beta trust: {trust_beta:.3f}")
    
    # Get top nodes
    top_nodes = registry.get_top_nodes("general", limit=5)
    print(f"\nTop nodes:")
    for node in top_nodes:
        print(f"  {node.node_id}: {node.general_trust:.3f}")
    
    # Get statistics
    stats = registry.get_statistics()
    print(f"\nStatistics: {stats}")

