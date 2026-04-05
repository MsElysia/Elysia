# project_guardian/runtime_health.py
# Runtime Health Monitoring System
# Continuously monitors system health during operation

import logging
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """System health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Some issues but functional
    WARNING = "warning"  # Issues detected
    CRITICAL = "critical"  # Critical issues
    UNKNOWN = "unknown"


class HealthCheck:
    """Represents a health check result."""
    def __init__(
        self,
        name: str,
        status: HealthStatus,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None
    ):
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}
        self.timestamp = timestamp or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


class RuntimeHealthMonitor:
    """
    Monitors system health during runtime.
    Tracks component health, performance metrics, and detects issues.
    """
    
    def __init__(
        self,
        check_interval: float = 30.0,
        history_size: int = 100
    ):
        """
        Initialize runtime health monitor.
        
        Args:
            check_interval: Seconds between health checks
            history_size: Number of health check results to keep
        """
        self.check_interval = check_interval
        self.history_size = history_size
        self.checks: Dict[str, HealthCheck] = {}
        self.history: deque = deque(maxlen=history_size)
        self.callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Health check functions
        self.check_functions: Dict[str, Callable[[], HealthCheck]] = {}
    
    def register_check(self, name: str, check_func: Callable[[], HealthCheck]):
        """
        Register a health check function.
        
        Args:
            name: Check name
            check_func: Function that returns HealthCheck
        """
        self.check_functions[name] = check_func
    
    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Add callback for health status changes.
        
        Args:
            callback: Function called with health summary when status changes
        """
        self.callbacks.append(callback)
    
    def check_health(self) -> Dict[str, Any]:
        """
        Perform all registered health checks.
        
        Returns:
            Dictionary with overall health status and individual checks
        """
        with self._lock:
            checks = {}
            statuses = []
            
            # Run all registered checks
            for name, check_func in self.check_functions.items():
                try:
                    check = check_func()
                    checks[name] = check.to_dict()
                    statuses.append(check.status)
                except Exception as e:
                    logger.error(f"Health check {name} failed: {e}")
                    check = HealthCheck(
                        name=name,
                        status=HealthStatus.UNKNOWN,
                        message=f"Check failed: {e}"
                    )
                    checks[name] = check.to_dict()
                    statuses.append(HealthStatus.UNKNOWN)
            
            # Determine overall status
            overall_status = self._determine_overall_status(statuses)
            
            # Store in history
            result = {
                "timestamp": datetime.now().isoformat(),
                "overall_status": overall_status.value,
                "checks": checks
            }
            self.history.append(result)
            
            # Update stored checks
            self.checks = {name: HealthCheck(**check) for name, check in checks.items()}
            
            return result
    
    def _determine_overall_status(self, statuses: List[HealthStatus]) -> HealthStatus:
        """
        Determine overall health status from individual check statuses.
        
        Args:
            statuses: List of individual check statuses
            
        Returns:
            Overall health status
        """
        if not statuses:
            return HealthStatus.UNKNOWN
        
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def get_health(self) -> Dict[str, Any]:
        """
        Get current health status.
        
        Returns:
            Dictionary with current health information
        """
        with self._lock:
            return {
                "timestamp": datetime.now().isoformat(),
                "checks": {name: check.to_dict() for name, check in self.checks.items()},
                "overall_status": self._determine_overall_status(
                    [check.status for check in self.checks.values()]
                ).value if self.checks else HealthStatus.UNKNOWN.value
            }
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get health check history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of historical health check results
        """
        with self._lock:
            history_list = list(self.history)
            if limit:
                return history_list[-limit:]
            return history_list
    
    def start_monitoring(self):
        """Start continuous health monitoring."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Runtime health monitoring started")
    
    def stop_monitoring(self):
        """Stop continuous health monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Runtime health monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        last_status = None
        
        while self._running:
            try:
                health_result = self.check_health()
                current_status = health_result["overall_status"]
                
                # Notify callbacks if status changed
                if last_status != current_status:
                    for callback in self.callbacks:
                        try:
                            callback(health_result)
                        except Exception as e:
                            logger.error(f"Health callback failed: {e}")
                    last_status = current_status
                
                # Log critical issues
                if current_status == HealthStatus.CRITICAL:
                    logger.error("CRITICAL health issues detected:")
                    for name, check in health_result["checks"].items():
                        if check["status"] == HealthStatus.CRITICAL.value:
                            logger.error(f"  - {name}: {check['message']}")
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
            
            # Sleep until next check
            time.sleep(self.check_interval)


def create_guardian_health_checks(guardian_core) -> Dict[str, Callable[[], HealthCheck]]:
    """
    Create health check functions for GuardianCore.
    
    Args:
        guardian_core: GuardianCore instance
        
    Returns:
        Dictionary of health check functions
    """
    checks = {}
    
    def check_memory():
        """Check memory system health."""
        try:
            if not hasattr(guardian_core, 'memory'):
                return HealthCheck("memory", HealthStatus.CRITICAL, "Memory system not initialized")
            
            # Check if memory is accessible
            try:
                status = guardian_core.memory.get_status()
                if status.get("healthy", False):
                    return HealthCheck("memory", HealthStatus.HEALTHY, "Memory system operational")
                else:
                    return HealthCheck("memory", HealthStatus.DEGRADED, "Memory system has issues", details=status)
            except Exception as e:
                return HealthCheck("memory", HealthStatus.WARNING, f"Memory check failed: {e}")
        except Exception as e:
            return HealthCheck("memory", HealthStatus.UNKNOWN, f"Memory check error: {e}")
    
    def check_mutation():
        """Check mutation system health."""
        try:
            if not hasattr(guardian_core, 'mutation'):
                return HealthCheck("mutation", HealthStatus.CRITICAL, "Mutation system not initialized")
            
            # Check if mutation system is accessible
            try:
                # Simple check - just verify it exists and has required methods
                if hasattr(guardian_core.mutation, 'get_status'):
                    return HealthCheck("mutation", HealthStatus.HEALTHY, "Mutation system operational")
                else:
                    return HealthCheck("mutation", HealthStatus.WARNING, "Mutation system missing methods")
            except Exception as e:
                return HealthCheck("mutation", HealthStatus.WARNING, f"Mutation check failed: {e}")
        except Exception as e:
            return HealthCheck("mutation", HealthStatus.UNKNOWN, f"Mutation check error: {e}")
    
    def check_trust():
        """Check trust system health."""
        try:
            if not hasattr(guardian_core, 'trust'):
                return HealthCheck("trust", HealthStatus.CRITICAL, "Trust system not initialized")
            
            return HealthCheck("trust", HealthStatus.HEALTHY, "Trust system operational")
        except Exception as e:
            return HealthCheck("trust", HealthStatus.UNKNOWN, f"Trust check error: {e}")
    
    def check_monitor():
        """Check monitoring system health."""
        try:
            if not hasattr(guardian_core, 'monitor'):
                return HealthCheck("monitor", HealthStatus.WARNING, "Monitor system not initialized")
            
            return HealthCheck("monitor", HealthStatus.HEALTHY, "Monitor system operational")
        except Exception as e:
            return HealthCheck("monitor", HealthStatus.UNKNOWN, f"Monitor check error: {e}")
    
    def check_resources():
        """Check resource monitoring."""
        try:
            if not hasattr(guardian_core, 'resource_monitor'):
                return HealthCheck("resources", HealthStatus.UNKNOWN, "Resource monitor not available")
            
            try:
                stats = guardian_core.get_resource_stats()
                violations = guardian_core.get_resource_violations(limit=1)
                
                if violations:
                    return HealthCheck(
                        "resources",
                        HealthStatus.WARNING,
                        f"Resource violations detected: {len(violations)}",
                        details={"violations": len(violations)}
                    )
                else:
                    return HealthCheck("resources", HealthStatus.HEALTHY, "Resources within limits", details=stats)
            except Exception as e:
                return HealthCheck("resources", HealthStatus.WARNING, f"Resource check failed: {e}")
        except Exception as e:
            return HealthCheck("resources", HealthStatus.UNKNOWN, f"Resource check error: {e}")
    
    def check_memory_count():
        """Check memory count and trigger cleanup if needed."""
        try:
            if not hasattr(guardian_core, 'memory') or not guardian_core.memory:
                return HealthCheck("memory_count", HealthStatus.UNKNOWN, "Memory system not available")
            
            try:
                gmem = guardian_core.memory
                if hasattr(gmem, "get_memory_count"):
                    memory_count = gmem.get_memory_count(load_if_needed=True)
                elif hasattr(gmem, "get_memory_state"):
                    memory_count = gmem.get_memory_state(load_if_needed=True).get("memory_count")
                else:
                    memory_count = None
                if memory_count is None:
                    return HealthCheck(
                        "memory_count", HealthStatus.UNKNOWN,
                        "JSON memory not loaded yet; skipping threshold check",
                        details={"memory_loaded": False},
                    )
                memory_threshold = getattr(guardian_core, 'config', {}).get("memory_cleanup_threshold", 3500)

                if memory_count > memory_threshold:
                    # Trigger automatic cleanup
                    try:
                        if hasattr(guardian_core.memory, 'consolidate'):
                            result = guardian_core.memory.consolidate(
                                max_memories=memory_threshold,
                                keep_recent_days=getattr(guardian_core, 'config', {}).get("memory_keep_recent_days", 30)
                            )
                            if "error" not in result:
                                final_count = result.get('final_count', memory_count)
                                removed = result.get('removed', 0)
                                return HealthCheck(
                                    "memory_count", HealthStatus.HEALTHY,
                                    f"Memory cleanup completed: {memory_count} -> {final_count} (removed {removed})",
                                    details={"original": memory_count, "final": final_count, "removed": removed}
                                )
                    except Exception as e:
                        logger.warning(f"Auto-cleanup in health check failed: {e}")

                    return HealthCheck(
                        "memory_count", HealthStatus.WARNING,
                        f"High memory count: {memory_count} (threshold: {memory_threshold})",
                        details={"count": memory_count, "threshold": memory_threshold}
                    )
                return HealthCheck(
                    "memory_count", HealthStatus.HEALTHY,
                    f"Memory count normal: {memory_count}",
                    details={"count": memory_count, "threshold": memory_threshold}
                )
            except Exception as e:
                return HealthCheck("memory_count", HealthStatus.WARNING, f"Memory count check failed: {e}")
        except Exception as e:
            return HealthCheck("memory_count", HealthStatus.UNKNOWN, f"Memory count check error: {e}")
    
    checks["memory"] = check_memory
    checks["mutation"] = check_mutation
    checks["trust"] = check_trust
    checks["monitor"] = check_monitor
    checks["resources"] = check_resources
    checks["memory_count"] = check_memory_count
    
    return checks

