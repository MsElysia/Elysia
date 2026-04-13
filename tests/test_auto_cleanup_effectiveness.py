"""
Unit tests for auto-cleanup effectiveness.
Verifies that cleanup reduces memory count and never increases it.
"""

import pytest
import sys
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_cleanup_reduces_memory_count():
    """Test that cleanup reduces memory count when over threshold"""
    import tempfile
    from project_guardian.memory import MemoryCore
    from project_guardian.memory_cleanup import MemoryCleanup
    
    # Create memory with temporary file to avoid loading existing memories
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        memory = MemoryCore(filepath=temp_file)
        
        # Clear any loaded memories
        memory.memory_log = []
        
        # Add memories beyond threshold
        threshold = 100
        initial_count = 150
        
        for i in range(initial_count):
            memory.remember(
                f"Test memory {i}",
                category="test",
                priority=0.3  # Low priority so they can be removed
            )
        
        assert len(memory.memory_log) == initial_count
    
        # Run cleanup
        cleanup = MemoryCleanup(memory)
        result = cleanup.consolidate_memories(max_memories=threshold, keep_recent_days=30)
        
        # Verify cleanup worked
        assert "error" not in result
        assert result["final_count"] <= threshold
        assert result["removed"] > 0
        assert len(memory.memory_log) <= threshold
        assert len(memory.memory_log) < initial_count
    finally:
        # Cleanup temp file
        import os
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_cleanup_never_increases_count():
    """Test that cleanup never increases memory count"""
    import tempfile
    import os
    from project_guardian.memory import MemoryCore
    from project_guardian.memory_cleanup import MemoryCleanup
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        memory = MemoryCore(filepath=temp_file)
        memory.memory_log = []
        
        # Add some memories
        initial_count = 50
        for i in range(initial_count):
            memory.remember(f"Test memory {i}", category="test", priority=0.5)
        
        before_count = len(memory.memory_log)
        
        # Run cleanup with threshold higher than current count
        cleanup = MemoryCleanup(memory)
        result = cleanup.consolidate_memories(max_memories=1000, keep_recent_days=30)
        
        after_count = len(memory.memory_log)
        
        # Count should not increase
        assert after_count <= before_count
        assert "error" not in result
        assert result["final_count"] <= before_count
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_force_trim_reduces_to_max():
    """Test that force_trim reduces memory to exactly max_memories"""
    import tempfile
    import os
    from project_guardian.monitoring import SystemMonitor
    from project_guardian.memory import MemoryCore
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        memory = MemoryCore(filepath=temp_file)
        memory.memory_log = []
        guardian = Mock()
        
        # Add many memories
        for i in range(200):
            memory.remember(f"Test {i}", category="test", priority=0.3)
        
        assert len(memory.memory_log) == 200
        
        # Create monitor and force trim
        monitor = SystemMonitor(memory, guardian)
        monitor._force_trim_memory(memory, max_memories=100)
        
        # Should be exactly 100 (most recent)
        assert len(memory.memory_log) == 100
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_max_memories_cap_enforced():
    """Test that max_memories cap is enforced during remember()"""
    import tempfile
    import os
    from project_guardian.memory import MemoryCore
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        memory = MemoryCore(filepath=temp_file, max_memories=50)
        memory.memory_log = []
        
        # Add more than max
        for i in range(60):
            memory.remember(f"Test {i}", category="test")
        
        # Should be capped at max_memories
        assert len(memory.memory_log) == 50
        # Should have the most recent 50
        assert "Test 10" in memory.memory_log[0]["thought"]  # First entry should be 10 (60-50)
        assert "Test 59" in memory.memory_log[-1]["thought"]  # Last entry should be 59
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_cache_clearing():
    """Test that caches are cleared during cleanup"""
    from project_guardian.monitoring import SystemMonitor
    from project_guardian.memory import MemoryCore
    
    memory = MemoryCore()
    guardian = Mock()
    
    # Mock vector search with cache
    memory.vector_search = Mock()
    memory.vector_search.embedding_cache = {"key1": "value1", "key2": "value2"}
    
    # Mock web_reader with cache
    guardian.web_reader = Mock()
    guardian.web_reader._cache = {"url1": "data1", "url2": "data2"}
    
    monitor = SystemMonitor(memory, guardian)
    
    # Clear caches
    monitor._clear_caches(memory)
    
    # Caches should be empty
    assert len(memory.vector_search.embedding_cache) == 0
    assert len(guardian.web_reader._cache) == 0


def test_cleanup_metrics_logging():
    """Test that cleanup metrics are collected correctly"""
    import tempfile
    import os
    from project_guardian.monitoring import SystemMonitor
    from project_guardian.memory import MemoryCore
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        memory = MemoryCore(filepath=temp_file)
        memory.memory_log = []
        guardian = Mock()
        
        # Add some memories
        for i in range(10):
            memory.remember(f"Test {i}", category="test")
        
        monitor = SystemMonitor(memory, guardian)
        
        # Get metrics
        metrics = monitor._get_cleanup_metrics()
        
        # Should have memory_count
        assert "memory_count" in metrics
        assert metrics["memory_count"] == 10
        
        # Should have cache_sizes
        assert "cache_sizes" in metrics
        
        # RSS might be None if psutil not available, but key should exist
        assert "rss_mb" in metrics
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_cleanup_with_heartbeat_pulse():
    """Test that cleanup works even when heartbeat adds memories during cleanup"""
    import tempfile
    import os
    from project_guardian.monitoring import Heartbeat
    from project_guardian.memory import MemoryCore
    from project_guardian.memory_cleanup import MemoryCleanup
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        memory = MemoryCore(filepath=temp_file)
        memory.memory_log = []
        
        # Add many memories
        for i in range(150):
            memory.remember(f"Test {i}", category="test", priority=0.3)
        
        initial_count = len(memory.memory_log)
        
        # Create heartbeat (which will add a pulse memory)
        heartbeat = Heartbeat(memory, interval=30)
        
        # Run cleanup
        cleanup = MemoryCleanup(memory)
        result = cleanup.consolidate_memories(max_memories=100, keep_recent_days=30)
        
        # Even if heartbeat adds a memory, cleanup should still reduce count
        # (The consolidate happens before new memories are added in the next heartbeat cycle)
        assert "error" not in result
        assert result["final_count"] <= 100
        assert result["removed"] > 0
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_consolidate_preserves_recent_memories():
    """Test that consolidate preserves recent memories even if over threshold"""
    import tempfile
    import os
    from project_guardian.memory import MemoryCore
    from project_guardian.memory_cleanup import MemoryCleanup
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        memory = MemoryCore(filepath=temp_file)
        memory.memory_log = []
        
        # Add old memories
        old_time = (datetime.datetime.now() - datetime.timedelta(days=60)).isoformat()
        for i in range(100):
            entry = {
                "time": old_time,
                "thought": f"Old memory {i}",
                "category": "test",
                "priority": 0.3
            }
            memory.memory_log.append(entry)
        
        # Add recent memories
        for i in range(50):
            memory.remember(f"Recent memory {i}", category="test", priority=0.3)
        
        assert len(memory.memory_log) == 150
        
        # Run cleanup with keep_recent_days=30
        cleanup = MemoryCleanup(memory)
        result = cleanup.consolidate_memories(max_memories=100, keep_recent_days=30)
        
        # Should keep recent memories (50) and some old high-priority ones
        assert "error" not in result
        assert result["final_count"] <= 100
        # Recent memories should be preserved
        recent_count = sum(1 for m in memory.memory_log if "Recent memory" in m.get("thought", ""))
        assert recent_count == 50  # All recent memories should be kept
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)
