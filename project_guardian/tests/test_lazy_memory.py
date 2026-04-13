# project_guardian/tests/test_lazy_memory.py
# Regression tests for lazy/deferred memory semantics

import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.memory import MemoryCore


@pytest.fixture
def mem_file(tmp_path):
    """Create a memory JSON file with sample data."""
    path = tmp_path / "guardian_memory.json"
    data = [
        {"time": "2025-01-01T00:00:00", "thought": "test1", "category": "general", "priority": 0.5, "metadata": {}},
        {"time": "2025-01-01T00:00:01", "thought": "test2", "category": "general", "priority": 0.5, "metadata": {}},
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(path)


class TestLazyMemorySemantics:
    """Lazy/deferred memory loading behavior."""

    def test_lazy_mode_starts_unloaded(self, mem_file):
        """MemoryCore with lazy_load=True starts unloaded."""
        mem = MemoryCore(filepath=mem_file, lazy_load=True)
        assert mem.loaded is False
        assert mem.is_loaded() is False

    def test_get_memory_state_non_forcing_reports_unloaded(self, mem_file):
        """get_memory_state(load_if_needed=False) reports non-authoritative when unloaded."""
        mem = MemoryCore(filepath=mem_file, lazy_load=True)
        st = mem.get_memory_state(load_if_needed=False)
        assert st.get("memory_loaded") is False
        assert st.get("memory_count") is None
        assert st.get("memory_count_authoritative") is False

    def test_get_memory_count_non_forcing_returns_none_when_unloaded(self, mem_file):
        """get_memory_count(load_if_needed=False) returns None when unloaded."""
        mem = MemoryCore(filepath=mem_file, lazy_load=True)
        assert mem.get_memory_count(load_if_needed=False) is None

    def test_get_memory_count_forcing_loads_and_returns_real_count(self, mem_file):
        """get_memory_count(load_if_needed=True) forces load and returns real count."""
        mem = MemoryCore(filepath=mem_file, lazy_load=True)
        count = mem.get_memory_count(load_if_needed=True)
        assert count == 2
        assert mem.loaded is True

    def test_unloaded_not_interpreted_as_empty(self, mem_file):
        """Unloaded state: memory_count is None, not 0. Status must not treat None as empty."""
        mem = MemoryCore(filepath=mem_file, lazy_load=True)
        st = mem.get_memory_state(load_if_needed=False)
        assert st.get("memory_count") is None
        assert st.get("memory_count_authoritative") is False
        # Contract: None means "unknown", not "zero memories"

    def test_get_recent_memories_non_forcing_returns_empty_when_unloaded(self, mem_file):
        """get_recent_memories(load_if_needed=False) returns [] when unloaded."""
        mem = MemoryCore(filepath=mem_file, lazy_load=True)
        result = mem.get_recent_memories(limit=10, load_if_needed=False)
        assert result == []

    def test_get_recent_memories_forcing_loads_and_returns(self, mem_file):
        """get_recent_memories(load_if_needed=True) loads and returns entries."""
        mem = MemoryCore(filepath=mem_file, lazy_load=True)
        result = mem.get_recent_memories(limit=10, load_if_needed=True)
        assert len(result) == 2
