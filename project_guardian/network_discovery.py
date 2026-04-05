# project_guardian/network_discovery.py
# NetworkDiscovery: Discover and Register Network Nodes
# Based on Functional Elysia Network Code

import logging
import json
import asyncio
import socket
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

try:
    from .trust_registry import TrustRegistry
except ImportError:
    from trust_registry import TrustRegistry

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """Node status states."""
    UNKNOWN = "unknown"
    DISCOVERING = "discovering"
    ACTIVE = "active"
    INACTIVE = "inactive"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class NetworkNode:
    """Represents a network node."""
    node_id: str
    name: str
    address: str  # IP address or hostname
    port: int
    status: NodeStatus = NodeStatus.UNKNOWN
    capabilities: List[str] = field(default_factory=list)
    trust_score: float = 0.5
    last_seen: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "name": self.name,
            "address": self.address,
            "port": self.port,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "trust_score": self.trust_score,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "metadata": self.metadata,
            "discovered_at": self.discovered_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NetworkNode":
        """Create NetworkNode from dictionary."""
        return cls(
            node_id=data["node_id"],
            name=data["name"],
            address=data["address"],
            port=data["port"],
            status=NodeStatus(data.get("status", "unknown")),
            capabilities=data.get("capabilities", []),
            trust_score=data.get("trust_score", 0.5),
            last_seen=datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None,
            metadata=data.get("metadata", {}),
            discovered_at=datetime.fromisoformat(data.get("discovered_at", datetime.now().isoformat()))
        )


