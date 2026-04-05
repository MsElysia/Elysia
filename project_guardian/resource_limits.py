# project_guardian/resource_limits.py
# Resource Limits and Monitoring
# Prevents resource exhaustion and provides monitoring

import os
import logging
import threading
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
from pathlib import Path

# Throttle repeated resource warnings (seconds between same-type logs)
# Override via ELYSIA_RESOURCE_COOLDOWN (e.g. 600 for 10 min)
try:
    RESOURCE_LOG_COOLDOWN = int(os.environ.get("ELYSIA_RESOURCE_COOLDOWN", "600"))
except (ValueError, TypeError):
    RESOURCE_LOG_COOLDOWN = 600
try:
    MEMORY_LIMIT_CALLBACK_STREAK = int(os.environ.get("ELYSIA_MEMORY_LIMIT_CALLBACK_STREAK", "2"))
except (ValueError, TypeError):
    MEMORY_LIMIT_CALLBACK_STREAK = 2

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """Resource types."""
    MEMORY = "memory"
    CPU = "cpu"
    DISK = "disk"


class ResourceLimit:
    """Represents a resource limit."""
    def __init__(
        self,
        resource_type: ResourceType,
        limit_percent: float,
        warning_threshold: float = 0.8,
        critical_threshold: float = 0.9
    ):
        """
        Initialize resource limit.
        
        Args:
            resource_type: Type of resource
            limit_percent: Maximum allowed usage (0.0-1.0)
            warning_threshold: Warning level (0.0-1.0 of limit)
            critical_threshold: Critical level (0.0-1.0 of limit)
        """
        self.resource_type = resource_type
        self.limit_percent = limit_percent
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold


