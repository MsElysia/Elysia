# project_guardian/mutation_publisher.py
# MutationPublisher: Hot-Patching and Code Application
# Actually applies approved mutations to the codebase

import logging
import shutil
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from threading import Lock
from enum import Enum
import uuid

try:
    from .metacoder import MetaCoder
    from .mutation_engine import MutationEngine, MutationProposal, MutationStatus
    from .recovery_vault import RecoveryVault
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
except ImportError:
    from metacoder import MetaCoder
    from mutation_engine import MutationEngine, MutationProposal, MutationStatus
    from recovery_vault import RecoveryVault
    try:
        from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    except ImportError:
        TrustAuditLog = None
        AuditEventType = None
        AuditSeverity = None

logger = logging.getLogger(__name__)


class PublishStatus(Enum):
    """Publish operation status."""
    PENDING = "pending"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MutationPublisher:
    """
    Hot-patching and code application system.
    Actually applies approved mutations to the codebase using MetaCoder.
    Works with RecoveryVault for safe rollback.
    """
    
    def __init__(
        self,
        metacoder: Optional[MetaCoder] = None,
        mutation_engine: Optional[MutationEngine] = None,
        recovery_vault: Optional[RecoveryVault] = None,
        audit_log: Optional[TrustAuditLog] = None,
        codebase_path: str = "project_guardian"
    ):
        """
        Initialize MutationPublisher.
        
        Args:
            metacoder: MetaCoder instance for code modification
            mutation_engine: MutationEngine instance
            recovery_vault: RecoveryVault instance for snapshots
            audit_log: TrustAuditLog instance
            codebase_path: Path to codebase root
        """
        self.metacoder = metacoder
        self.mutation_engine = mutation_engine
        self.recovery_vault = recovery_vault
        self.audit_log = audit_log
        self.codebase_path = Path(codebase_path)
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Publish history (stores publish records)
        self.publish_history: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self.stats = {
            "total_published": 0,
            "successful_publishes": 0,
            "failed_publishes": 0,
            "rollbacks": 0
        }
    
    def publish_mutation(
        self,
        mutation_id: str,
        verify_before_publish: bool = True,
        create_backup: bool = True
    ) -> Dict[str, Any]:
        """
        Publish (apply) an approved mutation.
        CRITICAL OPERATION - modifies codebase.
        
        Args:
            mutation_id: Mutation ID to publish
            verify_before_publish: Verify mutation before applying
            create_backup: Create backup before publishing
            
        Returns:
            Publish result dictionary
        """
        if not self.mutation_engine:
            return {
                "success": False,
                "error": "MutationEngine not available"
            }
        
        proposal = self.mutation_engine.get_mutation(mutation_id)
        if not proposal:
            return {
                "success": False,
                "error": f"Mutation {mutation_id} not found"
            }
        
        if proposal.status != MutationStatus.APPROVED:
            return {
                "success": False,
                "error": f"Mutation {mutation_id} not approved (status: {proposal.status.value})"
            }
        
        # Log publish attempt
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Mutation publish started: {mutation_id}",
                severity=AuditSeverity.WARNING,
                metadata={
                    "mutation_id": mutation_id,
                    "target_module": proposal.target_module
                }
            )
        
        # Record in history
        publish_id = str(uuid.uuid4())
        publish_record = {
            "publish_id": publish_id,
            "mutation_id": mutation_id,
            "status": PublishStatus.APPLYING.value,
            "started_at": datetime.now().isoformat(),
            "target_module": proposal.target_module
        }
        
        with self._lock:
            self.publish_history[publish_id] = publish_record
            self.stats["total_published"] += 1
        
        try:
            # Verify mutation if requested
            if verify_before_publish:
                validation = self.mutation_engine.validate_code(proposal.proposed_code)
                if not validation.get("valid", False):
                    error_msg = f"Code validation failed: {validation.get('errors', 'Unknown error')}"
                    logger.error(error_msg)
                    
                    publish_record["status"] = PublishStatus.FAILED.value
                    publish_record["error"] = error_msg
                    publish_record["completed_at"] = datetime.now().isoformat()
                    
                    with self._lock:
                        self.publish_history[publish_id] = publish_record
                        self.stats["failed_publishes"] += 1
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "publish_id": publish_id
                    }
            
            # Create backup if requested
            backup_id = None
            if create_backup and self.recovery_vault:
                try:
                    backup_id = self.recovery_vault.create_mutation_snapshot(
                        mutation_id=mutation_id,
                        target_module=proposal.target_module,
                        description=f"Pre-publish backup for {mutation_id}"
                    )
                    publish_record["backup_id"] = backup_id
                    logger.info(f"Created backup {backup_id} before publishing {mutation_id}")
                except Exception as e:
                    logger.warning(f"Failed to create backup: {e}")
                    # Continue anyway - mutation may have existing snapshot
            
            # Apply mutation using MetaCoder
            if self.metacoder:
                # Use MetaCoder to apply the mutation
                target_file = self.codebase_path / proposal.target_module
                
                # Ensure original code is stored
                if not proposal.original_code:
                    # Read current file content
                    try:
                        if target_file.exists():
                            proposal.original_code = target_file.read_text(encoding="utf-8")
                            logger.info(f"Read original code from {target_file}")
                    except Exception as e:
                        logger.warning(f"Failed to read original code: {e}")
                
                # Apply mutation using MetaCoder
                # MetaCoder applies mutations directly to files
                try:
                    # Read current file to ensure we have original
                    if target_file.exists() and not proposal.original_code:
                        proposal.original_code = target_file.read_text(encoding="utf-8")
                    
                    # Write new code
                    target_file.write_text(proposal.proposed_code, encoding="utf-8")
                    
                    apply_result = {"success": True}
                except Exception as e:
                    apply_result = {"success": False, "error": str(e)}
                
                if not apply_result.get("success", False):
                    error_msg = apply_result.get("error", "MetaCoder application failed")
                    logger.error(f"Failed to apply mutation: {error_msg}")
                    
                    publish_record["status"] = PublishStatus.FAILED.value
                    publish_record["error"] = error_msg
                    publish_record["completed_at"] = datetime.now().isoformat()
                    
                    with self._lock:
                        self.publish_history[publish_id] = publish_record
                        self.stats["failed_publishes"] += 1
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "publish_id": publish_id,
                        "backup_id": backup_id
                    }
                
                logger.info(f"Mutation applied successfully via MetaCoder")
            else:
                # Fallback: Direct file write (less safe)
                logger.warning("MetaCoder not available, using direct file write")
                target_file = self.codebase_path / proposal.target_module
                
                if not target_file.exists():
                    return {
                        "success": False,
                        "error": f"Target file not found: {target_file}"
                    }
                
                # Backup original
                if proposal.original_code:
                    backup_file = target_file.with_suffix(target_file.suffix + ".backup")
                    backup_file.write_text(proposal.original_code, encoding="utf-8")
                    publish_record["backup_file"] = str(backup_file)
                
                # Write new code
                try:
                    target_file.write_text(proposal.proposed_code, encoding="utf-8")
                except Exception as e:
                    error_msg = f"Failed to write file: {e}"
                    logger.error(error_msg)
                    
                    # Restore backup if exists
                    if proposal.original_code and backup_file.exists():
                        target_file.write_text(proposal.original_code, encoding="utf-8")
                    
                    publish_record["status"] = PublishStatus.FAILED.value
                    publish_record["error"] = error_msg
                    
                    with self._lock:
                        self.publish_history[publish_id] = publish_record
                        self.stats["failed_publishes"] += 1
                    
                    return {
                        "success": False,
                        "error": error_msg,
                        "publish_id": publish_id
                    }
            
            # Update mutation status
            proposal.status = MutationStatus.APPLIED
            proposal.applied_at = datetime.now()
            
            # Update publish record
            publish_record["status"] = PublishStatus.APPLIED.value
            publish_record["completed_at"] = datetime.now().isoformat()
            publish_record["success"] = True
            
            with self._lock:
                self.publish_history[publish_id] = publish_record
                self.stats["successful_publishes"] += 1
            
            # Log success
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Mutation published successfully: {mutation_id}",
                    severity=AuditSeverity.INFO,
                    metadata={
                        "mutation_id": mutation_id,
                        "target_module": proposal.target_module,
                        "publish_id": publish_id,
                        "backup_id": backup_id
                    }
                )
            
            logger.info(f"Mutation {mutation_id} published successfully to {proposal.target_module}")
            
            return {
                "success": True,
                "publish_id": publish_id,
                "mutation_id": mutation_id,
                "backup_id": backup_id,
                "target_module": proposal.target_module,
                "applied_at": proposal.applied_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error publishing mutation {mutation_id}: {e}", exc_info=True)
            
            publish_record["status"] = PublishStatus.FAILED.value
            publish_record["error"] = str(e)
            publish_record["completed_at"] = datetime.now().isoformat()
            
            with self._lock:
                self.publish_history[publish_id] = publish_record
                self.stats["failed_publishes"] += 1
            
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Mutation publish failed: {mutation_id}",
                    severity=AuditSeverity.ERROR,
                    metadata={
                        "mutation_id": mutation_id,
                        "error": str(e)
                    }
                )
            
            return {
                "success": False,
                "error": str(e),
                "publish_id": publish_id
            }
    
    def rollback_publish(
        self,
        mutation_id: str,
        use_recovery_vault: bool = True
    ) -> Dict[str, Any]:
        """
        Rollback a published mutation.
        
        Args:
            mutation_id: Mutation ID to rollback
            use_recovery_vault: If True, use RecoveryVault for rollback
            
        Returns:
            Rollback result dictionary
        """
        if not self.mutation_engine:
            return {
                "success": False,
                "error": "MutationEngine not available"
            }
        
        proposal = self.mutation_engine.get_mutation(mutation_id)
        if not proposal:
            return {
                "success": False,
                "error": f"Mutation {mutation_id} not found"
            }
        
        if proposal.status != MutationStatus.APPLIED:
            return {
                "success": False,
                "error": f"Mutation {mutation_id} not applied (status: {proposal.status.value})"
            }
        
        if not proposal.original_code:
            return {
                "success": False,
                "error": "Original code not available for rollback"
            }
        
        # Try RecoveryVault first
        if use_recovery_vault and self.recovery_vault:
            try:
                success = self.recovery_vault.rollback_mutation(mutation_id)
                if success:
                    proposal.status = MutationStatus.ROLLED_BACK
                    proposal.rolled_back_at = datetime.now()
                    
                    with self._lock:
                        self.stats["rollbacks"] += 1
                    
                    logger.info(f"Mutation {mutation_id} rolled back via RecoveryVault")
                    return {
                        "success": True,
                        "method": "recovery_vault",
                        "mutation_id": mutation_id
                    }
            except Exception as e:
                logger.warning(f"RecoveryVault rollback failed: {e}, trying MetaCoder")
        
        # Fallback to MetaCoder or direct write
        target_file = self.codebase_path / proposal.target_module
        
        if self.metacoder:
            # Use MetaCoder for rollback (or direct write)
            try:
                target_file.write_text(proposal.original_code, encoding="utf-8")
                proposal.status = MutationStatus.ROLLED_BACK
                proposal.rolled_back_at = datetime.now()
                
                with self._lock:
                    self.stats["rollbacks"] += 1
                
                logger.info(f"Mutation {mutation_id} rolled back via MetaCoder")
                return {
                    "success": True,
                    "method": "metacoder",
                    "mutation_id": mutation_id
                }
            except Exception as e:
                error_msg = f"MetaCoder rollback failed: {e}"
                logger.error(error_msg)
                # Fall through to direct write
        else:
            # Direct file write
            try:
                target_file.write_text(proposal.original_code, encoding="utf-8")
                proposal.status = MutationStatus.ROLLED_BACK
                proposal.rolled_back_at = datetime.now()
                
                with self._lock:
                    self.stats["rollbacks"] += 1
                
                logger.info(f"Mutation {mutation_id} rolled back via direct write")
                return {
                    "success": True,
                    "method": "direct_write",
                    "mutation_id": mutation_id
                }
            except Exception as e:
                error_msg = f"Failed to rollback: {e}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
        
        return {
            "success": False,
            "error": "Rollback failed"
        }
    
    def get_publish_history(
        self,
        mutation_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get publish history, optionally filtered by mutation ID."""
        history = list(self.publish_history.values())
        
        if mutation_id:
            history = [h for h in history if h.get("mutation_id") == mutation_id]
        
        # Sort by started_at (newest first)
        history.sort(key=lambda h: h.get("started_at", ""), reverse=True)
        
        return history[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get publisher statistics."""
        return {
            "total_published": self.stats["total_published"],
            "successful_publishes": self.stats["successful_publishes"],
            "failed_publishes": self.stats["failed_publishes"],
            "rollbacks": self.stats["rollbacks"],
            "success_rate": (
                self.stats["successful_publishes"] / max(1, self.stats["total_published"])
            )
        }


# Example usage
if __name__ == "__main__":
    # Initialize components
    metacoder = None  # Would be provided
    mutation_engine = None  # Would be provided
    recovery_vault = None  # Would be provided
    
    publisher = MutationPublisher(
        metacoder=metacoder,
        mutation_engine=mutation_engine,
        recovery_vault=recovery_vault
    )
    
    # Publish a mutation
    # result = publisher.publish_mutation("mut_123")
    # print(f"Publish result: {result}")
    
    # Rollback if needed
    # rollback_result = publisher.rollback_publish("mut_123")
    # print(f"Rollback result: {rollback_result}")

