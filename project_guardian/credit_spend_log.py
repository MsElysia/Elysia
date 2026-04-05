# project_guardian/credit_spend_log.py
# CreditSpendLog: Audit Trail of Credit Transactions
# Tracks all credit spending and earning activities

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
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


class TransactionType(Enum):
    """Types of credit transactions."""
    EARN = "earn"  # Credits earned
    SPEND = "spend"  # Credits spent
    TRANSFER = "transfer"  # Credits transferred
    REWARD = "reward"  # Reward granted
    PENALTY = "penalty"  # Penalty applied
    ADJUSTMENT = "adjustment"  # Manual adjustment


class TransactionCategory(Enum):
    """Transaction categories."""
    TASK_COMPLETION = "task_completion"
    MUTATION = "mutation"
    TRUST_IMPROVEMENT = "trust_improvement"
    REVENUE_GENERATION = "revenue_generation"
    SYSTEM_OPERATION = "system_operation"
    MANUAL = "manual"
    FRANCHISE_FEE = "franchise_fee"
    ROYALTY = "royalty"
    OTHER = "other"


@dataclass
class CreditTransaction:
    """Represents a credit transaction."""
    transaction_id: str
    account_id: str
    transaction_type: TransactionType
    category: TransactionCategory
    amount: float
    balance_before: float
    balance_after: float
    timestamp: datetime
    description: str
    reference_id: Optional[str] = None  # Reference to related entity (task_id, mutation_id, etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "account_id": self.account_id,
            "transaction_type": self.transaction_type.value,
            "category": self.category.value,
            "amount": self.amount,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "reference_id": self.reference_id,
            "metadata": self.metadata
        }


