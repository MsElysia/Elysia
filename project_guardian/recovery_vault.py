# project_guardian/recovery_vault.py
# RecoveryVault: System Recovery and Snapshots
# Critical for mutation safety - enables rollback to known-good states

import logging
import json
import hashlib
import shutil
import tarfile
import gzip
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

try:
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
except ImportError:
    try:
        from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    except ImportError:
        TrustAuditLog = None
        AuditEventType = None
        AuditSeverity = None

logger = logging.getLogger(__name__)


class SnapshotType(Enum):
    """Types of snapshots."""
    FULL = "full"  # Complete system state
    INCREMENTAL = "incremental"  # Changes since last snapshot
    MODULE = "module"  # Single module snapshot
    CONFIG = "config"  # Configuration only
    DATA = "data"  # Data only
    MUTATION = "mutation"  # Pre-mutation snapshot


class SnapshotStatus(Enum):
    """Snapshot status."""
    CREATING = "creating"
    COMPLETE = "complete"
    FAILED = "failed"
    VERIFIED = "verified"
    CORRUPTED = "corrupted"


@dataclass
class Snapshot:
    """Represents a system snapshot."""
    snapshot_id: str
    snapshot_type: SnapshotType
    created_at: datetime
    status: SnapshotStatus
    description: str
    checksum: Optional[str] = None
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type.value,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "description": self.description,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata
        }


