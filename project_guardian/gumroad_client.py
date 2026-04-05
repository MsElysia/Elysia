# project_guardian/gumroad_client.py
# GumroadClient: Gumroad API Integration for Product Sales
# Master-only: Never deployed to slaves - financial operations protected
#
# SECURITY: This module is MASTER-ONLY and handles sensitive financial data.
# It should never be imported or used in slave instances.
# All network operations route through WebReader gateway.

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)


class GumroadClient:
    """
    Gumroad API client for product sales management.
    MASTER-ONLY MODULE: Never deployed to slaves - handles sensitive financial data.
    """
    
    def __init__(
        self,
        web_reader,  # WebReader instance (required for gateway)
        access_token: Optional[str] = None,
        storage_path: str = "data/gumroad_data.json",
        caller_identity: Optional[str] = None
    ):
        """
        Initialize GumroadClient.
        
        Args:
            web_reader: WebReader instance (required for gateway)
            access_token: Gumroad API access token
            storage_path: Path to store Gumroad data
            caller_identity: Identity of caller (for audit)
        """
        self.web_reader = web_reader
        self.access_token = access_token
        self.api_base = "https://api.gumroad.com/v2"
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.caller_identity = caller_identity or "GumroadClient"
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Cached data
        self.products: List[Dict[str, Any]] = []
        self.sales: List[Dict[str, Any]] = []
        
        # Statistics
        self.stats = {
            "total_products": 0,
            "total_sales": 0,
            "total_revenue": 0.0,
            "last_sync": None
        }
        
        # Load cached data
        self.load()
        
        if not self.access_token:
            logger.warning("Gumroad access token not provided - API calls will fail")
    
    def set_access_token(self, token: str):
        """Set Gumroad access token (master-only operation)."""
        self.access_token = token
        logger.info("Gumroad access token updated")
    
    def list_products(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        List all products.
        MASTER-ONLY: Accesses financial API directly.
        
        Args:
            use_cache: Use cached data if available
            
        Returns:
            List of product dictionaries
        """
        if use_cache and self.products:
            return self.products
        
        if not self.access_token:
            logger.error("Gumroad access token required")
            return []
        
        try:
            # Route through WebReader gateway
            response = self.web_reader.request_json(
                method="GET",
                url=f"{self.api_base}/products",
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                },
                timeout_s=10,
                caller_identity=self.caller_identity,
                task_id=None
            )
            
            if response.get("status_code") == 200:
                data = response.get("json") or {}
                self.products = data.get("products", [])
                self.stats["total_products"] = len(self.products)
                self.save()
                logger.info(f"Retrieved {len(self.products)} products from Gumroad")
                return self.products
            else:
                status_code = response.get("status_code", 0)
                error_text = response.get("text", "")
                logger.error(f"Gumroad API error: {status_code} - {error_text}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching Gumroad products: {e}")
            return self.products if use_cache else []
    
    def get_sales(
        self,
        limit: int = 100,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get sales data.
        MASTER-ONLY: Accesses financial transaction data.
        
        Args:
            limit: Maximum number of sales to retrieve
            use_cache: Use cached data if available
            
        Returns:
            List of sale dictionaries
        """
        if use_cache and self.sales:
            return self.sales[:limit]
        
        if not self.access_token:
            logger.error("Gumroad access token required")
            return []
        
        try:
            # Route through WebReader gateway
            # Note: urllib.request doesn't support params directly, so we append to URL
            url = f"{self.api_base}/sales?limit={limit}"
            response = self.web_reader.request_json(
                method="GET",
                url=url,
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                },
                timeout_s=10,
                caller_identity=self.caller_identity,
                task_id=None
            )
            
            if response.get("status_code") == 200:
                data = response.get("json") or {}
                self.sales = data.get("sales", [])
                
                # Calculate total revenue
                total = sum(float(sale.get("price", 0)) for sale in self.sales)
                self.stats["total_sales"] = len(self.sales)
                self.stats["total_revenue"] = total
                self.stats["last_sync"] = datetime.now().isoformat()
                
                self.save()
                logger.info(f"Retrieved {len(self.sales)} sales from Gumroad")
                return self.sales[:limit]
            else:
                status_code = response.get("status_code", 0)
                error_text = response.get("text", "")
                logger.error(f"Gumroad API error: {status_code} - {error_text}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching Gumroad sales: {e}")
            return self.sales[:limit] if use_cache else []
    
    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific product.
        
        Args:
            product_id: Product ID
            
        Returns:
            Product dictionary or None
        """
        products = self.list_products()
        for product in products:
            if product.get("id") == product_id:
                return product
        return None
    
    def update_product(
        self,
        product_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update product details.
        MASTER-ONLY: Modifies product listings.
        
        Args:
            product_id: Product ID
            updates: Update dictionary
            
        Returns:
            True if updated successfully
        """
        if not self.access_token:
            logger.error("Gumroad access token required")
            return False
        
        try:
            # Route through WebReader gateway
            response = self.web_reader.request_json(
                method="PUT",
                url=f"{self.api_base}/products/{product_id}",
                json_body=updates,
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                },
                timeout_s=10,
                caller_identity=self.caller_identity,
                task_id=None
            )
            
            if response.get("status_code") == 200:
                # Refresh products cache
                self.list_products(use_cache=False)
                logger.info(f"Updated product: {product_id}")
                return True
            else:
                status_code = response.get("status_code", 0)
                error_text = response.get("text", "")
                logger.error(f"Gumroad API error: {status_code} - {error_text}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating product: {e}")
            return False
    
    def create_product(
        self,
        name: str,
        price: float,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create a new product.
        MASTER-ONLY: Creates financial product listings.
        
        Args:
            name: Product name
            price: Product price
            description: Product description
            metadata: Optional metadata
            
        Returns:
            Product ID if created successfully
        """
        if not self.access_token:
            logger.error("Gumroad access token required")
            return None
        
        product_data = {
            "name": name,
            "price": price,
            "description": description
        }
        
        if metadata:
            product_data.update(metadata)
        
        try:
            # Route through WebReader gateway
            response = self.web_reader.request_json(
                method="POST",
                url=f"{self.api_base}/products",
                json_body=product_data,
                headers={
                    "Authorization": f"Bearer {self.access_token}"
                },
                timeout_s=10,
                caller_identity=self.caller_identity,
                task_id=None
            )
            
            status_code = response.get("status_code", 0)
            if status_code == 200 or status_code == 201:
                data = response.get("json") or {}
                product_id = data.get("product", {}).get("id")
                
                # Refresh products cache
                self.list_products(use_cache=False)
                
                logger.info(f"Created product: {name} ({product_id})")
                return product_id
            else:
                error_text = response.get("text", "")
                logger.error(f"Gumroad API error: {status_code} - {error_text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating product: {e}")
            return None
    
    def get_revenue_statistics(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get revenue statistics.
        MASTER-ONLY: Financial reporting.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Revenue statistics dictionary
        """
        sales = self.get_sales(limit=1000)
        
        # Filter by date range
        cutoff = datetime.now().timestamp() - (days * 86400)
        recent_sales = [
            sale for sale in sales
            if datetime.fromisoformat(sale.get("created_at", "")).timestamp() > cutoff
        ]
        
        total_revenue = sum(float(sale.get("price", 0)) for sale in recent_sales)
        by_product = {}
        
        for sale in recent_sales:
            product_id = sale.get("product_id", "unknown")
            by_product[product_id] = by_product.get(product_id, 0) + float(sale.get("price", 0))
        
        return {
            "period_days": days,
            "total_sales": len(recent_sales),
            "total_revenue": total_revenue,
            "average_sale": total_revenue / len(recent_sales) if recent_sales else 0,
            "revenue_by_product": by_product,
            "products_count": self.stats["total_products"]
        }
    
    def sync_data(self):
        """Sync all data from Gumroad API."""
        logger.info("Syncing Gumroad data...")
        self.list_products(use_cache=False)
        self.get_sales(limit=1000, use_cache=False)
        logger.info("Gumroad sync complete")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get Gumroad statistics."""
        return {
            "total_products": self.stats["total_products"],
            "total_sales": self.stats["total_sales"],
            "total_revenue": self.stats["total_revenue"],
            "last_sync": self.stats["last_sync"],
            "has_access_token": bool(self.access_token)
        }
    
    def save(self):
        """Save cached data."""
        with self._lock:
            data = {
                "products": self.products,
                "sales": self.sales[-1000:],  # Last 1000 sales
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save Gumroad data: {e}")
    
    def load(self):
        """Load cached data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self.products = data.get("products", [])
                self.sales = data.get("sales", [])
                if "stats" in data:
                    self.stats.update(data["stats"])
            
            logger.info("Loaded cached Gumroad data")
        except Exception as e:
            logger.error(f"Failed to load Gumroad data: {e}")


# Example usage
if __name__ == "__main__":
    # This module is MASTER-ONLY
    # Should never be deployed to slaves
    
    client = GumroadClient()
    
    # Set access token (master-only)
    # client.set_access_token("your_gumroad_token")
    
    # List products
    products = client.list_products()
    print(f"Products: {len(products)}")
    
    # Get sales
    sales = client.get_sales(limit=10)
    print(f"Sales: {len(sales)}")
    
    # Get revenue stats
    stats = client.get_revenue_statistics(days=30)
    print(f"Revenue (30 days): ${stats['total_revenue']:.2f}")

