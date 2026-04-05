# project_guardian/core_credits.py
# CoreCredits: Virtual Currency System
# Based on elysia 4 (Main Consolidation) designs

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from threading import Lock
import uuid

logger = logging.getLogger(__name__)


class TransactionType(Enum):
    """Types of credit transactions."""
    EARNED = "earned"
    SPENT = "spent"
    TRANSFERRED = "transferred"
    REWARDED = "rewarded"
    PENALTY = "penalty"
    ADJUSTMENT = "adjustment"


@dataclass
class CreditTransaction:
    """A credit transaction record."""
    transaction_id: str
    account_id: str
    transaction_type: TransactionType
    amount: float
    balance_after: float
    description: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "account_id": self.account_id,
            "transaction_type": self.transaction_type.value,
            "amount": self.amount,
            "balance_after": self.balance_after,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreditTransaction":
        """Create CreditTransaction from dictionary."""
        return cls(
            transaction_id=data["transaction_id"],
            account_id=data["account_id"],
            transaction_type=TransactionType(data["transaction_type"]),
            amount=data["amount"],
            balance_after=data["balance_after"],
            description=data["description"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {})
        )


@dataclass
class CreditAccount:
    """A credit account."""
    account_id: str
    name: str
    balance: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    last_transaction_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "account_id": self.account_id,
            "name": self.name,
            "balance": self.balance,
            "created_at": self.created_at.isoformat(),
            "last_transaction_at": self.last_transaction_at.isoformat() if self.last_transaction_at else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreditAccount":
        """Create CreditAccount from dictionary."""
        return cls(
            account_id=data["account_id"],
            name=data["name"],
            balance=data.get("balance", 0.0),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            last_transaction_at=datetime.fromisoformat(data["last_transaction_at"]) if data.get("last_transaction_at") else None,
            metadata=data.get("metadata", {})
        )


