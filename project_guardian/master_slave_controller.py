# project_guardian/master_slave_controller.py
# MasterSlaveController: Master Control and Slave Management
# Architecture: One protected master Elysia, multiple deployable slave instances

import logging
import json
import asyncio
import hashlib
import secrets
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

try:
    from .network_discovery import NetworkDiscovery, NetworkNode, NodeStatus
    from .trust_registry import TrustRegistry
    from .trust_policy_manager import TrustPolicyManager, PolicyAction
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
except ImportError:
    from network_discovery import NetworkDiscovery, NetworkNode, NodeStatus
    from trust_registry import TrustRegistry
    from trust_policy_manager import TrustPolicyManager, PolicyAction
    try:
        from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    except ImportError:
        TrustAuditLog = None
        AuditEventType = None
        AuditSeverity = None

logger = logging.getLogger(__name__)


class SlaveRole(Enum):
    """Slave role/permission levels."""
    READ_ONLY = "read_only"  # Can only report status
    WORKER = "worker"  # Can execute tasks
    TRUSTED = "trusted"  # Can execute critical tasks
    ADMIN = "admin"  # Can control other slaves (master only)


class SlaveStatus(Enum):
    """Slave status states."""
    PENDING = "pending"  # Registered but not yet deployed
    DEPLOYING = "deploying"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"  # Suspended by master
    REVOKED = "revoked"  # Revoked/terminated
    ERROR = "error"


