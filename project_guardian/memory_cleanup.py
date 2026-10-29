#!/usr/bin/env python3
"""
Memory Cleanup and Optimization
================================
Automatic memory cleanup and consolidation to reduce memory usage
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_memory_time(value: Any, fallback: datetime) -> datetime:
    """
    Parse a memory entry's ``time`` into a naive local datetime comparable with
    ``datetime.now()``.

    MemoryCore stamps entries with naive local isoformat, but imported or
    merged records may carry ``Z`` / ``+HH:MM`` offsets. Comparing an aware
    datetime against the naive cutoff raises TypeError, which previously
    aborted the whole cleanup pass. Unparseable or missing values fall back to
    ``fallback`` (treated as recent, i.e. kept).
    """
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except Exception:
        return fallback
    if parsed.tzinfo is not None:
        try:
            parsed = parsed.astimezone().replace(tzinfo=None)
        except Exception:
            return fallback
    return parsed


def _persist_memory_log(json_mem: Any) -> Optional[bool]:
    """
    Call ``json_mem._save()`` and report the outcome.

    Returns True when the save reported success, False when it reported
    failure or raised, and None when the outcome is unknown (legacy ``_save``
    returning None, or no ``_save`` at all). Callers must not restore state on
    None; they only treat an explicit False as a failed write.
    """
    save = getattr(json_mem, "_save", None)
    if save is None:
        return None
    try:
        outcome = save()
    except Exception as e:
        logger.warning(f"Memory cleanup save raised: {e}")
        return False
    if outcome is None:
        return None
    return bool(outcome)


class MemoryCleanup:
    """Memory cleanup and optimization utilities"""
    
    def __init__(self, memory_core):
        """
        Initialize MemoryCleanup.
        
        Args:
            memory_core: MemoryCore instance
        """
        self.memory_core = memory_core
    
    def consolidate_memories(self, max_memories: int = 4000, keep_recent_days: int = 30) -> Dict[str, Any]:
        """
        Authoritative cleanup for JSON + vector memory.
        Handles both MemoryCore and EnhancedMemoryCore without causing a second heavy spike.
        """
        # Normalize memory implementations: MemoryCore vs EnhancedMemoryCore
        mem = self.memory_core
        is_enhanced = hasattr(mem, "json_memory") and hasattr(mem, "vector_memory")
        json_mem = mem.json_memory if is_enhanced else mem
        vector_mem = mem.vector_memory if is_enhanced else None

        if hasattr(json_mem, "load_if_needed"):
            json_mem.load_if_needed()
        if vector_mem is not None and hasattr(vector_mem, "load_if_needed"):
            vector_mem.load_if_needed()

        if not hasattr(json_mem, "memory_log"):
            return {
                "action": "error",
                "attempted": True,
                "action_taken": False,
                "no_op_reason": "memory_core_no_memory_log",
                "original_count": 0,
                "final_count": 0,
                "removed": 0,
                "metadata_before": 0,
                "metadata_after": 0,
                "faiss_before": 0,
                "faiss_after": 0,
                "rss_before_mb": 0.0,
                "rss_after_mb": 0.0,
                "vector_rebuild_status": "not_applicable",
                "vector_rebuild_success": False,
                "error": "Memory core does not have memory_log",
            }
        
        original_count = len(json_mem.memory_log)

        # Capture RSS before cleanup (best-effort)
        rss_before_mb: float = 0.0
        try:
            import psutil, os
            proc = psutil.Process(os.getpid())
            rss_before_mb = proc.memory_info().rss / (1024 * 1024)
        except Exception:
            pass
        
        if original_count <= max_memories:
            return {
                "action": "no_action_needed",
                "attempted": True,
                "action_taken": False,
                "no_op_reason": "memory_count_below_threshold",
                "original_count": original_count,
                "final_count": original_count,
                "removed": 0,
                "metadata_before": 0,
                "metadata_after": 0,
                "faiss_before": 0,
                "faiss_after": 0,
                "rss_before_mb": rss_before_mb,
                "rss_after_mb": rss_before_mb,
                "vector_rebuild_status": "not_applicable" if vector_mem is None else "deferred",
                "vector_rebuild_success": vector_mem is None,
                "error": None,
            }
        
        try:
            # Get cutoff date
            now = datetime.now()
            cutoff_date = now - timedelta(days=keep_recent_days)
            
            # Separate memories into categories
            recent_memories = []
            high_priority_memories = []
            old_low_priority = []
            
            original_log = json_mem.memory_log
            for memory in original_log:
                mem_date = _parse_memory_time(memory.get("time", ""), now)
                
                priority = memory.get("priority", 0.5)
                
                # Keep recent memories (last N days)
                if mem_date >= cutoff_date:
                    recent_memories.append(memory)
                # Keep high priority memories (priority > 0.7)
                elif priority > 0.7:
                    high_priority_memories.append(memory)
                else:
                    old_low_priority.append(memory)
            
            # Combine memories to keep
            memories_to_keep = recent_memories + high_priority_memories
            
            # If still too many, sort by priority and keep top N
            if len(memories_to_keep) > max_memories:
                memories_to_keep.sort(key=lambda x: x.get("priority", 0.5), reverse=True)
                memories_to_keep = memories_to_keep[:max_memories]
            
            # Update JSON memory log
            removed_count = original_count - len(memories_to_keep)
            json_mem.memory_log = memories_to_keep

            # Persist the JSON history before touching the vector index so a
            # failed write leaves JSON (authoritative) and vector consistent.
            # On an explicit failure, restore the in-memory log: the file on
            # disk still holds the full history and must stay the recall source.
            persisted = _persist_memory_log(json_mem)
            if persisted is False:
                json_mem.memory_log = original_log
                logger.warning(
                    f"Memory consolidation aborted: save failed; restored {original_count} in-memory memories"
                )
                return {
                    "action": "save_failed",
                    "attempted": True,
                    "action_taken": False,
                    "no_op_reason": "save_failed",
                    "original_count": original_count,
                    "final_count": original_count,
                    "removed": 0,
                    "metadata_before": 0,
                    "metadata_after": 0,
                    "faiss_before": 0,
                    "faiss_after": 0,
                    "rss_before_mb": rss_before_mb,
                    "rss_after_mb": rss_before_mb,
                    "vector_rebuild_status": "not_attempted",
                    "vector_rebuild_success": False,
                    "persisted": False,
                    "error": f"save failed; {removed_count} removals not persisted",
                }

            # Vector reconciliation (EnhancedMemoryCore only)
            from .memory_vector import VECTOR_REBUILD_SAFE_MAX
            metadata_before = 0
            metadata_after = 0
            faiss_before = 0
            faiss_after = 0
            vector_rebuild_status = "not_applicable"
            vector_rebuild_success = True
            vector_error = None

            if vector_mem is not None:
                vector_rebuild_status = "deferred"
                vector_rebuild_success = False
                try:
                    # Before metrics
                    try:
                        metadata_before = len(getattr(vector_mem, "metadata", []) or [])
                    except Exception:
                        metadata_before = 0
                    try:
                        idx = getattr(vector_mem, "index", None)
                        faiss_before = int(idx.ntotal) if idx is not None and hasattr(idx, "ntotal") else 0
                    except Exception:
                        faiss_before = 0

                    kept_count = len(memories_to_keep)
                    if kept_count <= VECTOR_REBUILD_SAFE_MAX:
                        from .memory_vector import VectorMemory  # type: ignore
                        if isinstance(vector_mem, VectorMemory):
                            vector_metrics = vector_mem._reconcile_with_memories(memories_to_keep, VECTOR_REBUILD_SAFE_MAX)
                            metadata_after = vector_metrics.get("metadata_after", metadata_before)
                            faiss_after = vector_metrics.get("faiss_after", faiss_before)
                            vector_rebuild_status = vector_metrics.get("vector_rebuild_status", "rebuilt")
                            vector_rebuild_success = vector_metrics.get("vector_rebuild_success", False)
                            vector_error = vector_metrics.get("error")
                        else:
                            vector_error = "Unknown vector memory implementation; cannot reconcile safely"
                            vector_rebuild_status = "failed"
                            vector_rebuild_success = False
                            try:
                                setattr(vector_mem, "degraded", True)
                                setattr(vector_mem, "rebuild_pending", False)
                            except Exception:
                                pass
                            if hasattr(vector_mem, "record_rebuild_outcome"):
                                vector_mem.record_rebuild_outcome("failed", "unknown vector impl", vector_error[:200])
                    else:
                        # Defer rebuild under pressure / large kept set
                        vector_error = (
                            f"kept set exceeded safe rebuild threshold "
                            f"({kept_count}>{VECTOR_REBUILD_SAFE_MAX}); rebuild deferred"
                        )
                        vector_rebuild_status = "deferred"
                        vector_rebuild_success = False
                        metadata_after = metadata_before
                        faiss_after = faiss_before
                        try:
                            setattr(vector_mem, "degraded", True)
                            setattr(vector_mem, "rebuild_pending", True)
                        except Exception:
                            pass
                        if hasattr(vector_mem, "record_rebuild_outcome"):
                            vector_mem.record_rebuild_outcome(
                                "skipped", f"kept set exceeded safe threshold ({kept_count}>{VECTOR_REBUILD_SAFE_MAX})", None
                            )
                except Exception as e:
                    # Vector reconciliation failed; mark degraded but keep JSON cleanup
                    vector_error = str(e)
                    vector_rebuild_status = "failed"
                    vector_rebuild_success = False
                    metadata_after = metadata_before
                    faiss_after = faiss_before
                    try:
                        setattr(vector_mem, "degraded", True)
                        setattr(vector_mem, "rebuild_pending", False)
                    except Exception:
                        pass
                    if hasattr(vector_mem, "record_rebuild_outcome"):
                        vector_mem.record_rebuild_outcome("failed", "exception", str(e)[:200])

            # Force garbage collection to free memory
            import gc
            gc.collect()

            # Capture RSS after cleanup
            rss_after_mb = rss_before_mb
            try:
                import psutil, os
                proc = psutil.Process(os.getpid())
                rss_after_mb = proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass
            
            logger.info(f"Memory consolidation: {original_count} -> {len(memories_to_keep)} (removed {removed_count})")
            
            return {
                "action": "consolidated",
                "attempted": True,
                "action_taken": True,
                "no_op_reason": None,
                "original_count": original_count,
                "final_count": len(memories_to_keep),
                "removed": removed_count,
                "metadata_before": metadata_before,
                "metadata_after": metadata_after,
                "faiss_before": faiss_before,
                "faiss_after": faiss_after,
                "rss_before_mb": rss_before_mb,
                "rss_after_mb": rss_after_mb,
                "vector_rebuild_status": vector_rebuild_status,
                "vector_rebuild_success": vector_rebuild_success,
                "persisted": persisted,
                "error": vector_error,
            }
            
        except Exception as e:
            logger.error(f"Error consolidating memories: {e}")
            return {
                "action": "error",
                "attempted": True,
                "action_taken": False,
                "no_op_reason": "consolidation_error",
                "original_count": original_count,
                "final_count": len(getattr(json_mem, "memory_log", []) or []),
                "removed": 0,
                "metadata_before": 0,
                "metadata_after": 0,
                "faiss_before": 0,
                "faiss_after": 0,
                "rss_before_mb": rss_before_mb,
                "rss_after_mb": rss_before_mb,
                "vector_rebuild_status": "failed",
                "vector_rebuild_success": False,
                "error": str(e),
            }
    
    def cleanup_old_memories(self, days: int = 90, min_priority: float = 0.3) -> Dict[str, Any]:
        """
        Remove old low-priority memories.
        
        Args:
            days: Remove memories older than N days
            min_priority: Only remove memories with priority below this
            
        Returns:
            Dictionary with cleanup results
        """
        if not hasattr(self.memory_core, 'memory_log'):
            return {"error": "Memory core does not have memory_log"}
        
        original_log = self.memory_core.memory_log
        original_count = len(original_log)
        now = datetime.now()
        cutoff_date = now - timedelta(days=days)
        
        try:
            kept_memories = []
            removed_memories = []
            
            for memory in original_log:
                priority = memory.get("priority", 0.5)
                mem_date = _parse_memory_time(memory.get("time", ""), now)
                
                # Keep if recent OR high priority
                if mem_date >= cutoff_date or priority >= min_priority:
                    kept_memories.append(memory)
                else:
                    removed_memories.append(memory)
            
            # Update memory log
            self.memory_core.memory_log = kept_memories
            
            persisted = _persist_memory_log(self.memory_core)
            if persisted is False:
                self.memory_core.memory_log = original_log
                logger.warning(
                    f"Memory cleanup aborted: save failed; restored {original_count} in-memory memories"
                )
                return {
                    "action": "save_failed",
                    "original_count": original_count,
                    "final_count": original_count,
                    "removed": 0,
                    "persisted": False,
                    "error": f"save failed; {len(removed_memories)} removals not persisted",
                }
            
            logger.info(f"Memory cleanup: {original_count} -> {len(kept_memories)} (removed {len(removed_memories)})")
            
            return {
                "action": "cleaned",
                "original_count": original_count,
                "final_count": len(kept_memories),
                "removed": len(removed_memories),
                "persisted": persisted,
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up memories: {e}")
            return {"error": str(e)}
    
    def get_memory_size_estimate(self) -> Dict[str, Any]:
        """
        Estimate memory usage.
        
        Returns:
            Dictionary with size estimates
        """
        if not hasattr(self.memory_core, 'memory_log'):
            return {"error": "Memory core does not have memory_log"}
        if hasattr(self.memory_core, "get_memory_state"):
            st = self.memory_core.get_memory_state(load_if_needed=False)
            if not st.get("memory_count_authoritative"):
                return {
                    "memory_loaded": False,
                    "memory_count_authoritative": False,
                    "total_memories": None,
                    "current_count": None,
                    "estimated_size_bytes": None,
                    "estimated_size_mb": None,
                    "note": "JSON memory not loaded; history size unknown (not empty)",
                }
        try:
            total_memories = len(self.memory_core.memory_log)
            
            # Estimate size (rough calculation)
            sample_size = 0
            if total_memories > 0:
                sample = json.dumps(self.memory_core.memory_log[:10])
                sample_size = len(sample.encode('utf-8'))
                avg_size_per_memory = sample_size / min(10, total_memories)
            else:
                avg_size_per_memory = 0
            
            estimated_size_bytes = avg_size_per_memory * total_memories
            estimated_size_mb = estimated_size_bytes / (1024 * 1024)
            
            return {
                "total_memories": total_memories,
                "estimated_size_bytes": estimated_size_bytes,
                "estimated_size_mb": round(estimated_size_mb, 2),
                "avg_size_per_memory": round(avg_size_per_memory, 2)
            }
            
        except Exception as e:
            logger.error(f"Error estimating memory size: {e}")
            return {"error": str(e)}


def auto_cleanup_memory(memory_core, memory_threshold: int = 4000) -> Dict[str, Any]:
    """
    Automatically cleanup memory if it exceeds threshold.
    
    Args:
        memory_core: MemoryCore instance
        memory_threshold: Trigger cleanup if memory count exceeds this
        
    Returns:
        Dictionary with cleanup results
    """
    if not hasattr(memory_core, 'memory_log'):
        return {"action": "skipped", "reason": "No memory_log attribute"}
    if hasattr(memory_core, "get_memory_count"):
        current_count = memory_core.get_memory_count(load_if_needed=True)
    else:
        current_count = len(memory_core.memory_log)
    if current_count is None:
        return {"action": "skipped", "reason": "Memory not loaded"}
    
    if current_count <= memory_threshold:
        return {
            "action": "no_action_needed",
            "current_count": current_count,
            "threshold": memory_threshold
        }
    
    # Perform consolidation
    cleanup = MemoryCleanup(memory_core)
    result = cleanup.consolidate_memories(max_memories=memory_threshold)
    
    return result

