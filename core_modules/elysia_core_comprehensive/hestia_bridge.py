"""
Hestia Bridge - Integration with Hestia Real Estate Platform
Connects Elysia with Hestia for real estate investment analysis
"""

import os
import json
import logging
import requests
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class HestiaBridge:
    """
    Bridge for connecting Elysia with Hestia Real Estate Platform.
    Supports API communication and data sharing.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Hestia bridge.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.hestia_path = Path(self.config.get("hestia_path", r"C:\Users\mrnat\Hestia"))
        self.api_url = self.config.get("api_url", "http://localhost:8501")
        self.data_dir = Path(self.config.get("data_dir", self.hestia_path / "data"))
        self.outputs_dir = Path(self.config.get("outputs_dir", self.hestia_path / "outputs"))
        self.connected = False
        
        logger.info(f"Initialized Hestia bridge (path: {self.hestia_path})")
    
    def check_hestia_running(self) -> bool:
        """Check if Hestia is running"""
        try:
            # Try to connect to Streamlit app
            response = requests.get(f"{self.api_url}", timeout=2)
            self.connected = response.status_code == 200
            return self.connected
        except:
            # Try to check if process is running
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq streamlit.exe"],
                    capture_output=True,
                    text=True
                )
                self.connected = "streamlit.exe" in result.stdout
                return self.connected
            except:
                self.connected = False
                return False
    
    def start_hestia(self) -> bool:
        """Start Hestia application"""
        try:
            hestia_bat = self.hestia_path / "START_HESTIA_PRO.bat"
            if hestia_bat.exists():
                subprocess.Popen(
                    [str(hestia_bat)],
                    cwd=str(self.hestia_path),
                    shell=True
                )
                logger.info("Hestia start command executed")
                return True
            else:
                # Try direct Python execution
                app_file = self.hestia_path / "app_hestia_pro.py"
                if app_file.exists():
                    subprocess.Popen(
                        ["streamlit", "run", str(app_file), "--server.headless", "true", "--server.port", "8501"],
                        cwd=str(self.hestia_path)
                    )
                    logger.info("Hestia started via streamlit")
                    return True
        except Exception as e:
            logger.error(f"Failed to start Hestia: {e}")
            return False
    
    def get_property_data(self, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Get property data from Hestia outputs"""
        try:
            csv_file = self.outputs_dir / "scored_listings.csv"
            if csv_file.exists():
                import pandas as pd
                df = pd.read_csv(csv_file)
                return df.head(limit).to_dict('records')
        except Exception as e:
            logger.error(f"Failed to read property data: {e}")
        return None
    
    def send_analysis_request(self, properties: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Send properties to Hestia for analysis"""
        try:
            # Write to shared data directory
            request_file = self.data_dir / f"elysia_request_{datetime.now().timestamp()}.json"
            with open(request_file, 'w') as f:
                json.dump({
                    "source": "elysia",
                    "properties": properties,
                    "timestamp": str(datetime.now())
                }, f)
            
            return {"status": "sent", "file": str(request_file)}
        except Exception as e:
            logger.error(f"Failed to send analysis request: {e}")
            return None
    
    def get_investment_insights(self, property_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get investment insights for a property"""
        try:
            # Use Hestia's scoring logic if available
            insights = {
                "score": property_data.get("score_0_100", 0),
                "dscr": property_data.get("dscr", 0),
                "cap_rate": property_data.get("cap_rate", 0),
                "cash_on_cash": property_data.get("cash_on_cash", 0),
                "recommendation": self._generate_recommendation(property_data)
            }
            return insights
        except Exception as e:
            logger.error(f"Failed to generate insights: {e}")
            return None
    
    def _generate_recommendation(self, property_data: Dict[str, Any]) -> str:
        """Generate investment recommendation"""
        score = property_data.get("score_0_100", 0)
        dscr = property_data.get("dscr", 0)
        cap_rate = property_data.get("cap_rate", 0)
        
        if score >= 80 and dscr >= 1.25 and cap_rate >= 8:
            return "STRONG BUY - Excellent metrics across all categories"
        elif score >= 70 and dscr >= 1.15 and cap_rate >= 7:
            return "BUY - Good investment opportunity"
        elif score >= 60:
            return "CONSIDER - Review carefully before investing"
        else:
            return "PASS - Below investment threshold"
    
    def sync_with_elysia(self, elysia_memory) -> bool:
        """Sync Hestia data with Elysia memory"""
        try:
            properties = self.get_property_data(limit=50)
            if properties:
                for prop in properties:
                    elysia_memory.remember(
                        f"Property: {prop.get('address', 'Unknown')} - Score: {prop.get('score_0_100', 0)}",
                        category="real_estate",
                        priority=0.7
                    )
                logger.info(f"Synced {len(properties)} properties to Elysia memory")
                return True
        except Exception as e:
            logger.error(f"Sync failed: {e}")
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get Hestia bridge status"""
        return {
            "connected": self.check_hestia_running(),
            "hestia_path": str(self.hestia_path),
            "api_url": self.api_url,
            "data_dir": str(self.data_dir),
            "outputs_dir": str(self.outputs_dir),
            "data_available": (self.outputs_dir / "scored_listings.csv").exists() if self.outputs_dir.exists() else False
        }


# Example usage
if __name__ == "__main__":
    bridge = HestiaBridge({
        "hestia_path": r"C:\Users\mrnat\Hestia"
    })
    
    print("Hestia Status:", bridge.get_status())
    
    if not bridge.check_hestia_running():
        print("Starting Hestia...")
        bridge.start_hestia()
    
    properties = bridge.get_property_data(limit=5)
    if properties:
        print(f"Found {len(properties)} properties")
        for prop in properties[:3]:
            print(f"  - {prop.get('address', 'Unknown')}: Score {prop.get('score_0_100', 0)}")

