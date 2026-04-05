# project_guardian/error_handler.py
# Error Handler: Graceful error handling and recovery mechanisms

import logging
import traceback
import shutil
from typing import Dict, Any, Optional, Callable, Type
from datetime import datetime
from enum import Enum
from functools import wraps
from pathlib import Path
import time

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    CRITICAL = "critical"  # System cannot continue
    ERROR = "error"  # Operation failed but system can continue
    WARNING = "warning"  # Issue but not fatal
    INFO = "info"  # Informational


class ErrorCategory(Enum):
    """Error categories for classification."""
    NETWORK = "network"
    DATABASE = "database"
    MEMORY = "memory"
    MUTATION = "mutation"
    API = "api"
    CONFIGURATION = "configuration"
    PERMISSIONS = "permissions"
    SLAVE = "slave"  # Slave connection/communication errors
    UNKNOWN = "unknown"


class ErrorContext:
    """Context information for an error."""
    def __init__(
        self,
        error: Exception,
        category: ErrorCategory,
        severity: ErrorSeverity,
        component: str,
        operation: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.error = error
        self.category = category
        self.severity = severity
        self.component = component
        self.operation = operation
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": type(self.error).__name__,
            "error_message": str(self.error),
            "category": self.category.value,
            "severity": self.severity.value,
            "component": self.component,
            "operation": self.operation,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "traceback": self.traceback
        }


