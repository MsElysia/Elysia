# project_guardian/tests/test_memory_paths.py
# Regression tests for canonical memory path resolution

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.memory_paths import (
    resolve_memory_paths,
    get_memory_file_path,
    MEMORY_FILEPATH_KEY,
    LEGACY_KEYS,
)


class TestMemoryPathResolution:
    """Canonical memory path resolution."""

    def test_memory_filepath_is_canonical(self, tmp_path):
        """memory_filepath is used when present."""
        cfg = {"memory_filepath": str(tmp_path / "canonical.json")}
        out = resolve_memory_paths(cfg, tmp_path)
        assert out[MEMORY_FILEPATH_KEY] == str((tmp_path / "canonical.json").resolve())

    def test_memory_file_fallback(self, tmp_path):
        """memory_file used when memory_filepath absent."""
        cfg = {"memory_file": "legacy_mem.json"}
        out = resolve_memory_paths(cfg, tmp_path)
        expected = (tmp_path / "legacy_mem.json").resolve()
        assert out[MEMORY_FILEPATH_KEY] == str(expected)

    def test_memory_path_fallback_when_canonical_absent(self, tmp_path):
        """memory_path used only when canonical and memory_file absent."""
        cfg = {"memory_path": "data/store.json"}
        out = resolve_memory_paths(cfg, tmp_path)
        expected = (tmp_path / "data" / "store.json").resolve()
        assert out[MEMORY_FILEPATH_KEY] == str(expected)

    def test_conflict_prefers_memory_filepath(self, tmp_path):
        """When both memory_filepath and legacy disagree, memory_filepath wins."""
        cfg = {
            "memory_filepath": str(tmp_path / "canonical.json"),
            "memory_file": str(tmp_path / "legacy.json"),
        }
        out = resolve_memory_paths(cfg, tmp_path)
        assert "canonical" in out[MEMORY_FILEPATH_KEY]
        assert "legacy" not in out[MEMORY_FILEPATH_KEY]

    def test_vector_paths_derived_from_memory_root(self, tmp_path):
        """Vector index/metadata derive from same memory file directory."""
        mem = tmp_path / "subdir" / "guardian_memory.json"
        mem.parent.mkdir(parents=True, exist_ok=True)
        cfg = {"memory_filepath": str(mem)}
        out = resolve_memory_paths(cfg, tmp_path)
        vc = out.get("vector_memory_config", {})
        assert "vectors" in vc.get("index_path", "")
        assert "vectors" in vc.get("metadata_path", "")
        assert "subdir" in vc.get("index_path", "") or str(mem.parent) in vc.get("index_path", "")

    def test_default_when_all_absent(self, tmp_path):
        """Default path when no keys present."""
        out = resolve_memory_paths({}, tmp_path)
        assert "guardian_memory" in out[MEMORY_FILEPATH_KEY]

    def test_get_memory_file_path_convenience(self, tmp_path):
        """get_memory_file_path returns only path string."""
        cfg = {"memory_filepath": str(tmp_path / "x.json")}
        path = get_memory_file_path(cfg, tmp_path)
        assert isinstance(path, str)
        assert "x.json" in path
