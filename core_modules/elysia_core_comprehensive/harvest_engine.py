"""
Harvest Engine - Autonomous revenue generation system
Integrated from old modules.
"""

import requests
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

GUMROAD_API_URL = "https://api.gumroad.com/v2"


class GumroadClient:
    """Client for Gumroad API integration"""
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize Gumroad client.
        
        Args:
            access_token: Gumroad API access token
        """
        self.access_token = access_token
        self.api_url = GUMROAD_API_URL
    
    def list_sales(self, page: int = 1) -> List[Dict[str, Any]]:
        """
        List sales from Gumroad.
        
        Args:
            page: Page number for pagination
        
        Returns:
            List of sale dictionaries
        """
        if not self.access_token:
            logging.warning("Gumroad access token not set")
            return []
        
        endpoint = f"{self.api_url}/sales"
        params = {
            "access_token": self.access_token,
            "page": page
        }
        
        try:
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            sales_data = response.json()
            sales = sales_data.get("sales", [])
            logging.info(f"Retrieved {len(sales)} sales from Gumroad (page {page})")
            return sales
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to retrieve sales: {e}")
            return []
    
    def get_account_details(self) -> Dict[str, Any]:
        """Get Gumroad account details"""
        if not self.access_token:
            logging.warning("Gumroad access token not set")
            return {}
        
        endpoint = f"{self.api_url}/user"
        params = {"access_token": self.access_token}
        
        try:
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            return response.json().get("user", {})
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to retrieve account info: {e}")
            return {}


class StripeClient:
    """Client for Stripe API integration (placeholder for future implementation)"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
    
    def get_balance(self) -> Dict[str, Any]:
        """Get Stripe account balance"""
        # Placeholder - implement Stripe API integration
        logging.warning("Stripe integration not yet implemented")
        return {"status": "not_implemented"}


class IncomeExecutor:
    """Executes income reporting and tracking"""
    
    def __init__(self, gumroad_client: Optional[GumroadClient] = None, 
                 stripe_client: Optional[StripeClient] = None):
        """
        Initialize Income Executor.
        
        Args:
            gumroad_client: Optional Gumroad client
            stripe_client: Optional Stripe client
        """
        self.gumroad = gumroad_client
        self.stripe = stripe_client
        self.income_log = []
    
    def execute_income_report(self, source: str = "gumroad") -> Dict[str, Any]:
        """
        Execute income report for specified source.
        
        Args:
            source: Income source ("gumroad", "stripe", "all")
        
        Returns:
            Income report dictionary
        """
        report = {
            "timestamp": str(datetime.now()),
            "sources": {},
            "total_earned": 0.0,
            "total_sales": 0
        }
        
        if source in ["gumroad", "all"] and self.gumroad:
            gumroad_report = self._get_gumroad_report()
            report["sources"]["gumroad"] = gumroad_report
            report["total_earned"] += gumroad_report.get("total_earned", 0.0)
            report["total_sales"] += gumroad_report.get("total_sales", 0)
        
        if source in ["stripe", "all"] and self.stripe:
            stripe_report = self._get_stripe_report()
            report["sources"]["stripe"] = stripe_report
        
        # Log the report
        self.income_log.append(report)
        logging.info(f"Income report generated: ${report['total_earned']:.2f} from {report['total_sales']} sales")
        
        return report
    
    def _get_gumroad_report(self) -> Dict[str, Any]:
        """Get Gumroad income report"""
        if not self.gumroad:
            return {"error": "Gumroad client not configured"}
        
        sales = self.gumroad.list_sales()
        total_earned = sum(float(sale.get('price', 0)) / 100 for sale in sales)
        
        return {
            "total_sales": len(sales),
            "total_earned": total_earned,
            "currency": "USD",
            "details": sales[:10]  # Return first 10 sales
        }
    
    def _get_stripe_report(self) -> Dict[str, Any]:
        """Get Stripe income report"""
        if not self.stripe:
            return {"error": "Stripe client not configured"}
        
        balance = self.stripe.get_balance()
        return balance
    
    def get_income_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent income history"""
        return self.income_log[-limit:]


class HarvestEngine:
    """
    Main Harvest Engine orchestrator.
    Coordinates revenue generation and tracking.
    """
    
    def __init__(self, gumroad_token: Optional[str] = None, stripe_key: Optional[str] = None):
        """
        Initialize Harvest Engine.
        
        Args:
            gumroad_token: Gumroad API token
            stripe_key: Stripe API key
        """
        self.gumroad_client = GumroadClient(gumroad_token) if gumroad_token else None
        self.stripe_client = StripeClient(stripe_key) if stripe_key else None
        self.executor = IncomeExecutor(self.gumroad_client, self.stripe_client)
    
    def generate_income_report(self, source: str = "all") -> Dict[str, Any]:
        """Generate comprehensive income report"""
        return self.executor.execute_income_report(source)
    
    def get_account_status(self) -> Dict[str, Any]:
        """Get status of all connected accounts"""
        status = {
            "gumroad": {"connected": self.gumroad_client is not None},
            "stripe": {"connected": self.stripe_client is not None}
        }
        
        if self.gumroad_client:
            account_details = self.gumroad_client.get_account_details()
            status["gumroad"].update(account_details)
        
        return status


# Example usage
if __name__ == "__main__":
    # Test with mock token
    ACCESS_TOKEN = "your_gumroad_access_token_here"
    
    if ACCESS_TOKEN != "your_gumroad_access_token_here":
        client = GumroadClient(ACCESS_TOKEN)
        executor = IncomeExecutor(client)
        report = executor.execute_income_report()
        print("Income Report:")
        import json
        print(json.dumps(report, indent=2))
    else:
        print("Set ACCESS_TOKEN to test Gumroad integration")