@dataclass
class SlaveInstance:
    """Represents a slave Elysia instance."""
    slave_id: str
    name: str
    deployment_target: str  # IP, hostname, or deployment identifier
    role: SlaveRole
    status: SlaveStatus = SlaveStatus.PENDING
    auth_token: str = ""  # Secure token for authentication
    capabilities: List[str] = field(default_factory=list)
    trust_score: float = 0.0  # Starts at 0, increases with performance
    deployed_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    last_command: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excludes sensitive auth_token)."""
        return {
            "slave_id": self.slave_id,
            "name": self.name,
            "deployment_target": self.deployment_target,
            "role": self.role.value,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "trust_score": self.trust_score,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_command": self.last_command,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], auth_token: Optional[str] = None) -> "SlaveInstance":
        """Create SlaveInstance from dictionary."""
        return cls(
            slave_id=data["slave_id"],
            name=data["name"],
            deployment_target=data["deployment_target"],
            role=SlaveRole(data["role"]),
            status=SlaveStatus(data.get("status", "pending")),
            auth_token=auth_token or "",  # Loaded separately from secure storage
            capabilities=data.get("capabilities", []),
            trust_score=data.get("trust_score", 0.0),
            deployed_at=datetime.fromisoformat(data["deployed_at"]) if data.get("deployed_at") else None,
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]) if data.get("last_heartbeat") else None,
            last_command=data.get("last_command"),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))
        )


class MasterSlaveController:
    """
    Master-slave architecture controller.
    Manages one protected master Elysia and multiple deployable slave instances.
    Master never shares its core code, only deploys limited-functionality slaves.
    """
    
    def __init__(
        self,
        master_id: str,
        master_name: str = "Elysia-Master",
        network_discovery: Optional[NetworkDiscovery] = None,
        trust_registry: Optional[TrustRegistry] = None,
        trust_policy: Optional[TrustPolicyManager] = None,
        audit_log: Optional[TrustAuditLog] = None,
        storage_path: str = "data/master_slaves.json",
        auth_token_path: str = "data/slave_tokens.json"  # Separate secure storage
    ):
        """
        Initialize MasterSlaveController.
        
        Args:
            master_id: Unique master identifier
            master_name: Master name
            network_discovery: NetworkDiscovery instance
            trust_registry: TrustRegistry instance
            trust_policy: TrustPolicyManager instance
            audit_log: TrustAuditLog instance
            storage_path: Path to slave registry storage
            auth_token_path: Path to secure auth token storage
        """
        self.master_id = master_id
        self.master_name = master_name
        self.network_discovery = network_discovery
        self.trust_registry = trust_registry
        self.trust_policy = trust_policy
        self.audit_log = audit_log
        
        self.storage_path = Path(storage_path)
        self.auth_token_path = Path(auth_token_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.auth_token_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe operations (use RLock for reentrant locking)
        self._lock = RLock()
        
        # Slave registry
        self.slaves: Dict[str, SlaveInstance] = {}
        self.auth_tokens: Dict[str, str] = {}  # slave_id -> token
        
        # Master credentials (for master authentication)
        self.master_token = self._generate_secure_token()
        
        # Command queue for slaves
        self.command_queue: Dict[str, List[Dict[str, Any]]] = {}  # slave_id -> commands
        
        # Statistics
        self.stats: Dict[str, Any] = {
            "total_slaves": 0,
            "active_slaves": 0,
            "suspended_slaves": 0,
            "revoked_slaves": 0,
            "commands_sent": 0,
            "commands_failed": 0
        }
        
        # Load existing slaves
        self.load()
        
        logger.info(f"MasterSlaveController initialized: {master_name} ({master_id})")
        logger.warning(f"MASTER TOKEN: {self.master_token} - KEEP SECURE!")
    
    def register_slave(
        self,
        name: str,
        deployment_target: str,
        role: SlaveRole = SlaveRole.WORKER,
        capabilities: Optional[List[str]] = None
    ) -> tuple[str, str]:
        """
        Register a new slave for deployment.
        Generates secure authentication token.
        
        Args:
            name: Slave name
            deployment_target: Where to deploy (IP, hostname, etc.)
            role: Slave role/permission level
            capabilities: Slave capabilities
            
        Returns:
            (slave_id, auth_token) tuple
        """
        slave_id = str(uuid.uuid4())
        auth_token = self._generate_secure_token()
        
        slave = SlaveInstance(
            slave_id=slave_id,
            name=name,
            deployment_target=deployment_target,
            role=role,
            status=SlaveStatus.PENDING,
            auth_token=auth_token,
            capabilities=capabilities or []
        )
        
        with self._lock:
            self.slaves[slave_id] = slave
            self.auth_tokens[slave_id] = auth_token
            self.stats["total_slaves"] += 1
            self.save()
        
        # Register in trust registry if available
        if self.trust_registry:
            self.trust_registry.register_node(
                node_id=slave_id,
                initial_trust=0.0  # Start with 0 trust
            )
        
        # Log registration
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Slave registered: {name} ({slave_id})",
                severity=AuditSeverity.INFO,
                metadata={
                    "slave_id": slave_id,
                    "role": role.value,
                    "deployment_target": deployment_target
                }
            )
        
        logger.info(f"Registered slave: {name} ({slave_id})")
        return slave_id, auth_token
    
    def deploy_slave(
        self,
        slave_id: str,
        slave_code_path: Optional[str] = None
    ) -> bool:
        """
        Deploy slave code to target.
        Note: Only deploys limited slave functionality, never master code.
        
        Args:
            slave_id: Slave ID to deploy
            slave_code_path: Optional path to slave code package
            
        Returns:
            True if deployment initiated successfully
        """
        slave = self.slaves.get(slave_id)
        if not slave:
            logger.error(f"Slave {slave_id} not found")
            return False
        
        with self._lock:
            slave.status = SlaveStatus.DEPLOYING
            self.save()
        
        # In production, this would:
        # 1. Package slave code (limited functionality)
        # 2. Deploy to target (SSH, API, etc.)
        # 3. Configure with auth token
        # 4. Start slave service
        # 5. Register in network discovery
        
        # Placeholder implementation
        logger.info(f"Deploying slave {slave_id} to {slave.deployment_target}")
        
        # Simulate deployment
        async def deploy():
            await asyncio.sleep(2)  # Simulate deployment time
            
            with self._lock:
                slave.status = SlaveStatus.ACTIVE
                slave.deployed_at = datetime.now()
                slave.last_heartbeat = datetime.now()
                self.stats["active_slaves"] += 1
                self.save()
            
            # Register in network discovery if available
            if self.network_discovery:
                try:
                    # Parse deployment target for address/port
                    parts = slave.deployment_target.split(":")
                    address = parts[0]
                    port = int(parts[1]) if len(parts) > 1 else 8080
                    
                    self.network_discovery.register_node(
                        name=slave.name,
                        address=address,
                        port=port,
                        node_id=slave_id,
                        capabilities=slave.capabilities
                    )
                except Exception as e:
                    logger.error(f"Failed to register slave in network discovery: {e}")
        
        asyncio.create_task(deploy())
        
        return True
    
    def revoke_slave(self, slave_id: str, reason: str = "") -> bool:
        """
        Revoke/terminate a slave.
        Critical security operation - removes slave access.
        
        Args:
            slave_id: Slave ID to revoke
            reason: Reason for revocation
            
        Returns:
            True if revoked successfully
        """
        slave = self.slaves.get(slave_id)
        if not slave:
            return False
        
        with self._lock:
            slave.status = SlaveStatus.REVOKED
            self.stats["active_slaves"] = max(0, self.stats["active_slaves"] - 1)
            self.stats["revoked_slaves"] += 1
            
            # Remove auth token
            if slave_id in self.auth_tokens:
                del self.auth_tokens[slave_id]
            
            self.save()
        
        # Log revocation
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Slave revoked: {slave.name} ({slave_id}) - {reason}",
                severity=AuditSeverity.CRITICAL,
                metadata={
                    "slave_id": slave_id,
                    "reason": reason
                }
            )
        
        logger.warning(f"Slave revoked: {slave.name} ({slave_id}) - {reason}")
        return True
    
    def suspend_slave(self, slave_id: str, reason: str = "") -> bool:
        """
        Suspend a slave (temporary disable).
        
        Args:
            slave_id: Slave ID to suspend
            reason: Reason for suspension
            
        Returns:
            True if suspended successfully
        """
        slave = self.slaves.get(slave_id)
        if not slave:
            return False
        
        with self._lock:
            slave.status = SlaveStatus.SUSPENDED
            self.stats["active_slaves"] = max(0, self.stats["active_slaves"] - 1)
            self.stats["suspended_slaves"] += 1
            self.save()
        
        logger.warning(f"Slave suspended: {slave.name} ({slave_id}) - {reason}")
        return True
    
    def authenticate_slave(self, slave_id: str, token: str) -> bool:
        """
        Authenticate a slave connection attempt.
        
        Args:
            slave_id: Slave ID
            token: Authentication token
            
        Returns:
            True if authenticated
        """
        stored_token = self.auth_tokens.get(slave_id)
        if not stored_token:
            logger.warning(f"Authentication failed: Slave {slave_id} not found")
            return False
        
        if token != stored_token:
            logger.warning(f"Authentication failed: Invalid token for slave {slave_id}")
            
            # Log failed authentication attempt
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Failed slave authentication: {slave_id}",
                    severity=AuditSeverity.WARNING,
                    metadata={"slave_id": slave_id}
                )
            
            return False
        
        # Update last heartbeat
        slave = self.slaves.get(slave_id)
        if slave:
            slave.last_heartbeat = datetime.now()
            if slave.status == SlaveStatus.INACTIVE:
                slave.status = SlaveStatus.ACTIVE
        
        return True
    
    def send_command(
        self,
        slave_id: str,
        command: str,
        data: Optional[Dict[str, Any]] = None,
        priority: int = 5
    ) -> bool:
        """
        Send a command to a slave.
        
        Args:
            slave_id: Target slave ID
            command: Command name
            data: Command data
            priority: Command priority
            
        Returns:
            True if command queued successfully
        """
        slave = self.slaves.get(slave_id)
        if not slave:
            logger.error(f"Slave {slave_id} not found")
            return False
        
        if slave.status != SlaveStatus.ACTIVE:
            logger.warning(f"Cannot send command to {slave.status.value} slave")
            return False
        
        # Check if command is allowed for slave role
        if self.trust_policy:
            action_data = {
                "action_type": "slave_command",
                "command": command,
                "slave_role": slave.role.value,
                "slave_id": slave_id
            }
            
            evaluation = self.trust_policy.evaluate_action(action_data)
            if evaluation["decision"] == "deny":
                logger.warning(f"Command denied by policy: {command}")
                return False
        
        # Queue command
        if slave_id not in self.command_queue:
            self.command_queue[slave_id] = []
        
        command_entry = {
            "command_id": str(uuid.uuid4()),
            "command": command,
            "data": data or {},
            "priority": priority,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        }
        
        self.command_queue[slave_id].append(command_entry)
        self.command_queue[slave_id].sort(key=lambda x: x["priority"], reverse=True)
        
        self.stats["commands_sent"] += 1
        
        slave.last_command = command
        
        logger.info(f"Command queued for slave {slave_id}: {command}")
        return True
    
    def get_pending_commands(self, slave_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get pending commands for a slave.
        
        Args:
            slave_id: Slave ID
            limit: Maximum number of commands
            
        Returns:
            List of pending commands
        """
        commands = self.command_queue.get(slave_id, [])
        pending = [cmd for cmd in commands if cmd["status"] == "pending"]
        return pending[:limit]
    
    def mark_command_complete(self, slave_id: str, command_id: str, success: bool):
        """Mark a command as complete."""
        commands = self.command_queue.get(slave_id, [])
        for cmd in commands:
            if cmd["command_id"] == command_id:
                cmd["status"] = "completed" if success else "failed"
                cmd["completed_at"] = datetime.now().isoformat()
                if not success:
                    self.stats["commands_failed"] += 1
                break
    
    def update_slave_trust(self, slave_id: str, trust_delta: float):
        """
        Update slave trust score based on performance.
        
        Args:
            slave_id: Slave ID
            trust_delta: Trust change (+/-)
        """
        slave = self.slaves.get(slave_id)
        if not slave:
            return
        
        with self._lock:
            old_trust = slave.trust_score
            slave.trust_score = max(0.0, min(1.0, slave.trust_score + trust_delta))
            self.save()
        
        # Update trust registry
        if self.trust_registry:
            self.trust_registry.adjust_trust(slave_id, trust_delta, "master_evaluation")
        
        logger.debug(f"Updated trust for slave {slave_id}: {old_trust:.2f} -> {slave.trust_score:.2f}")
    
    def get_slave(self, slave_id: str) -> Optional[SlaveInstance]:
        """Get a slave instance."""
        return self.slaves.get(slave_id)
    
    def list_slaves(
        self,
        status: Optional[SlaveStatus] = None,
        role: Optional[SlaveRole] = None,
        min_trust: float = 0.0
    ) -> List[SlaveInstance]:
        """
        List slaves with optional filtering.
        
        Args:
            status: Filter by status
            role: Filter by role
            min_trust: Minimum trust score
            
        Returns:
            List of matching slaves
        """
        with self._lock:
            slaves = list(self.slaves.values())
            
            if status:
                slaves = [s for s in slaves if s.status == status]
            
            if role:
                slaves = [s for s in slaves if s.role == role]
            
            slaves = [s for s in slaves if s.trust_score >= min_trust]
            
            # Sort by trust score
            slaves.sort(key=lambda s: s.trust_score, reverse=True)
            
            return slaves
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get master-slave system statistics."""
        with self._lock:
            by_status = {}
            by_role = {}
            
            for slave in self.slaves.values():
                status = slave.status.value
                role = slave.role.value
                
                by_status[status] = by_status.get(status, 0) + 1
                by_role[role] = by_role.get(role, 0) + 1
            
            return {
                "master_id": self.master_id,
                "master_name": self.master_name,
                "total_slaves": len(self.slaves),
                "slaves_by_status": by_status,
                "slaves_by_role": by_role,
                "statistics": self.stats.copy()
            }
    
    def _generate_secure_token(self) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)
    
    def save(self):
        """Save slave registry (without sensitive tokens)."""
        with self._lock:
            # Save slave data (without tokens)
            data = {
                "master_id": self.master_id,
                "master_name": self.master_name,
                "slaves": {
                    slave_id: slave.to_dict()
                    for slave_id, slave in self.slaves.items()
                },
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save slave registry: {e}")
            
            # Save auth tokens separately (more secure)
            auth_data = {
                "master_token": self.master_token,
                "slave_tokens": self.auth_tokens,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.auth_token_path, 'w') as f:
                    json.dump(auth_data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save auth tokens: {e}")
    
    def load(self):
        """Load slave registry and auth tokens."""
        # Load slave data
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                
                with self._lock:
                    slaves_data = data.get("slaves", {})
                    for slave_id, slave_dict in slaves_data.items():
                        try:
                            # Auth token loaded separately
                            slave = SlaveInstance.from_dict(slave_dict)
                            self.slaves[slave_id] = slave
                        except Exception as e:
                            logger.error(f"Failed to load slave {slave_id}: {e}")
                    
                    if "stats" in data:
                        self.stats.update(data["stats"])
            except Exception as e:
                logger.error(f"Failed to load slave registry: {e}")
        
        # Load auth tokens
        if self.auth_token_path.exists():
            try:
                with open(self.auth_token_path, 'r') as f:
                    auth_data = json.load(f)
                
                with self._lock:
                    self.master_token = auth_data.get("master_token", self.master_token)
                    self.auth_tokens = auth_data.get("slave_tokens", {})
            except Exception as e:
                logger.error(f"Failed to load auth tokens: {e}")


# Example usage
if __name__ == "__main__":
    async def test_master_slave():
        """Test MasterSlaveController."""
        controller = MasterSlaveController(
            master_id="master_001",
            master_name="Elysia-Master"
        )
        
        # Register a slave
        slave_id, token = controller.register_slave(
            name="Slave-Node-1",
            deployment_target="192.168.1.100:8080",
            role=SlaveRole.WORKER,
            capabilities=["ai_generation", "storage"]
        )
        
        print(f"Registered slave: {slave_id}")
        print(f"Auth token: {token}")
        
        # Deploy slave
        controller.deploy_slave(slave_id)
        
        # Send command
        controller.send_command(
            slave_id,
            "execute_task",
            data={"task_type": "ai_generation", "prompt": "Hello"}
        )
        
        # Get statistics
        stats = controller.get_statistics()
        print(f"Master-slave stats: {stats}")
    
    asyncio.run(test_master_slave())