class CoreCredits:
    """
    Virtual currency system for Elysia.
    Manages credit accounts, transactions, and economic operations.
    """
    
    def __init__(
        self,
        storage_path: str = "data/core_credits.json",
        default_starting_balance: float = 100.0
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_starting_balance = default_starting_balance
        
        # Thread-safe storage
        self._lock = Lock()
        self.accounts: Dict[str, CreditAccount] = {}
        self.transactions: List[CreditTransaction] = []
        
        # Economic rules
        self.earning_rates: Dict[str, float] = {
            "task_completion": 10.0,
            "goal_achievement": 50.0,
            "trust_improvement": 5.0,
            "optimization": 15.0
        }
        
        self.spending_costs: Dict[str, float] = {
            "api_call": 1.0,
            "mutation": 25.0,
            "resource_usage": 5.0,
            "priority_boost": 10.0
        }
        
        self.load()
    
    def create_account(
        self,
        account_id: Optional[str] = None,
        name: str = "Default Account",
        initial_balance: Optional[float] = None
    ) -> str:
        """
        Create a new credit account.
        
        Args:
            account_id: Optional custom account ID
            name: Account name
            initial_balance: Optional initial balance (defaults to default_starting_balance)
            
        Returns:
            Account ID
        """
        if account_id is None:
            account_id = str(uuid.uuid4())
        
        if account_id in self.accounts:
            logger.warning(f"Account {account_id} already exists")
            return account_id
        
        with self._lock:
            account = CreditAccount(
                account_id=account_id,
                name=name,
                balance=initial_balance if initial_balance is not None else self.default_starting_balance
            )
            
            self.accounts[account_id] = account
            
            # Record initial balance transaction
            if account.balance > 0:
                transaction = CreditTransaction(
                    transaction_id=str(uuid.uuid4()),
                    account_id=account_id,
                    transaction_type=TransactionType.ADJUSTMENT,
                    amount=account.balance,
                    balance_after=account.balance,
                    description=f"Initial balance for {name}"
                )
                self.transactions.append(transaction)
            
            self.save()
        
        logger.info(f"Created credit account: {name} (ID: {account_id}, balance: {account.balance:.2f})")
        return account_id
    
    def get_balance(self, account_id: str) -> float:
        """Get current balance for an account."""
        with self._lock:
            account = self.accounts.get(account_id)
            return account.balance if account else 0.0
    
    def earn_credits(
        self,
        account_id: str,
        amount: float,
        reason: str = "Task completion",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Add credits to an account.
        
        Args:
            account_id: Account ID
            amount: Amount to add
            reason: Reason for earning
            metadata: Optional metadata
            
        Returns:
            Transaction ID or None if account not found
        """
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                logger.error(f"Account {account_id} not found")
                return None
            
            account.balance += amount
            account.last_transaction_at = datetime.now()
            
            transaction = CreditTransaction(
                transaction_id=str(uuid.uuid4()),
                account_id=account_id,
                transaction_type=TransactionType.EARNED,
                amount=amount,
                balance_after=account.balance,
                description=reason,
                metadata=metadata or {}
            )
            
            self.transactions.append(transaction)
            
            # Keep only last 10000 transactions
            if len(self.transactions) > 10000:
                self.transactions = self.transactions[-10000:]
            
            self.save()
        
        logger.info(f"Earned {amount:.2f} credits for {account_id}: {reason}")
        return transaction.transaction_id
    
    def spend_credits(
        self,
        account_id: str,
        amount: float,
        reason: str = "Purchase",
        metadata: Optional[Dict[str, Any]] = None,
        allow_negative: bool = False
    ) -> Optional[str]:
        """
        Deduct credits from an account.
        
        Args:
            account_id: Account ID
            amount: Amount to deduct
            reason: Reason for spending
            metadata: Optional metadata
            allow_negative: Allow balance to go negative
            
        Returns:
            Transaction ID or None if insufficient funds or account not found
        """
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                logger.error(f"Account {account_id} not found")
                return None
            
            if not allow_negative and account.balance < amount:
                logger.warning(f"Insufficient credits for {account_id}: {account.balance:.2f} < {amount:.2f}")
                return None
            
            account.balance -= amount
            account.last_transaction_at = datetime.now()
            
            transaction = CreditTransaction(
                transaction_id=str(uuid.uuid4()),
                account_id=account_id,
                transaction_type=TransactionType.SPENT,
                amount=-amount,
                balance_after=account.balance,
                description=reason,
                metadata=metadata or {}
            )
            
            self.transactions.append(transaction)
            self.save()
        
        logger.info(f"Spent {amount:.2f} credits from {account_id}: {reason}")
        return transaction.transaction_id
    
    def transfer_credits(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: float,
        reason: str = "Transfer",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Transfer credits between accounts.
        
        Args:
            from_account_id: Source account
            to_account_id: Destination account
            amount: Amount to transfer
            reason: Reason for transfer
            metadata: Optional metadata
            
        Returns:
            Transaction ID or None if transfer failed
        """
        with self._lock:
            from_account = self.accounts.get(from_account_id)
            to_account = self.accounts.get(to_account_id)
            
            if not from_account:
                logger.error(f"Source account {from_account_id} not found")
                return None
            
            if not to_account:
                logger.error(f"Destination account {to_account_id} not found")
                return None
            
            if from_account.balance < amount:
                logger.warning(f"Insufficient credits for transfer: {from_account.balance:.2f} < {amount:.2f}")
                return None
            
            # Deduct from source
            from_account.balance -= amount
            from_account.last_transaction_at = datetime.now()
            
            # Add to destination
            to_account.balance += amount
            to_account.last_transaction_at = datetime.now()
            
            # Record transactions
            transaction_id = str(uuid.uuid4())
            
            from_transaction = CreditTransaction(
                transaction_id=f"{transaction_id}_from",
                account_id=from_account_id,
                transaction_type=TransactionType.TRANSFERRED,
                amount=-amount,
                balance_after=from_account.balance,
                description=f"Transfer to {to_account.name}: {reason}",
                metadata=metadata or {}
            )
            
            to_transaction = CreditTransaction(
                transaction_id=f"{transaction_id}_to",
                account_id=to_account_id,
                transaction_type=TransactionType.TRANSFERRED,
                amount=amount,
                balance_after=to_account.balance,
                description=f"Transfer from {from_account.name}: {reason}",
                metadata=metadata or {}
            )
            
            self.transactions.append(from_transaction)
            self.transactions.append(to_transaction)
            self.save()
        
        logger.info(f"Transferred {amount:.2f} credits from {from_account_id} to {to_account_id}")
        return transaction_id
    
    def reward(
        self,
        account_id: str,
        reward_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Reward credits based on predefined earning rates."""
        amount = self.earning_rates.get(reward_type, 0.0)
        if amount <= 0:
            logger.warning(f"Unknown reward type: {reward_type}")
            return None
        
        return self.earn_credits(
            account_id=account_id,
            amount=amount,
            reason=f"Reward: {reward_type}",
            metadata=metadata
        )
    
    def charge(
        self,
        account_id: str,
        charge_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        allow_negative: bool = False
    ) -> Optional[str]:
        """Charge credits based on predefined spending costs."""
        amount = self.spending_costs.get(charge_type, 0.0)
        if amount <= 0:
            logger.warning(f"Unknown charge type: {charge_type}")
            return None
        
        return self.spend_credits(
            account_id=account_id,
            amount=amount,
            reason=f"Charge: {charge_type}",
            metadata=metadata,
            allow_negative=allow_negative
        )
    
    def get_account(self, account_id: str) -> Optional[CreditAccount]:
        """Get account details."""
        with self._lock:
            return self.accounts.get(account_id)
    
    def list_accounts(self) -> List[CreditAccount]:
        """List all accounts."""
        with self._lock:
            return list(self.accounts.values())
    
    def get_transaction_history(
        self,
        account_id: Optional[str] = None,
        limit: int = 100
    ) -> List[CreditTransaction]:
        """Get transaction history, optionally filtered by account."""
        with self._lock:
            transactions = self.transactions[-limit:] if limit > 0 else self.transactions
            
            if account_id:
                transactions = [t for t in transactions if t.account_id == account_id]
            
            return transactions
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get credit system statistics."""
        with self._lock:
            total_credits = sum(account.balance for account in self.accounts.values())
            total_accounts = len(self.accounts)
            
            # Transaction statistics
            transaction_types = {}
            for transaction in self.transactions:
                tx_type = transaction.transaction_type.value
                transaction_types[tx_type] = transaction_types.get(tx_type, 0) + 1
            
            # Recent activity
            recent_24h = [
                t for t in self.transactions
                if (datetime.now() - t.timestamp).total_seconds() < 86400
            ]
            
            return {
                "total_credits": total_credits,
                "total_accounts": total_accounts,
                "transaction_count": len(self.transactions),
                "transaction_types": transaction_types,
                "recent_24h_transactions": len(recent_24h),
                "average_balance": total_credits / total_accounts if total_accounts > 0 else 0.0
            }
    
    def set_earning_rate(self, reward_type: str, rate: float):
        """Set earning rate for a reward type."""
        self.earning_rates[reward_type] = rate
        logger.info(f"Set earning rate for {reward_type}: {rate}")
    
    def set_spending_cost(self, charge_type: str, cost: float):
        """Set spending cost for a charge type."""
        self.spending_costs[charge_type] = cost
        logger.info(f"Set spending cost for {charge_type}: {cost}")
    
    def save(self):
        """Save credit system data."""
        with self._lock:
            data = {
                "accounts": {
                    account_id: account.to_dict()
                    for account_id, account in self.accounts.items()
                },
                "transactions": [
                    t.to_dict()
                    for t in self.transactions[-5000:]  # Last 5000
                ],
                "earning_rates": self.earning_rates,
                "spending_costs": self.spending_costs,
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
    
    def load(self):
        """Load credit system data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                # Load accounts
                for account_id, account_data in data.get("accounts", {}).items():
                    account = CreditAccount.from_dict(account_data)
                    self.accounts[account_id] = account
                
                # Load transactions
                for transaction_data in data.get("transactions", []):
                    transaction = CreditTransaction.from_dict(transaction_data)
                    self.transactions.append(transaction)
                
                # Load economic rules
                self.earning_rates = data.get("earning_rates", self.earning_rates)
                self.spending_costs = data.get("spending_costs", self.spending_costs)
            
            logger.info(f"Loaded {len(self.accounts)} accounts and {len(self.transactions)} transactions")
        except Exception as e:
            logger.error(f"Error loading credit system: {e}")


# Example usage
if __name__ == "__main__":
    credits = CoreCredits()
    
    # Create accounts
    account1 = credits.create_account(name="Main Account", initial_balance=100.0)
    account2 = credits.create_account(name="Rewards Account")
    
    # Earn credits
    credits.earn_credits(account1, 50.0, "Task completion")
    credits.reward(account1, "task_completion")
    credits.reward(account1, "goal_achievement")
    
    # Spend credits
    credits.spend_credits(account1, 10.0, "API call")
    credits.charge(account1, "api_call")
    
    # Transfer
    credits.transfer_credits(account1, account2, 25.0, "Reward distribution")
    
    # Get statistics
    stats = credits.get_statistics()
    print(f"Statistics: {stats}")
    
    # Get balance
    balance = credits.get_balance(account1)
    print(f"Account 1 balance: {balance:.2f}")

