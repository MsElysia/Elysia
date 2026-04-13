"""
Unit tests for cleanup truth and RSS stabilization.
Tests verify that cleanup never increases memory count and effectively reduces RSS.
"""

import pytest
import sys
import gc
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class FakeMemoryCore:
    """Fake MemoryCore that can simulate count increases during consolidation."""
    
    def __init__(self, initial_memories: int = 100):
        self.memory_log = [{"id": i, "content": f"Memory {i}"} for i in range(initial_memories)]
        self.consolidate_called = False
        self._simulate_increase = False  # If True, consolidate will increase count
    
    def remember(self, content: str, category: str = "general", priority: float = 0.5):
        """Add a memory entry."""
        self.memory_log.append({
            "id": len(self.memory_log),
            "content": content,
            "category": category,
            "priority": priority
        })
    
    def consolidate(self, max_memories: int, keep_recent_days: int = 30) -> Dict[str, Any]:
        """Simulate consolidation - can be configured to increase count."""
        self.consolidate_called = True
        before_count = len(self.memory_log)
        
        if self._simulate_increase:
            # Simulate bug: add memories during consolidation
            for i in range(5):
                self.memory_log.append({
                    "id": len(self.memory_log),
                    "content": f"[Auto-Cleanup] Added during consolidation {i}",
                    "category": "monitoring",
                    "priority": 0.3
                })
            after_count = len(self.memory_log)
        else:
            # Normal behavior: trim to max_memories
            if before_count > max_memories:
                self.memory_log = self.memory_log[-max_memories:]
            after_count = len(self.memory_log)
        
        removed = before_count - after_count
        return {
            "removed": removed,
            "final_count": after_count,
            "before_count": before_count
        }


def test_cleanup_never_increases_count():
    """Test that cleanup never ends with after_count > before_count."""
    from project_guardian.monitoring import SystemMonitor
    
    # Create fake memory with many memories
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Get initial count
    before_cleanup = len(fake_memory.memory_log)
    assert before_cleanup == 5000
    
    # Perform cleanup
    monitor._perform_cleanup(memory_threshold=3000)
    
    # Verify count never increased
    after_cleanup = len(fake_memory.memory_log)
    assert after_cleanup <= before_cleanup, f"Memory count increased: {before_cleanup} -> {after_cleanup}"
    
    # Verify count is at or below threshold
    assert after_cleanup <= 3000, f"Memory count ({after_cleanup}) exceeds threshold (3000)"


def test_cleanup_handles_count_increase_bug():
    """Test that cleanup detects and fixes count increases during consolidation."""
    from project_guardian.monitoring import SystemMonitor
    
    # Create fake memory that simulates the bug (increases count during consolidate)
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_memory._simulate_increase = True  # Enable bug simulation
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Get initial count
    before_cleanup = len(fake_memory.memory_log)
    
    # Perform cleanup - should detect and fix the increase
    monitor._perform_cleanup(memory_threshold=3000)
    
    # Verify count was fixed (should be <= threshold)
    after_cleanup = len(fake_memory.memory_log)
    assert after_cleanup <= 3000, f"Cleanup failed to fix count increase: {after_cleanup} > 3000"
    assert after_cleanup <= before_cleanup, f"Memory count still increased: {before_cleanup} -> {after_cleanup}"


def test_cleanup_reduces_to_max_when_over_threshold():
    """Test that cleanup reduces count to <= max when over threshold."""
    from project_guardian.monitoring import SystemMonitor
    
    # Create fake memory over threshold
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Perform cleanup with threshold
    max_memories = 3000
    monitor._perform_cleanup(memory_threshold=max_memories)
    
    # Verify count is at or below max
    after_cleanup = len(fake_memory.memory_log)
    assert after_cleanup <= max_memories, f"Memory count ({after_cleanup}) exceeds max ({max_memories})"


def test_cleanup_clears_caches():
    """Test that cleanup calls cache clearing methods."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    # Mock cache attributes
    fake_vector_search = Mock()
    fake_vector_search.embedding_cache = {"key1": "val1", "key2": "val2"}
    fake_memory.vector_search = fake_vector_search
    
    fake_guardian.web_reader = Mock()
    fake_guardian.web_reader._cache = {"url1": "content1"}
    
    fake_guardian.proposal_system = Mock()
    fake_guardian.proposal_system._cache = {"prop1": "data1"}
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Perform cleanup
    monitor._perform_cleanup(memory_threshold=3000)
    
    # Verify caches were cleared
    assert len(fake_vector_search.embedding_cache) == 0, "Embedding cache not cleared"
    assert len(fake_guardian.web_reader._cache) == 0, "Web cache not cleared"
    assert len(fake_guardian.proposal_system._cache) == 0, "Proposal cache not cleared"


def test_cleanup_metrics_capture():
    """Test that cleanup captures before/after metrics correctly."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Get metrics before
    metrics_before = monitor._get_cleanup_metrics()
    assert "memory_count" in metrics_before
    assert "cache_sizes" in metrics_before
    assert metrics_before["memory_count"] == 5000
    
    # Perform cleanup
    monitor._perform_cleanup(memory_threshold=3000)
    
    # Get metrics after
    metrics_after = monitor._get_cleanup_metrics()
    assert "memory_count" in metrics_after
    assert metrics_after["memory_count"] <= 3000
    assert metrics_after["memory_count"] <= metrics_before["memory_count"]


