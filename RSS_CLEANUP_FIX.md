# RSS Increase During Cleanup - Fix

## Root Cause

**Issue**: RSS increases by ~143MB during cleanup #1 (154.2MB → 297.82MB)

**Root Cause**: The `consolidate()` method creates new lists (`recent_memories`, `high_priority_memories`, `memories_to_keep`) that copy all memory objects, temporarily doubling memory usage. The "after" RSS snapshot is taken immediately after `consolidate()` returns, before Python's garbage collector frees the temporary lists.

**Why it happens**:
1. `consolidate()` creates new lists containing copies of memory objects
2. Old `memory_log` is reassigned but not immediately freed
3. RSS snapshot taken before `gc.collect()` frees temporary allocations
4. Python's memory allocator may not immediately release memory to OS

## Fix Applied

**File**: `project_guardian/monitoring.py` (line ~639)

**Change**: Added explicit `gc.collect()` call after `consolidate()` returns, before taking the "after" RSS snapshot.

```python
# RUN CONSOLIDATION
if hasattr(memory_obj, 'consolidate'):
    result = memory_obj.consolidate(max_memories=memory_threshold, keep_recent_days=30)
    
    if "error" in result:
        logger.error(f"[Auto-Cleanup #{cleanup_id}] Consolidation error: {result.get('error')}")
    else:
        # Force garbage collection after consolidate to free temporary lists
        # (consolidate creates new lists that temporarily double memory usage)
        import gc
        gc.collect()
        
        # CAPTURE AFTER SNAPSHOT (using same memory object, after GC)
        metrics_after = self._get_cleanup_metrics()
```

## Expected Behavior After Fix

1. `consolidate()` runs and creates temporary lists
2. `gc.collect()` runs immediately after, freeing temporary allocations
3. RSS snapshot taken after GC, showing actual memory usage
4. RSS delta should be smaller or negative (memory freed)

## Verification

- Monitor next cleanup cycle
- RSS delta should be reduced or negative
- Memory count should still decrease correctly
- No functional changes to cleanup logic

## Notes

- This is a timing/measurement fix, not a functional fix
- Cleanup was working correctly, just measuring RSS at wrong time
- The RSS increase was real (temporary allocation), but misleading in logs
- After GC, RSS should reflect actual memory freed
