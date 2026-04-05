# project_guardian/startup_verification.py
# Startup Verification System
# Ensures system starts flawlessly and all components initialize correctly

import logging
import traceback
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ComponentStatus(Enum):
    """Component initialization status."""
    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    SUCCESS = "success"
    WARNING = "warning"  # Works but with warnings
    FAILED = "failed"  # Failed but non-critical
    CRITICAL = "critical"  # Critical failure


class ComponentCheck:
    """Represents a component initialization check."""
    def __init__(
        self,
        name: str,
        status: ComponentStatus,
        message: str = "",
        error: Optional[Exception] = None,
        critical: bool = True
    ):
        self.name = name
        self.status = status
        self.message = message
        self.error = error
        self.critical = critical
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "error": str(self.error) if self.error else None,
            "critical": self.critical,
            "timestamp": self.timestamp.isoformat()
        }


class StartupVerifier:
    """
    Verifies system startup and component initialization.
    Ensures all critical components initialize correctly before system operation.
    """
    
    def __init__(self, start_time: Optional[datetime] = None):
        self.checks: List[ComponentCheck] = []
        # Use provided start time (e.g. GuardianCore.start_time) so duration measures real startup, not just verification
        self.start_time = start_time if start_time is not None else datetime.now()
    
    def verify_component(
        self,
        name: str,
        init_func: callable,
        critical: bool = True,
        fallback: Optional[callable] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify a component initializes correctly.
        
        Args:
            name: Component name
            init_func: Function that initializes the component
            critical: Whether component is critical for startup
            fallback: Optional fallback initialization function
            
        Returns:
            Tuple of (success, error_message)
        """
        check = ComponentCheck(name, ComponentStatus.INITIALIZING, critical=critical)
        self.checks.append(check)
        
        try:
            result = init_func()
            
            # Check if result indicates success
            if result is False or (isinstance(result, dict) and result.get("success") is False):
                error_msg = result.get("error", "Initialization returned False") if isinstance(result, dict) else "Initialization failed"
                check.status = ComponentStatus.FAILED if not critical else ComponentStatus.CRITICAL
                check.message = error_msg
                check.error = Exception(error_msg)
                
                # Try fallback if available
                if fallback:
                    logger.info(f"Attempting fallback for {name}")
                    try:
                        fallback_result = fallback()
                        if fallback_result:
                            check.status = ComponentStatus.WARNING
                            check.message = f"Using fallback initialization"
                            return True, None
                    except Exception as fallback_error:
                        logger.error(f"Fallback also failed for {name}: {fallback_error}")
                
                return False, error_msg
            
            check.status = ComponentStatus.SUCCESS
            check.message = "Initialized successfully"
            return True, None
            
        except Exception as e:
            error_msg = str(e)
            check.status = ComponentStatus.CRITICAL if critical else ComponentStatus.FAILED
            check.message = f"Initialization error: {error_msg}"
            check.error = e
            
            # Try fallback if available
            if fallback:
                logger.info(f"Attempting fallback for {name} after error")
                try:
                    fallback_result = fallback()
                    if fallback_result:
                        check.status = ComponentStatus.WARNING
                        check.message = f"Using fallback after error: {error_msg}"
                        return True, None
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed for {name}: {fallback_error}")
            
            if critical:
                logger.error(f"Critical component {name} failed: {e}")
                logger.error(traceback.format_exc())
            else:
                logger.warning(f"Non-critical component {name} failed: {e}")
            
            return False, error_msg
    
    def verify_import(self, module_name: str, critical: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Verify a module can be imported.
        
        Args:
            module_name: Module name to import
            critical: Whether import is critical
            
        Returns:
            Tuple of (success, error_message)
        """
        check = ComponentCheck(f"import:{module_name}", ComponentStatus.INITIALIZING, critical=critical)
        self.checks.append(check)
        
        try:
            __import__(module_name)
            check.status = ComponentStatus.SUCCESS
            check.message = "Import successful"
            return True, None
        except ImportError as e:
            check.status = ComponentStatus.CRITICAL if critical else ComponentStatus.FAILED
            check.message = f"Import failed: {e}"
            check.error = e
            
            if critical:
                logger.error(f"Critical import {module_name} failed: {e}")
            else:
                logger.warning(f"Optional import {module_name} failed: {e}")
            
            return False, str(e)
    
    def verify_attribute(self, obj: Any, attr_name: str, component_name: str, critical: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Verify an object has a required attribute.
        
        Args:
            obj: Object to check
            attr_name: Attribute name
            component_name: Component name for reporting
            critical: Whether attribute is critical
            
        Returns:
            Tuple of (success, error_message)
        """
        check = ComponentCheck(f"{component_name}.{attr_name}", ComponentStatus.INITIALIZING, critical=critical)
        self.checks.append(check)
        
        if not hasattr(obj, attr_name):
            check.status = ComponentStatus.CRITICAL if critical else ComponentStatus.FAILED
            check.message = f"Missing required attribute: {attr_name}"
            check.error = AttributeError(f"{component_name} missing {attr_name}")
            
            if critical:
                logger.error(f"Critical attribute {component_name}.{attr_name} missing")
            else:
                logger.warning(f"Optional attribute {component_name}.{attr_name} missing")
            
            return False, check.message
        
        check.status = ComponentStatus.SUCCESS
        check.message = "Attribute present"
        return True, None
    
    def verify_method(self, obj: Any, method_name: str, component_name: str, critical: bool = True) -> Tuple[bool, Optional[str]]:
        """
        Verify an object has a callable method.
        
        Args:
            obj: Object to check
            method_name: Method name
            component_name: Component name for reporting
            critical: Whether method is critical
            
        Returns:
            Tuple of (success, error_message)
        """
        check = ComponentCheck(f"{component_name}.{method_name}()", ComponentStatus.INITIALIZING, critical=critical)
        self.checks.append(check)
        
        if not hasattr(obj, method_name):
            check.status = ComponentStatus.CRITICAL if critical else ComponentStatus.FAILED
            check.message = f"Missing required method: {method_name}"
            check.error = AttributeError(f"{component_name} missing {method_name}")
            return False, check.message
        
        if not callable(getattr(obj, method_name)):
            check.status = ComponentStatus.CRITICAL if critical else ComponentStatus.FAILED
            check.message = f"Attribute {method_name} is not callable"
            check.error = TypeError(f"{component_name}.{method_name} is not callable")
            return False, check.message
        
        check.status = ComponentStatus.SUCCESS
        check.message = "Method present and callable"
        return True, None
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get verification summary.
        
        Returns:
            Dictionary with verification results
        """
        critical_failures = [c for c in self.checks if c.status == ComponentStatus.CRITICAL]
        failures = [c for c in self.checks if c.status == ComponentStatus.FAILED]
        warnings = [c for c in self.checks if c.status == ComponentStatus.WARNING]
        successes = [c for c in self.checks if c.status == ComponentStatus.SUCCESS]
        
        all_critical_passed = len(critical_failures) == 0
        all_passed = len(critical_failures) == 0 and len(failures) == 0

        # Classify overall status
        if not all_critical_passed:
            status = "failed"
        elif all_passed and len(warnings) == 0:
            status = "clean_success"
        else:
            status = "success_with_warnings"
        
        return {
            "startup_successful": all_critical_passed,
            "all_components_ok": all_passed,
            "status": status,
            "total_checks": len(self.checks),
            "critical_failures": len(critical_failures),
            "failures": len(failures),
            "warnings": len(warnings),
            "successes": len(successes),
            "checks": [c.to_dict() for c in self.checks],
            "duration_seconds": (datetime.now() - self.start_time).total_seconds()
        }
    
    def log_summary(self):
        """Log verification summary."""
        summary = self.get_summary()
        
        logger.info("=" * 60)
        logger.info("Startup Verification Summary")
        logger.info("=" * 60)
        logger.info(f"Total Checks: {summary['total_checks']}")
        logger.info(f"Successes: {summary['successes']}")
        logger.info(f"Warnings: {summary['warnings']}")
        logger.info(f"Failures: {summary['failures']}")
        logger.info(f"Critical Failures: {summary['critical_failures']}")
        
        status = summary.get("status", "unknown")
        if status == "failed":
            logger.error("=" * 60)
            logger.error("[FAIL] Startup verification detected critical failures")
            for check in self.checks:
                if check.status == ComponentStatus.CRITICAL:
                    logger.error(f"  - {check.name}: {check.message}")
            logger.error("=" * 60)
        elif status == "success_with_warnings":
            logger.warning("=" * 60)
            logger.warning("[WARN] Startup completed with warnings")
            # Log top warning messages (compact)
            warn_checks = [c for c in self.checks if c.status == ComponentStatus.WARNING][:5]
            for check in warn_checks:
                logger.warning(f"  - {check.name}: {check.message}")
            fail_checks = [c for c in self.checks if c.status == ComponentStatus.FAILED][:5]
            for check in fail_checks:
                logger.warning(f"  - {check.name}: {check.message}")
            logger.warning("=" * 60)
        elif status == "clean_success":
            logger.info("=" * 60)
            logger.info("[OK] Startup completed successfully")
            logger.info("=" * 60)
        else:
            logger.warning("=" * 60)
            logger.warning(f"[WARN] Startup status={status}")
            logger.warning("=" * 60)
        
        logger.info(
            f"Startup duration: {summary['duration_seconds']:.2f}s "
            f"(status={status})"
        )
    
    def should_continue(self) -> bool:
        """
        Determine if system should continue after verification.
        
        Returns:
            True if no critical failures, False otherwise
        """
        summary = self.get_summary()
        return summary['startup_successful']


def verify_guardian_startup(guardian_core) -> Dict[str, Any]:
    """
    Verify GuardianCore startup and component initialization.
    
    Args:
        guardian_core: GuardianCore instance
        
    Returns:
        Verification summary
    """
    # Use GuardianCore.start_time so "Startup duration" measures full init, not just verification (was 0.00s)
    start_time = getattr(guardian_core, "start_time", None)
    if start_time is not None and not isinstance(start_time, datetime):
        start_time = None
    verifier = StartupVerifier(start_time=start_time)
    
    # Verify core components
    verifier.verify_attribute(guardian_core, 'memory', 'GuardianCore', critical=True)
    verifier.verify_attribute(guardian_core, 'mutation', 'GuardianCore', critical=True)
    verifier.verify_attribute(guardian_core, 'trust', 'GuardianCore', critical=True)
    verifier.verify_attribute(guardian_core, 'monitor', 'GuardianCore', critical=True)
    
    # Verify methods
    verifier.verify_method(guardian_core, 'get_system_status', 'GuardianCore', critical=True)
    verifier.verify_method(guardian_core, 'shutdown', 'GuardianCore', critical=True)
    
    # Verify optional but important components
    verifier.verify_attribute(guardian_core, 'resource_monitor', 'GuardianCore', critical=False)
    verifier.verify_attribute(guardian_core, 'security_auditor', 'GuardianCore', critical=False)
    verifier.verify_attribute(guardian_core, 'elysia_loop', 'GuardianCore', critical=False)
    
    # Verify production readiness methods
    if hasattr(guardian_core, 'run_security_audit'):
        verifier.verify_method(guardian_core, 'run_security_audit', 'GuardianCore', critical=False)
    
    if hasattr(guardian_core, 'get_resource_status'):
        verifier.verify_method(guardian_core, 'get_resource_status', 'GuardianCore', critical=False)
    
    # Include any startup health issues as a synthetic check (warning or critical)
    health = getattr(guardian_core, "_startup_health", None)
    if health:
        passed = bool(health.get("passed", True))
        issues = health.get("issues", [])
        msg = "; ".join(str(i) for i in issues[:5]) if issues else "no issues"
        status = ComponentStatus.WARNING if passed else ComponentStatus.CRITICAL
        check = ComponentCheck(
            name="startup_health",
            status=status,
            message=msg,
            error=None,
            critical=not passed,
        )
        verifier.checks.append(check)

    # Operational state checks: deferred init, memory, vector, dashboard
    # Intentional deferred state -> WARNING (success_with_warnings), not failure
    if hasattr(guardian_core, "get_startup_operational_state"):
        try:
            op = guardian_core.get_startup_operational_state()
            defer_started = op.get("deferred_init_started", False)
            defer_running = op.get("deferred_init_running", False)
            defer_complete = op.get("deferred_init_complete", True)
            defer_failed = op.get("deferred_init_failed", False)
            defer_error = op.get("deferred_init_error") or ""
            defer_state = op.get("deferred_init_state", "not_started")
            mem_loaded = op.get("memory_loaded", True)
            vec_loaded = op.get("vector_loaded", True)
            vec_degraded = op.get("vector_degraded", False)
            vec_rebuild = op.get("vector_rebuild_pending", False)
            dash_ready = op.get("dashboard_ready", False)

            defer_mode = getattr(guardian_core, "_defer_heavy_startup", False)
            if defer_mode and defer_state == "inconsistent":
                verifier.checks.append(ComponentCheck(
                    name="deferred_init_inconsistent",
                    status=ComponentStatus.WARNING,
                    message="Deferred initialization state inconsistent (started but not running/complete/failed)",
                    critical=False,
                ))
            elif defer_mode and defer_failed:
                msg = f"Deferred initialization failed: {defer_error}" if defer_error else "Deferred initialization failed"
                verifier.checks.append(ComponentCheck(
                    name="deferred_init_failed",
                    status=ComponentStatus.WARNING,
                    message=msg,
                    critical=False,
                ))
            elif defer_mode and defer_running:
                verifier.checks.append(ComponentCheck(
                    name="deferred_init_running",
                    status=ComponentStatus.WARNING,
                    message="Deferred initialization still in progress",
                    critical=False,
                ))
            elif defer_mode and not defer_complete:
                verifier.checks.append(ComponentCheck(
                    name="deferred_init_pending",
                    status=ComponentStatus.WARNING,
                    message="Deferred initialization not yet started",
                    critical=False,
                ))
            if not mem_loaded and (defer_started or defer_mode):
                verifier.checks.append(ComponentCheck(
                    name="memory_not_loaded",
                    status=ComponentStatus.WARNING,
                    message="Memory history not yet loaded (deferred)",
                    critical=False,
                ))
            if not vec_loaded and (defer_started or defer_mode):
                verifier.checks.append(ComponentCheck(
                    name="vector_not_loaded",
                    status=ComponentStatus.WARNING,
                    message="Vector memory not yet loaded (deferred)",
                    critical=False,
                ))
            if vec_degraded:
                verifier.checks.append(ComponentCheck(
                    name="vector_degraded",
                    status=ComponentStatus.WARNING,
                    message="Vector memory degraded",
                    critical=False,
                ))
            if vec_rebuild:
                verifier.checks.append(ComponentCheck(
                    name="vector_rebuild_pending",
                    status=ComponentStatus.WARNING,
                    message="Vector memory rebuild pending",
                    critical=False,
                ))
            ui_expected = getattr(guardian_core, "ui_panel", None) is not None
            if ui_expected and not dash_ready:
                verifier.checks.append(ComponentCheck(
                    name="dashboard_not_ready",
                    status=ComponentStatus.WARNING,
                    message="Dashboard not yet ready",
                    critical=False,
                ))
        except Exception as e:
            logger.debug("Operational state check failed: %s", e)

    # Log summary
    verifier.log_summary()
    
    return verifier.get_summary()

