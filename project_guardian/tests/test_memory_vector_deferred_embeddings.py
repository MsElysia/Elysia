# project_guardian/tests/test_memory_vector_deferred_embeddings.py

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_enhanced_memory_defers_vector_add_until_embeddings_enabled(tmp_path):
    from project_guardian.memory_vector import EnhancedMemoryCore

    memory = EnhancedMemoryCore(
        json_filepath=str(tmp_path / "guardian_memory.json"),
        enable_vector=False,
        defer_embeddings=True,
    )

    calls = []

    class StubVectorMemory:
        def add_memory(self, **kwargs):
            calls.append(kwargs)

    memory.vector_memory = StubVectorMemory()

    assert getattr(memory.json_memory, "_embeddings_enabled", False) is False

    memory.remember(
        "Meaningful startup memory that should stay out of vector storage",
        category="system",
        priority=0.9,
    )
    assert calls == []

    memory.json_memory.enable_embeddings()
    memory.remember(
        "Meaningful post-startup memory that should reach vector storage",
        category="system",
        priority=0.9,
    )

    assert len(calls) == 1
    assert calls[0]["text"] == "Meaningful post-startup memory that should reach vector storage"
    assert calls[0]["category"] == "system"
