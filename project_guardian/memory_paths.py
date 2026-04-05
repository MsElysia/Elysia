# project_guardian/memory_paths.py
# Centralized memory file path resolution.
# Single source of truth: no drift between memory_filepath, memory_file, memory_path.

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Canonical config key
MEMORY_FILEPATH_KEY = "memory_filepath"

# Legacy compatibility aliases (checked in order if canonical absent)
LEGACY_KEYS = ("memory_file", "memory_path")

# One-time compatibility log (avoid spamming)
_compat_logged: set = set()


def resolve_memory_paths(
    config: Dict[str, Any],
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Resolve memory file path from config. Canonical key: memory_filepath.
    Legacy aliases: memory_file, memory_path (normalized with one-time log).

    If both memory_filepath and a legacy key are present and disagree, prefer
    memory_filepath and log a warning.

    Returns:
        dict with:
          - memory_filepath: str (authoritative resolved path)
          - vector_memory_config: dict with index_path, metadata_path (derived from memory root)
        Existing vector_memory_config in config is merged; derived paths override defaults.
    """
    proj = Path(project_root) if project_root else Path.cwd()
    canonical = config.get(MEMORY_FILEPATH_KEY)
    legacy_val = None
    legacy_key_used = None
    for key in LEGACY_KEYS:
        if key in config and config[key]:
            legacy_val = config[key]
            legacy_key_used = key
            break

    if canonical and legacy_val and str(canonical).strip() != str(legacy_val).strip():
        logger.warning(
            "[Config] memory_filepath and %s disagree: memory_filepath=%r, %s=%r; using memory_filepath",
            legacy_key_used, canonical, legacy_key_used, legacy_val,
        )
        resolved = str(canonical).strip()
    elif canonical:
        resolved = str(canonical).strip()
    elif legacy_val:
        resolved = str(legacy_val).strip()
        key = f"legacy_{legacy_key_used}"
        if key not in _compat_logged:
            _compat_logged.add(key)
            logger.info(
                "[Config] Using legacy %s; normalized to memory_filepath: %s",
                legacy_key_used, resolved,
            )
    else:
        resolved = str(proj / "guardian_memory.json")

    # Normalize to absolute path
    p = Path(resolved)
    if not p.is_absolute():
        p = (proj / p).resolve()
    # Preserve forward slashes for /tmp etc on Windows when input was path-like
    resolved = str(p)

    # Derive vector paths from memory file directory
    mem_dir = p.parent
    vectors_dir = mem_dir / "vectors"
    vector_config = dict(config.get("vector_memory_config") or {})
    vector_config.setdefault("index_path", str(vectors_dir / "index.faiss"))
    vector_config.setdefault("metadata_path", str(vectors_dir / "metadata.json"))

    return {
        MEMORY_FILEPATH_KEY: resolved,
        "vector_memory_config": vector_config,
    }


def get_memory_file_path(
    config: Dict[str, Any],
    project_root: Optional[Path] = None,
) -> str:
    """Convenience: return only the resolved memory file path."""
    return resolve_memory_paths(config, project_root)[MEMORY_FILEPATH_KEY]