class ErrorHandler:
    """
    Centralized error handling and recovery system.
    Provides graceful degradation, retry logic, and recovery mechanisms.
    """
    
    def __init__(
        self,
        recovery_vault: Optional[Any] = None,
        memory_snapshot: Optional[Any] = None,
        timeline_memory: Optional[Any] = None
    ):
        """
        Initialize ErrorHandler.
        
        Args:
            recovery_vault: Optional RecoveryVault instance for mutation rollback
            memory_snapshot: Optional MemorySnapshot instance for memory recovery
            timeline_memory: Optional TimelineMemory instance for database recovery
        """
        self.error_history: list = []
        self.max_history_size = 1000
        self.retry_configs: Dict[str, Dict[str, Any]] = {}
        self.recovery_strategies: Dict[ErrorCategory, Callable] = {}
        
        # Recovery systems (optional dependencies)
        self.recovery_vault = recovery_vault
        self.memory_snapshot = memory_snapshot
        self.timeline_memory = timeline_memory
        
        # Default retry configurations
        self._setup_default_retries()
        self._setup_recovery_strategies()
    
    def _setup_default_retries(self):
        """Setup default retry configurations."""
        self.retry_configs = {
            "network": {
                "max_attempts": 3,
                "backoff_factor": 2.0,
                "initial_delay": 1.0
            },
            "api": {
                "max_attempts": 2,
                "backoff_factor": 1.5,
                "initial_delay": 0.5
            },
            "database": {
                "max_attempts": 2,
                "backoff_factor": 2.0,
                "initial_delay": 0.5
            },
            "default": {
                "max_attempts": 1,
                "backoff_factor": 1.0,
                "initial_delay": 0.0
            }
        }
    
    def _setup_recovery_strategies(self):
        """Setup recovery strategies for different error categories."""
        self.recovery_strategies = {
            ErrorCategory.NETWORK: self._recover_network_error,
            ErrorCategory.DATABASE: self._recover_database_error,
            ErrorCategory.MEMORY: self._recover_memory_error,
            ErrorCategory.MUTATION: self._recover_mutation_error,
            ErrorCategory.API: self._recover_api_error,
            ErrorCategory.CONFIGURATION: self._recover_configuration_error,
            ErrorCategory.SLAVE: self._recover_slave_connection_error,
        }
    
    def handle_error(
        self,
        error: Exception,
        category: ErrorCategory,
        severity: ErrorSeverity,
        component: str,
        operation: str,
        metadata: Optional[Dict[str, Any]] = None,
        retry: bool = False,
        fallback: Optional[Callable] = None
    ) -> Any:
        """
        Handle an error with appropriate logging and recovery.
        
        Args:
            error: The exception that occurred
            category: Error category
            severity: Error severity
            component: Component where error occurred
            operation: Operation being performed
            metadata: Additional context
            retry: Whether to retry the operation
            fallback: Optional fallback function to call
            
        Returns:
            Result from fallback if available, None otherwise
        """
        # Create error context
        context = ErrorContext(
            error=error,
            category=category,
            severity=severity,
            component=component,
            operation=operation,
            metadata=metadata
        )
        
        # Log error
        self._log_error(context)
        
        # Store in history
        self._record_error(context)
        
        # Attempt recovery
        if context.severity != ErrorSeverity.CRITICAL:
            recovery_result = self._attempt_recovery(context)
            if recovery_result:
                return recovery_result
        
        # Try fallback
        if fallback:
            try:
                logger.info(f"Attempting fallback for {component}.{operation}")
                return fallback()
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
        
        # Return None if no recovery/fallback
        return None
    
    def _log_error(self, context: ErrorContext):
        """Log error with appropriate level."""
        log_message = (
            f"[{context.category.value.upper()}] {context.component}.{context.operation}: "
            f"{type(context.error).__name__}: {context.error}"
        )
        
        if context.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, exc_info=context.error)
        elif context.severity == ErrorSeverity.ERROR:
            logger.error(log_message, exc_info=context.error)
        elif context.severity == ErrorSeverity.WARNING:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def _record_error(self, context: ErrorContext):
        """Record error in history."""
        self.error_history.append(context.to_dict())
        
        # Trim history if too large
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size:]
    
    def _attempt_recovery(self, context: ErrorContext) -> Optional[Any]:
        """Attempt to recover from error."""
        recovery_strategy = self.recovery_strategies.get(context.category)
        
        if recovery_strategy:
            try:
                logger.info(f"Attempting recovery for {context.category.value} error")
                return recovery_strategy(context)
            except Exception as recovery_error:
                logger.error(f"Recovery strategy failed: {recovery_error}")
        
        return None
    
    def _recover_network_error(self, context: ErrorContext) -> Optional[Any]:
        """Recovery strategy for network errors."""
        # Network errors are often transient
        # Return indication that operation should be retried
        return {"retry": True, "delay": 2.0}
    
    def _recover_database_error(self, context: ErrorContext) -> Optional[Any]:
        """Recovery strategy for database errors."""
        error_msg = str(context.error).lower()
        
        if "corrupt" in error_msg or "database disk image is malformed" in error_msg:
            # Database corruption - attempt recovery
            logger.warning("Database corruption detected. Attempting recovery...")
            
            # Try to recover SQLite database
            if self.timeline_memory and hasattr(self.timeline_memory, 'db_path'):
                db_path = Path(self.timeline_memory.db_path)
                if db_path.exists():
                    try:
                        # Try to repair SQLite database
                        import sqlite3
                        backup_path = db_path.with_suffix('.db.backup')
                        
                        # Create backup of corrupted database
                        shutil.copy2(db_path, backup_path)
                        logger.info(f"Corrupted database backed up to {backup_path}")
                        
                        # Try to recover data
                        try:
                            conn = sqlite3.connect(str(db_path))
                            conn.execute("PRAGMA integrity_check")
                            conn.close()
                            logger.info("Database integrity check passed")
                            return {"recoverable": True, "action": "verified"}
                        except sqlite3.DatabaseError:
                            # Database is corrupted - need to restore from backup
                            logger.error("Database corruption confirmed. Requires manual restoration.")
                            return {"recoverable": False, "requires_backup": True, "backup_path": str(backup_path)}
                    except Exception as recovery_error:
                        logger.error(f"Database recovery attempt failed: {recovery_error}")
                        return {"recoverable": False, "requires_backup": True}
            else:
                logger.warning("Database corruption detected. Consider restoring from backup.")
                return {"recoverable": False, "requires_backup": True}
                
        elif "locked" in error_msg:
            # Database locked - wait and retry
            logger.info("Database locked, will retry")
            return {"retry": True, "delay": 1.0}
        elif "connection" in error_msg:
            # Connection issue - might be recoverable
            return {"retry": True, "delay": 1.0}
        
        return None
    
    def _recover_memory_error(self, context: ErrorContext) -> Optional[Any]:
        """Recovery strategy for memory errors."""
        error_msg = str(context.error).lower()
        
        if "corrupt" in error_msg or "json" in error_msg or "decode" in error_msg:
            # Memory corruption - attempt to reload from backup
            logger.warning("Memory corruption detected. Attempting to reload from backup.")
            
            if self.memory_snapshot:
                try:
                    # List available snapshots
                    snapshots = self.memory_snapshot.list_snapshots()
                    if snapshots:
                        # Use most recent snapshot
                        latest_snapshot = max(snapshots, key=lambda s: s.get("timestamp", ""))
                        snapshot_path = latest_snapshot.get("snapshot_id") or latest_snapshot.get("path")
                        
                        if snapshot_path:
                            logger.info(f"Attempting to restore from snapshot: {snapshot_path}")
                            # Return instruction to restore
                            return {
                                "recoverable": True,
                                "action": "restore_snapshot",
                                "snapshot_path": snapshot_path
                            }
                except Exception as recovery_error:
                    logger.error(f"Memory recovery attempt failed: {recovery_error}")
            
            # No snapshot available or recovery failed
            return {"recoverable": False, "requires_backup": True, "action": "reload_backup"}
        
        return None
    
    def _recover_mutation_error(self, context: ErrorContext) -> Optional[Any]:
        """Recovery strategy for mutation errors."""
        # Mutation errors should trigger rollback via RecoveryVault
        logger.warning("Mutation error detected. Attempting rollback...")
        
        if self.recovery_vault:
            try:
                # Get metadata to find mutation ID
                mutation_id = context.metadata.get("mutation_id")
                if mutation_id:
                    # Try to rollback this specific mutation
                    snapshots = self.recovery_vault.list_snapshots()
                    # Find snapshot related to this mutation
                    mutation_snapshots = [
                        s for s in snapshots 
                        if s.metadata.get("mutation_id") == mutation_id
                    ]
                    
                    if mutation_snapshots:
                        latest_snapshot = max(mutation_snapshots, key=lambda s: s.created_at)
                        logger.info(f"Found rollback snapshot: {latest_snapshot.snapshot_id}")
                        return {
                            "recoverable": True,
                            "action": "rollback",
                            "snapshot_id": latest_snapshot.snapshot_id,
                            "mutation_id": mutation_id
                        }
                
                # Try to get most recent snapshot
                snapshots = self.recovery_vault.list_snapshots()
                if snapshots:
                    latest = max(snapshots, key=lambda s: s.created_at)
                    logger.info(f"Rolling back to latest snapshot: {latest.snapshot_id}")
                    return {
                        "recoverable": True,
                        "action": "rollback",
                        "snapshot_id": latest.snapshot_id
                    }
            except Exception as recovery_error:
                logger.error(f"Mutation recovery attempt failed: {recovery_error}")
        
        # RecoveryVault not available or rollback failed
        return {"recoverable": True, "action": "rollback", "requires_manual": True}
    
    def _recover_api_error(self, context: ErrorContext) -> Optional[Any]:
        """Recovery strategy for API errors."""
        # API errors might be rate limits or temporary
        error_msg = str(context.error).lower()
        
        if "rate limit" in error_msg or "429" in str(context.error):
            # Rate limit - wait and retry
            return {"retry": True, "delay": 60.0}
        elif "connection" in error_msg or "timeout" in error_msg:
            # Network issue - retry
            return {"retry": True, "delay": 2.0}
        
        return None
    
    def _recover_configuration_error(self, context: ErrorContext) -> Optional[Any]:
        """Recovery strategy for configuration errors."""
        # Configuration errors usually require manual intervention
        logger.warning("Configuration error detected. May require manual fix.")
        return {"recoverable": False, "requires_manual_fix": True}
    
    def _recover_slave_connection_error(self, context: ErrorContext) -> Optional[Any]:
        """Recovery strategy for slave connection failures."""
        error_msg = str(context.error).lower()
        
        if "connection" in error_msg or "timeout" in error_msg:
            # Connection issue - retry with backoff
            logger.info("Slave connection failed, will retry")
            return {"retry": True, "delay": 5.0, "max_retries": 3}
        elif "authentication" in error_msg or "unauthorized" in error_msg:
            # Auth issue - may need re-authentication
            logger.warning("Slave authentication failed. May need re-authentication.")
            return {"recoverable": False, "requires_reauth": True}
        
        return None
    
    def retry_with_backoff(
        self,
        func: Callable,
        category: str = "default",
        max_attempts: Optional[int] = None,
        exceptions: tuple = (Exception,)
    ):
        """
        Decorator for retrying operations with exponential backoff.
        
        Args:
            func: Function to retry
            category: Retry category (network, api, database, etc.)
            max_attempts: Maximum retry attempts (uses category default if None)
            exceptions: Exceptions to catch and retry on
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            config = self.retry_configs.get(category, self.retry_configs["default"])
            attempts = max_attempts or config["max_attempts"]
            backoff = config["backoff_factor"]
            delay = config["initial_delay"]
            
            last_error = None
            
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < attempts - 1:
                        wait_time = delay * (backoff ** attempt)
                        logger.debug(
                            f"Retry attempt {attempt + 1}/{attempts} for {func.__name__} "
                            f"after {wait_time:.2f}s"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.warning(
                            f"All {attempts} retry attempts exhausted for {func.__name__}"
                        )
            
            # All retries failed
            raise last_error
        
        return wrapper
    
    def graceful_degradation(self, component: str, fallback_value: Any = None):
        """
        Decorator for graceful degradation - allows module to fail gracefully.
        
        Args:
            component: Component name
            fallback_value: Value to return if component fails
        """
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(
                        f"Graceful degradation: {component}.{func.__name__} failed: {e}. "
                        f"Using fallback."
                    )
                    
                    self.handle_error(
                        error=e,
                        category=ErrorCategory.UNKNOWN,
                        severity=ErrorSeverity.WARNING,
                        component=component,
                        operation=func.__name__
                    )
                    
                    return fallback_value
            
            return wrapper
        return decorator
    
    def get_error_summary(self, component: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Get summary of recent errors."""
        errors = self.error_history
        
        if component:
            errors = [e for e in errors if e.get("component") == component]
        
        # Group by category
        by_category = {}
        by_severity = {"critical": 0, "error": 0, "warning": 0, "info": 0}
        
        for error in errors[-limit:]:
            category = error.get("category", "unknown")
            severity = error.get("severity", "info")
            
            by_category.setdefault(category, []).append(error)
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        return {
            "total_errors": len(errors),
            "recent_errors": errors[-limit:],
            "by_category": {k: len(v) for k, v in by_category.items()},
            "by_severity": by_severity,
            "last_error": errors[-1] if errors else None
        }


