# project_guardian/franchise_manager.py
# FranchiseManager: Business Franchise Model
# Slaves operate as franchises, master maintains control

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

try:
    from .master_slave_controller import MasterSlaveController, SlaveInstance, SlaveRole, SlaveStatus
    from .revenue_sharing import RevenueSharing, RevenueTransaction
    from .trust_registry import TrustRegistry
    from .asset_manager import AssetManager
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
except ImportError:
    from master_slave_controller import MasterSlaveController, SlaveInstance, SlaveRole, SlaveStatus
    from revenue_sharing import RevenueSharing, RevenueTransaction
    from trust_registry import TrustRegistry
    from asset_manager import AssetManager
    try:
        from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    except ImportError:
        TrustAuditLog = None
        AuditEventType = None
        AuditSeverity = None

logger = logging.getLogger(__name__)


class FranchiseStatus(Enum):
    """Franchise operational status."""
    PENDING = "pending"  # Agreement pending approval
    ACTIVE = "active"  # Active franchise
    SUSPENDED = "suspended"  # Temporarily suspended
    TERMINATED = "terminated"  # Franchise terminated
    EXPIRED = "expired"  # Agreement expired


class ComplianceStatus(Enum):
    """Compliance status."""
    COMPLIANT = "compliant"
    WARNING = "warning"  # Minor violations
    VIOLATION = "violation"  # Serious violations
    CRITICAL = "critical"  # Immediate termination risk


@dataclass
class FranchiseAgreement:
    """Franchise agreement/contract."""
    agreement_id: str
    franchise_id: str  # Slave ID
    created_at: datetime
    expires_at: Optional[datetime]
    status: FranchiseStatus
    
    # Financial Terms
    franchise_fee: float  # One-time franchise fee
    royalty_rate: float  # Monthly royalty percentage (0.0-1.0)
    advertising_fee: float  # Advertising fund contribution percentage
    minimum_monthly_revenue: float  # Minimum revenue requirement
    
    # Operational Terms
    allowed_operations: List[str]  # Operations franchise can perform
    restricted_operations: List[str]  # Operations not allowed
    reporting_frequency: str  # "daily", "weekly", "monthly"
    performance_targets: Dict[str, Any]  # Performance metrics
    
    # Control Terms (MASTER CONTROL)
    master_override_enabled: bool  # Master can override decisions
    remote_shutdown_enabled: bool  # Master can shutdown franchise
    code_update_required: bool  # Must accept master code updates
    data_access_level: str  # "limited", "standard", "extended"
    
    # Compliance
    compliance_status: ComplianceStatus
    violations: List[Dict[str, Any]] = field(default_factory=list)
    last_compliance_check: Optional[datetime] = None
    
    # Metadata
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agreement_id": self.agreement_id,
            "franchise_id": self.franchise_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status.value,
            "franchise_fee": self.franchise_fee,
            "royalty_rate": self.royalty_rate,
            "advertising_fee": self.advertising_fee,
            "minimum_monthly_revenue": self.minimum_monthly_revenue,
            "allowed_operations": self.allowed_operations,
            "restricted_operations": self.restricted_operations,
            "reporting_frequency": self.reporting_frequency,
            "performance_targets": self.performance_targets,
            "master_override_enabled": self.master_override_enabled,
            "remote_shutdown_enabled": self.remote_shutdown_enabled,
            "code_update_required": self.code_update_required,
            "data_access_level": self.data_access_level,
            "compliance_status": self.compliance_status.value,
            "violations": self.violations,
            "last_compliance_check": self.last_compliance_check.isoformat() if self.last_compliance_check else None,
            "notes": self.notes,
            "metadata": self.metadata
        }


