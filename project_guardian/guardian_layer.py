# project_guardian/guardian_layer.py
# Guardian Layer: System Fingerprinting and Integrity Monitoring
# Based on elysia 4 (Main Consolidation) designs

import logging
import json
import hashlib
import platform
import os
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from threading import Lock

try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    SMTP_AVAILABLE = True
except ImportError:
    SMTP_AVAILABLE = False
    logger.warning("Email libraries not available - email alerts disabled")

logger = logging.getLogger(__name__)


class GuardianLayer:
    """
    System integrity monitoring, fingerprinting, and emergency alerts.
    Detects system identity mismatches and sends alerts on anomalies.
    """
    
    def __init__(
        self,
        config_path: str = "data/guardian.json",
        rebuild_log_path: str = "data/guardian_rebuild.log"
    ):
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.rebuild_log_path = Path(rebuild_log_path)
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Guardian state
        self.fingerprint: Optional[str] = None
        self.contact_email: Optional[str] = None
        self.smtp_config: Dict[str, Any] = {}
        
        # Load existing state
        self.load()
        
        # Generate/verify fingerprint
        self._update_fingerprint()
    
    def _generate_system_fingerprint(self) -> str:
        """
        Generate a cryptographic fingerprint of the system.
        Based on system characteristics that identify this installation.
        """
        fingerprint_data = []
        
        # System information
        fingerprint_data.append(f"platform={platform.platform()}")
        fingerprint_data.append(f"machine={platform.machine()}")
        fingerprint_data.append(f"processor={platform.processor()}")
        fingerprint_data.append(f"node={platform.node()}")
        
        # Python environment
        fingerprint_data.append(f"python_version={sys.version}")
        fingerprint_data.append(f"python_executable={sys.executable}")
        
        # Working directory
        fingerprint_data.append(f"cwd={os.getcwd()}")
        
        # User information
        fingerprint_data.append(f"user={os.getenv('USER', os.getenv('USERNAME', 'unknown'))}")
        
        # Combine and hash
        combined = "|".join(fingerprint_data)
        fingerprint_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
        
        return fingerprint_hash
    
    def _update_fingerprint(self):
        """Update system fingerprint."""
        new_fingerprint = self._generate_system_fingerprint()
        
        with self._lock:
            if self.fingerprint is None:
                # First time - store fingerprint
                self.fingerprint = new_fingerprint
                self.save()
                logger.info("Generated initial system fingerprint")
            elif self.fingerprint != new_fingerprint:
                # Fingerprint changed - potential rebuild/hijack
                logger.warning(f"System fingerprint changed!")
                logger.warning(f"  Old: {self.fingerprint[:16]}...")
                logger.warning(f"  New: {new_fingerprint[:16]}...")
                
                self._log_rebuild_event(new_fingerprint)
                self._check_and_alert()
                
                # Update to new fingerprint
                self.fingerprint = new_fingerprint
                self.save()
    
    def _log_rebuild_event(self, new_fingerprint: str):
        """Log a rebuild/change event."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "old_fingerprint": self.fingerprint,
            "new_fingerprint": new_fingerprint,
            "detected_as": "system_rebuild_or_change"
        }
        
        # Append to rebuild log
        with open(self.rebuild_log_path, 'a') as f:
            f.write(json.dumps(event) + "\n")
        
        logger.info(f"Rebuild event logged to {self.rebuild_log_path}")
    
    def _check_and_alert(self):
        """Check for anomalies and send alerts if configured."""
        if not self.contact_email:
            logger.info("No contact email configured, skipping alert")
            return
        
        try:
            self.send_alert_email(
                to_email=self.contact_email,
                subject="Elysia Guardian: System Identity Change Detected",
                message="System fingerprint has changed. This may indicate:\n"
                       "- System rebuild or reset\n"
                       "- Environment change\n"
                       "- Potential security issue\n\n"
                       f"Old fingerprint: {self.fingerprint[:32]}...\n"
                       f"New fingerprint: {self._generate_system_fingerprint()[:32]}...\n\n"
                       f"Timestamp: {datetime.now().isoformat()}"
            )
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
    
    def set_contact_email(self, email: str):
        """Set contact email for alerts."""
        with self._lock:
            self.contact_email = email
            self.save()
        logger.info(f"Contact email set: {email}")
    
    def configure_smtp(
        self,
        smtp_server: str,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True
    ):
        """Configure SMTP settings for email alerts."""
        with self._lock:
            self.smtp_config = {
                "server": smtp_server,
                "port": smtp_port,
                "username": username,
                "password": password,
                "use_tls": use_tls
            }
            self.save()
        logger.info(f"SMTP configured: {smtp_server}:{smtp_port}")
    
    def send_alert_email(
        self,
        to_email: str,
        subject: str,
        message: str,
        from_email: Optional[str] = None
    ) -> bool:
        """
        Send an alert email.
        
        Args:
            to_email: Recipient email
            subject: Email subject
            message: Email message
            from_email: Sender email (defaults to contact_email)
            
        Returns:
            True if sent successfully
        """
        if not SMTP_AVAILABLE:
            logger.warning("Email libraries not available")
            return False
        
        if not self.smtp_config.get("server"):
            logger.warning("SMTP not configured")
            return False
        
        from_email = from_email or self.contact_email or "elysia@guardian.local"
        
        try:
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(self.smtp_config["server"], self.smtp_config["port"])
            
            if self.smtp_config.get("use_tls", True):
                server.starttls()
            
            if self.smtp_config.get("username") and self.smtp_config.get("password"):
                server.login(self.smtp_config["username"], self.smtp_config["password"])
            
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Alert email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending alert email: {e}")
            return False
    
    def ping_guardian(
        self,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a signal/ping to guardian (via email or log).
        
        Args:
            message: Optional message
            metadata: Optional metadata
            
        Returns:
            True if ping sent
        """
        ping_data = {
            "timestamp": datetime.now().isoformat(),
            "message": message or "Guardian ping",
            "fingerprint": self.fingerprint,
            "metadata": metadata or {}
        }
        
        # Log ping
        logger.info(f"Guardian ping: {ping_data['message']}")
        
        # Send email if configured
        if self.contact_email:
            try:
                self.send_alert_email(
                    to_email=self.contact_email,
                    subject="Elysia Guardian: Ping",
                    message=f"Guardian ping received.\n\n{json.dumps(ping_data, indent=2)}"
                )
            except Exception as e:
                logger.debug(f"Email ping failed (non-critical): {e}")
        
        return True
    
    def silent_log(self, event: str, data: Optional[Dict[str, Any]] = None):
        """
        Record an event without triggering alerts.
        Useful for logging activity without alerting potential attackers.
        
        Args:
            event: Event description
            data: Optional event data
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data or {}
        }
        
        # Append to a silent log file
        silent_log_path = self.config_path.parent / "guardian_silent.log"
        with open(silent_log_path, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")
        
        logger.debug(f"Silent log: {event}")
    
    def verify_identity(self) -> Dict[str, Any]:
        """
        Verify current system identity matches stored fingerprint.
        
        Returns:
            Verification result dictionary
        """
        current_fingerprint = self._generate_system_fingerprint()
        matches = current_fingerprint == self.fingerprint
        
        return {
            "identity_verified": matches,
            "current_fingerprint": current_fingerprint,
            "stored_fingerprint": self.fingerprint,
            "fingerprint_match": matches,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_rebuild_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get history of rebuild events."""
        if not self.rebuild_log_path.exists():
            return []
        
        history = []
        try:
            with open(self.rebuild_log_path, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            event = json.loads(line.strip())
                            history.append(event)
                        except json.JSONDecodeError:
                            continue
            
            # Return most recent
            return history[-limit:]
        except Exception as e:
            logger.error(f"Error reading rebuild history: {e}")
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get guardian layer status."""
        verification = self.verify_identity()
        rebuild_history = self.get_rebuild_history(limit=10)
        
        return {
            "fingerprint": self.fingerprint,
            "fingerprint_short": self.fingerprint[:16] + "..." if self.fingerprint else None,
            "identity_verified": verification["identity_verified"],
            "contact_email": self.contact_email if self.contact_email else None,
            "smtp_configured": bool(self.smtp_config.get("server")),
            "rebuild_events_count": len(rebuild_history),
            "last_rebuild": rebuild_history[-1] if rebuild_history else None
        }
    
    def save(self):
        """Save guardian state."""
        with self._lock:
            data = {
                "fingerprint": self.fingerprint,
                "contact_email": self.contact_email,
                "smtp_config": self.smtp_config,
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def load(self):
        """Load guardian state."""
        if not self.config_path.exists():
            return
        
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self.fingerprint = data.get("fingerprint")
                self.contact_email = data.get("contact_email")
                self.smtp_config = data.get("smtp_config", {})
            
            logger.info("Guardian state loaded")
        except Exception as e:
            logger.error(f"Error loading guardian state: {e}")


# Example usage
if __name__ == "__main__":
    guardian = GuardianLayer()
    
    # Configure guardian
    guardian.set_contact_email("admin@example.com")
    guardian.configure_smtp(
        smtp_server="smtp.gmail.com",
        smtp_port=587,
        username="your_email@gmail.com",
        password="your_password"
    )
    
    # Verify identity
    verification = guardian.verify_identity()
    print(f"Identity verified: {verification['identity_verified']}")
    
    # Get status
    status = guardian.get_status()
    print(f"Guardian status: {status}")
    
    # Send ping
    guardian.ping_guardian("System startup complete")
    
    # Silent log
    guardian.silent_log("routine_check", {"check_type": "health"})