# Global error handler instance
_error_handler = None

def get_error_handler() -> ErrorHandler:
    """Get or create global error handler instance."""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler


# Convenience decorators
def handle_errors(category: ErrorCategory = ErrorCategory.UNKNOWN, severity: ErrorSeverity = ErrorSeverity.ERROR):
    """Decorator to automatically handle errors."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handler = get_error_handler()
                component = func.__module__ or "unknown"
                return handler.handle_error(
                    error=e,
                    category=category,
                    severity=severity,
                    component=component,
                    operation=func.__name__
                )
        return wrapper
    return decorator


if __name__ == "__main__":
    # Example usage
    handler = ErrorHandler()
    
    # Example: Retry with backoff
    @handler.retry_with_backoff(category="network")
    def fetch_data():
        # Simulated network operation
        raise ConnectionError("Network timeout")
    
    # Example: Graceful degradation
    @handler.graceful_degradation("test_component", fallback_value={})
    def optional_feature():
        raise ValueError("Feature unavailable")
    
    # Test
    try:
        fetch_data()
    except Exception as e:
        print(f"All retries failed: {e}")
    
    result = optional_feature()
    print(f"Graceful degradation result: {result}")
    
    # Get error summary
    summary = handler.get_error_summary()
    print(f"Error summary: {summary}")

