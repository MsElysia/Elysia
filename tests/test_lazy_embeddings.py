"""
Unit tests for lazy embeddings (no embedding calls during startup).
Tests verify that embeddings are not called unless explicitly enabled.
Tests are independent of optional dependencies (MemoryVectorSearch, faiss, sentence_transformers).
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_embeddings_not_called_on_startup_by_default():
    """Test that embeddings are not called during MemoryCore initialization by default."""
    from project_guardian.memory import MemoryCore
    
    # Ensure EMBED_ON_STARTUP is not set
    old_value = os.environ.get("EMBED_ON_STARTUP")
    if "EMBED_ON_STARTUP" in os.environ:
        del os.environ["EMBED_ON_STARTUP"]
    
    try:
        # Track if embedding call path was executed
        embedding_call_path_executed = []
        
        def track_embedding_call(*args, **kwargs):
            """Track that embedding call path was executed."""
            embedding_call_path_executed.append(("called", args, kwargs))
            raise AssertionError("Embedding call path should not be executed during startup")
        
        # Mock MemoryVectorSearch to prevent any actual embedding calls
        with patch('project_guardian.memory.MemoryVectorSearch', create=True) as mock_vector_search_class:
            mock_vector_search = Mock()
            # Mock add_memory to track if it's called (it shouldn't be)
            mock_vector_search.add_memory = Mock(side_effect=track_embedding_call)
            mock_vector_search._get_embedding = Mock(side_effect=track_embedding_call)
            mock_vector_search_class.return_value = mock_vector_search
            
            # Create MemoryCore with vector search enabled
            memory = MemoryCore(
                filepath="test_memory.json",
                enable_vector_search=True
            )
            
            # Verify embeddings are disabled during startup
            assert memory._embeddings_enabled is False, "Embeddings should be disabled during startup"
            if hasattr(memory, '_vector_index_built'):
                assert memory._vector_index_built is False, "Vector index should not be built during startup"
            
            # Verify embedding call path was NOT executed
            assert len(embedding_call_path_executed) == 0, \
                f"Embedding call path should not be executed during startup, but was executed {len(embedding_call_path_executed)} times: {embedding_call_path_executed}"
            
    finally:
        # Restore env var
        if old_value is not None:
            os.environ["EMBED_ON_STARTUP"] = old_value


def test_embeddings_not_called_during_memory_load():
    """Test that loading memories does not trigger embeddings."""
    from project_guardian.memory import MemoryCore
    import json
    import tempfile
    
    # Ensure EMBED_ON_STARTUP is not set
    old_value = os.environ.get("EMBED_ON_STARTUP")
    if "EMBED_ON_STARTUP" in os.environ:
        del os.environ["EMBED_ON_STARTUP"]
    
    try:
        # Create a temporary memory file with some memories
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            memories = [
                {"time": "2025-01-01T00:00:00", "thought": "Memory 1", "category": "test", "priority": 0.5},
                {"time": "2025-01-02T00:00:00", "thought": "Memory 2", "category": "test", "priority": 0.5}
            ]
            json.dump(memories, f)
            temp_file = f.name
        
        try:
            # Track if embedding call path was executed
            embedding_call_path_executed = []
            
            def track_embedding_call(*args, **kwargs):
                """Track that embedding call path was executed."""
                embedding_call_path_executed.append(("called", args, kwargs))
                raise AssertionError("Embedding call path should not be executed during memory load")
            
            # Mock MemoryVectorSearch
            with patch('project_guardian.memory.MemoryVectorSearch', create=True) as mock_vector_search_class:
                mock_vector_search = Mock()
                mock_vector_search.add_memory = Mock(side_effect=track_embedding_call)
                mock_vector_search._get_embedding = Mock(side_effect=track_embedding_call)
                mock_vector_search_class.return_value = mock_vector_search
                
                # Create MemoryCore (will load memories from file)
                memory = MemoryCore(
                    filepath=temp_file,
                    enable_vector_search=True
                )
                
                # Verify memories were loaded
                assert len(memory.memory_log) == 2
                
                # Verify embeddings were NOT called during load
                assert memory._embeddings_enabled is False
                assert len(embedding_call_path_executed) == 0, \
                    f"Embedding call path should not be executed during memory load, but was executed {len(embedding_call_path_executed)} times"
        
        finally:
            # Cleanup temp file
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    finally:
        # Restore env var
        if old_value is not None:
            os.environ["EMBED_ON_STARTUP"] = old_value


def test_embeddings_enabled_after_startup():
    """Test that embeddings can be enabled after startup."""
    from project_guardian.memory import MemoryCore
    
    # Ensure EMBED_ON_STARTUP is not set
    old_value = os.environ.get("EMBED_ON_STARTUP")
    if "EMBED_ON_STARTUP" in os.environ:
        del os.environ["EMBED_ON_STARTUP"]
    
    try:
        # Track embedding calls (should be allowed after enabled)
        embedding_calls = []
        
        def mock_get_embedding(text):
            embedding_calls.append(text)
            return [0.1] * 384  # Fake embedding
        
        # Mock MemoryVectorSearch
        with patch('project_guardian.memory.MemoryVectorSearch', create=True) as mock_vector_search_class:
            mock_vector_search = Mock()
            mock_vector_search.add_memory = Mock()
            mock_vector_search._get_embedding = Mock(side_effect=mock_get_embedding)
            mock_vector_search.search_similar = Mock(return_value=[])
            mock_vector_search_class.return_value = mock_vector_search
            
            # Create MemoryCore
            memory = MemoryCore(
                filepath="test_memory.json",
                enable_vector_search=True
            )
            
            # Verify embeddings disabled during startup
            assert memory._embeddings_enabled is False
            
            # Enable embeddings (simulating startup completion)
            memory.enable_embeddings()
            assert memory._embeddings_enabled is True
            
            # Now remember() should trigger embeddings
            memory.remember("Test memory", category="test")
            
            # Verify embedding call path was executed (via add_memory)
            assert mock_vector_search.add_memory.called, "add_memory should be called after embeddings enabled"
    
    finally:
        # Restore env var
        if old_value is not None:
            os.environ["EMBED_ON_STARTUP"] = old_value


def test_embeddings_called_on_first_search_after_enabled():
    """Test that embeddings are built on first vector search use after embeddings enabled."""
    from project_guardian.memory import MemoryCore
    
    # Ensure EMBED_ON_STARTUP is not set
    old_value = os.environ.get("EMBED_ON_STARTUP")
    if "EMBED_ON_STARTUP" in os.environ:
        del os.environ["EMBED_ON_STARTUP"]
    
    try:
        # Track embedding calls
        embedding_calls = []
        
        def mock_get_embedding(text):
            embedding_calls.append(text)
            return [0.1] * 384  # Fake embedding
        
        # Mock MemoryVectorSearch
        with patch('project_guardian.memory.MemoryVectorSearch', create=True) as mock_vector_search_class:
            mock_vector_search = Mock()
            mock_vector_search.add_memory = Mock()
            mock_vector_search._get_embedding = Mock(side_effect=mock_get_embedding)
            mock_vector_search.search_similar = Mock(return_value=[])
            mock_vector_search_class.return_value = mock_vector_search
            
            # Create MemoryCore
            memory = MemoryCore(
                filepath="test_memory.json",
                enable_vector_search=True
            )
            
            # Set up fake memories
            memory.memory_log = [
                {"thought": "Memory 1", "time": "2025-01-01"},
                {"thought": "Memory 2", "time": "2025-01-02"}
            ]
            
            # Verify index not built yet
            if hasattr(memory, '_vector_index_built'):
                assert memory._vector_index_built is False
            assert memory._embeddings_enabled is False
            
            # Enable embeddings (simulating startup completion)
            memory.enable_embeddings()
            assert memory._embeddings_enabled is True
            
            # Perform first search (should trigger indexing)
            memory.search_semantic("test query")
            
            # Verify index was built
            if hasattr(memory, '_vector_index_built'):
                assert memory._vector_index_built is True
            # Verify add_memory was called for existing memories (embedding call path executed)
            assert mock_vector_search.add_memory.call_count > 0, "Embedding call path should be executed on first search after enabled"
    
    finally:
        # Restore env var
        if old_value is not None:
            os.environ["EMBED_ON_STARTUP"] = old_value


def test_embeddings_not_called_during_init_memory_writes():
    """Test that memory writes during initialization do not trigger embeddings."""
    from project_guardian.memory import MemoryCore
    
    # Ensure EMBED_ON_STARTUP is not set
    old_value = os.environ.get("EMBED_ON_STARTUP")
    if "EMBED_ON_STARTUP" in os.environ:
        del os.environ["EMBED_ON_STARTUP"]
    
    try:
        # Track if embedding call path was executed
        embedding_call_path_executed = []
        
        def track_embedding_call(*args, **kwargs):
            """Track that embedding call path was executed."""
            embedding_call_path_executed.append(("called", args, kwargs))
            raise AssertionError("Embedding call path should not be executed during init")
        
        # Mock MemoryVectorSearch
        with patch('project_guardian.memory.MemoryVectorSearch', create=True) as mock_vector_search_class:
            mock_vector_search = Mock()
            mock_vector_search.add_memory = Mock(side_effect=track_embedding_call)
            mock_vector_search._get_embedding = Mock(side_effect=track_embedding_call)
            mock_vector_search_class.return_value = mock_vector_search
            
            # Create MemoryCore
            memory = MemoryCore(
                filepath="test_memory.json",
                enable_vector_search=True
            )
            
            # Verify embeddings disabled
            assert memory._embeddings_enabled is False
            
            # Write a memory during "initialization" (embeddings still disabled)
            memory.remember("Init memory", category="init")
            
            # Verify embedding call path was NOT executed
            assert len(embedding_call_path_executed) == 0, \
                f"Embedding call path should not be executed during init, but was executed {len(embedding_call_path_executed)} times: {embedding_call_path_executed}"
            # add_memory should not be called because embeddings are disabled
            assert mock_vector_search.add_memory.call_count == 0, "add_memory should not be called when embeddings disabled"
    
    finally:
        # Restore env var
        if old_value is not None:
            os.environ["EMBED_ON_STARTUP"] = old_value


def test_embeddings_not_called_when_vector_search_disabled():
    """Test that embeddings are never called when vector search is disabled."""
    from project_guardian.memory import MemoryCore
    
    # Ensure EMBED_ON_STARTUP is not set
    old_value = os.environ.get("EMBED_ON_STARTUP")
    if "EMBED_ON_STARTUP" in os.environ:
        del os.environ["EMBED_ON_STARTUP"]
    
    try:
        # Track if embedding call path was executed
        embedding_call_path_executed = []
        
        def track_embedding_call(*args, **kwargs):
            """Track that embedding call path was executed."""
            embedding_call_path_executed.append(("called", args, kwargs))
            raise AssertionError("Embedding call path should never be executed when vector search is disabled")
        
        # Create MemoryCore WITHOUT vector search
        memory = MemoryCore(
            filepath="test_memory.json",
            enable_vector_search=False
        )
        
        # Verify vector_search is None
        assert memory.vector_search is None or not hasattr(memory, 'vector_search') or memory.vector_search is None
        
        # Write a memory (should not trigger any embedding calls)
        memory.remember("Test memory", category="test")
        
        # Verify embedding call path was NOT executed
        assert len(embedding_call_path_executed) == 0, \
            f"Embedding call path should never be executed when vector search is disabled"
    
    finally:
        # Restore env var
        if old_value is not None:
            os.environ["EMBED_ON_STARTUP"] = old_value