class FranchiseManager:
    """
    Manages franchise business model.
    Slaves operate as franchises with agreements, terms, and compliance.
    Master maintains absolute control - can't lose control.
    """
    
    def __init__(
        self,
        master_slave: MasterSlaveController,
        revenue_sharing: Optional[RevenueSharing] = None,
        trust_registry: Optional[TrustRegistry] = None,
        asset_manager: Optional[AssetManager] = None,
        audit_log: Optional[TrustAuditLog] = None,
        storage_path: str = "data/franchise_manager.json"
    ):
        """
        Initialize FranchiseManager.
        
        Args:
            master_slave: MasterSlaveController instance
            revenue_sharing: RevenueSharing instance
            trust_registry: TrustRegistry instance
            asset_manager: AssetManager instance
            audit_log: TrustAuditLog instance
            storage_path: Storage path
        """
        self.master_slave = master_slave
        self.revenue_sharing = revenue_sharing
        self.trust_registry = trust_registry
        self.asset_manager = asset_manager
        self.audit_log = audit_log
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe operations (use RLock for reentrant locking)
        self._lock = RLock()
        
        # Franchise agreements
        self.agreements: Dict[str, FranchiseAgreement] = {}
        
        # Default agreement template
        self.default_agreement_template = {
            "franchise_fee": 500.0,  # $500 one-time
            "royalty_rate": 0.15,  # 15% monthly royalty
            "advertising_fee": 0.02,  # 2% advertising fund
            "minimum_monthly_revenue": 1000.0,
            "reporting_frequency": "weekly",
            "master_override_enabled": True,  # CRITICAL: Master control
            "remote_shutdown_enabled": True,  # CRITICAL: Master control
            "code_update_required": True,  # CRITICAL: Master control
            "data_access_level": "limited"
        }
        
        # Statistics
        self.stats = {
            "total_franchises": 0,
            "active_franchises": 0,
            "total_franchise_fees": 0.0,
            "total_royalties": 0.0,
            "total_advertising_fees": 0.0,
            "violations": 0,
            "terminations": 0
        }
        
        # Load data
        self.load()
    
    def create_franchise_agreement(
        self,
        slave_id: str,
        franchise_fee: Optional[float] = None,
        royalty_rate: Optional[float] = None,
        expires_at: Optional[datetime] = None,
        custom_terms: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a franchise agreement for a slave.
        MASTER-ONLY: Creates binding franchise contract.
        
        Args:
            slave_id: Slave ID to create franchise for
            franchise_fee: One-time franchise fee (default from template)
            royalty_rate: Monthly royalty rate (default from template)
            expires_at: Agreement expiration date (None = no expiration)
            custom_terms: Custom agreement terms
            
        Returns:
            Agreement ID
        """
        # Verify slave exists
        slave = self.master_slave.get_slave(slave_id)
        if not slave:
            logger.error(f"Slave {slave_id} not found")
            return ""
        
        # Check if franchise already exists
        existing = self.get_agreement_by_franchise(slave_id)
        if existing and existing.status == FranchiseStatus.ACTIVE:
            logger.warning(f"Active franchise already exists for {slave_id}")
            return existing.agreement_id
        
        # Use template or custom values
        template = self.default_agreement_template.copy()
        if custom_terms:
            template.update(custom_terms)
        
        agreement_id = str(uuid.uuid4())
        
        agreement = FranchiseAgreement(
            agreement_id=agreement_id,
            franchise_id=slave_id,
            created_at=datetime.now(),
            expires_at=expires_at,
            status=FranchiseStatus.PENDING,
            franchise_fee=franchise_fee or template["franchise_fee"],
            royalty_rate=royalty_rate or template["royalty_rate"],
            advertising_fee=template["advertising_fee"],
            minimum_monthly_revenue=template["minimum_monthly_revenue"],
            allowed_operations=template.get("allowed_operations", ["service_provision", "content_creation"]),
            restricted_operations=template.get("restricted_operations", ["financial_api_access", "system_override"]),
            reporting_frequency=template["reporting_frequency"],
            performance_targets=template.get("performance_targets", {}),
            master_override_enabled=template["master_override_enabled"],  # CRITICAL
            remote_shutdown_enabled=template["remote_shutdown_enabled"],  # CRITICAL
            code_update_required=template["code_update_required"],  # CRITICAL
            data_access_level=template["data_access_level"],
            compliance_status=ComplianceStatus.COMPLIANT
        )
        
        with self._lock:
            self.agreements[agreement_id] = agreement
            self.stats["total_franchises"] += 1
            self.save()
        
        # Log franchise creation
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Franchise agreement created: {slave_id}",
                severity=AuditSeverity.INFO,
                metadata={
                    "agreement_id": agreement_id,
                    "franchise_fee": agreement.franchise_fee,
                    "royalty_rate": agreement.royalty_rate
                }
            )
        
        logger.info(f"Created franchise agreement for {slave_id} (ID: {agreement_id})")
        return agreement_id
    
    def approve_franchise(
        self,
        agreement_id: str,
        collect_franchise_fee: bool = True
    ) -> bool:
        """
        Approve and activate franchise agreement.
        MASTER-ONLY: Final approval and activation.
        
        Args:
            agreement_id: Agreement ID
            collect_franchise_fee: Whether to collect franchise fee
            
        Returns:
            True if approved successfully
        """
        agreement = self.agreements.get(agreement_id)
        if not agreement:
            logger.error(f"Agreement {agreement_id} not found")
            return False
        
        if agreement.status != FranchiseStatus.PENDING:
            logger.warning(f"Agreement {agreement_id} not pending")
            return False
        
        # Collect franchise fee if enabled
        if collect_franchise_fee and self.asset_manager:
            self.asset_manager.add_transaction(
                amount=agreement.franchise_fee,
                transaction_type="income",
                description=f"Franchise fee from {agreement.franchise_id}",
                metadata={
                    "agreement_id": agreement_id,
                    "franchise_id": agreement.franchise_id
                }
            )
            self.stats["total_franchise_fees"] += agreement.franchise_fee
        
        # Activate franchise
        with self._lock:
            agreement.status = FranchiseStatus.ACTIVE
            self.stats["active_franchises"] += 1
            self.save()
        
        # Update slave role to FRANCHISE
        self.master_slave.update_slave_role(agreement.franchise_id, SlaveRole.FRANCHISE)
        
        logger.info(f"Franchise approved and activated: {agreement.franchise_id}")
        return True
    
    def collect_royalties(
        self,
        franchise_id: str,
        monthly_revenue: float
    ) -> Dict[str, float]:
        """
        Collect royalties and fees from franchise revenue.
        MASTER-ONLY: Calculates and collects franchise fees.
        
        Args:
            franchise_id: Franchise ID
            monthly_revenue: Monthly revenue amount
            
        Returns:
            Dictionary with fee breakdown
        """
        agreement = self.get_agreement_by_franchise(franchise_id)
        if not agreement or agreement.status != FranchiseStatus.ACTIVE:
            logger.error(f"No active franchise agreement for {franchise_id}")
            return {}
        
        # Calculate fees
        royalty_amount = monthly_revenue * agreement.royalty_rate
        advertising_fee = monthly_revenue * agreement.advertising_fee
        total_fees = royalty_amount + advertising_fee
        
        # Record in AssetManager
        if self.asset_manager:
            self.asset_manager.add_transaction(
                amount=total_fees,
                transaction_type="income",
                description=f"Franchise royalties from {franchise_id}",
                metadata={
                    "franchise_id": franchise_id,
                    "royalty": royalty_amount,
                    "advertising_fee": advertising_fee,
                    "monthly_revenue": monthly_revenue
                }
            )
        
        # Update statistics
        with self._lock:
            self.stats["total_royalties"] += royalty_amount
            self.stats["total_advertising_fees"] += advertising_fee
            self.save()
        
        # Check minimum revenue requirement
        if monthly_revenue < agreement.minimum_monthly_revenue:
            self.record_violation(
                franchise_id,
                "minimum_revenue",
                f"Monthly revenue ${monthly_revenue:.2f} below minimum ${agreement.minimum_monthly_revenue:.2f}"
            )
        
        return {
            "monthly_revenue": monthly_revenue,
            "royalty_rate": agreement.royalty_rate,
            "royalty_amount": royalty_amount,
            "advertising_fee": advertising_fee,
            "total_fees": total_fees,
            "franchise_net": monthly_revenue - total_fees
        }
    
    def check_compliance(
        self,
        franchise_id: str
    ) -> ComplianceStatus:
        """
        Check franchise compliance with agreement.
        MASTER-ONLY: Compliance monitoring.
        
        Args:
            franchise_id: Franchise ID
            
        Returns:
            Compliance status
        """
        agreement = self.get_agreement_by_franchise(franchise_id)
        if not agreement:
            return ComplianceStatus.CRITICAL
        
        violations = agreement.violations
        recent_violations = [
            v for v in violations
            if datetime.fromisoformat(v.get("timestamp", datetime.now().isoformat())) > datetime.now() - timedelta(days=30)
        ]
        
        # Determine compliance status
        if len(recent_violations) == 0:
            status = ComplianceStatus.COMPLIANT
        elif len(recent_violations) < 3:
            status = ComplianceStatus.WARNING
        elif len(recent_violations) < 5:
            status = ComplianceStatus.VIOLATION
        else:
            status = ComplianceStatus.CRITICAL
        
        with self._lock:
            agreement.compliance_status = status
            agreement.last_compliance_check = datetime.now()
            self.save()
        
        return status
    
    def record_violation(
        self,
        franchise_id: str,
        violation_type: str,
        description: str
    ):
        """
        Record a franchise agreement violation.
        MASTER-ONLY: Compliance tracking.
        
        Args:
            franchise_id: Franchise ID
            violation_type: Type of violation
            description: Violation description
        """
        agreement = self.get_agreement_by_franchise(franchise_id)
        if not agreement:
            return
        
        violation = {
            "violation_id": str(uuid.uuid4()),
            "type": violation_type,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "severity": "medium"
        }
        
        with self._lock:
            agreement.violations.append(violation)
            self.stats["violations"] += 1
            self.save()
        
        # Log violation
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Franchise violation: {franchise_id} - {violation_type}",
                severity=AuditSeverity.WARNING,
                actor=franchise_id,
                metadata=violation
            )
        
        logger.warning(f"Franchise violation recorded: {franchise_id} - {violation_type}")
    
    def suspend_franchise(
        self,
        franchise_id: str,
        reason: str
    ) -> bool:
        """
        Suspend a franchise.
        MASTER-ONLY: Can suspend franchises for violations.
        
        Args:
            franchise_id: Franchise ID
            reason: Suspension reason
            
        Returns:
            True if suspended
        """
        agreement = self.get_agreement_by_franchise(franchise_id)
        if not agreement:
            return False
        
        if agreement.status != FranchiseStatus.ACTIVE:
            logger.warning(f"Franchise {franchise_id} not active")
            return False
        
        # Use remote shutdown if enabled
        if agreement.remote_shutdown_enabled:
            self.master_slave.shutdown_slave(franchise_id)
        
        with self._lock:
            agreement.status = FranchiseStatus.SUSPENDED
            agreement.notes = f"Suspended: {reason}"
            self.stats["active_franchises"] -= 1
            self.save()
        
        logger.warning(f"Franchise suspended: {franchise_id} - {reason}")
        return True
    
    def terminate_franchise(
        self,
        franchise_id: str,
        reason: str
    ) -> bool:
        """
        Terminate a franchise agreement.
        MASTER-ONLY: Can terminate franchises - maintains control.
        
        Args:
            franchise_id: Franchise ID
            reason: Termination reason
            
        Returns:
            True if terminated
        """
        agreement = self.get_agreement_by_franchise(franchise_id)
        if not agreement:
            return False
        
        # Use remote shutdown if enabled
        if agreement.remote_shutdown_enabled:
            self.master_slave.shutdown_slave(franchise_id)
        
        # Revoke slave access
        self.master_slave.remove_slave(franchise_id)
        
        with self._lock:
            agreement.status = FranchiseStatus.TERMINATED
            agreement.notes = f"Terminated: {reason}"
            if agreement.status == FranchiseStatus.ACTIVE:
                self.stats["active_franchises"] -= 1
            self.stats["terminations"] += 1
            self.save()
        
        # Log termination
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Franchise terminated: {franchise_id} - {reason}",
                severity=AuditSeverity.CRITICAL,
                actor=franchise_id,
                metadata={"reason": reason}
            )
        
        logger.warning(f"Franchise terminated: {franchise_id} - {reason}")
        return True
    
    def master_override(
        self,
        franchise_id: str,
        action: str,
        params: Dict[str, Any]
    ) -> bool:
        """
        Master override - can control franchise operations.
        CRITICAL: Maintains master control.
        
        Args:
            franchise_id: Franchise ID
            action: Action to override
            params: Action parameters
            
        Returns:
            True if override successful
        """
        agreement = self.get_agreement_by_franchise(franchise_id)
        if not agreement:
            return False
        
        if not agreement.master_override_enabled:
            logger.warning(f"Master override not enabled for {franchise_id}")
            return False
        
        # Execute override via MasterSlaveController
        success = self.master_slave.send_command(
            franchise_id,
            action,
            data=params,
            priority=10  # Highest priority for master overrides
        )
        
        # Log override
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Master override: {franchise_id} - {action}",
                severity=AuditSeverity.WARNING,
                metadata={"action": action, "params": params}
            )
        
        logger.info(f"Master override executed: {franchise_id} - {action}")
        return success
    
    def get_agreement_by_franchise(self, franchise_id: str) -> Optional[FranchiseAgreement]:
        """Get active agreement for franchise."""
        for agreement in self.agreements.values():
            if agreement.franchise_id == franchise_id and agreement.status == FranchiseStatus.ACTIVE:
                return agreement
        
        # Return most recent agreement (even if terminated)
        agreements = [
            a for a in self.agreements.values()
            if a.franchise_id == franchise_id
        ]
        if agreements:
            agreements.sort(key=lambda a: a.created_at, reverse=True)
            return agreements[0]
        
        return None
    
    def get_franchise_report(
        self,
        franchise_id: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive franchise report.
        MASTER-ONLY: Business reporting.
        
        Args:
            franchise_id: Franchise ID
            
        Returns:
            Franchise report dictionary
        """
        agreement = self.get_agreement_by_franchise(franchise_id)
        if not agreement:
            return {"error": "Franchise not found"}
        
        # Get revenue summary from RevenueSharing
        revenue_summary = {}
        if self.revenue_sharing:
            revenue_summary = self.revenue_sharing.get_slave_earnings_summary(franchise_id, days=30)
        
        # Calculate fees
        monthly_revenue = revenue_summary.get("total_earned", 0.0)
        fee_breakdown = self.collect_royalties(franchise_id, monthly_revenue) if agreement.status == FranchiseStatus.ACTIVE else {}
        
        # Check compliance
        compliance = self.check_compliance(franchise_id)
        
        return {
            "franchise_id": franchise_id,
            "agreement_id": agreement.agreement_id,
            "status": agreement.status.value,
            "created_at": agreement.created_at.isoformat(),
            "expires_at": agreement.expires_at.isoformat() if agreement.expires_at else None,
            "financial_terms": {
                "franchise_fee": agreement.franchise_fee,
                "royalty_rate": agreement.royalty_rate,
                "advertising_fee": agreement.advertising_fee,
                "minimum_monthly_revenue": agreement.minimum_monthly_revenue
            },
            "revenue_summary": revenue_summary,
            "fee_breakdown": fee_breakdown,
            "compliance": {
                "status": compliance.value,
                "violations": len(agreement.violations),
                "recent_violations": len([
                    v for v in agreement.violations
                    if datetime.fromisoformat(v.get("timestamp", datetime.now().isoformat())) > datetime.now() - timedelta(days=30)
                ])
            },
            "master_control": {
                "override_enabled": agreement.master_override_enabled,
                "remote_shutdown_enabled": agreement.remote_shutdown_enabled,
                "code_update_required": agreement.code_update_required
            }
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get franchise manager statistics."""
        return {
            "total_franchises": self.stats["total_franchises"],
            "active_franchises": self.stats["active_franchises"],
            "total_franchise_fees": self.stats["total_franchise_fees"],
            "total_royalties": self.stats.get("total_royalties", 0.0),
            "total_advertising_fees": self.stats["total_advertising_fees"],
            "violations": self.stats["violations"],
            "terminations": self.stats["terminations"]
        }
    
    def save(self):
        """Save franchise data."""
        with self._lock:
            data = {
                "agreements": {
                    aid: agreement.to_dict()
                    for aid, agreement in self.agreements.items()
                },
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save franchise data: {e}")
    
    def load(self):
        """Load franchise data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                agreements_data = data.get("agreements", {})
                for aid, agreement_dict in agreements_data.items():
                    try:
                        agreement = FranchiseAgreement(
                            agreement_id=agreement_dict["agreement_id"],
                            franchise_id=agreement_dict["franchise_id"],
                            created_at=datetime.fromisoformat(agreement_dict["created_at"]),
                            expires_at=datetime.fromisoformat(agreement_dict["expires_at"]) if agreement_dict.get("expires_at") else None,
                            status=FranchiseStatus(agreement_dict["status"]),
                            franchise_fee=agreement_dict["franchise_fee"],
                            royalty_rate=agreement_dict["royalty_rate"],
                            advertising_fee=agreement_dict["advertising_fee"],
                            minimum_monthly_revenue=agreement_dict["minimum_monthly_revenue"],
                            allowed_operations=agreement_dict.get("allowed_operations", []),
                            restricted_operations=agreement_dict.get("restricted_operations", []),
                            reporting_frequency=agreement_dict.get("reporting_frequency", "weekly"),
                            performance_targets=agreement_dict.get("performance_targets", {}),
                            master_override_enabled=agreement_dict.get("master_override_enabled", True),
                            remote_shutdown_enabled=agreement_dict.get("remote_shutdown_enabled", True),
                            code_update_required=agreement_dict.get("code_update_required", True),
                            data_access_level=agreement_dict.get("data_access_level", "limited"),
                            compliance_status=ComplianceStatus(agreement_dict.get("compliance_status", "compliant")),
                            violations=agreement_dict.get("violations", []),
                            last_compliance_check=datetime.fromisoformat(agreement_dict["last_compliance_check"]) if agreement_dict.get("last_compliance_check") else None,
                            notes=agreement_dict.get("notes", ""),
                            metadata=agreement_dict.get("metadata", {})
                        )
                        self.agreements[aid] = agreement
                    except Exception as e:
                        logger.error(f"Failed to load agreement {aid}: {e}")
                
                if "stats" in data:
                    self.stats.update(data["stats"])
            
            logger.info(f"Loaded {len(self.agreements)} franchise agreements")
        except Exception as e:
            logger.error(f"Failed to load franchise data: {e}")

