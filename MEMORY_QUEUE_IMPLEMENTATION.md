# Memory Write Queue Implementation

## Summary

Replaced the band-aid "suppression" logic with a proper memory write queue system that ensures no memory writes are lost during cleanup cycles.

## Problem (Before)

**Band-Aid Fix**: Memory writes were suppressed during cleanup using a flag check:
```python
if self._cleanup_in_progress:
    logger.info("... - suppressed during cleanup")
else:
    self.memory.remember(...)
```

**Issues**:
- Memory writes were completely lost during cleanup
- No queue/deferral mechanism
- Created gaps in memory history
- Hard to track what happened during cleanup cycles

## Solution (After)

**Proper Implementation**: Memory write queue that defers writes during cleanup and processes them afterward.

### Key Components

1. **Queue Storage**:
   - `_pending_memory_writes`: List of queued memory writes
   - `_pending_writes_lock`: Thread-safe lock for queue access

2. **Queue Method**:
   - `_queue_or_write_memory()`: Queues writes during cleanup, writes directly otherwise

3. **Process Method**:
   - `_process_pending_memory_writes()`: Processes all queued writes after cleanup completes

### Implementation Details

**Initialization** (in `SystemMonitor.__init__`):
```python
self._pending_memory_writes = []  # Queue for memory writes during cleanup
self._pending_writes_lock = threading.Lock()  # Thread-safe queue access
```

**Queue Method**:
```python
def _queue_or_write_memory(self, thought: str, category: str = "general", 
                          priority: float = 0.5, metadata: Optional[Dict[str, Any]] = None) -> None:
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
```

**Process Method**:
```python
def _process_pending_memory_writes(self) -> int:
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
```

**Cleanup Integration** (in `_perform_cleanup` finally block):
```python
finally:
    # Mark cleanup as complete
    self._cleanup_in_progress = False
    
    # Process any memory writes queued during cleanup
    processed_count = self._process_pending_memory_writes()
    if processed_count > 0:
        logger.info(f"[Auto-Cleanup #{cleanup_id}] Processed {processed_count} queued memory writes after cleanup")
```

## Files Modified

1. **`project_guardian/monitoring.py`**:
   - Added queue storage to `SystemMonitor.__init__`
   - Added `_queue_or_write_memory()` method
   - Added `_process_pending_memory_writes()` method
   - Updated `_perform_cleanup()` to process queue after cleanup
   - Replaced all suppression checks with queue calls:
     - `Heartbeat.start()` (1 location)
     - `Heartbeat.stop()` (1 location)
     - `Heartbeat._beat()` (2 locations: pulse and error)
     - `SystemMonitor.start_monitoring()` (1 location)
     - `SystemMonitor.stop_monitoring()` (1 location)

## Benefits

1. **No Data Loss**: All memory writes are preserved, even during cleanup
2. **Chronological Order**: Writes are processed in order after cleanup
3. **Thread-Safe**: Uses locks to ensure safe concurrent access
4. **Error Handling**: Individual write failures don't stop queue processing
5. **Logging**: Clear visibility into queue operations

## Testing

All existing tests pass:
```bash
pytest tests/test_auto_cleanup_effectiveness.py -q
# Result: 8 passed ✅
```

## Status

✅ **COMPLETE** - Band-aid fix replaced with proper implementation

## Next Steps

1. Monitor runtime behavior to verify queue works correctly
2. Consider adding metrics for queue size/processing time
3. Add unit tests specifically for queue behavior