class NetworkDiscovery:
    """
    Discovers and registers network nodes.
    Supports manual registration, auto-discovery, and node health monitoring.
    """
    
    def __init__(
        self,
        local_node_id: Optional[str] = None,
        local_name: str = "Elysia",
        trust_registry: Optional[TrustRegistry] = None,
        storage_path: str = "data/network_nodes.json",
        discovery_interval: int = 60,  # seconds
        node_timeout: int = 300  # seconds
    ):
        """
        Initialize NetworkDiscovery.
        
        Args:
            local_node_id: Local node identifier
            local_name: Local node name
            trust_registry: Optional TrustRegistry for trust scores
            storage_path: Path to node registry storage
            discovery_interval: Auto-discovery interval in seconds
            node_timeout: Timeout for considering nodes offline
        """
        self.local_node_id = local_node_id or str(uuid.uuid4())
        self.local_name = local_name
        self.trust_registry = trust_registry
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.discovery_interval = discovery_interval
        self.node_timeout = node_timeout
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Node registry
        self.nodes: Dict[str, NetworkNode] = {}
        
        # Discovery state
        self._discovery_running = False
        self._discovery_task: Optional[asyncio.Task] = None
        
        # Load existing nodes
        self.load()
    
    def register_node(
        self,
        name: str,
        address: str,
        port: int,
        node_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Manually register a network node.
        
        Args:
            name: Node name
            address: IP address or hostname
            port: Port number
            node_id: Optional node ID (generated if not provided)
            capabilities: Optional list of capabilities
            metadata: Optional metadata
            
        Returns:
            Node ID
        """
        node_id = node_id or str(uuid.uuid4())
        
        node = NetworkNode(
            node_id=node_id,
            name=name,
            address=address,
            port=port,
            status=NodeStatus.DISCOVERING,
            capabilities=capabilities or [],
            metadata=metadata or {}
        )
        
        # Get trust score if available
        if self.trust_registry:
            trust_data = self.trust_registry.get_node_trust(node_id)
            if trust_data:
                node.trust_score = trust_data.get("overall_trust", 0.5)
        
        with self._lock:
            self.nodes[node_id] = node
            self.save()
        
        # Verify connectivity
        asyncio.create_task(self._verify_node(node_id))
        
        logger.info(f"Registered node: {name} ({node_id}) at {address}:{port}")
        return node_id
    
    async def _verify_node(self, node_id: str) -> bool:
        """
        Verify node connectivity.
        
        Args:
            node_id: Node ID to verify
            
        Returns:
            True if node is reachable
        """
        node = self.nodes.get(node_id)
        if not node:
            return False
        
        try:
            # Simple TCP connection test
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((node.address, node.port))
            sock.close()
            
            if result == 0:
                # Connection successful
                with self._lock:
                    node.status = NodeStatus.ACTIVE
                    node.last_seen = datetime.now()
                    self.save()
                
                logger.debug(f"Node {node_id} verified: ACTIVE")
                return True
            else:
                # Connection failed
                with self._lock:
                    node.status = NodeStatus.OFFLINE
                    self.save()
                
                logger.debug(f"Node {node_id} verification failed: OFFLINE")
                return False
                
        except Exception as e:
            logger.debug(f"Node {node_id} verification error: {e}")
            with self._lock:
                node.status = NodeStatus.ERROR
                self.save()
            return False
    
    async def discover_nodes(
        self,
        address_range: Optional[str] = None,
        port_range: Optional[tuple] = None
    ) -> List[str]:
        """
        Discover nodes on the network.
        
        Args:
            address_range: IP range to scan (e.g., "192.168.1.0/24")
            port_range: Port range to scan (start, end)
            
        Returns:
            List of discovered node IDs
        """
        discovered = []
        
        # For now, implement basic discovery
        # In production, this would:
        # - Broadcast discovery packets
        # - Listen for node announcements
        # - Scan network ranges
        # - Use service discovery protocols
        
        logger.info("Starting network discovery...")
        
        # Placeholder: In real implementation, this would:
        # 1. Send multicast discovery packets
        # 2. Listen for responses
        # 3. Parse node information
        # 4. Register discovered nodes
        
        logger.info(f"Discovery completed, found {len(discovered)} nodes")
        return discovered
    
    def get_node(self, node_id: str) -> Optional[NetworkNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def list_nodes(
        self,
        status: Optional[NodeStatus] = None,
        min_trust: float = 0.0
    ) -> List[NetworkNode]:
        """
        List nodes with optional filtering.
        
        Args:
            status: Filter by status
            min_trust: Minimum trust score
            
        Returns:
            List of matching nodes
        """
        with self._lock:
            nodes = list(self.nodes.values())
            
            if status:
                nodes = [n for n in nodes if n.status == status]
            
            nodes = [n for n in nodes if n.trust_score >= min_trust]
            
            # Sort by trust score (descending)
            nodes.sort(key=lambda n: n.trust_score, reverse=True)
            
            return nodes
    
    def find_nodes_by_capability(self, capability: str) -> List[NetworkNode]:
        """
        Find nodes that provide a specific capability.
        
        Args:
            capability: Capability to search for
            
        Returns:
            List of nodes with the capability
        """
        with self._lock:
            return [
                node for node in self.nodes.values()
                if capability in node.capabilities
            ]
    
    def update_node_status(
        self,
        node_id: str,
        status: NodeStatus,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update node status.
        
        Args:
            node_id: Node ID
            status: New status
            metadata: Optional metadata updates
            
        Returns:
            True if updated successfully
        """
        with self._lock:
            node = self.nodes.get(node_id)
            if not node:
                return False
            
            node.status = status
            node.last_seen = datetime.now()
            
            if metadata:
                node.metadata.update(metadata)
            
            self.save()
        
        logger.debug(f"Updated node {node_id} status: {status.value}")
        return True
    
    def remove_node(self, node_id: str) -> bool:
        """
        Remove a node from the registry.
        
        Args:
            node_id: Node ID to remove
            
        Returns:
            True if removed successfully
        """
        with self._lock:
            if node_id not in self.nodes:
                return False
            
            # Don't remove local node
            if node_id == self.local_node_id:
                logger.warning("Cannot remove local node")
                return False
            
            del self.nodes[node_id]
            self.save()
        
        logger.info(f"Removed node: {node_id}")
        return True
    
    async def start_auto_discovery(self):
        """Start automatic periodic discovery."""
        if self._discovery_running:
            logger.warning("Auto-discovery already running")
            return
        
        self._discovery_running = True
        
        async def discovery_loop():
            while self._discovery_running:
                try:
                    # Discover nodes
                    await self.discover_nodes()
                    
                    # Verify existing nodes
                    for node_id in list(self.nodes.keys()):
                        await self._verify_node(node_id)
                    
                    # Check for stale nodes
                    self._check_stale_nodes()
                    
                    # Wait for next interval
                    await asyncio.sleep(self.discovery_interval)
                    
                except Exception as e:
                    logger.error(f"Discovery loop error: {e}")
                    await asyncio.sleep(self.discovery_interval)
        
        self._discovery_task = asyncio.create_task(discovery_loop())
        logger.info("Auto-discovery started")
    
    async def stop_auto_discovery(self):
        """Stop automatic discovery."""
        self._discovery_running = False
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Auto-discovery stopped")
    
    def _check_stale_nodes(self):
        """Mark nodes as offline if they haven't been seen recently."""
        cutoff = datetime.now() - timedelta(seconds=self.node_timeout)
        
        with self._lock:
            for node in self.nodes.values():
                if (
                    node.last_seen and
                    node.last_seen < cutoff and
                    node.status == NodeStatus.ACTIVE
                ):
                    node.status = NodeStatus.INACTIVE
                    logger.debug(f"Marked node {node.node_id} as INACTIVE (stale)")
            
            self.save()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get network discovery statistics."""
        with self._lock:
            by_status = {}
            by_capability = {}
            
            for node in self.nodes.values():
                # By status
                status = node.status.value
                by_status[status] = by_status.get(status, 0) + 1
                
                # By capability
                for cap in node.capabilities:
                    by_capability[cap] = by_capability.get(cap, 0) + 1
            
            return {
                "total_nodes": len(self.nodes),
                "local_node_id": self.local_node_id,
                "nodes_by_status": by_status,
                "nodes_by_capability": by_capability,
                "discovery_running": self._discovery_running
            }
    
    def save(self):
        """Save node registry to disk."""
        with self._lock:
            data = {
                "nodes": {
                    node_id: node.to_dict()
                    for node_id, node in self.nodes.items()
                },
                "local_node_id": self.local_node_id,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save node registry: {e}")
    
    def load(self):
        """Load node registry from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                nodes_data = data.get("nodes", {})
                
                for node_id, node_dict in nodes_data.items():
                    try:
                        node = NetworkNode.from_dict(node_dict)
                        self.nodes[node_id] = node
                    except Exception as e:
                        logger.error(f"Failed to load node {node_id}: {e}")
                
                # Update local node ID if provided
                if "local_node_id" in data:
                    self.local_node_id = data["local_node_id"]
            
            logger.info(f"Loaded {len(self.nodes)} network nodes")
        except Exception as e:
            logger.error(f"Failed to load node registry: {e}")


# Example usage
if __name__ == "__main__":
    async def test_discovery():
        """Test NetworkDiscovery."""
        discovery = NetworkDiscovery(local_name="TestNode")
        
        # Register a node
        node_id = discovery.register_node(
            name="RemoteNode1",
            address="192.168.1.100",
            port=8080,
            capabilities=["ai_generation", "storage"]
        )
        
        # Get statistics
        stats = discovery.get_statistics()
        print(f"Network stats: {stats}")
        
        # Find nodes by capability
        ai_nodes = discovery.find_nodes_by_capability("ai_generation")
        print(f"AI nodes: {len(ai_nodes)}")
    
    asyncio.run(test_discovery())

