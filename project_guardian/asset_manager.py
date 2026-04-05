# project_guardian/asset_manager.py
# AssetManager: Financial Asset Tracking
# Based on elysia 4 (Main Consolidation) designs

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from threading import Lock, RLock
import uuid

try:
    from .core_credits import CoreCredits
except ImportError:
    from core_credits import CoreCredits

logger = logging.getLogger(__name__)


class AssetType(Enum):
    """Types of assets."""
    CURRENCY = "currency"  # Real currency (USD, EUR, etc.)
    CRYPTO = "crypto"      # Cryptocurrency
    CREDIT = "credit"      # Virtual credits
    INVESTMENT = "investment"  # Stocks, bonds, etc.
    PHYSICAL = "physical"  # Physical assets
    DIGITAL = "digital"   # Digital assets (NFTs, etc.)
    OTHER = "other"


@dataclass
class Asset:
    """Represents a financial asset."""
    asset_id: str
    name: str
    asset_type: AssetType
    quantity: float = 0.0
    unit: str = ""  # e.g., "USD", "BTC", "shares"
    value_per_unit: float = 0.0  # Current value per unit
    total_value: float = 0.0  # quantity * value_per_unit
    acquired_at: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_value(self, value_per_unit: float):
        """Update the value per unit and recalculate total."""
        self.value_per_unit = value_per_unit
        self.total_value = self.quantity * self.value_per_unit
        self.last_updated = datetime.now()
    
    def update_quantity(self, quantity: float):
        """Update quantity and recalculate total."""
        self.quantity = quantity
        self.total_value = self.quantity * self.value_per_unit
        self.last_updated = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "asset_type": self.asset_type.value,
            "quantity": self.quantity,
            "unit": self.unit,
            "value_per_unit": self.value_per_unit,
            "total_value": self.total_value,
            "acquired_at": self.acquired_at.isoformat() if self.acquired_at else None,
            "last_updated": self.last_updated.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Asset":
        """Create Asset from dictionary."""
        return cls(
            asset_id=data["asset_id"],
            name=data["name"],
            asset_type=AssetType(data["asset_type"]),
            quantity=data.get("quantity", 0.0),
            unit=data.get("unit", ""),
            value_per_unit=data.get("value_per_unit", 0.0),
            total_value=data.get("total_value", 0.0),
            acquired_at=datetime.fromisoformat(data["acquired_at"]) if data.get("acquired_at") else None,
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.now().isoformat())),
            metadata=data.get("metadata", {})
        )


