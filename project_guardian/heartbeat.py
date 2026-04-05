# project_guardian/heartbeat.py
# Heartbeat: Health Monitoring and Status Reporting
# Based on Elysia system designs

import logging
import json
import asyncio
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from threading import Lock

try:
    from .runtime_loop_core import RuntimeLoop
except ImportError:
    from runtime_loop_core import RuntimeLoop

logger = logging.getLogger(__name__)


class SystemStatus(Enum):
    """System health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"


@dataclass
class HealthMetric:
    """A single health metric."""
    name: str
    value: float
    unit: str = ""
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "threshold_warning": self.threshold_warning,
            "threshold_critical": self.threshold_critical,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class HeartbeatReport:
    """A complete heartbeat report."""
    timestamp: datetime
    status: SystemStatus
    uptime_seconds: float
    metrics: List[HealthMetric]
    module_statuses: Dict[str, Any] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "uptime_seconds": self.uptime_seconds,
            "metrics": [m.to_dict() for m in self.metrics],
            "module_statuses": self.module_statuses,
            "alerts": self.alerts
        }


class Heartbeat:
    """
    Health monitoring and status reporting system.
    Tracks system metrics, module health, and generates alerts.
    """
    
    def __init__(
        self,
        runtime_loop: Optional[RuntimeLoop] = None,
        storage_path: str = "data/heartbeat.json",
        interval_seconds: float = 30.0,
        start_time: Optional[datetime] = None
    ):
        self.runtime_loop = runtime_loop
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.interval_seconds = interval_seconds
        self.start_time = start_time or datetime.now()
        
        # Thread-safe storage
        self._lock = Lock()
        self._reports: List[HeartbeatReport] = []
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # Registered modules for health checks
        self._registered_modules: Dict[str, Any] = {}
        
        # Alert history
        self._alerts: List[Dict[str, Any]] = []
        
        self.load()
    
    def register_module(self, module_name: str, health_check: callable):
        """
        Register a module for health checks.
        
        Args:
            module_name: Module identifier
            health_check: Callable that returns module status dict
        """
        with self._lock:
            self._registered_modules[module_name] = health_check
            logger.info(f"Registered module for health checks: {module_name}")
    
    async def collect_metrics(self) -> List[HealthMetric]:
        """Collect system health metrics."""
        metrics = []
        
        try:
            # Check if psutil is available
            if not PSUTIL_AVAILABLE or psutil is None:
                # psutil not available, return safe defaults
                metrics.append(HealthMetric(
                    name="cpu_percent",
                    value=0.0,
                    unit="%",
                    threshold_warning=70.0,
                    threshold_critical=90.0
                ))
                metrics.append(HealthMetric(
                    name="memory_percent",
                    value=0.0,
                    unit="%",
                    threshold_warning=80.0,
                    threshold_critical=95.0
                ))
                return metrics
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            metrics.append(HealthMetric(
                name="cpu_percent",
                value=cpu_percent,
                unit="%",
                threshold_warning=70.0,
                threshold_critical=90.0
            ))
            
            # Memory usage
            memory = psutil.virtual_memory()
            metrics.append(HealthMetric(
                name="memory_percent",
                value=memory.percent,
                unit="%",
                threshold_warning=80.0,
                threshold_critical=95.0
            ))
            
            # Memory available
            metrics.append(HealthMetric(
                name="memory_available_mb",
                value=memory.available / (1024 * 1024),
                unit="MB",
                threshold_warning=1024.0,  # 1GB
                threshold_critical=512.0   # 512MB
            ))
            
            # Disk usage
            disk = psutil.disk_usage('/')
            metrics.append(HealthMetric(
                name="disk_percent",
                value=disk.percent,
                unit="%",
                threshold_warning=80.0,
                threshold_critical=95.0
            ))
            
            # Process-specific metrics (if runtime loop available)
            if self.runtime_loop:
                try:
                    runtime_status = self.runtime_loop.get_runtime_status()
                    
                    # Process memory
                    if "memory_usage" in runtime_status:
                        mem_info = runtime_status["memory_usage"]
                        if "process_mb" in mem_info:
                            metrics.append(HealthMetric(
                                name="process_memory_mb",
                                value=mem_info["process_mb"],
                                unit="MB",
                                threshold_warning=8000.0,
                                threshold_critical=12000.0
                            ))
                    
                    # Scheduled tasks
                    if "scheduled_tasks_count" in runtime_status:
                        metrics.append(HealthMetric(
                            name="scheduled_tasks",
                            value=runtime_status["scheduled_tasks_count"],
                            unit="count"
                        ))
                except Exception as e:
                    logger.error(f"Error collecting runtime metrics: {e}")
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
        
        return metrics
    
    async def check_module_health(self) -> Dict[str, Any]:
        """Check health of registered modules."""
        module_statuses = {}
        
        with self._lock:
            for module_name, health_check in self._registered_modules.items():
                try:
                    if asyncio.iscoroutinefunction(health_check):
                        status = await health_check()
                    else:
                        status = health_check()
                    
                    module_statuses[module_name] = status
                except Exception as e:
                    logger.error(f"Error checking health for {module_name}: {e}")
                    module_statuses[module_name] = {
                        "status": "error",
                        "error": str(e)
                    }
        
        return module_statuses
    
    def evaluate_status(self, metrics: List[HealthMetric]) -> SystemStatus:
        """Evaluate overall system status based on metrics."""
        critical_count = 0
        warning_count = 0
        
        for metric in metrics:
            if metric.threshold_critical and metric.value >= metric.threshold_critical:
                critical_count += 1
            elif metric.threshold_warning and metric.value >= metric.threshold_warning:
                warning_count += 1
        
        if critical_count > 0:
            return SystemStatus.CRITICAL
        elif warning_count > 0:
            return SystemStatus.WARNING
        else:
            return SystemStatus.HEALTHY
    
    def generate_alerts(self, metrics: List[HealthMetric], status: SystemStatus) -> List[str]:
        """Generate alert messages for concerning metrics."""
        alerts = []
        
        for metric in metrics:
            if metric.threshold_critical and metric.value >= metric.threshold_critical:
                alerts.append(
                    f"CRITICAL: {metric.name} = {metric.value}{metric.unit} "
                    f"(threshold: {metric.threshold_critical}{metric.unit})"
                )
            elif metric.threshold_warning and metric.value >= metric.threshold_warning:
                alerts.append(
                    f"WARNING: {metric.name} = {metric.value}{metric.unit} "
                    f"(threshold: {metric.threshold_warning}{metric.unit})"
                )
        
        return alerts
    
    async def generate_report(self) -> HeartbeatReport:
        """Generate a complete heartbeat report."""
        metrics = await self.collect_metrics()
        module_statuses = await self.check_module_health()
        
        status = self.evaluate_status(metrics)
        alerts = self.generate_alerts(metrics, status)
        
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        report = HeartbeatReport(
            timestamp=datetime.now(),
            status=status,
            uptime_seconds=uptime,
            metrics=metrics,
            module_statuses=module_statuses,
            alerts=alerts
        )
        
        # Store alert if present
        if alerts:
            self._alerts.append({
                "timestamp": datetime.now().isoformat(),
                "alerts": alerts,
                "status": status.value
            })
            
            # Keep only last 100 alerts
            if len(self._alerts) > 100:
                self._alerts = self._alerts[-100:]
        
        return report
    
    async def _heartbeat_loop(self):
        """Main heartbeat loop."""
        while self._running:
            try:
                report = await self.generate_report()
                
                with self._lock:
                    self._reports.append(report)
                    
                    # Keep only last 1000 reports
                    if len(self._reports) > 1000:
                        self._reports = self._reports[-1000:]
                
                self.save()
                
                # Log status if not healthy
                if report.status != SystemStatus.HEALTHY:
                    logger.warning(f"Heartbeat status: {report.status.value} - {len(report.alerts)} alerts")
                else:
                    logger.debug(f"Heartbeat: {report.status.value} - System healthy")
                
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(self.interval_seconds)
    
    def start(self):
        """Start the heartbeat monitoring."""
        if self._running:
            logger.warning("Heartbeat already running")
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Heartbeat started (interval: {self.interval_seconds}s)")
    
    def stop(self):
        """Stop the heartbeat monitoring."""
        if not self._running:
            return
        
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        logger.info("Heartbeat stopped")
    
    def get_latest_report(self) -> Optional[HeartbeatReport]:
        """Get the most recent heartbeat report."""
        with self._lock:
            return self._reports[-1] if self._reports else None
    
    def get_recent_reports(self, count: int = 10) -> List[HeartbeatReport]:
        """Get recent heartbeat reports."""
        with self._lock:
            return self._reports[-count:] if self._reports else []
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get a summary of system status."""
        latest = self.get_latest_report()
        if not latest:
            return {
                "status": "unknown",
                "message": "No heartbeat data available"
            }
        
        recent_reports = self.get_recent_reports(count=100)
        
        # Calculate status over time
        status_counts = {}
        for report in recent_reports:
            status = report.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Average uptime
        avg_uptime = sum(r.uptime_seconds for r in recent_reports) / len(recent_reports) if recent_reports else 0
        
        return {
            "current_status": latest.status.value,
            "uptime_seconds": latest.uptime_seconds,
            "total_reports": len(recent_reports),
            "status_distribution": status_counts,
            "current_alerts": latest.alerts,
            "recent_alerts_count": len(self._alerts),
            "modules_registered": len(self._registered_modules),
            "last_report_time": latest.timestamp.isoformat()
        }
    
    def get_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        with self._lock:
            return self._alerts[-limit:]
    
    def save(self):
        """Save heartbeat data."""
        with self._lock:
            data = {
                "reports": [r.to_dict() for r in self._reports[-100:]],  # Last 100
                "alerts": self._alerts[-50:],  # Last 50
                "start_time": self.start_time.isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
    
    def load(self):
        """Load heartbeat data."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                # Load reports
                for report_data in data.get("reports", []):
                    # Reconstruct report from dict
                    report = HeartbeatReport(
                        timestamp=datetime.fromisoformat(report_data["timestamp"]),
                        status=SystemStatus(report_data["status"]),
                        uptime_seconds=report_data["uptime_seconds"],
                        metrics=[
                            HealthMetric(
                                name=m["name"],
                                value=m["value"],
                                unit=m.get("unit", ""),
                                threshold_warning=m.get("threshold_warning"),
                                threshold_critical=m.get("threshold_critical"),
                                timestamp=datetime.fromisoformat(m["timestamp"])
                            )
                            for m in report_data.get("metrics", [])
                        ],
                        module_statuses=report_data.get("module_statuses", {}),
                        alerts=report_data.get("alerts", [])
                    )
                    self._reports.append(report)
                
                # Load alerts
                self._alerts = data.get("alerts", [])
                
                # Load start time if available
                if "start_time" in data:
                    self.start_time = datetime.fromisoformat(data["start_time"])
            
            logger.info(f"Loaded {len(self._reports)} heartbeat reports")
        except Exception as e:
            logger.error(f"Error loading heartbeat data: {e}")


# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_heartbeat():
        """Test the Heartbeat system."""
        heartbeat = Heartbeat(interval_seconds=5.0)
        
        # Register a simple health check
        def module_health_check():
            return {
                "status": "healthy",
                "last_check": datetime.now().isoformat()
            }
        
        heartbeat.register_module("test_module", module_health_check)
        
        # Start heartbeat
        heartbeat.start()
        
        # Generate a report manually
        report = await heartbeat.generate_report()
        print(f"Status: {report.status.value}")
        print(f"Uptime: {report.uptime_seconds:.0f}s")
        print(f"Metrics: {len(report.metrics)}")
        print(f"Alerts: {len(report.alerts)}")
        
        # Get summary
        summary = heartbeat.get_status_summary()
        print(f"\nSummary: {summary}")
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Stop
        heartbeat.stop()
    
    asyncio.run(test_heartbeat())

