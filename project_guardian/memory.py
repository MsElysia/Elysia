# project_guardian/memory.py
# Memory Core System for Project Guardian
# Enhanced with TimelineMemory integration for persistent event logging

import datetime
import json
import os
import logging
import threading
from typing import List, Dict, Any, Optional

try:
    from .timeline_memory import TimelineMemory
    from .memory_vector_search import MemoryVectorSearch, add_vector_search_to_memory_core
except ImportError:
    try:
        from timeline_memory import TimelineMemory
        from memory_vector_search import MemoryVectorSearch, add_vector_search_to_memory_core
    except ImportError:
        TimelineMemory = None
        try:
            from memory_vector_search import MemoryVectorSearch, add_vector_search_to_memory_core
        except ImportError:
            MemoryVectorSearch = None
            add_vector_search_to_memory_core = None

logger = logging.getLogger(__name__)

class MemoryCore:
    """
    Persistent memory system for Project Guardian.
    Provides timestamped memory storage with JSON persistence.
    Enhanced with TimelineMemory integration for SQLite-backed event logging.
    """
    
    def __init__(
        self,
        filepath: str = "guardian_memory.json",
        timeline_memory: Optional[TimelineMemory] = None,
        enable_timeline_logging: bool = True,
        enable_vector_search: bool = False,
        max_memories: Optional[int] = None,
        lazy_load: bool = False,
    ):
        self.memory_log: List[Dict[str, Any]] = []
        self.filepath = filepath
        # Configurable max memories (None = no limit)
        self.max_memories = max_memories
        self._lazy_load = lazy_load
        self.loaded: bool = False
        self._load_lock = threading.Lock()
        self._save_file_lock = threading.Lock()
        
        # Embeddings control (defer until startup completes)
        self._embeddings_enabled = False
        
        # TimelineMemory integration (optional)
        self.timeline = timeline_memory
        self.enable_timeline_logging = enable_timeline_logging and self.timeline is not None
        
        if lazy_load:
            logger.info("[Startup] MemoryCore JSON history load deferred (lazy_load=True)")
        else:
            self.load()
            self.loaded = True
        
        # Vector search (optional) - lazy initialization
        self.vector_search: Optional[MemoryVectorSearch] = None
        self._vector_search_enabled = enable_vector_search
        self._vector_index_built = False
        self._embed_on_startup = os.getenv("EMBED_ON_STARTUP", "false").lower() == "true"
        self._vector_embed_batch_counter = 0
        self._vector_embed_batch_every = max(1, int(os.getenv("MEMORY_VECTOR_EMBED_EVERY", "1") or 1))

        if enable_vector_search and MemoryVectorSearch:
            try:
                self.vector_search = MemoryVectorSearch()
                logger.info("MemoryCore: Vector search enabled (lazy indexing)")
                
                # Only index existing memories if EMBED_ON_STARTUP is true
                if self._embed_on_startup:
                    logger.info("MemoryCore: EMBED_ON_STARTUP=true, indexing existing memories...")
                    self._build_vector_index()
                else:
                    logger.debug("MemoryCore: EMBED_ON_STARTUP=false, skipping startup indexing (will index on-demand)")
            except Exception as e:
                logger.warning(f"Failed to initialize vector search: {e}")
                self.vector_search = None
    
    def load_if_needed(self) -> None:
        """
        Load full JSON history once (idempotent). Required before reads/writes
        that must see on-disk state when lazy_load was used at construction.
        """
        if self.loaded:
            return
        with self._load_lock:
            if self.loaded:
                return
            logger.info("[Startup] MemoryCore: loading JSON history (deferred)")
            self.load()
            self.loaded = True

    def is_loaded(self) -> bool:
        return self.loaded

    def get_memory_count(self, load_if_needed: bool = False) -> Optional[int]:
        """
        Return JSON memory entry count, or None if not loaded and load_if_needed is False.
        Pass load_if_needed=True for authoritative count (e.g. cleanup decisions).
        """
        if load_if_needed:
            self.load_if_needed()
        if not self.loaded:
            return None
        return len(self.memory_log)

    def get_memory_state(self, load_if_needed: bool = False) -> Dict[str, Any]:
        """
        Persistence-aware memory state for status APIs.
        When not loaded and load_if_needed=False, count is None (not "empty history").
        """
        if load_if_needed:
            self.load_if_needed()
        if self.loaded:
            n = len(self.memory_log)
            return {
                "memory_loaded": True,
                "json_loaded": True,
                "memory_count": n,
                "memory_count_authoritative": True,
            }
        return {
            "memory_loaded": False,
            "json_loaded": False,
            "memory_count": None,
            "memory_count_authoritative": False,
        }
    
    def _build_vector_index(self):
        """Build vector index from existing memories (lazy, called on first use or if EMBED_ON_STARTUP=true)."""
        if not self.vector_search or self._vector_index_built:
            return
        
        existing_memories = self.memory_log
        logger.info(f"MemoryCore: Building vector index for {len(existing_memories)} existing memories...")
        
        for i, memory in enumerate(existing_memories):
            memory_id = f"existing_{i}_{memory.get('time', '')}"
            text = memory.get('thought', '')
            if text:
                try:
                    self.vector_search.add_memory(memory_id, text, memory)
                except Exception as e:
                    logger.debug(f"Failed to index memory {i}: {e}")
        
        self._vector_index_built = True
        logger.info("MemoryCore: Vector index built")
    
    def enable_embeddings(self):
        """
        Enable embeddings (call after startup completes).
        Idempotent: safe to call multiple times.
        """
        if self._embeddings_enabled:
            logger.debug("MemoryCore: Embeddings already enabled, skipping")
            return
        
        self._embeddings_enabled = True
        logger.info("MemoryCore: Embeddings enabled (startup complete)")
        
    def remember(
        self,
        thought: str,
        category: str = "general",
        priority: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Store a new memory entry with timestamp and metadata.
        Enhanced with TimelineMemory integration for persistent event logging.
        
        Args:
            thought: The memory content
            category: Memory category (e.g., 'safety', 'task', 'mutation', 'conversation')
            priority: Priority level (0.0 to 1.0)
            metadata: Optional additional metadata
        """
        self.load_if_needed()
        try:
            from .startup_runtime_guard import should_skip_nonessential_remember

            if should_skip_nonessential_remember(category, float(priority or 0), thought or ""):
                logger.debug("MemoryCore.remember skipped (startup memory-thin mode)")
                return
        except Exception:
            pass
        try:
            from .memory_noise import routine_autonomy_remember_suppressed

            if routine_autonomy_remember_suppressed(category, float(priority or 0), thought):
                logger.debug("MemoryCore.remember skipped (host RAM pressure + routine duplicate)")
                return
        except Exception:
            pass
        try:
            from .memory_noise import is_low_value_memory_text

            if is_low_value_memory_text(thought, min_chars_for_substantive=22) and float(priority or 0) < 0.52:
                logger.debug("Memory remember skipped (noise text, low priority)")
                return
        except Exception:
            pass
        # Reject low-value writes under memory pressure to reduce junk growth
        try:
            from pathlib import Path
            import json as _json
            cfg_path = Path(__file__).parent.parent / "config" / "memory_pressure.json"
            if cfg_path.exists():
                with open(cfg_path, "r") as f:
                    pressure_cfg = _json.load(f)
                count_thresh = pressure_cfg.get("low_value_write_reject_when_count_above", 1600)
                priority_thresh = pressure_cfg.get("low_value_write_reject_priority_below", 0.25)
                if len(self.memory_log) >= count_thresh and priority < priority_thresh:
                    return
        except Exception:
            pass
        # Enforce max_memories limit if set
        if self.max_memories is not None and len(self.memory_log) >= self.max_memories:
            # Remove oldest memory to make room
            self.memory_log.pop(0)
        
        timestamp = datetime.datetime.now().isoformat()
        entry = {
            "time": timestamp,
            "thought": thought,
            "category": category,
            "priority": priority,
            "metadata": metadata or {}
        }
        self.memory_log.append(entry)
        self._save()
        
        # Add to vector search index (only if embeddings are enabled)
        if self.vector_search and self._embeddings_enabled:
            try:
                from .memory_noise import is_embedding_entirely_skipped, is_low_value_memory_text

                if is_embedding_entirely_skipped(thought):
                    logger.debug("Skipping vector index for non-vectorizable fragment")
                elif is_low_value_memory_text(thought, min_chars_for_substantive=22):
                    logger.debug("Skipping vector index for low-value memory text")
                else:
                    self._vector_embed_batch_counter += 1
                    if self._vector_embed_batch_counter % self._vector_embed_batch_every != 0:
                        pass
                    else:
                        try:
                            if not self._vector_index_built:
                                self._build_vector_index()

                            memory_id = f"{category}_{timestamp}"
                            self.vector_search.add_memory(memory_id, thought, entry)
                        except Exception as e:
                            logger.debug(f"Vector search indexing failed: {e}")
            except Exception as ve:
                logger.debug(f"Vector embed gate: {ve}")
        
        # Log to TimelineMemory for persistent event logging
        if self.enable_timeline_logging and self.timeline:
            try:
                # Create event payload
                payload = {
                    "thought": thought,
                    "category": category,
                    "priority": priority,
                    "metadata": metadata or {}
                }
                
                # Log as event to timeline
                self.timeline.log_event(
                    event_type=f"memory_{category}",
                    summary=f"Memory: {thought[:100]}",
                    payload=json.dumps(payload),
                    module="MemoryCore"
                )
            except Exception as e:
                logger.debug(f"TimelineMemory logging failed: {e}")
        
        logger.debug(f"[Guardian Memory] {timestamp}: {thought}")
        # Avoid flooding console with heartbeat pulses and startup lines
        if "[Heartbeat]" in thought:
            return
        print(f"[Guardian Memory] {timestamp}: {thought}")
        
    def recall_last(
        self,
        count: int = 1,
        category: Optional[str] = None,
        use_timeline: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent memories.
        Enhanced with TimelineMemory query support.
        
        Args:
            count: Number of memories to retrieve
            category: Filter by category (optional)
            use_timeline: If True, query TimelineMemory for additional events
            
        Returns:
            List of memory entries
        """
        self.load_if_needed()
        memories = self.memory_log
        if category:
            memories = [m for m in memories if m.get("category") == category]
        
        result = memories[-count:] if memories else []
        
        # Supplement with TimelineMemory events if enabled
        if use_timeline and self.enable_timeline_logging and self.timeline:
            try:
                # Query timeline for memory events
                event_type = f"memory_{category}" if category else None
                timeline_events = self.timeline.query_events(
                    event_type=event_type,
                    limit=count,
                    order_by="timestamp DESC"
                )
                
                # Convert timeline events to memory format
                timeline_memories = []
                for event in timeline_events:
                    try:
                        payload = json.loads(event.get("payload", "{}"))
                        timeline_memories.append({
                            "time": event.get("timestamp", ""),
                            "thought": payload.get("thought", event.get("summary", "")),
                            "category": payload.get("category", category or "general"),
                            "priority": payload.get("priority", 0.5),
                            "metadata": payload.get("metadata", {}),
                            "source": "timeline"
                        })
                    except Exception as e:
                        logger.debug(f"Failed to parse timeline event: {e}")
                
                # Merge and deduplicate
                all_memories = result + timeline_memories
                # Sort by timestamp
                all_memories.sort(key=lambda x: x.get("time", ""))
                result = all_memories[-count:]
            except Exception as e:
                logger.debug(f"TimelineMemory query failed: {e}")
        
        return result
        
    def search_memories(
        self,
        keyword: str,
        limit: int = 10,
        use_timeline: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search memories by keyword.
        Enhanced with TimelineMemory search support.
        
        Args:
            keyword: Search term
            limit: Maximum number of results
            use_timeline: If True, search TimelineMemory as well
            
        Returns:
            List of matching memory entries
        """
        self.load_if_needed()
        results = []
        
        # Search local memory log
        for memory in reversed(self.memory_log):
            if keyword.lower() in memory["thought"].lower():
                results.append(memory)
                if len(results) >= limit:
                    break
        
        # Search TimelineMemory if enabled
        if use_timeline and self.enable_timeline_logging and self.timeline:
            try:
                # Query timeline events
                timeline_events = self.timeline.query_events(
                    summary_contains=keyword,
                    limit=limit,
                    order_by="timestamp DESC"
                )
                
                # Convert to memory format
                for event in timeline_events:
                    try:
                        payload = json.loads(event.get("payload", "{}"))
                        memory_entry = {
                            "time": event.get("timestamp", ""),
                            "thought": payload.get("thought", event.get("summary", "")),
                            "category": payload.get("category", "general"),
                            "priority": payload.get("priority", 0.5),
                            "metadata": payload.get("metadata", {}),
                            "source": "timeline"
                        }
                        
                        # Add if not already in results
                        if memory_entry not in results:
                            results.append(memory_entry)
                            if len(results) >= limit:
                                break
                    except Exception as e:
                        logger.debug(f"Failed to parse timeline event: {e}")
            except Exception as e:
                logger.debug(f"TimelineMemory search failed: {e}")
        
        return results[:limit]
    
    def search_semantic(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Semantic similarity search using vector embeddings.
        
        Args:
            query: Search query
            limit: Maximum results
            threshold: Minimum similarity score (0.0-1.0)
            
        Returns:
            List of memory entries with similarity scores
        """
        self.load_if_needed()
        # Lazy indexing: build index on first use if not already built
        if self.vector_search and not self._vector_index_built:
            self._build_vector_index()
        
        if not self.vector_search:
            logger.warning("Vector search not enabled, falling back to keyword search")
            return self.search_memories(query, limit=limit)
        
        try:
            # Search using vector similarity
            similar_memories = self.vector_search.search_similar(
                query,
                limit=limit,
                threshold=threshold
            )
            
            # Convert to memory format
            results = []
            for memory_id, similarity, metadata in similar_memories:
                # Try to find original memory
                # Extract time from memory_id if possible
                for memory in self.memory_log:
                    memory_text = memory.get("thought", "")
                    if memory_text and memory_id.endswith(memory.get("time", "")):
                        result_memory = memory.copy()
                        result_memory["similarity_score"] = similarity
                        result_memory["search_method"] = "semantic"
                        results.append(result_memory)
                        break
                else:
                    # Create from metadata if memory not found
                    if metadata:
                        results.append({
                            "similarity_score": similarity,
                            "search_method": "semantic",
                            "metadata": metadata
                        })
            
            return results
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return self.search_memories(query, limit=limit)
    
    def get_memories_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Get all memories in a specific category.
        
        Args:
            category: Memory category
            
        Returns:
            List of memories in the category
        """
        self.load_if_needed()
        return [m for m in self.memory_log if m.get("category") == category]

    def get_recent_memories(
        self,
        limit: int = 50,
        category: Optional[str] = None,
        load_if_needed: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get most recent memories. Safe for UI/routes.
        Set load_if_needed=True to force load (memory-detail routes); False for non-forcing status.
        """
        if not load_if_needed and not self.loaded:
            return []
        return self.recall_last(limit, category)
        
    def dump_all(self) -> List[Dict[str, Any]]:
        """
        Get all memories. ADMIN/EXPORT only; use get_recent_memories for bounded UI/runtime.
        """
        self.load_if_needed()
        return self.memory_log.copy()
        
    def forget(self) -> None:
        """
        Clear all memories and delete the memory file.
        """
        self.load_if_needed()
        self.memory_log = []
        if os.path.exists(self.filepath):
            os.remove(self.filepath)
        print("[Guardian Memory] All memories cleared.")
        
    def _save(self) -> None:
        """
        Save memories to JSON file.
        """
        import time as _time

        with self._save_file_lock:
            last_err: Optional[Exception] = None
            for attempt in range(3):
                try:
                    with open(self.filepath, "w", encoding="utf-8") as f:
                        json.dump(self.memory_log, f, indent=2)
                    return
                except Exception as e:
                    last_err = e
                    _time.sleep(0.04 * (attempt + 1))
            if last_err:
                print(f"[Guardian Memory] Save failed after retries: {last_err}")
            
    def load(self) -> None:
        """
        Load memories from JSON file.
        """
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.memory_log = json.load(f)
                print(f"[Guardian Memory] Loaded {len(self.memory_log)} past memories.")
            except Exception as e:
                print(f"[Guardian Memory] Load failed: {e}")
                
    def consolidate(self, max_memories: int = 5000, keep_recent_days: int = 30) -> Dict[str, Any]:
        """
        Consolidate memories to reduce memory usage.
        
        Args:
            max_memories: Maximum number of memories to keep
            keep_recent_days: Keep all memories from last N days
            
        Returns:
            Dictionary with consolidation results
        """
        self.load_if_needed()
        from .memory_cleanup import MemoryCleanup
        cleanup = MemoryCleanup(self)
        return cleanup.consolidate_memories(max_memories=max_memories, keep_recent_days=keep_recent_days)
    
    def cleanup_old_memories(self, days: int = 90, min_priority: float = 0.3) -> Dict[str, Any]:
        """
        Remove old low-priority memories.
        
        Args:
            days: Remove memories older than N days
            min_priority: Only remove memories with priority below this
            
        Returns:
            Dictionary with cleanup results
        """
        self.load_if_needed()
        from .memory_cleanup import MemoryCleanup
        cleanup = MemoryCleanup(self)
        return cleanup.cleanup_old_memories(days=days, min_priority=min_priority)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get memory system statistics.
        Enhanced with TimelineMemory statistics if available.
        
        Returns:
            Dictionary with memory statistics
        """
        if not self.loaded:
            return {
                "total_memories": None,
                "categories": {},
                "oldest_memory": None,
                "newest_memory": None,
                "timeline_integration": self.enable_timeline_logging,
                "json_loaded": False,
                "memory_loaded": False,
                "memory_count_authoritative": False,
            }
        categories = {}
        for memory in self.memory_log:
            cat = memory.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        
        stats = {
            "total_memories": len(self.memory_log),
            "categories": categories,
            "oldest_memory": self.memory_log[0]["time"] if self.memory_log else None,
            "newest_memory": self.memory_log[-1]["time"] if self.memory_log else None,
            "timeline_integration": self.enable_timeline_logging,
            "json_loaded": True,
            "memory_loaded": True,
            "memory_count_authoritative": True,
        }
        
        # Add TimelineMemory stats if enabled
        if self.enable_timeline_logging and self.timeline:
            try:
                timeline_stats = self.timeline.get_statistics()
                stats["timeline_stats"] = {
                "total_events": timeline_stats.get("total_events", 0),
                "total_tasks": timeline_stats.get("total_tasks", 0)
                }
            except Exception as e:
                logger.debug(f"Failed to get TimelineMemory stats: {e}")
        
        return stats
    
    def get_timeline_memories(
        self,
        event_type: Optional[str] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Query memories from TimelineMemory directly.
        
        Args:
            event_type: Filter by event type (e.g., 'memory_conversation')
            start_time: Start time for query
            end_time: End time for query
            limit: Maximum number of results
            
        Returns:
            List of memory entries from timeline
        """
        if not self.enable_timeline_logging or not self.timeline:
            return []
        
        try:
            # Build query parameters
            events = self.timeline.query_events(
                event_type=event_type,
                start_time=start_time.isoformat() if start_time else None,
                end_time=end_time.isoformat() if end_time else None,
                limit=limit,
                order_by="timestamp DESC"
            )
            
            # Convert to memory format
            memories = []
            for event in events:
                try:
                    payload = json.loads(event.get("payload", "{}"))
                    memories.append({
                        "time": event.get("timestamp", ""),
                        "thought": payload.get("thought", event.get("summary", "")),
                        "category": payload.get("category", "general"),
                        "priority": payload.get("priority", 0.5),
                        "metadata": payload.get("metadata", {}),
                        "source": "timeline",
                        "event_type": event.get("event_type", "")
                    })
                except Exception as e:
                    logger.debug(f"Failed to parse timeline event: {e}")
            
            return memories
        except Exception as e:
            logger.error(f"Error querying TimelineMemory: {e}")
            return [] 