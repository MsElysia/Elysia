# project_guardian/monitoring.py
# Monitoring and Health Systems for Project Guardian

import time
import threading
import traceback
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from .memory import MemoryCore

logger = logging.getLogger(__name__)

# Cleanup reasons - passed into cleanup path and logged
CLEANUP_REASON_MEMORY_COUNT_THRESHOLD = "memory_count_threshold"
CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE = "system_memory_pressure"
CLEANUP_REASON_MANUAL = "manual"
CLEANUP_REASON_VECTOR_REBUILD_RECOVERY = "vector_rebuild_recovery"

# Single terminal outcome per attempt - one of these per cleanup call
CLEANUP_OUTCOME_SKIPPED_COOLDOWN = "skipped_cooldown"
CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD = "skipped_below_threshold"
CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA = "skipped_small_delta"
CLEANUP_OUTCOME_SKIPPED_QUIET_ZONE = "skipped_quiet_zone"
CLEANUP_OUTCOME_PARTIAL_RECLAIM = "partial_reclaim"
CLEANUP_OUTCOME_CONSOLIDATED = "consolidated"
CLEANUP_OUTCOME_FAILED = "failed"

# Pressure no-op backoff: after this many consecutive no-ops, skip pressure cleanups
_PRESSURE_NO_OP_COUNT_BEFORE_COOLDOWN = 3
_PRESSURE_NO_OP_COOLDOWN_MINUTES = 10

# When system RAM is critically high (>= 85%), run consolidation even if guardian count
# is below normal consolidation_threshold - use this min so we actually free process memory
_PRESSURE_CONSOLIDATION_MIN_COUNT = 1000
# Under critical pressure, allow a lower emergency floor for low-count sessions to avoid
# repeated no-op skips when count is well below normal pressure trim target.
_PRESSURE_EMERGENCY_MIN_COUNT = 100

# Headroom when trimming: trim to (threshold - headroom) to avoid treadmill (beat adds 1, cleanup removes 1)
_CLEANUP_HEADROOM = 300

# Minimum memories that would be removed before we run consolidation. Avoids thrash (1754->1750, 1755->1750).
# Only consolidate when memory_count > trim_target + MIN_TRIM_DELTA.
MIN_TRIM_DELTA = 25

# memory_cleanup_threshold: config-driven (config.get("memory_cleanup_threshold", 3500)).


def _load_memory_pressure_config() -> Dict[str, Any]:
    """Load config/memory_pressure.json for pressure-loop knobs."""
    cfg_path = Path(__file__).parent.parent / "config" / "memory_pressure.json"
    if cfg_path.exists():
        try:
            import json
            with open(cfg_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "pressure_trim_target": 1600,
        "memory_pressure_trigger_fraction": 1.0,
        "vector_embed_batch_every": 5,
        "bad_learning_streak_cooldown_multiplier": 3.0,
        "pressure_emergency_min_count": _PRESSURE_EMERGENCY_MIN_COUNT,
        "skipped_small_delta_force_after": 4,
        "memory_search_no_novelty_block_cycles": 2,
        "stagnation_force_non_memory_after_cycles": 3,
        "low_value_write_reject_priority_below": 0.25,
        "low_value_write_reject_when_count_above": 1600,
        "bad_learning_session_cooldown_minutes": 90,
        "embedding_fallback_log_level": "warning",
    }
# Logs showing threshold=2800 mean it is set in config (e.g. config/*.json or passed at init).
# Default 3500; adjust per deployment based on typical memory counts and host RAM.

