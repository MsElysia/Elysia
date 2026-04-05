"""
External Program Bridge
Connects Elysia with external programs like Hestia
Supports API, file-based, and process communication
"""

import os
import json
import logging
import subprocess
import requests
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ExternalProgramBridge:
    """
    Bridge for connecting Elysia with external programs.
    Supports multiple communication methods.
    """
    
    def __init__(self, program_name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize bridge for external program.
        
        Args:
            program_name: Name of external program (e.g., "Hestia")
            config: Configuration dictionary
        """
        self.program_name = program_name
        self.config = config or {}
        self.communication_method = self.config.get("method", "api")  # api, file, process
        self.connection_status = False
        
        # API configuration
        self.api_url = self.config.get("api_url")
        self.api_key = self.config.get("api_key")
        
        # File-based configuration
        self.shared_dir = Path(self.config.get("shared_dir", "shared_data"))
        self.shared_dir.mkdir(exist_ok=True)
        
        # Process configuration
        self.process_path = self.config.get("process_path")
        self.process_args = self.config.get("process_args", [])
        
        logger.info(f"Initialized bridge for {program_name}")
    
    def connect(self) -> bool:
        """Establish connection with external program"""
        try:
            if self.communication_method == "api":
                return self._connect_api()
            elif self.communication_method == "file":
                return self._connect_file()
            elif self.communication_method == "process":
                return self._connect_process()
            else:
                logger.error(f"Unknown communication method: {self.communication_method}")
                return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def _connect_api(self) -> bool:
        """Connect via API"""
        if not self.api_url:
            logger.warning("API URL not configured")
            return False
        
        try:
            # Test connection
            response = requests.get(f"{self.api_url}/health", timeout=5)
            if response.status_code == 200:
                self.connection_status = True
                logger.info(f"Connected to {self.program_name} via API")
                return True
        except Exception as e:
            logger.warning(f"API connection test failed: {e}")
        
        return False
    
    def _connect_file(self) -> bool:
        """Connect via shared files"""
        try:
            # Create handshake file
            handshake_file = self.shared_dir / f"{self.program_name}_handshake.json"
            handshake_data = {
                "program": "Elysia",
                "timestamp": str(datetime.now()),
                "status": "ready"
            }
            with open(handshake_file, 'w') as f:
                json.dump(handshake_data, f)
            
            self.connection_status = True
            logger.info(f"Connected to {self.program_name} via file system")
            return True
        except Exception as e:
            logger.error(f"File connection failed: {e}")
            return False
    
    def _connect_process(self) -> bool:
        """Connect via process communication"""
        if not self.process_path:
            logger.warning("Process path not configured")
            return False
        
        try:
            # Check if process exists
            if os.path.exists(self.process_path):
                self.connection_status = True
                logger.info(f"Process path verified for {self.program_name}")
                return True
        except Exception as e:
            logger.error(f"Process connection failed: {e}")
        
        return False
    
    def send_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send message to external program"""
        if not self.connection_status:
            logger.warning("Not connected to external program")
            return None
        
        try:
            if self.communication_method == "api":
                return self._send_api(message)
            elif self.communication_method == "file":
                return self._send_file(message)
            elif self.communication_method == "process":
                return self._send_process(message)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return None
    
    def _send_api(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send via API"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            response = requests.post(
                f"{self.api_url}/message",
                json=message,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"API send failed: {e}")
        
        return None
    
    def _send_file(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send via file"""
        try:
            message_file = self.shared_dir / f"{self.program_name}_message_{datetime.now().timestamp()}.json"
            with open(message_file, 'w') as f:
                json.dump(message, f)
            
            # Wait for response
            response_file = self.shared_dir / f"{self.program_name}_response_{datetime.now().timestamp()}.json"
            # In real implementation, would wait/poll for response
            
            return {"status": "sent", "file": str(message_file)}
        except Exception as e:
            logger.error(f"File send failed: {e}")
            return None
    
    def _send_process(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send via process"""
        try:
            # Execute process with message as input
            result = subprocess.run(
                [self.process_path] + self.process_args,
                input=json.dumps(message),
                text=True,
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout) if result.stdout else {"status": "success"}
        except Exception as e:
            logger.error(f"Process send failed: {e}")
        
        return None
    
    def receive_message(self) -> Optional[Dict[str, Any]]:
        """Receive message from external program"""
        if not self.connection_status:
            return None
        
        try:
            if self.communication_method == "file":
                return self._receive_file()
            # API and process would use different methods
        except Exception as e:
            logger.error(f"Failed to receive message: {e}")
        
        return None
    
    def _receive_file(self) -> Optional[Dict[str, Any]]:
        """Receive via file"""
        try:
            # Look for incoming messages
            pattern = f"elysia_message_*.json"
            for msg_file in self.shared_dir.glob(pattern):
                with open(msg_file, 'r') as f:
                    message = json.load(f)
                # Delete after reading
                msg_file.unlink()
                return message
        except Exception as e:
            logger.error(f"File receive failed: {e}")
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get bridge status"""
        return {
            "program": self.program_name,
            "connected": self.connection_status,
            "method": self.communication_method,
            "config": {
                "api_url": self.api_url,
                "shared_dir": str(self.shared_dir),
                "process_path": self.process_path
            }
        }


class HestiaBridge(ExternalProgramBridge):
    """Specialized bridge for Hestia program"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Hestia bridge with default config"""
        hestia_config = {
            "method": config.get("method", "api") if config else "api",
            "api_url": config.get("api_url", "http://localhost:5001") if config else "http://localhost:5001",
            "shared_dir": config.get("shared_dir", "shared_data/hestia") if config else "shared_data/hestia",
            "process_path": config.get("process_path") if config else None,
            **({} if not config else config)
        }
        super().__init__("Hestia", hestia_config)
    
    def sync_with_elysia(self, elysia_core) -> bool:
        """Sync Hestia with Elysia core systems"""
        try:
            # Get Elysia status
            elysia_status = {
                "memory_count": len(elysia_core.memory.memories) if hasattr(elysia_core, 'memory') else 0,
                "trust_scores": elysia_core.trust.get_all_trust() if hasattr(elysia_core, 'trust') else {},
                "active_tasks": len(elysia_core.tasks.get_active_tasks()) if hasattr(elysia_core, 'tasks') else 0
            }
            
            # Send to Hestia
            result = self.send_message({
                "type": "sync",
                "data": elysia_status,
                "timestamp": str(datetime.now())
            })
            
            return result is not None
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Example: Connect to Hestia via API
    hestia = HestiaBridge({
        "method": "api",
        "api_url": "http://localhost:5001"
    })
    
    if hestia.connect():
        print("Connected to Hestia!")
        status = hestia.get_status()
        print(f"Status: {status}")
        
        # Send a test message
        response = hestia.send_message({
            "type": "test",
            "message": "Hello from Elysia!"
        })
        print(f"Response: {response}")
    else:
        print("Failed to connect to Hestia")