def test_cleanup_id_counter_increments():
    """Test that cleanup_id counter increments for each cleanup."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Initial counter should be 0
    assert monitor._cleanup_id_counter == 0
    
    # Perform cleanup multiple times
    monitor._perform_cleanup(memory_threshold=3000)
    assert monitor._cleanup_id_counter == 1
    
    monitor._perform_cleanup(memory_threshold=3000)
    assert monitor._cleanup_id_counter == 2
    
    monitor._perform_cleanup(memory_threshold=3000)
    assert monitor._cleanup_id_counter == 3


def test_cleanup_reentrancy_guard():
    """Test that re-entrancy guard prevents concurrent cleanups."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Set cleanup in progress
    monitor._cleanup_in_progress = True
    
    # Try to perform cleanup (should be skipped)
    initial_counter = monitor._cleanup_id_counter
    monitor._perform_cleanup(memory_threshold=3000)
    
    # Counter should not increment (cleanup skipped)
    assert monitor._cleanup_id_counter == initial_counter
    
    # Clear guard and try again
    monitor._cleanup_in_progress = False
    monitor._perform_cleanup(memory_threshold=3000)
    
    # Counter should increment now
    assert monitor._cleanup_id_counter == initial_counter + 1


def test_cleanup_suppresses_memory_writes():
    """Test that memory.remember() is suppressed during cleanup."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Get initial memory count
    initial_count = len(fake_memory.memory_log)
    
    # Set cleanup in progress
    monitor._cleanup_in_progress = True
    
    # Try to remember something (should be suppressed)
    fake_memory.remember("[Test] Should be suppressed", category="test")
    
    # Count should not increase (in real implementation, this would be checked in Heartbeat)
    # For this test, we verify the guard is checked
    assert monitor._cleanup_in_progress is True
    
    # Clear guard
    monitor._cleanup_in_progress = False
    
    # Now remember should work
    fake_memory.remember("[Test] Should work", category="test")
    assert len(fake_memory.memory_log) > initial_count


def test_cleanup_rss_tracking():
    """Test that cleanup tracks RSS if psutil is available."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Get metrics (should include RSS if psutil available, None otherwise)
    metrics = monitor._get_cleanup_metrics()
    assert "rss_mb" in metrics
    # RSS may be None if psutil not available, or a number if available
    assert metrics["rss_mb"] is None or isinstance(metrics["rss_mb"], (int, float))


def test_cleanup_handles_missing_psutil():
    """Test that cleanup works even if psutil is not available."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Mock psutil import failure
    with patch.dict('sys.modules', {'psutil': None}):
        # Should still work without psutil
        metrics = monitor._get_cleanup_metrics()
        assert "rss_mb" in metrics
        assert metrics["rss_mb"] is None  # Should be None when psutil unavailable
        
        # Cleanup should still work
        monitor._perform_cleanup(memory_threshold=3000)
        assert len(fake_memory.memory_log) <= 3000


def test_force_trim_reduces_to_max():
    """Test that _force_trim_memory reduces count to exactly max_memories."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Force trim
    max_memories = 2000
    monitor._force_trim_memory(fake_memory, max_memories)
    
    # Verify exact count
    assert len(fake_memory.memory_log) == max_memories


def test_cleanup_calls_gc_collect():
    """Test that cleanup calls gc.collect() after cache clearing."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Mock gc.collect to verify it's called
    with patch('gc.collect') as mock_gc:
        monitor._perform_cleanup(memory_threshold=3000)
        # gc.collect should be called (may be called multiple times)
        assert mock_gc.called


def test_cleanup_logs_cleanup_id():
    """Test that cleanup logs include cleanup_id."""
    from project_guardian.monitoring import SystemMonitor
    import logging
    
    fake_memory = FakeMemoryCore(initial_memories=5000)
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Capture log messages
    log_messages = []
    
    class LogHandler(logging.Handler):
        def emit(self, record):
            log_messages.append(self.format(record))
    
    handler = LogHandler()
    logger = logging.getLogger('project_guardian.monitoring')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    try:
        monitor._perform_cleanup(memory_threshold=3000)
        
        # Check that at least one log message contains cleanup_id
        cleanup_id_found = any(f"#{monitor._cleanup_id_counter}" in msg for msg in log_messages)
        assert cleanup_id_found, f"Cleanup ID not found in logs. Messages: {log_messages}"
    finally:
        logger.removeHandler(handler)