class RecoveryVault:
    """
    System recovery and snapshot management.
    Enables rollback to known-good states, critical for mutation safety.
    """
    
    def __init__(
        self,
        vault_path: str = "data/recovery_vault",
        max_snapshots: int = 100,
        audit_log: Optional[TrustAuditLog] = None,
        protected_paths: Optional[List[str]] = None
    ):
        """
        Initialize RecoveryVault.
        
        Args:
            vault_path: Path to store snapshots
            max_snapshots: Maximum number of snapshots to keep
            audit_log: TrustAuditLog instance for audit trail
            protected_paths: List of paths to protect (defaults to project_guardian/)
        """
        self.vault_path = Path(vault_path)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.max_snapshots = max_snapshots
        self.audit_log = audit_log
        self.protected_paths = protected_paths or ["project_guardian"]
        
        # Thread-safe operations
        self._lock = RLock()
        
        # Snapshot registry
        self.snapshots: Dict[str, Snapshot] = {}
        
        # Metadata file
        self.metadata_file = self.vault_path / "snapshots.json"
        
        # Load existing snapshots
        self.load()
        
        # Statistics
        self.stats = {
            "total_snapshots": len(self.snapshots),
            "total_recoveries": 0,
            "total_bytes_saved": 0,
            "last_snapshot": None,
            "last_recovery": None
        }
    
    def create_snapshot(
        self,
        snapshot_type: SnapshotType,
        description: str = "",
        paths: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a system snapshot.
        
        Args:
            snapshot_type: Type of snapshot to create
            description: Human-readable description
            paths: Specific paths to snapshot (None = all protected paths)
            metadata: Optional metadata
            
        Returns:
            Snapshot ID
        """
        snapshot_id = str(uuid.uuid4())
        
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            snapshot_type=snapshot_type,
            created_at=datetime.now(),
            status=SnapshotStatus.CREATING,
            description=description or f"{snapshot_type.value} snapshot",
            metadata=metadata or {}
        )
        
        with self._lock:
            self.snapshots[snapshot_id] = snapshot
            self.save()
        
        # Log snapshot creation
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Snapshot creation started: {snapshot_id}",
                severity=AuditSeverity.INFO,
                metadata={
                    "snapshot_id": snapshot_id,
                    "snapshot_type": snapshot_type.value,
                    "description": description
                }
            )
        
        try:
            # Determine paths to snapshot
            snapshot_paths = paths or self._get_protected_paths()
            
            # Create snapshot archive
            snapshot_file = self.vault_path / f"{snapshot_id}.tar.gz"
            total_size = self._create_archive(snapshot_file, snapshot_paths)
            
            # Calculate checksum
            checksum = self._calculate_checksum(snapshot_file)
            
            # Update snapshot
            with self._lock:
                snapshot.status = SnapshotStatus.COMPLETE
                snapshot.checksum = checksum
                snapshot.size_bytes = total_size
                self.snapshots[snapshot_id] = snapshot
                self.stats["total_snapshots"] = len(self.snapshots)
                self.stats["total_bytes_saved"] += total_size
                self.stats["last_snapshot"] = datetime.now().isoformat()
                self.save()
            
            # Verify snapshot integrity
            if self._verify_snapshot(snapshot_file, checksum):
                snapshot.status = SnapshotStatus.VERIFIED
                self.snapshots[snapshot_id] = snapshot
                self.save()
            
            logger.info(f"Snapshot created: {snapshot_id} ({snapshot_type.value}, {total_size} bytes)")
            
            # Cleanup old snapshots
            self._cleanup_old_snapshots()
            
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to create snapshot {snapshot_id}: {e}", exc_info=True)
            with self._lock:
                snapshot.status = SnapshotStatus.FAILED
                snapshot.metadata["error"] = str(e)
                self.snapshots[snapshot_id] = snapshot
                self.save()
            
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Snapshot creation failed: {snapshot_id}",
                    severity=AuditSeverity.ERROR,
                    metadata={"snapshot_id": snapshot_id, "error": str(e)}
                )
            
            raise
    
    def restore_snapshot(
        self,
        snapshot_id: str,
        target_path: Optional[str] = None,
        verify: bool = True
    ) -> bool:
        """
        Restore a snapshot.
        CRITICAL OPERATION - restores system to previous state.
        
        Args:
            snapshot_id: Snapshot ID to restore
            target_path: Target path for restoration (None = original locations)
            verify: Verify snapshot integrity before restore
            
        Returns:
            True if restoration successful
        """
        snapshot = self.snapshots.get(snapshot_id)
        if not snapshot:
            logger.error(f"Snapshot {snapshot_id} not found")
            return False
        
        if snapshot.status != SnapshotStatus.COMPLETE and snapshot.status != SnapshotStatus.VERIFIED:
            logger.error(f"Snapshot {snapshot_id} not in restorable state: {snapshot.status.value}")
            return False
        
        snapshot_file = self.vault_path / f"{snapshot_id}.tar.gz"
        if not snapshot_file.exists():
            logger.error(f"Snapshot file not found: {snapshot_file}")
            return False
        
        # Verify snapshot integrity
        if verify:
            if snapshot.checksum:
                if not self._verify_snapshot(snapshot_file, snapshot.checksum):
                    logger.error(f"Snapshot {snapshot_id} checksum verification failed")
                    with self._lock:
                        snapshot.status = SnapshotStatus.CORRUPTED
                        self.snapshots[snapshot_id] = snapshot
                        self.save()
                    return False
        
        # Log restoration attempt
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Snapshot restoration started: {snapshot_id}",
                severity=AuditSeverity.WARNING,
                metadata={
                    "snapshot_id": snapshot_id,
                    "snapshot_type": snapshot.snapshot_type.value,
                    "target_path": target_path
                }
            )
        
        try:
            # Extract snapshot
            self._extract_archive(snapshot_file, target_path)
            
            # Update statistics
            with self._lock:
                self.stats["total_recoveries"] += 1
                self.stats["last_recovery"] = datetime.now().isoformat()
                snapshot.metadata["restored_at"] = datetime.now().isoformat()
                self.snapshots[snapshot_id] = snapshot
                self.save()
            
            logger.warning(f"Snapshot restored: {snapshot_id}")
            
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Snapshot restoration completed: {snapshot_id}",
                    severity=AuditSeverity.INFO,
                    metadata={"snapshot_id": snapshot_id}
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore snapshot {snapshot_id}: {e}", exc_info=True)
            
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Snapshot restoration failed: {snapshot_id}",
                    severity=AuditSeverity.ERROR,
                    metadata={"snapshot_id": snapshot_id, "error": str(e)}
                )
            
            return False
    
    def create_mutation_snapshot(
        self,
        mutation_id: str,
        target_module: str,
        description: str = ""
    ) -> str:
        """
        Create a snapshot before mutation (safety measure).
        
        Args:
            mutation_id: Mutation ID
            target_module: Module being mutated
            description: Optional description
            
        Returns:
            Snapshot ID
        """
        return self.create_snapshot(
            snapshot_type=SnapshotType.MUTATION,
            description=f"Pre-mutation snapshot: {target_module} (mutation: {mutation_id})",
            paths=[f"project_guardian/{target_module}"],
            metadata={
                "mutation_id": mutation_id,
                "target_module": target_module,
                "created_before_mutation": True
            }
        )
    
    def rollback_mutation(
        self,
        mutation_id: str
    ) -> bool:
        """
        Rollback to snapshot created before a mutation.
        
        Args:
            mutation_id: Mutation ID to rollback
            
        Returns:
            True if rollback successful
        """
        # Find snapshot for this mutation
        mutation_snapshots = [
            (sid, snap) for sid, snap in self.snapshots.items()
            if snap.snapshot_type == SnapshotType.MUTATION
            and snap.metadata.get("mutation_id") == mutation_id
        ]
        
        if not mutation_snapshots:
            logger.error(f"No mutation snapshot found for mutation {mutation_id}")
            return False
        
        # Get most recent snapshot for this mutation
        mutation_snapshots.sort(key=lambda x: x[1].created_at, reverse=True)
        snapshot_id, snapshot = mutation_snapshots[0]
        
        logger.info(f"Rolling back mutation {mutation_id} using snapshot {snapshot_id}")
        return self.restore_snapshot(snapshot_id, verify=True)
    
    def list_snapshots(
        self,
        snapshot_type: Optional[SnapshotType] = None,
        limit: int = 50
    ) -> List[Snapshot]:
        """List snapshots, optionally filtered by type."""
        snapshots = list(self.snapshots.values())
        
        if snapshot_type:
            snapshots = [s for s in snapshots if s.snapshot_type == snapshot_type]
        
        # Sort by creation time (newest first)
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        
        return snapshots[:limit]
    
    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get a snapshot by ID."""
        return self.snapshots.get(snapshot_id)
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        Delete a snapshot.
        WARNING: This is permanent!
        
        Args:
            snapshot_id: Snapshot ID to delete
            
        Returns:
            True if deleted successfully
        """
        snapshot = self.snapshots.get(snapshot_id)
        if not snapshot:
            return False
        
        snapshot_file = self.vault_path / f"{snapshot_id}.tar.gz"
        
        try:
            # Delete file
            if snapshot_file.exists():
                snapshot_file.unlink()
            
            # Remove from registry
            with self._lock:
                del self.snapshots[snapshot_id]
                self.save()
            
            logger.info(f"Snapshot deleted: {snapshot_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            return False
    
    def _get_protected_paths(self) -> List[str]:
        """Get list of protected paths to snapshot."""
        paths = []
        for path_str in self.protected_paths:
            path = Path(path_str)
            if path.exists():
                paths.append(str(path))
        return paths
    
    def _create_archive(
        self,
        archive_path: Path,
        paths: List[str]
    ) -> int:
        """Create compressed tar archive of paths."""
        total_size = 0
        
        with tarfile.open(archive_path, "w:gz") as tar:
            for path_str in paths:
                path = Path(path_str)
                if not path.exists():
                    continue
                
                if path.is_file():
                    tar.add(path_str, arcname=path_str)
                    total_size += path.stat().st_size
                elif path.is_dir():
                    for file_path in path.rglob("*"):
                        if file_path.is_file():
                            tar.add(str(file_path), arcname=str(file_path))
                            total_size += file_path.stat().st_size
        
        return total_size
    
    def _extract_archive(
        self,
        archive_path: Path,
        target_path: Optional[str] = None
    ):
        """Extract snapshot archive."""
        with tarfile.open(archive_path, "r:gz") as tar:
            if target_path:
                # Extract to target path
                tar.extractall(path=target_path)
            else:
                # Extract to original locations
                tar.extractall(path=".")
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _verify_snapshot(
        self,
        snapshot_file: Path,
        expected_checksum: str
    ) -> bool:
        """Verify snapshot file integrity."""
        if not snapshot_file.exists():
            return False
        
        actual_checksum = self._calculate_checksum(snapshot_file)
        return actual_checksum == expected_checksum
    
    def _cleanup_old_snapshots(self):
        """Remove oldest snapshots if over limit."""
        if len(self.snapshots) <= self.max_snapshots:
            return
        
        # Sort by creation time (oldest first)
        sorted_snapshots = sorted(
            self.snapshots.items(),
            key=lambda x: x[1].created_at
        )
        
        # Delete oldest snapshots
        num_to_delete = len(self.snapshots) - self.max_snapshots
        for snapshot_id, snapshot in sorted_snapshots[:num_to_delete]:
            logger.info(f"Cleaning up old snapshot: {snapshot_id}")
            self.delete_snapshot(snapshot_id)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get recovery vault statistics."""
        snapshot_types = {}
        total_size = 0
        
        for snapshot in self.snapshots.values():
            snap_type = snapshot.snapshot_type.value
            snapshot_types[snap_type] = snapshot_types.get(snap_type, 0) + 1
            total_size += snapshot.size_bytes
        
        return {
            "total_snapshots": self.stats["total_snapshots"],
            "total_recoveries": self.stats["total_recoveries"],
            "total_bytes_saved": total_size,
            "snapshots_by_type": snapshot_types,
            "last_snapshot": self.stats["last_snapshot"],
            "last_recovery": self.stats["last_recovery"],
            "vault_path": str(self.vault_path),
            "max_snapshots": self.max_snapshots
        }
    
    def save(self):
        """Save snapshot registry."""
        with self._lock:
            data = {
                "snapshots": {
                    sid: snapshot.to_dict()
                    for sid, snapshot in self.snapshots.items()
                },
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.metadata_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save recovery vault metadata: {e}")
    
    def load(self):
        """Load snapshot registry."""
        if not self.metadata_file.exists():
            return
        
        try:
            with open(self.metadata_file, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                snapshots_data = data.get("snapshots", {})
                for sid, snap_dict in snapshots_data.items():
                    try:
                        snapshot = Snapshot(
                            snapshot_id=snap_dict["snapshot_id"],
                            snapshot_type=SnapshotType(snap_dict["snapshot_type"]),
                            created_at=datetime.fromisoformat(snap_dict["created_at"]),
                            status=SnapshotStatus(snap_dict["status"]),
                            description=snap_dict.get("description", ""),
                            checksum=snap_dict.get("checksum"),
                            size_bytes=snap_dict.get("size_bytes", 0),
                            metadata=snap_dict.get("metadata", {})
                        )
                        self.snapshots[sid] = snapshot
                    except Exception as e:
                        logger.error(f"Failed to load snapshot {sid}: {e}")
                
                if "stats" in data:
                    self.stats.update(data["stats"])
            
            logger.info(f"Loaded {len(self.snapshots)} snapshots from recovery vault")
        except Exception as e:
            logger.error(f"Failed to load recovery vault metadata: {e}")


# Example usage
if __name__ == "__main__":
    # Create recovery vault
    vault = RecoveryVault()
    
    # Create snapshot before mutation
    snapshot_id = vault.create_mutation_snapshot(
        mutation_id="mut_123",
        target_module="runtime_loop_core.py",
        description="Before runtime loop optimization"
    )
    
    print(f"Created snapshot: {snapshot_id}")
    
    # ... mutation happens ...
    
    # If mutation fails, rollback
    # vault.rollback_mutation("mut_123")
    
    # List snapshots
    snapshots = vault.list_snapshots()
    print(f"Total snapshots: {len(snapshots)}")
    
    # Get statistics
    stats = vault.get_statistics()
    print(f"Vault statistics: {stats}")

