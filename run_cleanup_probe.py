#!/usr/bin/env python3
"""
Runtime Cleanup Probe
====================
Creates artificial memory load and triggers cleanup to verify effectiveness.
"""

import sys
import time
import gc
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from project_guardian.guardian_singleton import reset_singleton, get_guardian_core
from project_guardian.core import GuardianCore


def create_fake_memories(core, count: int):
    """Create fake memory entries to simulate high memory usage."""
    print(f"Creating {count} fake memories...")
    for i in range(count):
        core.memory.remember(
            f"[Probe] Fake memory entry {i} - " + "x" * 100,  # Add some size
            category="probe",
            priority=0.5
        )
    print(f"Created {count} memories. Current count: {len(core.memory.memory_log)}")


def create_fake_caches(core):
    """Create fake cache entries if possible."""
    print("Creating fake caches...")
    
    # Try to populate embedding cache
    memory_obj = core.memory
    if hasattr(core.memory, 'json_memory'):
        memory_obj = core.memory.json_memory
    
    if hasattr(memory_obj, 'vector_search') and memory_obj.vector_search:
        if hasattr(memory_obj.vector_search, 'embedding_cache'):
            for i in range(100):
                memory_obj.vector_search.embedding_cache[f"key_{i}"] = [0.1] * 384  # Fake embedding
            print(f"  Embedding cache: {len(memory_obj.vector_search.embedding_cache)} entries")
    
    # Try to populate web cache
    if hasattr(core, 'web_reader') and core.web_reader:
        if hasattr(core.web_reader, '_cache'):
            for i in range(50):
                core.web_reader._cache[f"url_{i}"] = "x" * 1000
            print(f"  Web cache: {len(core.web_reader._cache)} entries")
    
    # Try to populate proposal cache
    if hasattr(core, 'proposal_system') and core.proposal_system:
        if hasattr(core.proposal_system, '_cache'):
            for i in range(30):
                core.proposal_system._cache[f"prop_{i}"] = {"data": "x" * 500}
            print(f"  Proposal cache: {len(core.proposal_system._cache)} entries")


def get_rss_mb():
    """Get current RSS in MB."""
    try:
        import psutil
        import os
        process = psutil.Process(os.getpid())
        rss_bytes = process.memory_info().rss
        return round(rss_bytes / (1024 * 1024), 2)
    except:
        return None


