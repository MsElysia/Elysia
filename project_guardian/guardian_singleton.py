"""
GuardianCore Singleton Module
==============================
Provides a singleton pattern for GuardianCore to prevent double initialization.
"""

import threading
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Global singleton instance
_guardian_core_instance: Optional[Any] = None
_guardian_core_lock = threading.Lock()
_monitoring_started = False
_monitoring_lock = threading.Lock()


def _guardian_core_class():
    """Resolve GuardianCore whether loaded as a package submodule or with project_guardian/ on sys.path."""
    try:
        from .core import GuardianCore
    except ImportError:
        try:
            from project_guardian.core import GuardianCore
        except ImportError:
            from core import GuardianCore
    return GuardianCore


def get_guardian_core(
    config: Optional[Dict[str, Any]] = None,
    control_path: Optional[Path] = None,
    tasks_dir: Optional[Path] = None,
    mutations_dir: Optional[Path] = None,
    force_new: bool = False
) -> Optional[Any]:
    """
    Get or create the GuardianCore singleton instance.
    
    Args:
        config: Configuration dictionary (only used if creating new instance)
        control_path: Optional path to CONTROL.md (only used if creating new instance)
        tasks_dir: Optional path to TASKS directory (only used if creating new instance)
        mutations_dir: Optional path to MUTATIONS directory (only used if creating new instance)
        force_new: If True, create a new instance even if one exists (for testing only)
    
    Returns:
        GuardianCore instance, or None if initialization fails
    """
    global _guardian_core_instance
    
    with _guardian_core_lock:
        if _guardian_core_instance is not None and not force_new:
            logger.debug("Returning existing GuardianCore instance")
            return _guardian_core_instance
        
        GuardianCore = _guardian_core_class()

        try:
            if force_new:
                logger.warning("Creating new GuardianCore instance (force_new=True)")
                # For testing, allow multiple instances
                instance = GuardianCore(
                    config=config or {},
                    control_path=control_path,
                    tasks_dir=tasks_dir,
                    mutations_dir=mutations_dir,
                    allow_multiple=True
                )
            else:
                logger.info("Creating GuardianCore singleton instance")
                instance = GuardianCore(
                    config=config or {},
                    control_path=control_path,
                    tasks_dir=tasks_dir,
                    mutations_dir=mutations_dir,
                    allow_multiple=False
                )
                _guardian_core_instance = instance
            
            return instance

        except RuntimeError as e:
            if "already exists" in str(e):
                logger.warning(f"GuardianCore already initialized: {e}")
                # Try to get existing instance if possible
                if _guardian_core_instance is not None:
                    return _guardian_core_instance
            logger.error(f"Failed to create GuardianCore: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating GuardianCore: {e}")
            return None


def reset_singleton() -> None:
    """
    Reset the singleton instance (for testing only).
    """
    global _guardian_core_instance, _monitoring_started
    
    with _guardian_core_lock:
        if _guardian_core_instance is not None:
            # Try to stop monitoring if it was started
            try:
                if hasattr(_guardian_core_instance, 'monitor') and _guardian_core_instance.monitor:
                    if hasattr(_guardian_core_instance.monitor, 'stop'):
                        _guardian_core_instance.monitor.stop()
            except Exception:
                pass
            
            # Reset class-level flag in GuardianCore
            _guardian_core_class()._any_instance_initialized = False
        
        _guardian_core_instance = None

    with _monitoring_lock:
        _monitoring_started = False

    logger.info("GuardianCore singleton reset")


def ensure_monitoring_started(guardian_core: Any) -> bool:
    """
    Ensure monitoring/heartbeat is started exactly once.
    
    Args:
        guardian_core: GuardianCore instance
    
    Returns:
        True if monitoring was started (or already running), False on error
    """
    global _monitoring_started
    
    with _monitoring_lock:
        if _monitoring_started:
            logger.debug("Monitoring already started, skipping")
            return True
        
        try:
            # Start monitoring if available
            if hasattr(guardian_core, 'monitor') and guardian_core.monitor:
                # SystemMonitor uses start_monitoring() method
                if hasattr(guardian_core.monitor, 'start_monitoring'):
                    guardian_core.monitor.start_monitoring()
                    logger.info("Monitoring started via singleton guard")
                    _monitoring_started = True
                    if hasattr(guardian_core, 'prompt_evolution_scheduler') and guardian_core.prompt_evolution_scheduler:
                        guardian_core.prompt_evolution_scheduler.start()
                    return True
                elif hasattr(guardian_core.monitor, 'start'):
                    # Fallback for other monitor types
                    guardian_core.monitor.start()
                    logger.info("Monitoring started via singleton guard (fallback)")
                    _monitoring_started = True
                    if hasattr(guardian_core, 'prompt_evolution_scheduler') and guardian_core.prompt_evolution_scheduler:
                        guardian_core.prompt_evolution_scheduler.start()
                    return True
            
            # Also check for heartbeat in elysia_loop
            if hasattr(guardian_core, 'elysia_loop') and guardian_core.elysia_loop:
                if hasattr(guardian_core.elysia_loop, 'start'):
                    # Check if already running
                    if hasattr(guardian_core.elysia_loop, '_running'):
                        if guardian_core.elysia_loop._running:
                            logger.debug("ElysiaLoop already running")
                            _monitoring_started = True
                            return True
                    guardian_core.elysia_loop.start()
                    logger.info("ElysiaLoop started via singleton guard")
                    _monitoring_started = True
                    # Start automatic prompt evolution if available
                    if hasattr(guardian_core, 'prompt_evolution_scheduler') and guardian_core.prompt_evolution_scheduler:
                        guardian_core.prompt_evolution_scheduler.start()
                    return True
            
            logger.warning("No monitoring/loop found to start")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")
            return False
