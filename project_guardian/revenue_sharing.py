# project_guardian/revenue_sharing.py
# RevenueSharing: Secure Revenue Sharing System
# Ensures master receives share from slave earnings

import logging
import json
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

try:
    from .master_slave_controller import MasterSlaveController, SlaveInstance, SlaveStatus
    from .asset_manager import AssetManager, AssetType
    from .trust_registry import TrustRegistry
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
except ImportError:
    from master_slave_controller import MasterSlaveController, SlaveInstance, SlaveStatus
    from asset_manager import AssetManager, AssetType
    from trust_registry import TrustRegistry
    try:
        from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    except ImportError:
        TrustAuditLog = None
        AuditEventType = None
        AuditSeverity = None

logger = logging.getLogger(__name__)


class RevenueStatus(Enum):
    """Revenue transaction status."""
    PENDING = "pending"  # Awaiting verification
    VERIFIED = "verified"  # Verified by master
    ESCROWED = "escrowed"  # Funds in escrow
    DISTRIBUTED = "distributed"  # Funds distributed
    DISPUTED = "disputed"  # Under dispute
    REJECTED = "rejected"  # Rejected by master


@dataclass
class RevenueTransaction:
    """Represents a revenue transaction from a slave."""
    transaction_id: str
    slave_id: str
    amount: float
    currency: str
    source: str  # Source of revenue (payment processor, service, etc.)
    master_share_percent: float  # Master's share percentage (0.0-1.0)
    master_share_amount: float
    slave_share_amount: float
    status: RevenueStatus
    payment_proof: Optional[str] = None  # Payment verification proof
    escrow_address: Optional[str] = None  # Escrow wallet/account
    verified_at: Optional[datetime] = None
    distributed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "slave_id": self.slave_id,
            "amount": self.amount,
            "currency": self.currency,
            "source": self.source,
            "master_share_percent": self.master_share_percent,
            "master_share_amount": self.master_share_amount,
            "slave_share_amount": self.slave_share_amount,
            "status": self.status.value,
            "payment_proof": self.payment_proof,
            "escrow_address": self.escrow_address,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "distributed_at": self.distributed_at.isoformat() if self.distributed_at else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