class CreditSpendLog:
    """
    Audit trail of credit transactions.
    Tracks all credit earning, spending, and transfers for complete financial accountability.
    """
    
    def __init__(
        self,
        storage_path: str = "data/credit_spend_log.json",
        audit_log: Optional[TrustAuditLog] = None,
        retention_days: int = 365
    ):
        """
        Initialize CreditSpendLog.
        
        Args:
            storage_path: Path to store transaction log
            audit_log: TrustAuditLog instance for audit integration
            retention_days: Days to retain transactions (default: 1 year)
        """
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log = audit_log
        self.retention_days = retention_days
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Transaction registry
        self.transactions: Dict[str, CreditTransaction] = {}
        
        # Statistics
        self.stats = {
            "total_transactions": 0,
            "total_earned": 0.0,
            "total_spent": 0.0,
            "total_transferred": 0.0,
            "total_rewards": 0.0,
            "total_penalties": 0.0,
            "by_category": {},
            "by_type": {}
        }
        
        # Load existing transactions
        self.load()
    
    def log_transaction(
        self,
        account_id: str,
        transaction_type: TransactionType,
        category: TransactionCategory,
        amount: float,
        balance_before: float,
        balance_after: float,
        description: str,
        reference_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a credit transaction.
        
        Args:
            account_id: Account ID
            transaction_type: Type of transaction
            category: Transaction category
            amount: Transaction amount (positive for earn, negative for spend)
            balance_before: Balance before transaction
            balance_after: Balance after transaction
            description: Transaction description
            reference_id: Optional reference ID (task_id, mutation_id, etc.)
            metadata: Optional metadata
            
        Returns:
            Transaction ID
        """
        transaction_id = str(uuid.uuid4())
        
        transaction = CreditTransaction(
            transaction_id=transaction_id,
            account_id=account_id,
            transaction_type=transaction_type,
            category=category,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            timestamp=datetime.now(),
            description=description,
            reference_id=reference_id,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.transactions[transaction_id] = transaction
            self.stats["total_transactions"] += 1
            
            # Update statistics
            if transaction_type == TransactionType.EARN:
                self.stats["total_earned"] += abs(amount)
            elif transaction_type == TransactionType.SPEND:
                self.stats["total_spent"] += abs(amount)
            elif transaction_type == TransactionType.TRANSFER:
                self.stats["total_transferred"] += abs(amount)
            elif transaction_type == TransactionType.REWARD:
                self.stats["total_rewards"] += abs(amount)
            elif transaction_type == TransactionType.PENALTY:
                self.stats["total_penalties"] += abs(amount)
            
            # Category statistics
            cat = category.value
            self.stats["by_category"][cat] = self.stats["by_category"].get(cat, 0) + abs(amount)
            
            # Type statistics
            trans_type = transaction_type.value
            self.stats["by_type"][trans_type] = self.stats["by_type"].get(trans_type, 0) + abs(amount)
            
            self.save()
        
        # Log to audit trail if available
        if self.audit_log and AuditEventType and AuditSeverity:
            severity = AuditSeverity.INFO
            if transaction_type == TransactionType.PENALTY:
                severity = AuditSeverity.WARNING
            
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Credit transaction: {transaction_type.value} {abs(amount):.2f} credits - {description}",
                severity=severity,
                actor=account_id,
                metadata={
                    "transaction_id": transaction_id,
                    "transaction_type": transaction_type.value,
                    "category": category.value,
                    "amount": amount,
                    "reference_id": reference_id
                }
            )
        
        logger.info(f"Logged credit transaction: {transaction_id} - {transaction_type.value} {abs(amount):.2f} credits")
        return transaction_id
    
    def get_transaction(self, transaction_id: str) -> Optional[CreditTransaction]:
        """Get a transaction by ID."""
        return self.transactions.get(transaction_id)
    
    def get_account_transactions(
        self,
        account_id: str,
        limit: int = 100,
        transaction_type: Optional[TransactionType] = None,
        category: Optional[TransactionCategory] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[CreditTransaction]:
        """
        Get transactions for a specific account with filters.
        
        Args:
            account_id: Account ID
            limit: Maximum number of transactions
            transaction_type: Filter by transaction type
            category: Filter by category
            start_date: Start date filter
            end_date: End date filter
            
        Returns:
            List of transactions
        """
        filtered = [
            t for t in self.transactions.values()
            if t.account_id == account_id
        ]
        
        # Apply filters
        if transaction_type:
            filtered = [t for t in filtered if t.transaction_type == transaction_type]
        
        if category:
            filtered = [t for t in filtered if t.category == category]
        
        if start_date:
            filtered = [t for t in filtered if t.timestamp >= start_date]
        
        if end_date:
            filtered = [t for t in filtered if t.timestamp <= end_date]
        
        # Sort by timestamp (newest first)
        filtered.sort(key=lambda t: t.timestamp, reverse=True)
        
        return filtered[:limit]
    
    def get_transactions_by_reference(
        self,
        reference_id: str
    ) -> List[CreditTransaction]:
        """Get all transactions for a reference ID (e.g., task_id, mutation_id)."""
        return [
            t for t in self.transactions.values()
            if t.reference_id == reference_id
        ]
    
    def get_spending_summary(
        self,
        account_id: Optional[str] = None,
        days: int = 30,
        category: Optional[TransactionCategory] = None
    ) -> Dict[str, Any]:
        """
        Get spending summary for an account or all accounts.
        
        Args:
            account_id: Specific account ID (None = all accounts)
            days: Number of days to analyze
            category: Filter by category
            
        Returns:
            Spending summary dictionary
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        filtered = [
            t for t in self.transactions.values()
            if t.timestamp >= cutoff
        ]
        
        if account_id:
            filtered = [t for t in filtered if t.account_id == account_id]
        
        if category:
            filtered = [t for t in filtered if t.category == category]
        
        # Calculate summary
        total_earned = sum(abs(t.amount) for t in filtered if t.transaction_type == TransactionType.EARN)
        total_spent = sum(abs(t.amount) for t in filtered if t.transaction_type == TransactionType.SPEND)
        total_rewards = sum(abs(t.amount) for t in filtered if t.transaction_type == TransactionType.REWARD)
        total_penalties = sum(abs(t.amount) for t in filtered if t.transaction_type == TransactionType.PENALTY)
        
        by_category = {}
        for transaction in filtered:
            cat = transaction.category.value
            if cat not in by_category:
                by_category[cat] = {"earned": 0.0, "spent": 0.0, "count": 0}
            
            if transaction.transaction_type == TransactionType.EARN:
                by_category[cat]["earned"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.SPEND:
                by_category[cat]["spent"] += abs(transaction.amount)
            
            by_category[cat]["count"] += 1
        
        return {
            "period_days": days,
            "account_id": account_id,
            "total_transactions": len(filtered),
            "total_earned": total_earned,
            "total_spent": total_spent,
            "total_rewards": total_rewards,
            "total_penalties": total_penalties,
            "net_change": total_earned - total_spent + total_rewards - total_penalties,
            "by_category": by_category,
            "average_daily_earned": total_earned / days if days > 0 else 0,
            "average_daily_spent": total_spent / days if days > 0 else 0
        }
    
    def get_category_breakdown(
        self,
        account_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Dict[str, float]]:
        """
        Get spending breakdown by category.
        
        Args:
            account_id: Specific account ID (None = all accounts)
            days: Number of days to analyze
            
        Returns:
            Dictionary of category -> spending data
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        filtered = [
            t for t in self.transactions.values()
            if t.timestamp >= cutoff
        ]
        
        if account_id:
            filtered = [t for t in filtered if t.account_id == account_id]
        
        breakdown = {}
        for transaction in filtered:
            cat = transaction.category.value
            if cat not in breakdown:
                breakdown[cat] = {
                    "earned": 0.0,
                    "spent": 0.0,
                    "rewards": 0.0,
                    "penalties": 0.0,
                    "count": 0
                }
            
            if transaction.transaction_type == TransactionType.EARN:
                breakdown[cat]["earned"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.SPEND:
                breakdown[cat]["spent"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.REWARD:
                breakdown[cat]["rewards"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.PENALTY:
                breakdown[cat]["penalties"] += abs(transaction.amount)
            
            breakdown[cat]["count"] += 1
        
        return breakdown
    
    def cleanup_old_transactions(self):
        """Remove transactions older than retention period."""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        
        with self._lock:
            to_remove = [
                tid for tid, transaction in self.transactions.items()
                if transaction.timestamp < cutoff
            ]
            
            for tid in to_remove:
                del self.transactions[tid]
            
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old transactions")
                self.save()
        
        return len(to_remove)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get credit spend log statistics."""
        return {
            "total_transactions": self.stats["total_transactions"],
            "total_earned": self.stats["total_earned"],
            "total_spent": self.stats["total_spent"],
            "total_transferred": self.stats["total_transferred"],
            "total_rewards": self.stats["total_rewards"],
            "total_penalties": self.stats["total_penalties"],
            "by_category": self.stats["by_category"],
            "by_type": self.stats["by_type"],
            "retention_days": self.retention_days,
            "stored_transactions": len(self.transactions)
        }
    
    def export_transactions(
        self,
        output_path: str,
        account_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> bool:
        """
        Export transactions to JSON file.
        
        Args:
            output_path: Output file path
            account_id: Filter by account ID
            start_date: Start date filter
            end_date: End date filter
            
        Returns:
            True if export successful
        """
        filtered = list(self.transactions.values())
        
        if account_id:
            filtered = [t for t in filtered if t.account_id == account_id]
        
        if start_date:
            filtered = [t for t in filtered if t.timestamp >= start_date]
        
        if end_date:
            filtered = [t for t in filtered if t.timestamp <= end_date]
        
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "export_timestamp": datetime.now().isoformat(),
                "filters": {
                    "account_id": account_id,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None
                },
                "transaction_count": len(filtered),
                "transactions": [t.to_dict() for t in filtered]
            }
            
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Exported {len(filtered)} transactions to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export transactions: {e}")
            return False
    
    def save(self):
        """Save transaction log."""
        with self._lock:
            data = {
                "transactions": {
                    tid: transaction.to_dict()
                    for tid, transaction in self.transactions.items()
                },
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save credit spend log: {e}")
    
    def load(self):
        """Load transaction log."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                transactions_data = data.get("transactions", {})
                for tid, trans_dict in transactions_data.items():
                    try:
                        transaction = CreditTransaction(
                            transaction_id=trans_dict["transaction_id"],
                            account_id=trans_dict["account_id"],
                            transaction_type=TransactionType(trans_dict["transaction_type"]),
                            category=TransactionCategory(trans_dict["category"]),
                            amount=trans_dict["amount"],
                            balance_before=trans_dict["balance_before"],
                            balance_after=trans_dict["balance_after"],
                            timestamp=datetime.fromisoformat(trans_dict["timestamp"]),
                            description=trans_dict["description"],
                            reference_id=trans_dict.get("reference_id"),
                            metadata=trans_dict.get("metadata", {})
                        )
                        self.transactions[tid] = transaction
                    except Exception as e:
                        logger.error(f"Failed to load transaction {tid}: {e}")
                
                if "stats" in data:
                    # Merge stats but recalculate from loaded transactions
                    self.stats.update(data["stats"])
                    # Recalculate to ensure accuracy
                    self._recalculate_stats()
            
            logger.info(f"Loaded {len(self.transactions)} credit transactions")
        except Exception as e:
            logger.error(f"Failed to load credit spend log: {e}")
    
    def _recalculate_stats(self):
        """Recalculate statistics from loaded transactions."""
        self.stats = {
            "total_transactions": len(self.transactions),
            "total_earned": 0.0,
            "total_spent": 0.0,
            "total_transferred": 0.0,
            "total_rewards": 0.0,
            "total_penalties": 0.0,
            "by_category": {},
            "by_type": {}
        }
        
        for transaction in self.transactions.values():
            if transaction.transaction_type == TransactionType.EARN:
                self.stats["total_earned"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.SPEND:
                self.stats["total_spent"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.TRANSFER:
                self.stats["total_transferred"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.REWARD:
                self.stats["total_rewards"] += abs(transaction.amount)
            elif transaction.transaction_type == TransactionType.PENALTY:
                self.stats["total_penalties"] += abs(transaction.amount)
            
            cat = transaction.category.value
            self.stats["by_category"][cat] = self.stats["by_category"].get(cat, 0) + abs(transaction.amount)
            
            trans_type = transaction.transaction_type.value
            self.stats["by_type"][trans_type] = self.stats["by_type"].get(trans_type, 0) + abs(transaction.amount)


# Integration helper for CoreCredits
def integrate_with_core_credits(core_credits_instance, credit_spend_log_instance):
    """
    Integrate CreditSpendLog with CoreCredits to automatically log transactions.
    
    Args:
        core_credits_instance: CoreCredits instance
        credit_spend_log_instance: CreditSpendLog instance
    """
    # Store references
    original_earn = core_credits_instance.earn_credits
    original_spend = core_credits_instance.spend_credits
    original_transfer = core_credits_instance.transfer_credits
    
    def logged_earn(account_id: str, amount: float, reason: str = "", metadata: Optional[Dict[str, Any]] = None):
        """Logged version of earn_credits."""
        balance_before = core_credits_instance.get_balance(account_id)
        result = original_earn(account_id, amount, reason, metadata)
        balance_after = core_credits_instance.get_balance(account_id)
        
        # Log transaction
        credit_spend_log_instance.log_transaction(
            account_id=account_id,
            transaction_type=TransactionType.EARN,
            category=TransactionCategory.SYSTEM_OPERATION,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=reason or "Credits earned",
            metadata=metadata or {}
        )
        
        return result
    
    def logged_spend(account_id: str, amount: float, reason: str = "", metadata: Optional[Dict[str, Any]] = None):
        """Logged version of spend_credits."""
        balance_before = core_credits_instance.get_balance(account_id)
        result = original_spend(account_id, amount, reason, metadata)
        balance_after = core_credits_instance.get_balance(account_id)
        
        # Determine category from metadata
        category = TransactionCategory.SYSTEM_OPERATION
        if metadata and metadata.get("category"):
            try:
                category = TransactionCategory(metadata["category"])
            except ValueError:
                pass
        
        # Log transaction
        credit_spend_log_instance.log_transaction(
            account_id=account_id,
            transaction_type=TransactionType.SPEND,
            category=category,
            amount=-amount,  # Negative for spending
            balance_before=balance_before,
            balance_after=balance_after,
            description=reason or "Credits spent",
            reference_id=metadata.get("reference_id") if metadata else None,
            metadata=metadata or {}
        )
        
        return result
    
    def logged_transfer(from_account: str, to_account: str, amount: float, reason: str = "", metadata: Optional[Dict[str, Any]] = None):
        """Logged version of transfer_credits."""
        from_balance_before = core_credits_instance.get_balance(from_account)
        to_balance_before = core_credits_instance.get_balance(to_account)
        
        result = original_transfer(from_account, to_account, amount, reason, metadata)
        
        from_balance_after = core_credits_instance.get_balance(from_account)
        to_balance_after = core_credits_instance.get_balance(to_account)
        
        # Log transfer out
        credit_spend_log_instance.log_transaction(
            account_id=from_account,
            transaction_type=TransactionType.TRANSFER,
            category=TransactionCategory.SYSTEM_OPERATION,
            amount=-amount,
            balance_before=from_balance_before,
            balance_after=from_balance_after,
            description=f"Transfer to {to_account}: {reason}",
            metadata={**(metadata or {}), "to_account": to_account}
        )
        
        # Log transfer in
        credit_spend_log_instance.log_transaction(
            account_id=to_account,
            transaction_type=TransactionType.TRANSFER,
            category=TransactionCategory.SYSTEM_OPERATION,
            amount=amount,
            balance_before=to_balance_before,
            balance_after=to_balance_after,
            description=f"Transfer from {from_account}: {reason}",
            metadata={**(metadata or {}), "from_account": from_account}
        )
        
        return result
    
    # Replace methods
    core_credits_instance.earn_credits = logged_earn
    core_credits_instance.spend_credits = logged_spend
    core_credits_instance.transfer_credits = logged_transfer
    
    logger.info("CreditSpendLog integrated with CoreCredits")


# Example usage
if __name__ == "__main__":
    # Create credit spend log
    spend_log = CreditSpendLog()
    
    # Log a transaction
    transaction_id = spend_log.log_transaction(
        account_id="account_001",
        transaction_type=TransactionType.EARN,
        category=TransactionCategory.TASK_COMPLETION,
        amount=100.0,
        balance_before=500.0,
        balance_after=600.0,
        description="Task completion reward",
        reference_id="task_123"
    )
    
    # Get spending summary
    summary = spend_log.get_spending_summary(account_id="account_001", days=30)
    print(f"Spending summary: {summary}")
    
    # Get statistics
    stats = spend_log.get_statistics()
    print(f"Statistics: {stats}")