class Heartbeat:
    """
    System health monitoring and liveness detection for Project Guardian.
    Provides periodic health checks and system monitoring.
    """
    
    def __init__(self, memory: MemoryCore, interval: int = 30, system_monitor=None):
        self.memory = memory
        self.interval = interval
        self.running = False
        self.thread = None
        self.health_metrics = {}
        self.system_monitor = system_monitor  # Reference to SystemMonitor for cleanup methods
        # Hysteresis state for auto-cleanup (high/low watermarks)
        self._cleanup_active = False
        self._high_water = None
        self._low_water = None
        # Autonomy: run guardian's autonomous cycle at config interval
        self._last_autonomy_run = None
        
    def start(self) -> None:
        """Start the heartbeat monitoring."""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._beat, daemon=True)
        self.thread.start()
        
        # Queue memory write if cleanup in progress, otherwise write directly
        if self.system_monitor:
            self.system_monitor._queue_or_write_memory(
                f"[Heartbeat] Started monitoring (interval: {self.interval}s)",
                category="monitoring",
                priority=0.7
            )
        else:
            self.memory.remember(
                f"[Heartbeat] Started monitoring (interval: {self.interval}s)",
                category="monitoring",
                priority=0.7
            )
        
    def stop(self) -> None:
        """Stop the heartbeat monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        
        # Queue memory write if cleanup in progress, otherwise write directly
        if self.system_monitor:
            self.system_monitor._queue_or_write_memory(
                "[Heartbeat] Stopped monitoring",
                category="monitoring",
                priority=0.6
            )
        else:
            self.memory.remember(
                "[Heartbeat] Stopped monitoring",
                category="monitoring",
                priority=0.6
            )
        
    def _beat(self) -> None:
        """Main heartbeat loop."""
        while self.running:
            try:
                # Queue memory write if cleanup in progress, otherwise write directly
                if self.system_monitor:
                    self.system_monitor._queue_or_write_memory(
                        "[Heartbeat] Pulse",
                        category="monitoring",
                        priority=0.3
                    )
                else:
                    self.memory.remember(
                        "[Heartbeat] Pulse",
                        category="monitoring",
                        priority=0.3
                    )
                
                # Update health metrics
                self._update_health_metrics()

                mem = self.memory
                guardian = getattr(self.system_monitor, "guardian", None) if self.system_monitor else None

                # Event-driven adversarial: repeated error detection
                try:
                    if guardian and hasattr(mem, "get_recent_memories"):
                        errs = mem.get_recent_memories(limit=20, category="error", load_if_needed=True)
                        seen = {}
                        for e in errs:
                            p = (e.get("thought") or "")[:60]
                            seen[p] = seen.get(p, 0) + 1
                        if any(c >= 2 for c in seen.values()):
                            from .adversarial_self_learning import trigger_adversarial_on_event
                            from .adversarial_self_learning import TRIGGER_REPEATED_ERROR
                            trigger_adversarial_on_event(guardian, TRIGGER_REPEATED_ERROR, {})
                except Exception as re:
                    logger.debug("Adversarial error trigger: %s", re)
                if hasattr(mem, "get_memory_state"):
                    st = mem.get_memory_state(load_if_needed=False)
                    authoritative = st.get("memory_count_authoritative", False)
                    defer_pending = (
                        guardian
                        and getattr(guardian, "_defer_heavy_startup", False)
                        and not getattr(guardian, "deferred_init_complete", True)
                    )
                    if authoritative:
                        memory_count = st.get("memory_count")
                    elif defer_pending:
                        memory_count = None
                    else:
                        memory_count = mem.get_memory_count(load_if_needed=True)
                elif hasattr(mem, "get_memory_state"):
                    memory_count = mem.get_memory_state(load_if_needed=True).get("memory_count")
                else:
                    memory_count = None
                if memory_count is not None:
                    logger.debug(f"[Heartbeat] Tick - {memory_count} memories (authoritative)")
                else:
                    logger.debug(
                        "[Heartbeat] Tick - JSON memory not loaded yet (deferred); "
                        "skipping count-based cleanup threshold until loaded"
                    )
                
                # Auto-cleanup if memory count is high (runs every heartbeat if needed)
                # Base threshold (high watermark) before hysteresis
                base_threshold = 4000
                
                # Also check system memory usage if psutil available
                system_memory_high = False
                try:
                    import psutil
                    sys_mem = psutil.virtual_memory()
                    if sys_mem.percent > 70:  # System memory over 70%
                        system_memory_high = True
                        # Use even lower base threshold if system memory is high
                        base_threshold = 3000
                except (AttributeError, ImportError, RuntimeError):
                    # psutil not available or error accessing memory info - use defaults
                    pass
                
                # Initialize hysteresis bounds if needed
                if self._high_water is None or self._low_water is None:
                    self._high_water = base_threshold
                    # Low watermark at 80% of high watermark (avoid cleanup thrash around edge)
                    self._low_water = int(base_threshold * 0.8)
                
                # Only run full cleanup when we have memories to trim or system pressure.
                # Use high/low watermarks so we don't thrash around the edge.
                # Unknown count (lazy, deferred) must not be treated as 0 — skip count trigger.
                if memory_count is None:
                    needs_full_cleanup = False
                elif self._cleanup_active:
                    # Once cleanup has started, keep going until we are safely below low watermark
                    needs_full_cleanup = memory_count > self._low_water
                else:
                    needs_full_cleanup = memory_count > self._high_water
                system_only_pressure = system_memory_high and not needs_full_cleanup

                if needs_full_cleanup:
                    self._cleanup_active = True
                    if self.system_monitor:
                        self.system_monitor._perform_cleanup(
                            self._high_water,
                            reason=CLEANUP_REASON_MEMORY_COUNT_THRESHOLD,
                        )
                    else:
                        logger.warning(f"[Auto-Cleanup] High memory ({memory_count} memories), triggering cleanup...")
                        try:
                            memory_obj = self.memory
                            if hasattr(self.memory, "json_memory"):
                                memory_obj = self.memory.json_memory
                            if hasattr(memory_obj, "consolidate"):
                                memory_obj.consolidate(max_memories=self._high_water, keep_recent_days=30)
                            import gc
                            gc.collect()
                        except Exception as e:
                            logger.error(f"[Auto-Cleanup] Failed: {e}")
                elif system_only_pressure:
                    if self.system_monitor:
                        self.system_monitor._perform_light_cleanup()
                    else:
                        import gc
                        gc.collect()
                else:
                    # No cleanup needed this beat; if we're comfortably below low watermark, reset state
                    if self._cleanup_active and memory_count <= self._low_water:
                        self._cleanup_active = False

                # Event-driven adversarial: vector degraded / rebuild pending
                try:
                    if guardian and hasattr(guardian, "get_startup_operational_state"):
                        op = guardian.get_startup_operational_state()
                        if op.get("vector_degraded") or op.get("vector_rebuild_pending"):
                            from .adversarial_self_learning import trigger_adversarial_on_event
                            from .adversarial_self_learning import TRIGGER_VECTOR_DEGRADED
                            trigger_adversarial_on_event(
                                guardian,
                                TRIGGER_VECTOR_DEGRADED,
                                {"vector_degraded": op.get("vector_degraded"), "vector_rebuild_pending": op.get("vector_rebuild_pending")},
                            )
                except Exception as ve:
                    logger.debug("Adversarial vector trigger: %s", ve)

                # Autonomy: let Elysia run her own modules/agents (learning, dream, prompt evolution)
                if self.system_monitor:
                    guardian = getattr(self.system_monitor, "guardian", None)
                    if guardian and hasattr(guardian, "run_autonomous_cycle") and hasattr(guardian, "_load_autonomy_config"):
                        try:
                            cfg = guardian._load_autonomy_config()
                            if cfg.get("enabled"):
                                interval = max(30, cfg.get("interval_seconds", 120))
                                now_ts = time.time()
                                last = self._last_autonomy_run
                                if last is None or (now_ts - last) >= interval:
                                    guardian.run_autonomous_cycle()
                                    self._last_autonomy_run = now_ts
                        except Exception as e:
                            logger.debug("Autonomy cycle: %s", e)

                time.sleep(self.interval)
                
            except Exception as e:
                # Check if cleanup is in progress - suppress memory writes during cleanup
                # Queue memory write if cleanup in progress, otherwise write directly
                if self.system_monitor:
                    self.system_monitor._queue_or_write_memory(
                        f"[Heartbeat] Error: {str(e)}",
                        category="error",
                        priority=0.8
                    )
                else:
                    self.memory.remember(
                        f"[Heartbeat] Error: {str(e)}",
                        category="error",
                        priority=0.8
                    )
                time.sleep(self.interval)
                
    def _update_health_metrics(self) -> None:
        """Update system health metrics. Bounded (no dump_all)."""
        total_memories = 0
        if hasattr(self.memory, "get_memory_count"):
            total_memories = self.memory.get_memory_count(load_if_needed=True) or 0
        recent = []
        if hasattr(self.memory, "get_recent_memories"):
            recent = self.memory.get_recent_memories(limit=50, load_if_needed=True)
        recent_high_priority = len([m for m in recent[-10:] if m.get("priority", 0.5) > 0.7])
        error_count = len([m for m in recent if m.get("category") == "error"])
        
        self.health_metrics = {
            "timestamp": time.time(),
            "total_memories": total_memories,
            "recent_high_priority": recent_high_priority,
            "recent_errors": error_count,
            "memory_growth_rate": self._calculate_growth_rate(),
            "system_health": "healthy" if error_count < 3 else "warning"
        }
        
    def _calculate_growth_rate(self) -> float:
        """Calculate memory growth rate. Bounded (no dump_all)."""
        recent = []
        if hasattr(self.memory, "get_recent_memories"):
            recent = self.memory.get_recent_memories(limit=10, load_if_needed=True)
        if len(recent) < 10:
            return 0.0
        recent_memories = recent
        if not recent_memories:
            return 0.0
            
        try:
            first_time = time.time() - (self.interval * 10)  # Approximate
            growth_rate = len(recent_memories) / (self.interval / 3600)  # Per hour
            return growth_rate
        except (ZeroDivisionError, AttributeError, TypeError):
            # Division by zero or missing attributes - return safe default
            return 0.0
    
            
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get current health metrics."""
        return self.health_metrics.copy()
        
    def is_healthy(self) -> bool:
        """Check if system is healthy."""
        return self.health_metrics.get("system_health", "unknown") == "healthy"