class ResourceMonitor:
    """
    Resource monitoring and limit enforcement.
    Monitors memory, CPU, and disk usage with configurable limits.
    """
    
    def __init__(
        self,
        memory_limit_percent: float = 0.8,  # 80% memory limit
        cpu_limit_percent: float = 0.9,  # 90% CPU limit
        disk_limit_percent: float = 0.9,  # 90% disk limit
        disk_path: str = "."
    ):
        """
        Initialize ResourceMonitor.
        
        Args:
            memory_limit_percent: Maximum memory usage (0.0-1.0)
            cpu_limit_percent: Maximum CPU usage (0.0-1.0)
            disk_limit_percent: Maximum disk usage (0.0-1.0)
            disk_path: Path to monitor disk usage for
        """
        self.limits = {
            ResourceType.MEMORY: ResourceLimit(
                ResourceType.MEMORY,
                memory_limit_percent,
                warning_threshold=0.7,
                critical_threshold=0.85
            ),
            ResourceType.CPU: ResourceLimit(
                ResourceType.CPU,
                cpu_limit_percent,
                warning_threshold=0.75,
                critical_threshold=0.9
            ),
            ResourceType.DISK: ResourceLimit(
                ResourceType.DISK,
                disk_limit_percent,
                warning_threshold=0.8,
                critical_threshold=0.9
            )
        }
        
        self.disk_path = Path(disk_path)
        self.monitoring_active = False
        self.monitor_thread = None
        self.resource_stats = {}
        self.violations = []
        self.callbacks = {
            ResourceType.MEMORY: [],
            ResourceType.CPU: [],
            ResourceType.DISK: []
        }
        
        # Check if psutil is available
        self.psutil_available = PSUTIL_AVAILABLE
        if not self.psutil_available:
            logger.warning("psutil not available, resource monitoring disabled")

        # Throttle repeated warnings (key: (resource_type, log_kind), value: last_log_time)
        self._log_throttle: Dict[tuple, float] = {}
        # Consecutive over-limit streak by resource for transient-spike suppression.
        self._over_limit_streak: Dict[ResourceType, int] = {
            ResourceType.MEMORY: 0,
            ResourceType.CPU: 0,
            ResourceType.DISK: 0,
        }
    
    def start_monitoring(self, interval: int = 30):
        """
        Start resource monitoring.
        
        Args:
            interval: Monitoring interval in seconds
        """
        if not self.psutil_available:
            logger.warning("Cannot start monitoring: psutil not available")
            return
        
        if self.monitoring_active:
            logger.warning("Monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
        logger.info("Resource monitoring started")
    
    def stop_monitoring(self):
        """Stop resource monitoring."""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("Resource monitoring stopped")
    
    def _monitor_loop(self, interval: int):
        """Main monitoring loop."""
        import time
        
        while self.monitoring_active:
            try:
                self.check_resources()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                time.sleep(interval)
    
    def check_resources(self) -> Dict[str, Any]:
        """
        Check current resource usage.
        
        Returns:
            Dictionary with resource usage stats
        """
        if not self.psutil_available:
            return {}
        
        stats = {}
        
        try:
            if psutil:
                # Memory usage
                memory = psutil.virtual_memory()
                memory_percent = memory.percent / 100.0
                stats['memory'] = {
                    'used_percent': memory_percent,
                    'used_mb': memory.used / (1024 * 1024),
                    'total_mb': memory.total / (1024 * 1024),
                    'available_mb': memory.available / (1024 * 1024)
                }
                self._check_limit(ResourceType.MEMORY, memory_percent)
                
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=0.1) / 100.0
                stats['cpu'] = {
                    'used_percent': cpu_percent,
                    'cores': psutil.cpu_count()
                }
                self._check_limit(ResourceType.CPU, cpu_percent)
                
                # Disk usage
                disk = psutil.disk_usage(str(self.disk_path))
                disk_percent = disk.percent / 100.0
                stats['disk'] = {
                    'used_percent': disk_percent,
                    'used_gb': disk.used / (1024 * 1024 * 1024),
                    'total_gb': disk.total / (1024 * 1024 * 1024),
                    'free_gb': disk.free / (1024 * 1024 * 1024)
                }
                self._check_limit(ResourceType.DISK, disk_percent)
        except Exception as e:
            logger.error(f"Error checking resources: {e}")
        
        self.resource_stats = stats
        return stats
    
    def _should_log(self, key: tuple) -> bool:
        """Return True if we should log (throttle passed or first time)."""
        now = time.time()
        last = self._log_throttle.get(key, 0)
        if now - last >= RESOURCE_LOG_COOLDOWN:
            self._log_throttle[key] = now
            return True
        return False

    def _check_limit(self, resource_type: ResourceType, usage_percent: float):
        """Check if resource usage exceeds limits."""
        limit = self.limits[resource_type]

        # If memory usage is high, trigger aggressive cleanup
        if resource_type == ResourceType.MEMORY and usage_percent > 0.70:  # 70% threshold
            try:
                import gc
                gc.collect()
                # Only log memory_alert when NOT over limit (limit_exceeded log below handles that)
                over_limit = usage_percent > limit.limit_percent
                if not over_limit:
                    log_key = (resource_type.value, "memory_alert")
                    if self._should_log(log_key):
                        if usage_percent > 0.75:
                            logger.warning(
                                f"[Memory Alert] System memory at {usage_percent*100:.1f}% - "
                                "Automatic cleanup should trigger on next heartbeat"
                            )
                        else:
                            logger.info(
                                f"[Memory Alert] System memory at {usage_percent*100:.1f}% - "
                                "Garbage collection triggered"
                            )
            except Exception as e:
                logger.debug(f"Error in memory cleanup trigger: {e}")

        # Check if exceeded limit
        if usage_percent > limit.limit_percent:
            self._over_limit_streak[resource_type] = self._over_limit_streak.get(resource_type, 0) + 1
            streak = self._over_limit_streak[resource_type]
            violation = {
                "resource": resource_type.value,
                "usage_percent": usage_percent,
                "limit_percent": limit.limit_percent,
                "timestamp": datetime.now().isoformat(),
                "severity": "critical" if usage_percent > limit.critical_threshold else "warning",
                "streak": streak,
            }

            self.violations.append(violation)

            log_key = (resource_type.value, "limit_exceeded")
            if self._should_log(log_key):
                logger.warning(
                    f"Resource limit exceeded: {resource_type.value} at {usage_percent:.1%} "
                    f"(limit: {limit.limit_percent:.1%})"
                )

            # Trigger callbacks after a sustained breach for memory, to avoid noisy
            # cleanup loops from one-off host RAM spikes.
            callback_streak_threshold = 1
            if resource_type == ResourceType.MEMORY:
                callback_streak_threshold = max(1, MEMORY_LIMIT_CALLBACK_STREAK)
            if streak >= callback_streak_threshold:
                if resource_type == ResourceType.MEMORY and streak == callback_streak_threshold:
                    logger.info(
                        "[ResourceMonitor] Memory callback armed: sustained breach streak=%d threshold=%d usage=%.1f%%",
                        streak,
                        callback_streak_threshold,
                        usage_percent * 100.0,
                    )
                for callback in self.callbacks[resource_type]:
                    try:
                        callback(violation)
                    except Exception as e:
                        logger.error(f"Error in resource limit callback: {e}")
            elif resource_type == ResourceType.MEMORY:
                logger.debug(
                    "[ResourceMonitor] Memory callback suppressed: streak=%d/%d usage=%.1f%%",
                    streak,
                    callback_streak_threshold,
                    usage_percent * 100.0,
                )

            # Keep only recent violations
            if len(self.violations) > 100:
                self.violations = self.violations[-100:]
        else:
            # Reset streak after a healthy sample.
            self._over_limit_streak[resource_type] = 0

        # Check warning threshold
        if usage_percent > limit.warning_threshold * limit.limit_percent:
            log_key = (resource_type.value, "warning_threshold")
            if self._should_log(log_key):
                logger.debug(
                    f"Resource usage high: {resource_type.value} at {usage_percent:.1%} "
                    f"(warning threshold: {limit.warning_threshold * limit.limit_percent:.1%})"
                )
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """
        Get current resource statistics.
        
        Returns:
            Dictionary with resource stats
        """
        if not self.resource_stats:
            self.check_resources()
        
        return self.resource_stats.copy()
    
    def get_violations(self, limit: Optional[int] = None) -> list:
        """
        Get resource limit violations.
        
        Args:
            limit: Maximum number of violations to return
            
        Returns:
            List of violations
        """
        violations = self.violations.copy()
        if limit:
            violations = violations[-limit:]
        return violations
    
    def set_limit(
        self,
        resource_type: ResourceType,
        limit_percent: float,
        warning_threshold: Optional[float] = None,
        critical_threshold: Optional[float] = None
    ):
        """
        Set resource limit.
        
        Args:
            resource_type: Type of resource
            limit_percent: Maximum allowed usage (0.0-1.0)
            warning_threshold: Warning level (0.0-1.0 of limit)
            critical_threshold: Critical level (0.0-1.0 of limit)
        """
        limit = ResourceLimit(
            resource_type,
            limit_percent,
            warning_threshold=warning_threshold or 0.8,
            critical_threshold=critical_threshold or 0.9
        )
        self.limits[resource_type] = limit
        logger.info(f"Set {resource_type.value} limit to {limit_percent:.1%}")
    
    def register_callback(
        self,
        resource_type: ResourceType,
        callback: Callable[[Dict[str, Any]], None]
    ):
        """
        Register callback for resource limit violations.
        
        Args:
            resource_type: Type of resource
            callback: Function to call when limit exceeded
        """
        self.callbacks[resource_type].append(callback)
    
    def is_resource_available(self, resource_type: ResourceType) -> bool:
        """
        Check if resource is available (below limit).
        
        Args:
            resource_type: Type of resource
            
        Returns:
            True if resource is available
        """
        if not self.psutil_available:
            return True  # Assume available if can't check
        
        stats = self.get_resource_stats()
        limit = self.limits[resource_type]
        
        if resource_type == ResourceType.MEMORY:
            usage = stats.get('memory', {}).get('used_percent', 0)
        elif resource_type == ResourceType.CPU:
            usage = stats.get('cpu', {}).get('used_percent', 0)
        elif resource_type == ResourceType.DISK:
            usage = stats.get('disk', {}).get('used_percent', 0)
        else:
            return True
        
        return usage < limit.limit_percent
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get monitoring status.
        
        Returns:
            Dictionary with status information
        """
        return {
            'monitoring_active': self.monitoring_active,
            'psutil_available': self.psutil_available,
            'limits': {
                rt.value: {
                    'limit_percent': limit.limit_percent,
                    'warning_threshold': limit.warning_threshold,
                    'critical_threshold': limit.critical_threshold
                }
                for rt, limit in self.limits.items()
            },
            'recent_violations': len(self.violations),
            'resource_stats': self.get_resource_stats()
        }

