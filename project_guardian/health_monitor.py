# project_guardian/health_monitor.py
# HealthMonitor: System health monitoring and reporting

import logging
import time
import psutil
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from threading import Lock
from enum import Enum

try:
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """System health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class ComponentHealth:
    """Health status for a system component."""
    def __init__(
        self,
        component: str,
        status: HealthStatus,
        message: str = "",
        last_check: Optional[datetime] = None,
        metrics: Optional[Dict[str, Any]] = None
    ):
        self.component = component
        self.status = status
        self.message = message
        self.last_check = last_check or datetime.now()
        self.metrics = metrics or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "last_check": self.last_check.isoformat(),
            "metrics": self.metrics
        }


class HealthMonitor:
    """
    System health monitoring and reporting.
    Tracks component health, system resources, and provides health check endpoints.
    """
    
    def __init__(self, check_interval: float = 30.0):
        """
        Initialize HealthMonitor.
        
        Args:
            check_interval: Interval between health checks (seconds)
        """
        self.check_interval = check_interval
        self._lock = Lock()
        self.component_health: Dict[str, ComponentHealth] = {}
        self.health_history: List[Dict[str, Any]] = []
        self.max_history_size = 100
        self.last_full_check: Optional[datetime] = None
        
        # Thresholds
        self.cpu_threshold = 90.0  # CPU usage %
        self.memory_threshold = 85.0  # Memory usage %
        self.disk_threshold = 90.0  # Disk usage %
    
    def register_component(
        self,
        component: str,
        health_check: callable,
        critical: bool = False
    ):
        """
        Register a component for health monitoring.
        
        Args:
            component: Component name
            health_check: Function that returns health status (HealthStatus, message)
            critical: If True, component failure marks system as unhealthy
        """
        with self._lock:
            # Store health check function (would need component registry for this)
            # For now, components report their own health
            pass
    
    def check_component_health(
        self,
        component: str,
        status: HealthStatus,
        message: str = "",
        metrics: Optional[Dict[str, Any]] = None
    ):
        """
        Update health status for a component.
        
        Args:
            component: Component name
            status: Health status
            message: Status message
            metrics: Optional metrics
        """
        with self._lock:
            self.component_health[component] = ComponentHealth(
                component=component,
                status=status,
                message=message,
                metrics=metrics or {}
            )
    
    def get_system_health(self) -> Dict[str, Any]:
        """
        Get overall system health status.
        
        Returns:
            Health status dictionary
        """
        with self._lock:
            # Check component health
            components = {
                name: health.to_dict()
                for name, health in self.component_health.items()
            }
            
            # Get resource usage
            resources = self._get_resource_usage()
            
            # Determine overall status
            overall_status = self._determine_overall_status(components, resources)
            
            return {
                "status": overall_status.value,
                "timestamp": datetime.now().isoformat(),
                "components": components,
                "resources": resources,
                "uptime": self._get_uptime()
            }
    
    def _get_resource_usage(self) -> Dict[str, Any]:
        """Get system resource usage."""
        if not PSUTIL_AVAILABLE:
            return {
                "cpu_percent": None,
                "memory_percent": None,
                "disk_percent": None,
                "error": "psutil not available"
            }
        
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / (1024**3)
            }
        except Exception as e:
            logger.error(f"Error getting resource usage: {e}")
            return {
                "error": str(e)
            }
    
    def _determine_overall_status(
        self,
        components: Dict[str, Any],
        resources: Dict[str, Any]
    ) -> HealthStatus:
        """Determine overall system health status."""
        # Check for critical component failures
        critical_failures = [
            name for name, comp in components.items()
            if comp["status"] == HealthStatus.CRITICAL.value
        ]
        
        if critical_failures:
            return HealthStatus.CRITICAL
        
        # Check resource usage
        cpu_percent = resources.get("cpu_percent")
        memory_percent = resources.get("memory_percent")
        disk_percent = resources.get("disk_percent")
        
        if cpu_percent and cpu_percent > self.cpu_threshold:
            return HealthStatus.UNHEALTHY
        
        if memory_percent and memory_percent > self.memory_threshold:
            return HealthStatus.DEGRADED
        
        if disk_percent and disk_percent > self.disk_threshold:
            return HealthStatus.DEGRADED
        
        # Check component health
        unhealthy_components = [
            name for name, comp in components.items()
            if comp["status"] in [HealthStatus.UNHEALTHY.value, HealthStatus.CRITICAL.value]
        ]
        
        if unhealthy_components:
            return HealthStatus.DEGRADED
        
        return HealthStatus.HEALTHY
    
    def _get_uptime(self) -> Optional[float]:
        """Get system uptime in seconds."""
        # Would track system start time
        # For now, return None (would be implemented with system start tracking)
        return None
    
    def get_health_endpoint_response(self) -> Dict[str, Any]:
        """
        Get response for health check endpoint.
        
        Returns:
            Health status suitable for HTTP response
        """
        health = self.get_system_health()
        
        # HTTP status code based on health
        status_code = 200
        if health["status"] == HealthStatus.CRITICAL.value:
            status_code = 503  # Service Unavailable
        elif health["status"] == HealthStatus.UNHEALTHY.value:
            status_code = 503
        elif health["status"] == HealthStatus.DEGRADED.value:
            status_code = 200  # OK but degraded
        
        return {
            "status": health["status"],
            "timestamp": health["timestamp"],
            "components": health["components"],
            "resources": health["resources"],
            "http_status": status_code
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get system metrics for monitoring."""
        resources = self._get_resource_usage()
        components = {
            name: health.to_dict()
            for name, health in self.component_health.items()
        }
        
        return {
            "resources": resources,
            "components": components,
            "health_history_size": len(self.health_history),
            "last_check": self.last_full_check.isoformat() if self.last_full_check else None
        }


# Global health monitor instance
_health_monitor = None

def get_health_monitor() -> HealthMonitor:
    """Get or create global health monitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor


if __name__ == "__main__":
    # Example usage
    monitor = HealthMonitor()
    
    # Register component health
    monitor.check_component_health(
        "memory",
        HealthStatus.HEALTHY,
        "Memory system operational",
        {"items_stored": 1000}
    )
    
    monitor.check_component_health(
        "api",
        HealthStatus.DEGRADED,
        "API rate limited",
        {"requests_per_minute": 50}
    )
    
    # Get system health
    health = monitor.get_system_health()
    print("System Health:", health["status"])
    print("Components:", list(health["components"].keys()))
    print("Resources:", health["resources"])

