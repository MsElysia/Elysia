# project_guardian/guardian_layer.py
# Guardian Layer: System Fingerprinting and Integrity Monitoring
# Based on elysia 4 (Main Consolidation) designs

import logging
import json
import hashlib
import platform
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from threading import RLock, Condition, get_ident

try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    SMTP_AVAILABLE = True
except ImportError:
    SMTP_AVAILABLE = False
    logger.warning("Email libraries not available - email alerts disabled")

logger = logging.getLogger(__name__)


class _GuardianStateConflict(RuntimeError):
    """The persisted Guardian configuration differs from its verified snapshot."""


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
        self.rebuild_log_path = Path(rebuild_log_path)
        
        # Thread-safe operations
        self._lock = RLock()
        self._activation_condition = Condition(self._lock)
        self._activating_thread = None
        
        # Guardian state. Construction is intentionally inspection-only:
        # load existing state, but do not probe the host, write files, or send alerts.
        self.fingerprint: Optional[str] = None
        self.contact_email: Optional[str] = None
        self.smtp_config: Dict[str, Any] = {}
        self._activated = False
        self._state_load_error = False
        self._durable_state_unknown = False
        self._loaded_config_digest: Optional[str] = None
        
        # Reading existing persisted state is safe during construction.
        self.load()

    def activate(self) -> bool:
        """Explicit single-flight activation with a separate notification phase.

        Another caller may observe a completed durable activation without
        waiting on a callback that could itself request Guardian services.
        """
        with self._activation_condition:
            if self._state_load_error:
                logger.error("Guardian activation refused: persisted state is unverified")
                return False
            if self._activated:
                return self._revalidate_activation()
            while self._activating_thread is not None:
                if self._activating_thread == get_ident():
                    logger.warning("Recursive activation before commit refused")
                    return False
                self._activation_condition.wait()
                if self._state_load_error:
                    return False
                if self._activated:
                    return self._revalidate_activation()
            # An existing invalid file may never be treated as a fresh install.
            if self.config_path.exists() and self.fingerprint is None:
                self.load()
                if self._state_load_error:
                    return False
            self._activating_thread = get_ident()

        try:
            with self._lock:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                self.rebuild_log_path.parent.mkdir(parents=True, exist_ok=True)
                self._assert_unchanged_disk()
                notification = self._update_fingerprint()
                # Durable data is now verified. Commit this *before* invoking
                # external callbacks, so their cross-thread activate() calls
                # can safely observe an already-completed activation.
                self._activated = True

            if notification is not None:
                old_fingerprint, new_fingerprint = notification
                try:
                    self._check_and_alert(
                        old_fingerprint=old_fingerprint,
                        new_fingerprint=new_fingerprint,
                    )
                except Exception:
                    logger.exception(
                        "Guardian identity alert failed after fingerprint persistence"
                    )

            logger.info("GuardianLayer activated")
            return True
        except Exception as exc:
            logger.error("GuardianLayer activation failed: %s", exc)
            return False
        finally:
            with self._activation_condition:
                self._activating_thread = None
                self._activation_condition.notify_all()

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
            previous = self.fingerprint
            previous_digest = self._loaded_config_digest
            if previous == new_fingerprint:
                # The first disk check in activate() can become stale while
                # the host fingerprint is being probed. A no-write path still
                # needs its own cooperative lock and final revision check.
                with self._exclusive_persistence_lock():
                    self._assert_unchanged_disk()
                    # Mark the no-change activation committed *inside* the
                    # cooperative lock, without reopening the save path.
                    self._activated = True
                return

            # First persist the complete payload; a write exception may occur
            # after atomic replacement, so verify the durable bytes rather than
            # blindly reverting to the old in-memory identity.
            self.fingerprint = new_fingerprint
            intended = {
                "fingerprint": new_fingerprint,
                "contact_email": self.contact_email,
                "smtp_config": self.smtp_config,
            }
            save_error = None
            try:
                self.save()
            except _GuardianStateConflict:
                self.fingerprint = previous
                raise
            except Exception as exc:
                if self._durable_state_unknown:
                    # Once the authoritative inspection failed, only explicit
                    # load() may reopen the fence, even if a later read works.
                    raise
                save_error = exc

            try:
                # Older valid config files did not include updated_at. A
                # failed pre-commit save must still be retriable from that
                # intact old record, while a newly committed record needs it.
                persisted, persisted_digest = self._read_persisted_config(
                    retries=2, with_digest=True
                )
            except (OSError, ValueError):
                # If an artifact exists but cannot be validated, never retry
                # activation as a fresh install or overwrite its raw evidence.
                # Only a verified unchanged prior revision permits rollback.
                # Absence on first run is likewise a verified pre-commit state.
                try:
                    current_digest = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
                except FileNotFoundError:
                    current_digest = None
                except OSError:
                    self._mark_durable_unknown()
                    raise
                if current_digest == previous_digest:
                    self.fingerprint = previous
                    self._loaded_config_digest = previous_digest
                else:
                    self._mark_durable_unknown()
                raise

            if (persisted["fingerprint"] == new_fingerprint
                    and not isinstance(persisted.get("updated_at"), str)):
                self._state_load_error = True
                self._mark_durable_unknown()
                raise OSError("Guardian new record has no commit timestamp")

            if (persisted_digest != self._loaded_config_digest or any(
                persisted[key] != value for key, value in intended.items()
            )):
                if persisted_digest == previous_digest:
                    self.fingerprint = previous
                    self._loaded_config_digest = previous_digest
                else:
                    self._mark_durable_unknown()
                raise OSError("Guardian persisted state does not match full payload")

            self._loaded_config_digest = persisted_digest
            if save_error is not None:
                logger.warning("Guardian commit verified after write exception: %s", save_error)

            if previous is None:
                logger.info("Generated initial system fingerprint")
                return

            logger.warning("System fingerprint changed!")
            logger.warning("  Old: %s...", previous[:16])
            logger.warning("  New: %s...", new_fingerprint[:16])

            # Persistence has committed. A diagnostic/alert failure after an
            # externally visible effect must not turn activation into a retry
            # that emits the same rebuild record or alert a second time.
            try:
                self._log_rebuild_event(new_fingerprint, old_fingerprint=previous)
            except Exception:
                logger.exception("Guardian rebuild diagnostic failed after fingerprint persistence")
            # Caller sends any notification after releasing the state lock.
            return previous, new_fingerprint
    
    def _log_rebuild_event(self, new_fingerprint: str, *, old_fingerprint: Optional[str] = None):
        """Log a rebuild/change event."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "old_fingerprint": old_fingerprint if old_fingerprint is not None else self.fingerprint,
            "new_fingerprint": new_fingerprint,
            "detected_as": "system_rebuild_or_change"
        }
        
        # Append to rebuild log
        self.rebuild_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rebuild_log_path, 'a') as f:
            f.write(json.dumps(event) + "\n")
        
        logger.info(f"Rebuild event logged to {self.rebuild_log_path}")
    
    def _check_and_alert(
        self, *, old_fingerprint: Optional[str] = None,
        new_fingerprint: Optional[str] = None
    ):
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
                       f"Old fingerprint: {(old_fingerprint or self.fingerprint)[:32]}...\n"
                       f"New fingerprint: {(new_fingerprint or self._generate_system_fingerprint())[:32]}...\n\n"
                       f"Timestamp: {datetime.now().isoformat()}"
            )
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
    
    def set_contact_email(self, email: str):
        """Set contact email for alerts."""
        with self._lock:
            if self._state_load_error:
                raise RuntimeError("Guardian configuration invalid; refusing update")
            prior = self.contact_email
            prior_digest = self._loaded_config_digest
            self.contact_email = email
            try:
                self.save()
            except BaseException:
                if self._state_load_error or self._loaded_config_digest == prior_digest:
                    self.contact_email = prior
                raise
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
            if self._state_load_error:
                raise RuntimeError("Guardian configuration invalid; refusing update")
            prior = self.smtp_config
            prior_digest = self._loaded_config_digest
            self.smtp_config = {
                "server": smtp_server,
                "port": smtp_port,
                "username": username,
                "password": password,
                "use_tls": use_tls
            }
            try:
                self.save()
            except BaseException:
                if self._state_load_error or self._loaded_config_digest == prior_digest:
                    self.smtp_config = prior
                raise
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
        silent_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(silent_log_path, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")
        
        logger.debug(f"Silent log: {event}")
    
    def verify_identity(self) -> Dict[str, Any]:
        """
        Verify current system identity matches stored fingerprint.

        Before explicit activation this method remains inspection-safe and does
        not invoke host fingerprint providers.
        
        Returns:
            Verification result dictionary
        """
        with self._lock:
            if self._activated and not self._state_load_error:
                self._revalidate_activation()
            return self._inspect_identity()

    def _inspect_identity(self) -> Dict[str, Any]:
        """Inspect under the state lock after durable activation revalidation."""
        if not self._activated or self._state_load_error:
            return {
                "identity_verified": None,
                "current_fingerprint": None,
                "stored_fingerprint": self.fingerprint,
                "fingerprint_match": None,
                "activated": False,
                "timestamp": datetime.now().isoformat(),
            }

        current_fingerprint = self._generate_system_fingerprint()
        matches = current_fingerprint == self.fingerprint
        
        return {
            "identity_verified": matches,
            "current_fingerprint": current_fingerprint,
            "stored_fingerprint": self.fingerprint,
            "fingerprint_match": matches,
            "activated": True,
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
            "activated": self._activated,
            "durable_state_unknown": self._durable_state_unknown,
            "fingerprint": self.fingerprint,
            "fingerprint_short": self.fingerprint[:16] + "..." if self.fingerprint else None,
            "identity_verified": verification["identity_verified"],
            "contact_email": self.contact_email if self.contact_email else None,
            "smtp_configured": bool(self.smtp_config.get("server")),
            "rebuild_events_count": len(rebuild_history),
            "last_rebuild": rebuild_history[-1] if rebuild_history else None
        }
    
    def _assert_unchanged_disk(self):
        """Reject activation and writes if durable state changed since load."""
        if self._state_load_error:
            raise _GuardianStateConflict("Guardian configuration is unverified")
        try:
            current = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        except FileNotFoundError:
            current = None
        except OSError as exc:
            self._state_load_error = True
            raise _GuardianStateConflict("Guardian configuration cannot be inspected") from exc
        if current != self._loaded_config_digest:
            self._state_load_error = True
            raise _GuardianStateConflict(
                "Guardian configuration changed since load; refusing stale overwrite"
            )

    def _mark_durable_unknown(self):
        """Fence ambiguous state without claiming either fingerprint is current."""
        self._state_load_error = True
        self._durable_state_unknown = True
        self._activated = False
        self.fingerprint = None
        self._loaded_config_digest = None

    def _revalidate_activation(self):
        """Called with the state lock; never adopt another writer's revision."""
        try:
            with self._exclusive_persistence_lock():
                self._assert_unchanged_disk()
                data, digest = self._read_persisted_config(with_digest=True)
                if digest != self._loaded_config_digest or any(
                    data[key] != getattr(self, key)
                    for key in ("fingerprint", "contact_email", "smtp_config")
                ):
                    raise _GuardianStateConflict("Guardian activated payload changed")
            return True
        except (OSError, ValueError, _GuardianStateConflict):
            self._state_load_error = True
            self._activated = False
            logger.exception("Guardian repeated activation refused: revalidation required")
            return False

    @contextmanager
    def _exclusive_persistence_lock(self):
        """Serialize cooperative Guardian writers across processes and instances."""
        lock_path = self.config_path.with_name(self.config_path.name + ".lock")
        with lock_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\x00")
                stream.flush()
            deadline = time.monotonic() + 2.0
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Guardian persistence lock unavailable") from exc
                    time.sleep(0.025)
            try:
                yield
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def save(self):
        """Save atomically only if the previously verified revision is unchanged."""
        with self._lock:
            if self._state_load_error:
                raise _GuardianStateConflict("Guardian configuration invalid; refusing save")
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with self._exclusive_persistence_lock():
                self._assert_unchanged_disk()
                data = {
                    "fingerprint": self.fingerprint,
                    "contact_email": self.contact_email,
                    "smtp_config": self.smtp_config,
                    "updated_at": datetime.now().isoformat(),
                }
                # Serialize once and hash the *same bytes* published on
                # every platform. Text-mode output translates LF to CRLF on
                # Windows and otherwise poisons the cached revision digest.
                payload = json.dumps(data, indent=2).encode("utf-8")
                intended_digest = hashlib.sha256(payload).hexdigest()
                previous_digest = self._loaded_config_digest
                temp_path = None
                committed = False
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        dir=self.config_path.parent, prefix=".guardian-", suffix=".tmp",
                        delete=False,
                    ) as stream:
                        temp_path = Path(stream.name)
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp_path, self.config_path)
                    committed = True
                    self._loaded_config_digest = intended_digest
                except BaseException as exc:
                    # Replacement can commit and then raise. Resolve while
                    # still owning the cooperative lock, using exact bytes,
                    # including this attempt's timestamp, not field similarity.
                    try:
                        raw = self.config_path.read_bytes()
                    except FileNotFoundError:
                        durable_digest = None
                    except OSError:
                        self._mark_durable_unknown()
                        raise exc
                    else:
                        durable_digest = hashlib.sha256(raw).hexdigest()
                    if durable_digest == intended_digest:
                        committed = True
                        self._loaded_config_digest = intended_digest
                        logger.warning("Guardian replacement verified after write exception")
                        if not isinstance(exc, Exception):
                            raise
                    elif durable_digest == previous_digest:
                        raise
                    else:
                        self._mark_durable_unknown()
                        raise
                finally:
                    if temp_path is not None:
                        try:
                            temp_path.unlink(missing_ok=True)
                        except OSError as exc:
                            if committed:
                                logger.warning("Guardian post-commit cleanup failed: %s", exc)
                            else:
                                raise

    def _read_persisted_config(
        self, *, retries: int = 0, require_updated_at: bool = False,
        with_digest: bool = False
    ) -> Dict[str, Any]:
        """Read and validate all security-relevant fields, never only fingerprint."""
        for attempt in range(retries + 1):
            try:
                raw = self.config_path.read_bytes()
                data = json.loads(raw)
                break
            except OSError:
                if attempt == retries:
                    raise
        if not isinstance(data, dict):
            raise ValueError("Guardian configuration is not an object")
        if not all(key in data for key in ("fingerprint", "contact_email", "smtp_config")):
            raise ValueError("Guardian configuration has missing protected fields")
        if data["fingerprint"] is not None and not isinstance(data["fingerprint"], str):
            raise ValueError("Guardian fingerprint has invalid type")
        if data["contact_email"] is not None and not isinstance(data["contact_email"], str):
            raise ValueError("Guardian contact email has invalid type")
        if not isinstance(data["smtp_config"], dict):
            raise ValueError("Guardian SMTP configuration has invalid type")
        if require_updated_at and not isinstance(data.get("updated_at"), str):
            raise ValueError("Guardian configuration has no commit timestamp")
        if "updated_at" in data:
            if not isinstance(data["updated_at"], str):
                raise ValueError("Guardian commit timestamp has invalid type")
            try:
                datetime.fromisoformat(data["updated_at"])
            except ValueError as exc:
                raise ValueError("Guardian commit timestamp is not ISO 8601") from exc
        return (data, hashlib.sha256(raw).hexdigest()) if with_digest else data

    def load(self):
        """Load existing configuration; never accept malformed state as absent."""
        if not self.config_path.exists():
            if self._loaded_config_digest is not None:
                self._state_load_error = True
            return
        try:
            data, digest = self._read_persisted_config(with_digest=True)
            with self._lock:
                self.fingerprint = data["fingerprint"]
                self.contact_email = data["contact_email"]
                self.smtp_config = data["smtp_config"]
                self._state_load_error = False
                self._durable_state_unknown = False
                self._activated = False
                self._loaded_config_digest = digest
            logger.info("Guardian state loaded")
        except (OSError, ValueError) as exc:
            self._state_load_error = True
            logger.error("Guardian persisted state invalid, activation refused: %s", exc)


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