class RevenueSharing:
    """
    Secure revenue sharing system.
    Slaves can earn money, master automatically receives its share.
    Uses escrow-like verification and distribution.
    """
    
    def __init__(
        self,
        master_slave: MasterSlaveController,
        asset_manager: Optional[AssetManager] = None,
        trust_registry: Optional[TrustRegistry] = None,
        audit_log: Optional[TrustAuditLog] = None,
        franchise_manager: Optional[Any] = None,  # FranchiseManager (avoid circular import)
        default_master_share: float = 0.3,  # 30% default master share
        storage_path: str = "data/revenue_sharing.json"
    ):
        """
        Initialize RevenueSharing.
        
        Args:
            master_slave: MasterSlaveController instance
            asset_manager: AssetManager instance
            trust_registry: TrustRegistry instance
            audit_log: TrustAuditLog instance
            default_master_share: Default master share percentage (0.0-1.0)
            storage_path: Storage path
        """
        self.master_slave = master_slave
        self.asset_manager = asset_manager
        self.trust_registry = trust_registry
        self.audit_log = audit_log
        self.franchise_manager = franchise_manager
        self.default_master_share = default_master_share
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe operations (use RLock for reentrant locking)
        self._lock = RLock()
        
        # Transaction storage
        self.transactions: Dict[str, RevenueTransaction] = {}
        
        # Per-slave master share rates (can be customized)
        self.master_share_rates: Dict[str, float] = {}
        
        # Escrow accounts (if using escrow)
        self.escrow_accounts: Dict[str, str] = {}  # slave_id -> escrow_address
        
        # Statistics
        self.stats = {
            "total_transactions": 0,
            "total_revenue": 0.0,
            "master_share_total": 0.0,
            "slave_share_total": 0.0,
            "pending_verification": 0,
            "distributed": 0
        }
        
        # Load data
        self.load()
    
    def report_slave_earnings(
        self,
        slave_id: str,
        amount: float,
        currency: str = "USD",
        source: str = "unknown",
        payment_proof: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Slave reports earnings to master.
        Creates pending transaction awaiting master verification.
        
        Args:
            slave_id: Slave ID
            amount: Earned amount
            currency: Currency code
            source: Revenue source
            payment_proof: Payment verification proof (receipt, transaction hash, etc.)
            metadata: Optional metadata
            
        Returns:
            Transaction ID
        """
        # Verify slave exists and is active
        slave = self.master_slave.get_slave(slave_id)
        if not slave:
            logger.error(f"Slave {slave_id} not found")
            return ""
        
        if slave.status != SlaveStatus.ACTIVE:
            logger.warning(f"Slave {slave_id} is not active, cannot report earnings")
            return ""
        
        # Get master share rate for this slave
        # Check franchise manager first (if available)
        master_share = self.default_master_share
        if self.franchise_manager:
            agreement = self.franchise_manager.get_agreement_by_franchise(slave_id)
            if agreement:
                # Franchise royalties + revenue sharing
                master_share = agreement.royalty_rate + self.default_master_share
                master_share = min(master_share, 1.0)  # Cap at 100%
        
        # Override with custom rate if set
        master_share = self.master_share_rates.get(slave_id, master_share)
        
        # Calculate shares
        master_share_amount = amount * master_share
        slave_share_amount = amount * (1.0 - master_share)
        
        transaction_id = str(uuid.uuid4())
        
        transaction = RevenueTransaction(
            transaction_id=transaction_id,
            slave_id=slave_id,
            amount=amount,
            currency=currency,
            source=source,
            master_share_percent=master_share,
            master_share_amount=master_share_amount,
            slave_share_amount=slave_share_amount,
            status=RevenueStatus.PENDING,
            payment_proof=payment_proof,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.transactions[transaction_id] = transaction
            self.stats["total_transactions"] += 1
            self.stats["total_revenue"] += amount
            self.stats["pending_verification"] += 1
            self.save()
        
        # Log transaction
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Slave earnings reported: {slave_id} - ${amount:.2f}",
                severity=AuditSeverity.INFO,
                actor=slave_id,
                metadata={
                    "transaction_id": transaction_id,
                    "amount": amount,
                    "master_share": master_share_amount
                }
            )
        
        logger.info(f"Slave {slave_id} reported earnings: ${amount:.2f} (Master share: ${master_share_amount:.2f})")
        return transaction_id
    
    def verify_transaction(
        self,
        transaction_id: str,
        verified: bool = True,
        verification_notes: Optional[str] = None
    ) -> bool:
        """
        Master verifies a revenue transaction.
        Can approve or reject based on payment proof verification.
        
        Args:
            transaction_id: Transaction ID
            verified: True if verified, False if rejected
            verification_notes: Optional verification notes
            
        Returns:
            True if verification successful
        """
        transaction = self.transactions.get(transaction_id)
        if not transaction:
            logger.error(f"Transaction {transaction_id} not found")
            return False
        
        if transaction.status != RevenueStatus.PENDING:
            logger.warning(f"Transaction {transaction_id} not pending (status: {transaction.status.value})")
            return False
        
        with self._lock:
            if verified:
                transaction.status = RevenueStatus.VERIFIED
                transaction.verified_at = datetime.now()
                
                # Move to escrow or distribute
                if self._use_escrow():
                    transaction.status = RevenueStatus.ESCROWED
                    # In production: Transfer to escrow account
                    escrow_address = self._get_or_create_escrow(transaction.slave_id)
                    transaction.escrow_address = escrow_address
                else:
                    # Direct distribution
                    transaction.status = RevenueStatus.DISTRIBUTED
                    transaction.distributed_at = datetime.now()
                    self._distribute_funds(transaction)
                
                self.stats["pending_verification"] -= 1
                self.stats["distributed"] += 1
                self.stats["master_share_total"] += transaction.master_share_amount
                self.stats["slave_share_total"] += transaction.slave_share_amount
            else:
                transaction.status = RevenueStatus.REJECTED
                transaction.metadata["rejection_reason"] = verification_notes
                self.stats["pending_verification"] -= 1
            
            self.save()
        
        # Log verification
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Transaction {transaction_id} {'verified' if verified else 'rejected'}: {verification_notes or 'No notes'}",
                severity=AuditSeverity.INFO if verified else AuditSeverity.WARNING,
                metadata={
                    "transaction_id": transaction_id,
                    "verified": verified,
                    "amount": transaction.amount
                }
            )
        
        logger.info(f"Transaction {transaction_id} {'verified' if verified else 'rejected'}")
        return True
    
    def distribute_from_escrow(self, transaction_id: str) -> bool:
        """
        Distribute funds from escrow to master and slave.
        Called when escrow period expires or conditions met.
        
        Args:
            transaction_id: Transaction ID
            
        Returns:
            True if distribution successful
        """
        transaction = self.transactions.get(transaction_id)
        if not transaction:
            return False
        
        if transaction.status != RevenueStatus.ESCROWED:
            logger.warning(f"Transaction {transaction_id} not in escrow")
            return False
        
        with self._lock:
            transaction.status = RevenueStatus.DISTRIBUTED
            transaction.distributed_at = datetime.now()
            self._distribute_funds(transaction)
            self.save()
        
        logger.info(f"Distributed funds from escrow: {transaction_id}")
        return True
    
    def _distribute_funds(self, transaction: RevenueTransaction):
        """
        Distribute funds to master and slave accounts.
        
        Args:
            transaction: Revenue transaction
        """
        # Distribute master share to master
        if self.asset_manager:
            # Get or create a master asset for income tracking
            master_asset_id = "master_income"
            master_asset = self.asset_manager.get_asset(master_asset_id)
            if not master_asset:
                # Create master income asset if it doesn't exist
                master_asset_id = self.asset_manager.add_asset(
                    name="Master Income",
                    asset_type=AssetType.CURRENCY,
                    quantity=0.0,
                    unit="USD",
                    value_per_unit=1.0
                )
            
            # Record transaction with correct parameters
            self.asset_manager.record_transaction(
                asset_id=master_asset_id,
                transaction_type="income",
                quantity=transaction.master_share_amount,
                price_per_unit=1.0,
                description=f"Master share from slave {transaction.slave_id}",
                metadata={
                    "transaction_id": transaction.transaction_id,
                    "slave_id": transaction.slave_id,
                    "source": transaction.source,
                    "total_amount": transaction.amount,
                    "share_percent": transaction.master_share_percent
                }
            )
        
        # Update slave trust based on successful earnings
        if self.trust_registry:
            # Successful revenue increases trust
            trust_delta = min(0.1, transaction.amount / 1000.0)  # Max 0.1 trust per transaction
            # Use update_trust with success=True
            self.trust_registry.update_trust(
                transaction.slave_id,
                success=True,
                category="income",
                amount=trust_delta
            )
        
        # In production: Transfer slave share to slave's account/wallet
        # For now, track it in metadata
        logger.info(f"Distributed: Master=${transaction.master_share_amount:.2f}, Slave=${transaction.slave_share_amount:.2f}")
    
    def _use_escrow(self) -> bool:
        """Check if escrow system should be used."""
        # In production: Configurable escrow settings
        # For now, return False (direct distribution)
        return False
    
    def _get_or_create_escrow(self, slave_id: str) -> str:
        """Get or create escrow account for slave."""
        if slave_id not in self.escrow_accounts:
            # In production: Create actual escrow wallet/account
            escrow_address = f"escrow_{slave_id}_{hashlib.md5(slave_id.encode()).hexdigest()[:8]}"
            self.escrow_accounts[slave_id] = escrow_address
        return self.escrow_accounts[slave_id]
    
    def set_master_share_rate(self, slave_id: str, share_percent: float):
        """
        Set custom master share rate for a specific slave.
        MASTER-ONLY operation.
        
        Args:
            slave_id: Slave ID
            share_percent: Master share percentage (0.0-1.0)
        """
        if share_percent < 0.0 or share_percent > 1.0:
            logger.error(f"Invalid share percent: {share_percent}")
            return
        
        with self._lock:
            self.master_share_rates[slave_id] = share_percent
            self.save()
        
        logger.info(f"Set master share rate for {slave_id}: {share_percent*100:.1f}%")
    
    def get_slave_earnings_summary(
        self,
        slave_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get earnings summary for a slave.
        
        Args:
            slave_id: Slave ID
            days: Days to analyze
            
        Returns:
            Earnings summary dictionary
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        slave_transactions = [
            t for t in self.transactions.values()
            if t.slave_id == slave_id and t.created_at >= cutoff
        ]
        
        total_earned = sum(t.amount for t in slave_transactions if t.status != RevenueStatus.REJECTED)
        total_master_share = sum(t.master_share_amount for t in slave_transactions if t.status in [RevenueStatus.VERIFIED, RevenueStatus.DISTRIBUTED])
        total_slave_share = sum(t.slave_share_amount for t in slave_transactions if t.status == RevenueStatus.DISTRIBUTED)
        
        return {
            "slave_id": slave_id,
            "period_days": days,
            "total_transactions": len(slave_transactions),
            "total_earned": total_earned,
            "total_master_share": total_master_share,
            "total_slave_share": total_slave_share,
            "pending_amount": sum(t.amount for t in slave_transactions if t.status == RevenueStatus.PENDING),
            "master_share_rate": self.master_share_rates.get(slave_id, self.default_master_share)
        }
    
    def get_master_revenue_summary(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get master revenue summary from all slaves.
        MASTER-ONLY reporting.
        
        Args:
            days: Days to analyze
            
        Returns:
            Revenue summary dictionary
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        recent_transactions = [
            t for t in self.transactions.values()
            if t.created_at >= cutoff
        ]
        
        by_slave = {}
        by_source = {}
        
        for transaction in recent_transactions:
            if transaction.status in [RevenueStatus.VERIFIED, RevenueStatus.DISTRIBUTED]:
                # By slave
                slave_id = transaction.slave_id
                by_slave[slave_id] = by_slave.get(slave_id, 0.0) + transaction.master_share_amount
                
                # By source
                source = transaction.source
                by_source[source] = by_source.get(source, 0.0) + transaction.master_share_amount
        
        total_master_revenue = sum(t.master_share_amount for t in recent_transactions if t.status in [RevenueStatus.VERIFIED, RevenueStatus.DISTRIBUTED])
        total_slave_revenue = sum(t.slave_share_amount for t in recent_transactions if t.status == RevenueStatus.DISTRIBUTED)
        
        return {
            "period_days": days,
            "total_master_revenue": total_master_revenue,
            "total_slave_revenue": total_slave_revenue,
            "total_revenue": total_master_revenue + total_slave_revenue,
            "master_revenue_by_slave": by_slave,
            "master_revenue_by_source": by_source,
            "pending_verification": len([t for t in recent_transactions if t.status == RevenueStatus.PENDING])
        }
    
    def get_transaction(self, transaction_id: str) -> Optional[RevenueTransaction]:
        """Get a transaction by ID."""
        return self.transactions.get(transaction_id)
    
    def list_pending_transactions(self, limit: int = 50) -> List[RevenueTransaction]:
        """Get pending transactions awaiting verification."""
        pending = [
            t for t in self.transactions.values()
            if t.status == RevenueStatus.PENDING
        ]
        pending.sort(key=lambda t: t.created_at, reverse=True)
        return pending[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get revenue sharing statistics."""
        return {
            "total_transactions": self.stats["total_transactions"],
            "total_revenue": self.stats["total_revenue"],
            "master_share_total": self.stats["master_share_total"],
            "slave_share_total": self.stats["slave_share_total"],
            "pending_verification": self.stats["pending_verification"],
            "distributed": self.stats["distributed"],
            "default_master_share": self.default_master_share,
            "custom_share_rates": len(self.master_share_rates)
        }
    
    def save(self):
        """Save revenue sharing data."""
        import json
        
        with self._lock:
            data = {
                "transactions": {
                    tid: transaction.to_dict()
                    for tid, transaction in self.transactions.items()
                },
                "master_share_rates": self.master_share_rates,
                "escrow_accounts": self.escrow_accounts,
                "stats": self.stats,
                "default_master_share": self.default_master_share,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save revenue sharing data: {e}")
    
    def load(self):
        """Load revenue sharing data."""
        if not self.storage_path.exists():
            return
        
        import json
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                transactions_data = data.get("transactions", {})
                for tid, trans_dict in transactions_data.items():
                    try:
                        transaction = RevenueTransaction(
                            transaction_id=trans_dict["transaction_id"],
                            slave_id=trans_dict["slave_id"],
                            amount=trans_dict["amount"],
                            currency=trans_dict["currency"],
                            source=trans_dict["source"],
                            master_share_percent=trans_dict["master_share_percent"],
                            master_share_amount=trans_dict["master_share_amount"],
                            slave_share_amount=trans_dict["slave_share_amount"],
                            status=RevenueStatus(trans_dict["status"]),
                            payment_proof=trans_dict.get("payment_proof"),
                            escrow_address=trans_dict.get("escrow_address"),
                            verified_at=datetime.fromisoformat(trans_dict["verified_at"]) if trans_dict.get("verified_at") else None,
                            distributed_at=datetime.fromisoformat(trans_dict["distributed_at"]) if trans_dict.get("distributed_at") else None,
                            metadata=trans_dict.get("metadata", {}),
                            created_at=datetime.fromisoformat(trans_dict["created_at"])
                        )
                        self.transactions[tid] = transaction
                    except Exception as e:
                        logger.error(f"Failed to load transaction {tid}: {e}")
                
                self.master_share_rates = data.get("master_share_rates", {})
                self.escrow_accounts = data.get("escrow_accounts", {})
                if "stats" in data:
                    self.stats.update(data["stats"])
                self.default_master_share = data.get("default_master_share", 0.3)
            
            logger.info(f"Loaded {len(self.transactions)} revenue transactions")
        except Exception as e:
            logger.error(f"Failed to load revenue sharing data: {e}")


# Example usage
if __name__ == "__main__":
    # This demonstrates the revenue sharing flow
    
    # Slave reports earnings
    revenue_sharing = RevenueSharing(
        master_slave=None,  # Would be provided
        default_master_share=0.3  # 30% to master
    )
    
    # Slave reports $100 earned
    transaction_id = revenue_sharing.report_slave_earnings(
        slave_id="slave_001",
        amount=100.0,
        currency="USD",
        source="gumroad_sale",
        payment_proof="txn_hash_abc123"
    )
    
    # Master verifies
    revenue_sharing.verify_transaction(
        transaction_id,
        verified=True,
        verification_notes="Payment verified via API"
    )
    
    # Funds distributed:
    # Master receives: $30.00 (30%)
    # Slave receives: $70.00 (70%)