@dataclass
class Transaction:
    """A financial transaction."""
    transaction_id: str
    asset_id: str
    transaction_type: str  # "buy", "sell", "transfer", "dividend", etc.
    quantity: float
    price_per_unit: float
    total_amount: float
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "asset_id": self.asset_id,
            "transaction_type": self.transaction_type,
            "quantity": self.quantity,
            "price_per_unit": self.price_per_unit,
            "total_amount": self.total_amount,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transaction":
        """Create Transaction from dictionary."""
        return cls(
            transaction_id=data["transaction_id"],
            asset_id=data["asset_id"],
            transaction_type=data["transaction_type"],
            quantity=data["quantity"],
            price_per_unit=data["price_per_unit"],
            total_amount=data["total_amount"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


class AssetManager:
    """
    Tracks financial assets and their values.
    Integrates with CoreCredits for virtual currency tracking.
    """
    
    def __init__(
        self,
        core_credits: Optional[CoreCredits] = None,
        storage_path: str = "data/asset_manager.json"
    ):
        self.core_credits = core_credits
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe storage (use RLock for reentrant locking)
        self._lock = RLock()
        self.assets: Dict[str, Asset] = {}
        self.transactions: List[Transaction] = []
        
        self.load()
    
    def add_asset(
        self,
        name: str,
        asset_type: AssetType,
        quantity: float = 0.0,
        unit: str = "",
        value_per_unit: float = 0.0,
        asset_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a new asset.
        
        Args:
            name: Asset name
            asset_type: Type of asset
            quantity: Initial quantity
            unit: Unit of measurement
            value_per_unit: Current value per unit
            asset_id: Optional custom asset ID
            metadata: Optional metadata
            
        Returns:
            Asset ID
        """
        if asset_id is None:
            asset_id = str(uuid.uuid4())
        
        if asset_id in self.assets:
            logger.warning(f"Asset {asset_id} already exists")
            return asset_id
        
        with self._lock:
            total_value = quantity * value_per_unit
            
            asset = Asset(
                asset_id=asset_id,
                name=name,
                asset_type=asset_type,
                quantity=quantity,
                unit=unit,
                value_per_unit=value_per_unit,
                total_value=total_value,
                acquired_at=datetime.now(),
                metadata=metadata or {}
            )
            
            self.assets[asset_id] = asset
            self.save()
        
        logger.info(f"Added asset: {name} ({quantity} {unit}, value: ${total_value:.2f})")
        return asset_id
    
    def update_asset_value(
        self,
        asset_id: str,
        value_per_unit: float
    ) -> bool:
        """
        Update the value per unit of an asset.
        
        Args:
            asset_id: Asset ID
            value_per_unit: New value per unit
            
        Returns:
            True if successful
        """
        with self._lock:
            asset = self.assets.get(asset_id)
            if not asset:
                logger.error(f"Asset {asset_id} not found")
                return False
            
            asset.update_value(value_per_unit)
            self.save()
        
        logger.debug(f"Updated asset {asset_id} value: ${value_per_unit:.2f} per {asset.unit}")
        return True
    
    def update_asset_quantity(
        self,
        asset_id: str,
        quantity: float
    ) -> bool:
        """
        Update the quantity of an asset.
        
        Args:
            asset_id: Asset ID
            quantity: New quantity
            
        Returns:
            True if successful
        """
        with self._lock:
            asset = self.assets.get(asset_id)
            if not asset:
                logger.error(f"Asset {asset_id} not found")
                return False
            
            asset.update_quantity(quantity)
            self.save()
        
        logger.debug(f"Updated asset {asset_id} quantity: {quantity} {asset.unit}")
        return True
    
    def record_transaction(
        self,
        asset_id: str,
        transaction_type: str,
        quantity: float,
        price_per_unit: float,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Record a financial transaction.
        
        Args:
            asset_id: Asset ID
            transaction_type: Type of transaction (buy, sell, transfer, etc.)
            quantity: Quantity involved
            price_per_unit: Price per unit
            description: Transaction description
            metadata: Optional metadata
            
        Returns:
            Transaction ID or None if asset not found
        """
        with self._lock:
            asset = self.assets.get(asset_id)
            if not asset:
                logger.error(f"Asset {asset_id} not found")
                return None
            
            total_amount = quantity * price_per_unit
            
            transaction = Transaction(
                transaction_id=str(uuid.uuid4()),
                asset_id=asset_id,
                transaction_type=transaction_type,
                quantity=quantity,
                price_per_unit=price_per_unit,
                total_amount=total_amount,
                description=description,
                metadata=metadata or {}
            )
            
            self.transactions.append(transaction)
            
            # Update asset based on transaction type
            if transaction_type == "buy":
                asset.update_quantity(asset.quantity + quantity)
                asset.update_value(price_per_unit)  # Update to latest price
            elif transaction_type == "sell":
                if asset.quantity >= quantity:
                    asset.update_quantity(asset.quantity - quantity)
                    asset.update_value(price_per_unit)
                else:
                    logger.warning(f"Insufficient quantity for sale: {asset.quantity} < {quantity}")
            elif transaction_type == "transfer_in":
                asset.update_quantity(asset.quantity + quantity)
            elif transaction_type == "transfer_out":
                if asset.quantity >= quantity:
                    asset.update_quantity(asset.quantity - quantity)
                else:
                    logger.warning(f"Insufficient quantity for transfer: {asset.quantity} < {quantity}")
            else:
                # Other types (dividend, interest, etc.) - update value but not quantity
                asset.update_value(price_per_unit)
            
            # Keep only last 10000 transactions
            if len(self.transactions) > 10000:
                self.transactions = self.transactions[-10000:]
            
            self.save()
        
        logger.info(f"Recorded transaction: {transaction_type} {quantity} {asset.unit} of {asset.name}")
        return transaction.transaction_id
    
    def get_asset(self, asset_id: str) -> Optional[Asset]:
        """Get an asset by ID."""
        with self._lock:
            return self.assets.get(asset_id)
    
    def list_assets(
        self,
        asset_type: Optional[AssetType] = None
    ) -> List[Asset]:
        """List all assets, optionally filtered by type."""
        with self._lock:
            if asset_type:
                return [asset for asset in self.assets.values() if asset.asset_type == asset_type]
            return list(self.assets.values())
    
    def get_total_portfolio_value(self) -> float:
        """Get total value of all assets."""
        with self._lock:
            return sum(asset.total_value for asset in self.assets.values())
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get summary of portfolio."""
        with self._lock:
            total_value = self.get_total_portfolio_value()
            
            # Value by asset type
            value_by_type = {}
            for asset in self.assets.values():
                asset_type = asset.asset_type.value
                value_by_type[asset_type] = value_by_type.get(asset_type, 0.0) + asset.total_value
            
            # Asset counts
            asset_counts = {}
            for asset in self.assets.values():
                asset_type = asset.asset_type.value
                asset_counts[asset_type] = asset_counts.get(asset_type, 0) + 1
            
            return {
                "total_assets": len(self.assets),
                "total_portfolio_value": total_value,
                "value_by_type": value_by_type,
                "asset_counts": asset_counts,
                "transaction_count": len(self.transactions)
            }
    
    def sync_with_credits(self, account_id: str) -> bool:
        """
        Sync virtual credits from CoreCredits as an asset.
        Creates or updates a CREDIT asset based on CoreCredits balance.
        
        Args:
            account_id: CoreCredits account ID
            
        Returns:
            True if successful
        """
        if not self.core_credits:
            logger.warning("CoreCredits not configured")
            return False
        
        balance = self.core_credits.get_balance(account_id)
        
        # Find or create credit asset
        credit_assets = [
            asset for asset in self.assets.values()
            if asset.asset_type == AssetType.CREDIT and asset.metadata.get("account_id") == account_id
        ]
        
        if credit_assets:
            # Update existing
            asset = credit_assets[0]
            asset.update_quantity(balance)
            asset.update_value(1.0)  # 1 credit = 1 credit
        else:
            # Create new
            account = self.core_credits.get_account(account_id)
            account_name = account.name if account else f"Account {account_id}"
            
            self.add_asset(
                name=f"{account_name} Credits",
                asset_type=AssetType.CREDIT,
                quantity=balance,
                unit="credits",
                value_per_unit=1.0,
                metadata={"account_id": account_id}
            )
        
        self.save()
        logger.info(f"Synced credits from account {account_id}: {balance} credits")
        return True
    
    def get_transaction_history(
        self,
        asset_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Transaction]:
        """Get transaction history, optionally filtered by asset."""
        with self._lock:
            transactions = self.transactions[-limit:] if limit > 0 else self.transactions
            
            if asset_id:
                transactions = [t for t in transactions if t.asset_id == asset_id]
            
            return transactions
    
    def delete_asset(self, asset_id: str) -> bool:
        """Delete an asset and its transactions."""
        with self._lock:
            if asset_id not in self.assets:
                return False
            
            del self.assets[asset_id]
            
            # Remove transactions for this asset
            self.transactions = [t for t in self.transactions if t.asset_id != asset_id]
            
            self.save()
            logger.info(f"Deleted asset: {asset_id}")
            return True
    
    def export_portfolio(self, filepath: Optional[str] = None) -> str:
        """Export portfolio to JSON file."""
        path = Path(filepath) if filepath else self.storage_path.parent / "portfolio_export.json"
        
        with self._lock:
            data = {
                "assets": {asset_id: asset.to_dict() for asset_id, asset in self.assets.items()},
                "transactions": [t.to_dict() for t in self.transactions[-1000:]],  # Last 1000
                "summary": self.get_portfolio_summary(),
                "exported_at": datetime.now().isoformat()
            }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported portfolio to {path}")
        return str(path)
    
    def save(self):
        """Save asset manager data."""
        with self._lock:
            data = {
                "assets": {
                    asset_id: asset.to_dict()
                    for asset_id, asset in self.assets.items()
                },
                "transactions": [
                    t.to_dict()
                    for t in self.transactions[-5000:]  # Last 5000
                ],
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
    
    def load(self):
        """Load asset manager data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                # Load assets
                for asset_id, asset_data in data.get("assets", {}).items():
                    asset = Asset.from_dict(asset_data)
                    self.assets[asset_id] = asset
                
                # Load transactions
                for transaction_data in data.get("transactions", []):
                    transaction = Transaction.from_dict(transaction_data)
                    self.transactions.append(transaction)
            
            logger.info(f"Loaded {len(self.assets)} assets and {len(self.transactions)} transactions")
        except Exception as e:
            logger.error(f"Error loading asset manager: {e}")


# Example usage
if __name__ == "__main__":
    asset_manager = AssetManager()
    
    # Add some assets
    cash_id = asset_manager.add_asset(
        name="Cash Reserve",
        asset_type=AssetType.CURRENCY,
        quantity=10000.0,
        unit="USD",
        value_per_unit=1.0
    )
    
    crypto_id = asset_manager.add_asset(
        name="Bitcoin",
        asset_type=AssetType.CRYPTO,
        quantity=0.5,
        unit="BTC",
        value_per_unit=45000.0
    )
    
    # Record transactions
    asset_manager.record_transaction(
        asset_id=cash_id,
        transaction_type="buy",
        quantity=500.0,
        price_per_unit=1.0,
        description="Deposit"
    )
    
    asset_manager.record_transaction(
        asset_id=crypto_id,
        transaction_type="buy",
        quantity=0.1,
        price_per_unit=46000.0,
        description="Bought Bitcoin"
    )
    
    # Get summary
    summary = asset_manager.get_portfolio_summary()
    print(f"Portfolio summary: {summary}")
    
    print(f"Total portfolio value: ${asset_manager.get_total_portfolio_value():,.2f}")