class ErrorTrap:
    """
    Comprehensive error handling and logging for Project Guardian.
    Provides exception wrapping and error recovery.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        self.error_count = 0
        self.recent_errors = []
        
    def wrap(self, func: Callable) -> Callable:
        """
        Wrap a function with error handling.
        
        Args:
            func: Function to wrap
            
        Returns:
            Wrapped function
        """
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self._handle_error(e, func.__name__, args, kwargs)
                return None
        return wrapped
        
    def _handle_error(self, error: Exception, func_name: str, args: tuple, kwargs: dict) -> None:
        """
        Handle an error with comprehensive logging.
        
        Args:
            error: The exception that occurred
            func_name: Name of the function that failed
            args: Function arguments
            kwargs: Function keyword arguments
        """
        self.error_count += 1
        
        # Get traceback
        tb = traceback.format_exc()
        
        # Log error details
        error_entry = {
            "timestamp": time.time(),
            "function": func_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": tb,
            "args": str(args)[:200],  # Truncate long args
            "kwargs": str(kwargs)[:200]  # Truncate long kwargs
        }
        
        self.recent_errors.append(error_entry)
        
        # Keep only recent errors
        if len(self.recent_errors) > 10:
            self.recent_errors = self.recent_errors[-10:]
            
        # Log to memory
        self.memory.remember(
            f"[Error] {func_name}: {type(error).__name__} - {str(error)}",
            category="error",
            priority=0.9
        )
        
        self.memory.remember(
            f"[ErrorTrace] {tb[:500]}...",
            category="error",
            priority=0.8
        )
        
        logger.error(f"[ErrorTrap] {func_name}: {error}\n{tb}")
        
    def get_error_stats(self) -> Dict[str, Any]:
        """
        Get error statistics.
        
        Returns:
            Error statistics dictionary
        """
        error_memories = self.memory.get_memories_by_category("error")
        
        return {
            "total_errors": self.error_count,
            "recent_errors": len(self.recent_errors),
            "error_memories": len(error_memories),
            "last_error": self.recent_errors[-1] if self.recent_errors else None,
            "error_rate": self.error_count / max(
                1,
                (self.memory.get_memory_count(load_if_needed=True) or 1)
                if hasattr(self.memory, "get_memory_count")
                else (self.memory.get_memory_state(load_if_needed=True).get("memory_count") or 1)
                if hasattr(self.memory, "get_memory_state")
                else 1,
            ),
        }
        
    def clear_errors(self) -> None:
        """Clear recent error history."""
        self.recent_errors.clear()
        self.memory.remember(
            "[ErrorTrap] Error history cleared",
            category="monitoring",
            priority=0.5
        )

class SystemMonitor:
    """
    Comprehensive system monitoring for Project Guardian.
    Integrates heartbeat and error monitoring.
    """
    
    def __init__(self, memory: MemoryCore, guardian_core):
        self.memory = memory
        self.guardian = guardian_core
        self.heartbeat = Heartbeat(memory, system_monitor=self)  # Pass self reference for cleanup methods
        self.error_trap = ErrorTrap(memory)
        self.monitoring_active = False
        self._started = False  # Internal flag for idempotency
        self._cleanup_in_progress = False  # Re-entrancy guard for cleanup
        self._cleanup_id_counter = 0  # Unique ID for each cleanup cycle
        self._pending_memory_writes = []  # Queue for memory writes during cleanup
        self._pending_writes_lock = threading.Lock()  # Thread-safe queue access
        # Pressure no-op backoff: avoid repeated no-op cleanups when system RAM high but count low
        self._pressure_no_op_count = 0
        self._pressure_no_op_cooldown_until: Optional[float] = None
        # After N consecutive skipped_small_delta under pressure, force cleanup
        self._pressure_skipped_small_delta_count = 0
        # Post-cleanup quiet zone: suppress repeat cleanup checks briefly after consolidating to trim_target
        self._post_cleanup_quiet_until: Optional[float] = None
        
    def start_monitoring(self) -> None:
        """Start system monitoring (idempotent - won't start if already running)."""
        if self._started:
            logger.debug("Monitoring already started, skipping")
            return
        
        self.heartbeat.start()
        self.monitoring_active = True
        self._started = True

        # Auto-activate: run one autonomy cycle after a short delay so Elysia activates her own modules/agents
        def _run_first_autonomy():
            try:
                time.sleep(15)
                if not self.monitoring_active:
                    return
                g = getattr(self, "guardian", None)
                if g and hasattr(g, "run_autonomous_cycle"):
                    try:
                        cfg = g._load_autonomy_config()
                        if cfg.get("enabled"):
                            g.run_autonomous_cycle()
                            logger.info("[SystemMonitor] First autonomy cycle completed (modules/agents auto-activated)")
                            # Run adversarial self-learning after startup stabilization
                            try:
                                from .adversarial_self_learning import run_adversarial_cycle
                                run_adversarial_cycle(g)
                                logger.info("[SystemMonitor] Post-startup adversarial self-learning completed")
                            except Exception as ae:
                                logger.debug("Post-startup adversarial: %s", ae)
                    except Exception as e:
                        logger.debug("First autonomy cycle: %s", e)
            except Exception as e:
                logger.debug("First autonomy delay: %s", e)
        threading.Thread(target=_run_first_autonomy, daemon=True).start()
        
        # Queue memory write if cleanup in progress, otherwise write directly
        self._queue_or_write_memory(
            "[SystemMonitor] Monitoring started",
            category="monitoring",
            priority=0.8
        )
        
    def stop_monitoring(self) -> None:
        """Stop system monitoring."""
        self.heartbeat.stop()
        self.monitoring_active = False
        self._started = False
        
        # Queue memory write if cleanup in progress, otherwise write directly
        self._queue_or_write_memory(
            "[SystemMonitor] Monitoring stopped",
            category="monitoring",
            priority=0.8
        )
        
    def get_system_health(self) -> Dict[str, Any]:
        """
        Get comprehensive system health report.
        
        Returns:
            System health report
        """
        heartbeat_metrics = self.heartbeat.get_health_metrics()
        error_stats = self.error_trap.get_error_stats()
        
        # Avoid circular dependency - don't call get_system_status() from here
        # Calculate overall health score based on available metrics
        health_score = 1.0
        
        # Deduct for errors
        if error_stats["recent_errors"] > 0:
            health_score -= min(0.3, error_stats["recent_errors"] * 0.1)
            
        # Deduct for high memory usage
        if heartbeat_metrics.get("total_memories", 0) > 1000:
            health_score -= 0.1
            
        health_score = max(0.0, health_score)
        
        return {
            "timestamp": time.time(),
            "health_score": health_score,
            "status": "healthy" if health_score > 0.7 else "warning" if health_score > 0.4 else "critical",
            "heartbeat": heartbeat_metrics,
            "errors": error_stats,
            "monitoring_active": self.monitoring_active
        }
        
    def get_health_summary(self) -> str:
        """
        Get a human-readable health summary.
        
        Returns:
            Health summary string
        """
        health = self.get_system_health()
        
        summary = f"[System Health] Status: {health['status'].upper()}\n"
        summary += f"  Health Score: {health['health_score']:.2f}\n"
        summary += f"  Memory Count: {health['heartbeat']['total_memories']}\n"
        summary += f"  Recent Errors: {health['errors']['recent_errors']}\n"
        if 'guardian_status' in health and 'trust' in health['guardian_status']:
            summary += f"  Trust Level: {health['guardian_status']['trust']['average_trust']:.2f}\n"
        summary += f"  Monitoring: {'Active' if health['monitoring_active'] else 'Inactive'}"
        
        return summary
    
    def _queue_or_write_memory(self, thought: str, category: str = "general", priority: float = 0.5, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Queue memory write during cleanup, or write directly if cleanup not in progress.
        
        This ensures no memory writes are lost during cleanup cycles.
        
        Args:
            thought: Memory content
            category: Memory category
            priority: Priority level
            metadata: Optional metadata
        """
        if self._cleanup_in_progress:
            # Queue the write for processing after cleanup
            with self._pending_writes_lock:
                self._pending_memory_writes.append({
                    "thought": thought,
                    "category": category,
                    "priority": priority,
                    "metadata": metadata or {}
                })
            logger.debug(f"[MemoryQueue] Queued memory write during cleanup: {thought[:50]}...")
        else:
            # Write directly if cleanup not in progress
            self.memory.remember(thought, category=category, priority=priority, metadata=metadata)
    
    def _process_pending_memory_writes(self) -> int:
        """
        Process all pending memory writes queued during cleanup.
        
        Returns:
            Number of writes processed
        """
        with self._pending_writes_lock:
            if not self._pending_memory_writes:
                return 0
            
            count = len(self._pending_memory_writes)
            logger.info(f"[MemoryQueue] Processing {count} queued memory writes after cleanup")
            
            # Process all queued writes
            for write in self._pending_memory_writes:
                try:
                    self.memory.remember(
                        write["thought"],
                        category=write["category"],
                        priority=write["priority"],
                        metadata=write.get("metadata")
                    )
                except Exception as e:
                    logger.error(f"[MemoryQueue] Failed to process queued write: {e}")
            
            # Clear the queue
            self._pending_memory_writes.clear()
            logger.info(f"[MemoryQueue] Processed {count} memory writes successfully")
            return count
    
    def _get_cleanup_metrics(self) -> Dict[str, Any]:
        """Get metrics for cleanup logging (single source of truth)."""
        # Get the underlying memory object
        memory_obj = self.memory
        if hasattr(self.memory, 'json_memory'):
            memory_obj = self.memory.json_memory
        if hasattr(memory_obj, "get_memory_count"):
            cnt = memory_obj.get_memory_count(load_if_needed=True)
        elif hasattr(memory_obj, "get_memory_state"):
            cnt = memory_obj.get_memory_state(load_if_needed=True).get("memory_count")
        else:
            cnt = None
        metrics = {
            "memory_count": cnt if cnt is not None else 0,
            "memory_count_authoritative": cnt is not None,
            "cache_sizes": {}
        }
        
        # Get RSS if available (capture as raw bytes)
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            rss_bytes = process.memory_info().rss
            metrics["rss_bytes"] = rss_bytes  # Store raw bytes
            metrics["rss_mb"] = round(rss_bytes / (1024 * 1024), 2)  # Also store MB for convenience
        except (AttributeError, ImportError, RuntimeError):
            # psutil not available or error accessing process info - use None
            metrics["rss_bytes"] = None
            metrics["rss_mb"] = None
        
        # Get cache sizes
        # Check for embedding cache
        if hasattr(memory_obj, 'vector_search') and memory_obj.vector_search:
            if hasattr(memory_obj.vector_search, 'embedding_cache'):
                metrics["cache_sizes"]["embedding_cache"] = len(memory_obj.vector_search.embedding_cache)
        
        # Check for web cache (if exists)
        if self.guardian and hasattr(self.guardian, 'web_reader') and self.guardian.web_reader:
            if hasattr(self.guardian.web_reader, '_cache'):
                metrics["cache_sizes"]["web_cache"] = len(self.guardian.web_reader._cache) if hasattr(self.guardian.web_reader._cache, '__len__') else 'N/A'
        
        # Check for proposal cache (if exists)
        if self.guardian and hasattr(self.guardian, 'proposal_system') and self.guardian.proposal_system:
            if hasattr(self.guardian.proposal_system, '_cache'):
                metrics["cache_sizes"]["proposal_cache"] = len(self.guardian.proposal_system._cache) if hasattr(self.guardian.proposal_system._cache, '__len__') else 'N/A'
        
        return metrics
    
    def _clear_caches(self, memory_obj) -> Dict[str, int]:
        """
        Clear in-memory caches to free memory.
        
        Returns:
            Dictionary of cleared cache sizes
        """
        cleared = {}
        
        # Clear embedding cache
        if hasattr(memory_obj, 'vector_search') and memory_obj.vector_search:
            if hasattr(memory_obj.vector_search, 'embedding_cache'):
                cache_size = len(memory_obj.vector_search.embedding_cache)
                memory_obj.vector_search.embedding_cache.clear()
                cleared["embedding_cache"] = cache_size
        
        # Clear web cache if available
        if self.guardian and hasattr(self.guardian, 'web_reader') and self.guardian.web_reader:
            if hasattr(self.guardian.web_reader, '_cache'):
                try:
                    cache_size = len(self.guardian.web_reader._cache) if hasattr(self.guardian.web_reader._cache, '__len__') else 0
                    self.guardian.web_reader._cache.clear()
                    cleared["web_cache"] = cache_size
                except:
                    pass
        
        # Clear proposal cache if available
        if self.guardian and hasattr(self.guardian, 'proposal_system') and self.guardian.proposal_system:
            if hasattr(self.guardian.proposal_system, '_cache'):
                try:
                    cache_size = len(self.guardian.proposal_system._cache) if hasattr(self.guardian.proposal_system._cache, '__len__') else 0
                    self.guardian.proposal_system._cache.clear()
                    cleared["proposal_cache"] = cache_size
                except:
                    pass
        
        # Try to clear PyTorch CUDA cache if available
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                cleared["torch_cuda_cache"] = 1  # Flag that it was cleared
        except:
            pass
        
        # Try to clear NumPy cache if applicable
        try:
            import numpy as np
            # NumPy doesn't have a global cache, but we can try to free memory
            # This is mostly a no-op but documents intent
            pass
        except:
            pass
        
        return cleared
    
    def _format_rss_change(self, rss_before_bytes: Optional[int], rss_after_bytes: Optional[int]) -> Optional[str]:
        """
        Format RSS change for logging.
        
        Args:
            rss_before_bytes: RSS before cleanup in bytes (None if unavailable)
            rss_after_bytes: RSS after cleanup in bytes (None if unavailable)
        
        Returns:
            Formatted string like "(delta: +X.XXMB)" or "(delta: -X.XXMB)", or None if unavailable
        """
        if rss_before_bytes is None or rss_after_bytes is None:
            return None
        
        # Calculate delta in bytes
        delta_bytes = rss_after_bytes - rss_before_bytes
        
        # Convert to MB
        delta_mb = delta_bytes / (1024 * 1024)
        
        # Format with correct sign (+ if increased, - if decreased)
        sign = "+" if delta_mb >= 0 else ""
        return f"(delta: {sign}{delta_mb:.2f}MB)"
    
    def _perform_light_cleanup(self) -> None:
        """Light cleanup when system memory high but our memory count is OK. Clears caches + gc only."""
        try:
            memory_obj = self.memory
            if hasattr(self.memory, "json_memory"):
                memory_obj = self.memory.json_memory
            cleared = self._clear_caches(memory_obj)
            if cleared:
                import gc
                gc.collect()
                logger.debug(f"[Auto-Cleanup] Light cleanup: cleared caches {list(cleared.keys())}")
        except Exception as e:
            logger.debug(f"[Auto-Cleanup] Light cleanup failed: {e}")

    def _perform_cleanup(
        self,
        memory_threshold: int,
        reason: str = CLEANUP_REASON_MEMORY_COUNT_THRESHOLD,
        system_memory_percent: Optional[float] = None,
        consolidation_threshold: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Perform cleanup with full instrumentation and truth guarantees.
        
        reason: Why cleanup was triggered (memory_count_threshold, system_memory_pressure, manual, etc.)
        system_memory_percent: Host RAM usage 0.0-1.0 when reason=system_memory_pressure
        consolidation_threshold: Count above which consolidation runs (from config). When reason=pressure
            and count <= this, we skip consolidation and do light reclaim only.
        
        Returns structured result: attempted, action_taken, no_op_reason, memory_before/after, etc.
        """
        # Re-entrancy guard - must check before any state change
        if self._cleanup_in_progress:
            early_result = {
                "cleanup_id": 0,
                "reason": reason,
                "outcome": CLEANUP_OUTCOME_FAILED,
                "attempted": False,
                "action_taken": False,
                "no_op_reason": "cleanup_already_in_progress",
                "cooldown_active": False,
                "memory_before": None,
                "memory_after": None,
                "rss_before_mb": None,
                "rss_after_mb": None,
                "error": None,
            }
            logger.warning("[Auto-Cleanup] Cleanup already in progress, skipping duplicate call")
            return early_result
        
        self._cleanup_in_progress = True
        self._cleanup_id_counter += 1
        cleanup_id = self._cleanup_id_counter
        
        result: Dict[str, Any] = {
            "cleanup_id": cleanup_id,
            "reason": reason,
            "outcome": None,
            "attempted": False,
            "action_taken": False,
            "no_op_reason": None,
            "cleanup_path": None,  # which strategy branch was used (e.g. pressure_emergency_cleanup)
            "cooldown_active": False,
            "memory_before": None,
            "memory_after": None,
            "rss_before_mb": None,
            "rss_after_mb": None,
            "gc_ran": False,
            "caches_cleared": False,
            "vector_rebuild_status": "not_applicable",
            "error": None,
            "trim_policy": None,  # trigger_threshold, trim_target, min_trim_delta, source
        }
        
        def _log_terminal(outcome: str, msg: str, level: str = "info") -> None:
            """Single terminal log per attempt."""
            result["outcome"] = outcome
            if level == "warning":
                logger.warning(msg)
            else:
                logger.info(msg)
        
        try:
            memory_obj = self.memory
            if hasattr(self.memory, 'json_memory'):
                memory_obj = self.memory.json_memory
            
            metrics_before = self._get_cleanup_metrics()
            memory_count_before = metrics_before["memory_count"]
            rss_before_mb = metrics_before.get("rss_mb")
            result["memory_before"] = memory_count_before
            result["rss_before_mb"] = rss_before_mb
            
            consol_thresh = consolidation_threshold if consolidation_threshold is not None else memory_threshold
            
            # Pressure path: check cooldown first (affects this attempt only; set by prior attempts)
            if reason == CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE:
                now = time.time()
                cooldown_active = (
                    self._pressure_no_op_cooldown_until is not None
                    and now < self._pressure_no_op_cooldown_until
                )
                if cooldown_active:
                    result["cooldown_active"] = True
                    result["attempted"] = True
                    _log_terminal(
                        CLEANUP_OUTCOME_SKIPPED_COOLDOWN,
                        f"[Auto-Cleanup #{cleanup_id}] Skipped: reason={reason}, "
                        f"outcome={CLEANUP_OUTCOME_SKIPPED_COOLDOWN}, cooldown_active=True",
                        "warning",
                    )
                    return result

                # Post-cleanup quiet zone: suppress repeat checks when count near trim_target
                pressure_cfg = _load_memory_pressure_config()
                trim_target = memory_threshold
                quiet_min = pressure_cfg.get("post_cleanup_quiet_minutes", 5)
                quiet_margin = pressure_cfg.get("post_cleanup_quiet_margin", 50)
                in_quiet_zone = (
                    self._post_cleanup_quiet_until is not None
                    and now < self._post_cleanup_quiet_until
                )
                count_near_target = (
                    memory_count_before is not None
                    and memory_count_before <= trim_target + quiet_margin
                )
                if in_quiet_zone and count_near_target:
                    result["attempted"] = True
                    _log_terminal(
                        CLEANUP_OUTCOME_SKIPPED_QUIET_ZONE,
                        f"[Auto-Cleanup #{cleanup_id}] Skipped: reason={reason}, "
                        f"outcome={CLEANUP_OUTCOME_SKIPPED_QUIET_ZONE}, "
                        f"memory_count={memory_count_before}, trim_target={trim_target}, "
                        f"post-cleanup quiet zone suppresses unnecessary cleanup check",
                        "info",
                    )
                    return result

                # When system RAM is critically high (>= 85%), run full consolidation to free process memory
                # even if guardian count is below normal threshold (consol_thresh). Use lower effective
                # threshold (_PRESSURE_CONSOLIDATION_MIN_COUNT) so we consolidate e.g. 3000 -> 1750.
                sys_critical = system_memory_percent is not None and system_memory_percent >= 0.85
                skip_thresh = _PRESSURE_CONSOLIDATION_MIN_COUNT if sys_critical else consol_thresh
                if memory_count_before is not None and memory_count_before <= skip_thresh:
                    # Pressure-based cleanup conflict fix:
                    # Even when guardian count is below the caller's consolidation threshold,
                    # host RAM pressure can still require freeing process memory.
                    #
                    # If we can still trim down to a pressure emergency floor, run an
                    # emergency pressure cleanup path (consolidate to a lower max_memories),
                    # instead of blocking solely on "count below threshold".
                    result["attempted"] = True
                    pressure_emergency_min_count = int(
                        pressure_cfg.get("pressure_emergency_min_count", _PRESSURE_EMERGENCY_MIN_COUNT)
                    )
                    if memory_count_before > pressure_emergency_min_count:
                        result["cleanup_path"] = "pressure_emergency_cleanup"
                        if memory_count_before > _PRESSURE_CONSOLIDATION_MIN_COUNT:
                            emergency_target = _PRESSURE_CONSOLIDATION_MIN_COUNT
                        else:
                            emergency_target = pressure_emergency_min_count
                        result["trim_policy"] = {
                            "trigger_threshold": skip_thresh,
                            "trim_target": emergency_target,
                            "min_trim_delta": MIN_TRIM_DELTA,
                            "source": "pressure_emergency",
                        }
                        cleared = self._clear_caches(memory_obj)
                        import gc
                        gc.collect()
                        result["gc_ran"] = True
                        result["caches_cleared"] = bool(cleared)
                        consol_result = memory_obj.consolidate(max_memories=emergency_target, keep_recent_days=30)
                        result["action_taken"] = bool(
                            consol_result.get("action_taken", consol_result.get("action") == "consolidated")
                        )
                        result["no_op_reason"] = consol_result.get("no_op_reason")
                        result["memory_after"] = consol_result.get("final_count", memory_count_before)
                        result["rss_after_mb"] = consol_result.get("rss_after_mb", rss_before_mb)
                        result["vector_rebuild_status"] = consol_result.get("vector_rebuild_status", "not_applicable")
                        result["error"] = consol_result.get("error")
                        if result["action_taken"]:
                            self._pressure_no_op_count = 0
                            _log_terminal(
                                CLEANUP_OUTCOME_CONSOLIDATED,
                                f"[Auto-Cleanup #{cleanup_id}] Pressure emergency cleanup: reason={reason}, "
                                f"outcome={CLEANUP_OUTCOME_CONSOLIDATED}, path=pressure_emergency_cleanup, "
                                f"memory={memory_count_before}->{result['memory_after']}",
                            )
                        else:
                            result["action_taken"] = False
                            self._pressure_no_op_count += 1
                            sys_pct = f"{system_memory_percent*100:.1f}%" if system_memory_percent is not None else "N/A"
                            _log_terminal(
                                CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD,
                                f"[Auto-Cleanup #{cleanup_id}] Pressure emergency cleanup skipped: reason={reason}, "
                                f"outcome={CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD}, system_memory={sys_pct}, "
                                f"memory_count={memory_count_before} emergency_target={emergency_target}",
                                "warning",
                            )
                        return result

                    result["no_op_reason"] = "memory_count_below_threshold"
                    cleared = self._clear_caches(memory_obj)
                    import gc
                    gc.collect()
                    result["gc_ran"] = True
                    result["caches_cleared"] = bool(cleared)
                    metrics_after = self._get_cleanup_metrics()
                    result["rss_after_mb"] = metrics_after.get("rss_mb")
                    result["memory_after"] = metrics_after["memory_count"]
                    
                    if cleared:
                        result["action_taken"] = True
                        self._pressure_no_op_count = 0
                        _log_terminal(
                            CLEANUP_OUTCOME_PARTIAL_RECLAIM,
                            f"[Auto-Cleanup #{cleanup_id}] Partial reclaim: reason={reason}, "
                            f"outcome={CLEANUP_OUTCOME_PARTIAL_RECLAIM}, "
                            f"rss={rss_before_mb}MB->{result['rss_after_mb']}MB",
                        )
                    else:
                        result["action_taken"] = False
                        self._pressure_no_op_count += 1
                        if self._pressure_no_op_count >= _PRESSURE_NO_OP_COUNT_BEFORE_COOLDOWN:
                            self._pressure_no_op_cooldown_until = now + (_PRESSURE_NO_OP_COOLDOWN_MINUTES * 60)
                        sys_pct = f"{system_memory_percent*100:.1f}%" if system_memory_percent is not None else "N/A"
                        _log_terminal(
                            CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD,
                            f"[Auto-Cleanup #{cleanup_id}] Skipped: reason={reason}, "
                            f"outcome={CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD}, "
                            f"system_memory={sys_pct}, memory_count={memory_count_before} below threshold={consol_thresh}",
                            "warning",
                        )
                        # Event-driven adversarial: repeated cleanup no-op
                        try:
                            g = getattr(self, "guardian", None)
                            if g:
                                from .adversarial_self_learning import trigger_adversarial_on_event, TRIGGER_CLEANUP_ANOMALY
                                trigger_adversarial_on_event(g, TRIGGER_CLEANUP_ANOMALY, {
                                    "skip_count": self._pressure_no_op_count,
                                    "system_memory_percent": system_memory_percent,
                                    "memory_count": memory_count_before,
                                    "threshold": consol_thresh,
                                })
                        except Exception as ae:
                            logger.debug("Adversarial cleanup trigger: %s", ae)
                    return result

                # Pressure path: memory_count > skip_thresh. Compute trim_target and check min_trim_delta.
                # Trim target for pressure: memory_threshold (from caller; now 1600 under pressure).
                pressure_trim_target = memory_threshold
                delta_would_remove = (memory_count_before or 0) - pressure_trim_target
                pressure_cfg = _load_memory_pressure_config()
                force_after = pressure_cfg.get("skipped_small_delta_force_after", 4)
                force_cleanup = self._pressure_skipped_small_delta_count >= force_after

                result["trim_policy"] = {
                    "trigger_threshold": skip_thresh,
                    "trim_target": pressure_trim_target,
                    "min_trim_delta": MIN_TRIM_DELTA,
                    "source": "config_memory_pressure",
                    "skipped_small_delta_count": self._pressure_skipped_small_delta_count,
                }
                if delta_would_remove < MIN_TRIM_DELTA and not force_cleanup:
                    # Slightly above floor - light reclaim only, avoid thrash (1754->1750, 1755->1750)
                    # After repeated skipped_small_delta, force_cleanup bypasses this
                    self._pressure_skipped_small_delta_count += 1
                    result["attempted"] = True
                    result["action_taken"] = False
                    cleared = self._clear_caches(memory_obj)
                    import gc
                    gc.collect()
                    result["gc_ran"] = True
                    result["caches_cleared"] = bool(cleared)
                    metrics_after = self._get_cleanup_metrics()
                    result["rss_after_mb"] = metrics_after.get("rss_mb")
                    result["memory_after"] = metrics_after["memory_count"]
                    _log_terminal(
                        CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA,
                        f"[Auto-Cleanup #{cleanup_id}] Skipped: reason={reason}, "
                        f"outcome={CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA}, "
                        f"memory_count={memory_count_before}, trim_target={pressure_trim_target}, "
                        f"skipped_count={self._pressure_skipped_small_delta_count}/{force_after}",
                        "warning",
                    )
                    return result
                # Force cleanup after repeated skipped_small_delta - fall through to consolidation
                if force_cleanup:
                    logger.info(
                        "[Auto-Cleanup #%d] Forcing consolidation after %d skipped_small_delta (bypass min_trim_delta)",
                        cleanup_id, self._pressure_skipped_small_delta_count,
                    )
                    self._pressure_skipped_small_delta_count = 0
                    result["force_cleanup_bypass_delta"] = True
            
            # Count-threshold or eligible pressure path: run full consolidation
            result["attempted"] = True
            cleared_caches = self._clear_caches(memory_obj)
            result["caches_cleared"] = bool(cleared_caches)
            
            if not hasattr(memory_obj, 'consolidate'):
                result["no_op_reason"] = "no_consolidate_method"
                _log_terminal(
                    CLEANUP_OUTCOME_FAILED,
                    f"[Auto-Cleanup #{cleanup_id}] Failed: reason={reason}, outcome={CLEANUP_OUTCOME_FAILED}, "
                    f"no_consolidate_method",
                    "warning",
                )
                return result
            
            # Trim to (threshold - headroom) for count-based path to avoid treadmill (beat adds 1, we remove 1)
            # Only apply headroom when threshold is high enough (e.g. 3000) - not for small test thresholds
            trim_target = memory_threshold
            if reason == CLEANUP_REASON_MEMORY_COUNT_THRESHOLD and memory_threshold > 1500:
                trim_target = max(1000, memory_threshold - _CLEANUP_HEADROOM)

            # Populate trim_policy for consolidation path if not already set (pressure sets it earlier)
            if result.get("trim_policy") is None:
                trigger_thresh = consol_thresh if reason == CLEANUP_REASON_MEMORY_COUNT_THRESHOLD else memory_threshold
                result["trim_policy"] = {
                    "trigger_threshold": trigger_thresh,
                    "trim_target": trim_target,
                    "min_trim_delta": MIN_TRIM_DELTA,
                    "source": "config" if reason == CLEANUP_REASON_MEMORY_COUNT_THRESHOLD else "config_memory_cleanup_threshold_x05",
                }

            # Hysteresis: skip consolidation if would remove fewer than min_trim_delta (avoid thrash).
            # Bypass when force_cleanup_bypass_delta (forced after repeated skipped_small_delta).
            delta_would_remove = (memory_count_before or 0) - trim_target
            bypass_delta = result.get("force_cleanup_bypass_delta", False)
            if delta_would_remove < MIN_TRIM_DELTA and not bypass_delta:
                result["action_taken"] = False
                result["no_op_reason"] = "delta_below_min_trim"
                cleared = self._clear_caches(memory_obj)
                import gc
                gc.collect()
                result["gc_ran"] = True
                result["caches_cleared"] = bool(cleared)
                metrics_after = self._get_cleanup_metrics()
                result["memory_after"] = metrics_after["memory_count"]
                result["rss_after_mb"] = metrics_after.get("rss_mb")
                if reason == CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE:
                    self._pressure_no_op_count = 0
                _log_terminal(
                    CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA,
                    f"[Auto-Cleanup #{cleanup_id}] Skipped: reason={reason}, "
                    f"outcome={CLEANUP_OUTCOME_SKIPPED_SMALL_DELTA}, "
                    f"memory_count={memory_count_before}, trim_target={trim_target}, min_trim_delta={MIN_TRIM_DELTA}",
                    "warning",
                )
                return result

            if bypass_delta:
                logger.info(
                    "[Auto-Cleanup #%d] Forced cleanup override: bypassing min_trim_delta (delta=%d, min=%d)",
                    cleanup_id, delta_would_remove, MIN_TRIM_DELTA,
                )
            consol_result = memory_obj.consolidate(max_memories=trim_target, keep_recent_days=30)
            result["action_taken"] = bool(consol_result.get("action_taken", consol_result.get("action") == "consolidated"))
            result["no_op_reason"] = consol_result.get("no_op_reason")
            result["memory_after"] = consol_result.get("final_count", memory_count_before)
            result["rss_after_mb"] = consol_result.get("rss_after_mb", rss_before_mb)
            result["vector_rebuild_status"] = consol_result.get("vector_rebuild_status", "not_applicable")
            result["error"] = consol_result.get("error")
            
            if reason == CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE and not result["action_taken"]:
                self._pressure_no_op_count += 1
                if self._pressure_no_op_count >= _PRESSURE_NO_OP_COUNT_BEFORE_COOLDOWN:
                    self._pressure_no_op_cooldown_until = time.time() + (_PRESSURE_NO_OP_COOLDOWN_MINUTES * 60)
            else:
                self._pressure_no_op_count = 0
                if reason == CLEANUP_REASON_SYSTEM_MEMORY_PRESSURE and result["action_taken"]:
                    self._pressure_skipped_small_delta_count = 0
            
            if consol_result.get("action") == "error":
                _log_terminal(
                    CLEANUP_OUTCOME_FAILED,
                    f"[Auto-Cleanup #{cleanup_id}] Failed: reason={reason}, outcome={CLEANUP_OUTCOME_FAILED}, "
                    f"error={consol_result.get('error')}",
                    "warning",
                )
                return result
            
            # Handle count increase (critical) and over-threshold
            memory_count_after = result["memory_after"]
            if memory_count_after > memory_count_before:
                logger.error(
                    f"[Auto-Cleanup #{cleanup_id}] CRITICAL: Memory count increased during cleanup! "
                    f"BEFORE: {memory_count_before} AFTER: {memory_count_after}"
                )
                self._force_trim_memory(memory_obj, memory_threshold)
                metrics_after = self._get_cleanup_metrics()
                result["memory_after"] = metrics_after["memory_count"]
                result["rss_after_mb"] = metrics_after.get("rss_mb")
            elif memory_count_after is not None and memory_count_after > memory_threshold:
                self._force_trim_memory(memory_obj, memory_threshold)
                metrics_after = self._get_cleanup_metrics()
                result["memory_after"] = metrics_after["memory_count"]
                result["rss_after_mb"] = metrics_after.get("rss_mb")
            
            # Single terminal log for consolidation path
            if result["action_taken"]:
                orig = consol_result.get("original_count", memory_count_before)
                final = result["memory_after"]
                removed = consol_result.get("removed", (orig or 0) - (final or 0))
                _log_terminal(
                    CLEANUP_OUTCOME_CONSOLIDATED,
                    f"[Auto-Cleanup #{cleanup_id}] Consolidated: reason={reason}, "
                    f"outcome={CLEANUP_OUTCOME_CONSOLIDATED}, memory={orig}->{final}, removed={removed}",
                )
                # Post-cleanup quiet zone: suppress repeat checks for a short window
                pressure_cfg = _load_memory_pressure_config()
                quiet_min = pressure_cfg.get("post_cleanup_quiet_minutes", 5)
                if quiet_min > 0:
                    self._post_cleanup_quiet_until = time.time() + (quiet_min * 60)
                    logger.info(
                        "[Auto-Cleanup #%d] Post-cleanup quiet zone active for %d min (suppresses repeat cleanup checks)",
                        cleanup_id, quiet_min,
                    )
            else:
                _log_terminal(
                    CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD,
                    f"[Auto-Cleanup #{cleanup_id}] Skipped: reason={reason}, "
                    f"outcome={CLEANUP_OUTCOME_SKIPPED_BELOW_THRESHOLD}, "
                    f"no_op_reason={result['no_op_reason']}, memory={memory_count_before} (unchanged)",
                    "warning",
                )
            
            return result
                
        except Exception as e:
            result["outcome"] = CLEANUP_OUTCOME_FAILED
            result["error"] = str(e)
            logger.error(
                f"[Auto-Cleanup #{cleanup_id}] Failed: reason={result.get('reason', 'unknown')}, "
                f"outcome={CLEANUP_OUTCOME_FAILED}, error={e}"
            )
            import traceback
            logger.debug(traceback.format_exc())
            return result
        finally:
            self._cleanup_in_progress = False
            processed_count = self._process_pending_memory_writes()
            if processed_count > 0:
                result["queued_writes_processed"] = processed_count
                logger.info(
                    f"[Auto-Cleanup #{cleanup_id}] Processed {processed_count} queued memory writes after cleanup "
                    "(min_trim_delta prevents thrash when slight refill)"
                )
    
    def _force_trim_memory(self, memory_obj, max_memories: int) -> None:
        """Force trim to max_memories by keeping most recent. Uses load_if_needed then internal trim."""
        if hasattr(memory_obj, "load_if_needed"):
            memory_obj.load_if_needed()
        if not hasattr(memory_obj, 'memory_log'):
            return
        current_count = len(memory_obj.memory_log)
        if current_count <= max_memories:
            return
        # Keep only the most recent max_memories (internal trim; load already done)
        memory_obj.memory_log = memory_obj.memory_log[-max_memories:]
        
        # Explicitly delete old references
        import gc
        gc.collect()
        
        logger.info(f"[Auto-Cleanup] Force trimmed memory: {current_count} -> {len(memory_obj.memory_log)}")
        
        # Save if possible
        if hasattr(memory_obj, '_save'):
            try:
                memory_obj._save()
            except:
                pass
        
    def check_critical_conditions(self) -> List[str]:
        """
        Check for critical system conditions.
        
        Returns:
            List of critical condition messages
        """
        health = self.get_system_health()
        critical_conditions = []
        
        # Check for critical errors
        if health["errors"]["recent_errors"] > 5:
            critical_conditions.append("High error rate detected")
            
        # Check for low health score
        if health["health_score"] < 0.3:
            critical_conditions.append("Critical system health")
            
        # Check for memory issues
        if health["heartbeat"]["total_memories"] > 2000:
            critical_conditions.append("High memory usage")
            
        # Check for trust issues
        if health["guardian_status"]["trust"]["average_trust"] < 0.3:
            critical_conditions.append("Low trust levels")
            
        return critical_conditions 