def main():
    """Run cleanup probe."""
    print("=" * 70)
    print("CLEANUP PROBE - Runtime Evidence")
    print("=" * 70)
    print()
    
    # Reset singleton for clean test
    reset_singleton()
    GuardianCore._any_instance_initialized = False
    
    try:
        # Create GuardianCore instance
        print("Initializing GuardianCore...")
        core = get_guardian_core(config={}, force_new=True)
        
        if not core:
            print("[ERROR] Failed to create GuardianCore")
            return 1
        
        # Get initial metrics
        print("\n--- BEFORE SETUP ---")
        memory_obj = core.memory
        if hasattr(core.memory, 'json_memory'):
            memory_obj = core.memory.json_memory
        
        initial_count = len(memory_obj.memory_log)
        initial_rss = get_rss_mb()
        print(f"Initial memory count: {initial_count}")
        print(f"Initial RSS: {initial_rss}MB" if initial_rss else "Initial RSS: N/A (psutil not available)")
        
        # Create fake memories (enough to trigger cleanup)
        print("\n--- CREATING FAKE LOAD ---")
        target_count = 5000  # Over threshold
        create_fake_memories(core, target_count - initial_count)
        
        # Create fake caches
        create_fake_caches(core)
        
        # Get metrics after setup
        print("\n--- AFTER SETUP (BEFORE CLEANUP) ---")
        after_setup_count = len(memory_obj.memory_log)
        after_setup_rss = get_rss_mb()
        print(f"Memory count: {after_setup_count}")
        print(f"RSS: {after_setup_rss}MB" if after_setup_rss else "RSS: N/A")
        
        # Get cache sizes
        cache_sizes_before = {}
        if hasattr(memory_obj, 'vector_search') and memory_obj.vector_search:
            if hasattr(memory_obj.vector_search, 'embedding_cache'):
                cache_sizes_before["embedding_cache"] = len(memory_obj.vector_search.embedding_cache)
        
        if hasattr(core, 'web_reader') and core.web_reader:
            if hasattr(core.web_reader, '_cache'):
                cache_sizes_before["web_cache"] = len(core.web_reader._cache)
        
        if hasattr(core, 'proposal_system') and core.proposal_system:
            if hasattr(core.proposal_system, '_cache'):
                cache_sizes_before["proposal_cache"] = len(core.proposal_system._cache)
        
        print(f"Cache sizes before: {cache_sizes_before}")
        
        # Trigger cleanup
        print("\n--- TRIGGERING CLEANUP ---")
        memory_threshold = 3000
        if core.monitor:
            core.monitor._perform_cleanup(memory_threshold=memory_threshold)
        else:
            print("[WARN] SystemMonitor not available")
        
        # Wait a moment for cleanup to complete
        time.sleep(0.5)
        
        # Force GC
        gc.collect()
        time.sleep(0.2)
        
        # Get metrics after cleanup
        print("\n--- AFTER CLEANUP ---")
        after_cleanup_count = len(memory_obj.memory_log)
        after_cleanup_rss = get_rss_mb()
        print(f"Memory count: {after_cleanup_count}")
        print(f"RSS: {after_cleanup_rss}MB" if after_cleanup_rss else "RSS: N/A")
        
        # Get cache sizes after
        cache_sizes_after = {}
        if hasattr(memory_obj, 'vector_search') and memory_obj.vector_search:
            if hasattr(memory_obj.vector_search, 'embedding_cache'):
                cache_sizes_after["embedding_cache"] = len(memory_obj.vector_search.embedding_cache)
        
        if hasattr(core, 'web_reader') and core.web_reader:
            if hasattr(core.web_reader, '_cache'):
                cache_sizes_after["web_cache"] = len(core.web_reader._cache)
        
        if hasattr(core, 'proposal_system') and core.proposal_system:
            if hasattr(core.proposal_system, '_cache'):
                cache_sizes_after["proposal_cache"] = len(core.proposal_system._cache)
        
        print(f"Cache sizes after: {cache_sizes_after}")
        
        # Calculate deltas
        print("\n--- DELTAS ---")
        memory_delta = after_setup_count - after_cleanup_count
        print(f"Memory count delta: {after_setup_count} -> {after_cleanup_count} (removed {memory_delta})")
        
        if initial_rss and after_cleanup_rss:
            rss_delta = initial_rss - after_cleanup_rss
            print(f"RSS delta: {initial_rss}MB -> {after_cleanup_rss}MB (delta: {rss_delta:+.2f}MB)")
        else:
            print("RSS delta: N/A (psutil not available)")
        
        # Cache deltas
        for cache_name in set(list(cache_sizes_before.keys()) + list(cache_sizes_after.keys())):
            before_size = cache_sizes_before.get(cache_name, 0)
            after_size = cache_sizes_after.get(cache_name, 0)
            delta = before_size - after_size
            print(f"Cache {cache_name} delta: {before_size} -> {after_size} (removed {delta})")
        
        # Verification
        print("\n--- VERIFICATION ---")
        success = True
        
        if after_cleanup_count > after_setup_count:
            print(f"[FAIL] Memory count increased: {after_setup_count} -> {after_cleanup_count}")
            success = False
        else:
            print(f"[OK] Memory count did not increase: {after_setup_count} -> {after_cleanup_count}")
        
        if after_cleanup_count > memory_threshold:
            print(f"[FAIL] Memory count ({after_cleanup_count}) exceeds threshold ({memory_threshold})")
            success = False
        else:
            print(f"[OK] Memory count ({after_cleanup_count}) is at or below threshold ({memory_threshold})")
        
        if initial_rss and after_cleanup_rss:
            # RSS should stabilize or drop (allow small tolerance for measurement noise)
            if after_cleanup_rss > initial_rss + 10:  # Allow 10MB tolerance
                print(f"[WARN] RSS increased significantly: {initial_rss}MB -> {after_cleanup_rss}MB")
            else:
                print(f"[OK] RSS stabilized or dropped: {initial_rss}MB -> {after_cleanup_rss}MB")
        
        # Check caches were cleared
        all_caches_cleared = True
        for cache_name, after_size in cache_sizes_after.items():
            before_size = cache_sizes_before.get(cache_name, 0)
            if after_size >= before_size:
                print(f"[WARN] Cache {cache_name} not cleared: {before_size} -> {after_size}")
                all_caches_cleared = False
        
        if all_caches_cleared and cache_sizes_after:
            print("[OK] All caches were cleared")
        
        print("\n" + "=" * 70)
        if success:
            print("PROBE RESULT: SUCCESS")
        else:
            print("PROBE RESULT: FAILED")
        print("=" * 70)
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n[ERROR] Probe failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        try:
            reset_singleton()
            GuardianCore._any_instance_initialized = False
        except:
            pass


if __name__ == "__main__":
    sys.exit(main())
