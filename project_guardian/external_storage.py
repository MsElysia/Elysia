#!/usr/bin/env python3
"""
External Storage Management
===========================
Utilities for detecting and using external storage (USB drives, etc.) for memory storage
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

logger = logging.getLogger(__name__)
_fallback_warned: set = set()  # Paths we've already warned about (avoid spam)


def normalize_storage_root(path: str) -> str:
    """
    On Windows, ensure a drive letter (e.g. "F" or "F:") becomes drive root "F:\\"
    so that Path(root) / "ProjectGuardian" / ... yields F:\\ProjectGuardian\\...
    and not F:ProjectGuardian\\...
    """
    if not path or not path.strip():
        return path
    s = path.strip().rstrip("/\\")
    if os.name == "nt" and len(s) >= 1 and len(s) <= 2 and s[0].isalpha():
        if len(s) == 1:
            return s + ":\\"
        if s[1] == ":":
            return s + "\\"
    return path.strip().rstrip("/\\") or path


def detect_removable_drives() -> List[Dict[str, Any]]:
    """
    Detect all removable/USB drives.
    
    Returns:
        List of dictionaries with drive information
    """
    drives = []
    
    if not PSUTIL_AVAILABLE:
        logger.warning("psutil not available, cannot detect removable drives")
        return drives
    
    try:
        # Get all disk partitions
        partitions = psutil.disk_partitions()
        
        for partition in partitions:
            try:
                # Check if it's a removable drive
                # On Windows, removable drives often have 'removable' in fstype or are USB
                usage = psutil.disk_usage(partition.mountpoint)
                
                # Calculate free space in GB
                free_gb = usage.free / (1024 ** 3)
                total_gb = usage.total / (1024 ** 3)
                
                # Check if it looks like a removable drive
                # Windows: removable drives often have specific characteristics
                is_removable = (
                    'removable' in partition.opts.lower() or
                    partition.fstype.lower() in ['fat32', 'exfat', 'ntfs'] and free_gb > 1.0
                )
                
                # Also check if it's not the system drive
                is_system = partition.mountpoint.lower() in ['c:\\', 'c:/']
                
                if not is_system and free_gb > 1.0:  # At least 1GB free
                    drives.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total_gb": round(total_gb, 2),
                        "free_gb": round(free_gb, 2),
                        "used_gb": round((usage.used / (1024 ** 3)), 2),
                        "is_removable": is_removable,
                        "opts": partition.opts
                    })
            except PermissionError:
                # Skip drives we can't access
                continue
            except Exception as e:
                logger.debug(f"Error checking partition {partition.mountpoint}: {e}")
                continue
        
        # Sort by free space (largest first)
        drives.sort(key=lambda x: x['free_gb'], reverse=True)
        
    except Exception as e:
        logger.error(f"Error detecting removable drives: {e}")
    
    return drives


def find_best_external_drive(min_free_gb: float = 5.0) -> Optional[str]:
    """
    Find the best external drive for memory storage.
    
    Args:
        min_free_gb: Minimum free space required in GB
        
    Returns:
        Mount point path of best drive, or None if none found
    """
    drives = detect_removable_drives()
    
    if not drives:
        logger.info("No external drives detected")
        return None
    
    # Filter by minimum free space
    suitable_drives = [d for d in drives if d['free_gb'] >= min_free_gb]
    
    if not suitable_drives:
        logger.warning(f"No drives with at least {min_free_gb}GB free space")
        return None
    
    # Return the drive with most free space
    best_drive = suitable_drives[0]
    logger.info(f"Selected external drive: {best_drive['mountpoint']} ({best_drive['free_gb']}GB free)")
    return best_drive['mountpoint']


def setup_external_memory_storage(drive_path: str, project_name: str = "ProjectGuardian") -> Dict[str, str]:
    """
    Set up memory storage on external drive.
    
    Args:
        drive_path: Path to external drive (e.g., "E:\\" or "/media/usb")
        project_name: Name for the project folder
        
    Returns:
        Dictionary with storage paths
    """
    drive_path = Path(normalize_storage_root(str(drive_path).strip()))
    
    # Create project directory on external drive
    project_dir = drive_path / project_name
    memory_dir = project_dir / "memory"
    vectors_dir = memory_dir / "vectors"
    data_dir = project_dir / "data"
    
    # Create directories
    for directory in [project_dir, memory_dir, vectors_dir, data_dir]:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {directory}")
    
    # Return paths
    paths = {
        "base": str(project_dir),
        "memory_file": str(memory_dir / "guardian_memory.json"),
        "vector_index": str(vectors_dir / "index.faiss"),
        "vector_metadata": str(vectors_dir / "metadata.json"),
        "timeline_db": str(memory_dir / "elysia_timeline.db"),
        "data_dir": str(data_dir)
    }
    
    logger.info(f"External storage setup complete at: {project_dir}")
    return paths


def migrate_memory_to_external(
    source_memory_file: str,
    external_paths: Dict[str, str],
    source_vector_index: Optional[str] = None,
    source_vector_metadata: Optional[str] = None
) -> bool:
    """
    Migrate memory files to external storage.
    
    Args:
        source_memory_file: Path to current memory file
        external_paths: Dictionary with external storage paths
        source_vector_index: Path to current vector index (optional)
        source_vector_metadata: Path to current vector metadata (optional)
        
    Returns:
        True if migration successful
    """
    try:
        source_memory = Path(source_memory_file)
        
        if not source_memory.exists():
            logger.warning(f"Source memory file not found: {source_memory_file}")
            return False
        
        # Copy memory file
        dest_memory = Path(external_paths["memory_file"])
        shutil.copy2(source_memory, dest_memory)
        logger.info(f"Copied memory file: {source_memory} -> {dest_memory}")
        
        # Copy vector index if exists
        if source_vector_index:
            source_idx = Path(source_vector_index)
            if source_idx.exists():
                dest_idx = Path(external_paths["vector_index"])
                dest_idx.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_idx, dest_idx)
                logger.info(f"Copied vector index: {source_idx} -> {dest_idx}")
        
        # Copy vector metadata if exists
        if source_vector_metadata:
            source_meta = Path(source_vector_metadata)
            if source_meta.exists():
                dest_meta = Path(external_paths["vector_metadata"])
                dest_meta.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_meta, dest_meta)
                logger.info(f"Copied vector metadata: {source_meta} -> {dest_meta}")
        
        logger.info("[OK] Memory migration to external storage completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] Memory migration failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def get_default_fallback_path() -> Path:
    """
    Get default fallback path for memory storage.
    
    Returns:
        Path object for fallback storage location
    """
    import os
    # Try LOCALAPPDATA first (Windows)
    if os.name == 'nt':
        localappdata = os.environ.get('LOCALAPPDATA')
        if localappdata:
            return Path(localappdata) / "ElysiaGuardian" / "memory"
    
    # Fallback to home directory
    return Path.home() / ".elysia_guardian" / "memory"


def validate_and_resolve_storage_paths(
    external_config: Dict[str, Any],
    project_name: str = "ProjectGuardian"
) -> Dict[str, Any]:
    """
    Validate external storage paths and fallback to default if invalid.
    
    Args:
        external_config: External storage configuration dictionary
        project_name: Name for the project folder
        
    Returns:
        Validated configuration dictionary with resolved paths
    """
    external_drive = external_config.get("external_drive", "")
    fallback_drives = external_config.get("fallback_drives", [])
    original_drive = external_drive
    
    # Try primary drive, then fallback drives, before using LOCALAPPDATA
    candidates = [external_drive] + [d for d in fallback_drives if d and d != external_drive]
    drive_path = None
    chosen_drive = None
    for candidate in candidates:
        if not candidate:
            continue
        p = Path(normalize_storage_root(str(candidate).strip()))
        if p.exists():
            try:
                test_file = p / ".elysia_test_write"
                test_file.touch()
                test_file.unlink()
                drive_path = p
                chosen_drive = normalize_storage_root(str(candidate).strip())
                break
            except (PermissionError, OSError):
                continue
    
    use_fallback = drive_path is None
    fallback_reason = f"No writable drive among: {candidates}" if not chosen_drive else None
    
    if use_fallback:
        # Use fallback path
        fallback_base = get_default_fallback_path()
        fallback_base.mkdir(parents=True, exist_ok=True)
        # Only warn once per original path to reduce log noise
        if original_drive not in _fallback_warned:
            _fallback_warned.add(original_drive)
            logger.warning(
                f"[External Storage] Path validation failed: {fallback_reason}. "
                f"Falling back to: {fallback_base}"
            )
        
        # Setup paths using fallback location
        memory_dir = fallback_base
        vectors_dir = memory_dir / "vectors"
        data_dir = fallback_base.parent / "data"
        
        # Create directories
        for directory in [memory_dir, vectors_dir, data_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        resolved_paths = {
            "base": str(fallback_base),
            "memory_file": str(memory_dir / "guardian_memory.json"),
            "vector_index": str(vectors_dir / "index.faiss"),
            "vector_metadata": str(vectors_dir / "metadata.json"),
            "timeline_db": str(memory_dir / "elysia_timeline.db"),
            "data_dir": str(data_dir)
        }
        
        return {
            "use_external_storage": False,  # Mark as not external since we fell back
            "external_drive": None,
            "original_drive": original_drive,  # Keep for logging
            "fallback_used": True,
            "memory_filepath": resolved_paths["memory_file"],  # canonical key
            "vector_memory_config": {
                "index_path": resolved_paths["vector_index"],
                "metadata_path": resolved_paths["vector_metadata"]
            },
            "timeline_db_path": resolved_paths["timeline_db"],
            "data_dir": resolved_paths["data_dir"]
        }
    else:
        # Path is valid, use it
        logger.info(f"[External Storage] Using configured path: {chosen_drive}")
        
        # Setup storage paths on external drive
        paths = setup_external_memory_storage(chosen_drive, project_name)
        
        return {
            "use_external_storage": True,
            "external_drive": chosen_drive,
            "original_drive": original_drive,
            "fallback_used": False,
            "memory_filepath": paths["memory_file"],
            "vector_memory_config": {
                "index_path": paths["vector_index"],
                "metadata_path": paths["vector_metadata"]
            },
            "timeline_db_path": paths["timeline_db"],
            "data_dir": paths["data_dir"]
        }


def get_external_storage_config() -> Optional[Dict[str, Any]]:
    """
    Get configuration for external storage if available.
    
    Returns:
        Configuration dictionary or None if no external drive found
    """
    external_drive = find_best_external_drive(min_free_gb=5.0)
    
    if not external_drive:
        return None
    
    # Setup storage paths
    paths = setup_external_memory_storage(external_drive)
    
    return {
        "use_external_storage": True,
        "external_drive": external_drive,
        "memory_filepath": paths["memory_file"],
        "vector_memory_config": {
            "index_path": paths["vector_index"],
            "metadata_path": paths["vector_metadata"]
        },
        "timeline_db_path": paths["timeline_db"],
        "data_dir": paths["data_dir"]
    }

