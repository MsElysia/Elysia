"""
Memory Storage Configuration
Configures Elysia to use F: drive (thumb drive) for memory storage
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MemoryStorageConfig:
    """
    Manages memory storage configuration for Elysia.
    Supports thumb drive (F:) and local storage fallback.
    """
    
    def __init__(self, thumb_drive: str = "F:", fallback_local: bool = True):
        """
        Initialize memory storage configuration.
        
        Args:
            thumb_drive: Thumb drive letter (e.g., "F:")
            fallback_local: Fallback to local storage if thumb drive unavailable
        """
        self.thumb_drive = thumb_drive
        self.fallback_local = fallback_local
        self.storage_path = self._determine_storage_path()
        
        logger.info(f"Memory storage configured: {self.storage_path}")
    
    def _determine_storage_path(self) -> Path:
        """Determine the best storage path"""
        # Check if thumb drive is available
        thumb_path = Path(f"{self.thumb_drive}/ElysiaMemory")
        
        if self._is_drive_available(self.thumb_drive):
            try:
                # Create directory if it doesn't exist
                thumb_path.mkdir(parents=True, exist_ok=True)
                
                # Test write access
                test_file = thumb_path / ".elysia_test"
                test_file.write_text("test")
                test_file.unlink()
                
                logger.info(f"Using thumb drive storage: {thumb_path}")
                return thumb_path
            except Exception as e:
                logger.warning(f"Thumb drive available but not writable: {e}")
                if self.fallback_local:
                    return self._get_local_fallback()
        else:
            logger.warning(f"Thumb drive {self.thumb_drive} not available")
            if self.fallback_local:
                return self._get_local_fallback()
        
        # Last resort: use current directory
        return Path("elysia_memory")
    
    def _is_drive_available(self, drive: str) -> bool:
        """Check if drive is available"""
        try:
            drive_path = Path(drive)
            return drive_path.exists() and drive_path.is_dir()
        except:
            return False
    
    def _get_local_fallback(self) -> Path:
        """Get local fallback path"""
        local_path = Path.home() / "ElysiaMemory"
        local_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using local fallback storage: {local_path}")
        return local_path
    
    def get_memory_file_path(self, filename: str = "guardian_memory.json") -> Path:
        """Get full path for memory file"""
        return self.storage_path / filename
    
    def get_trust_file_path(self, filename: str = "enhanced_trust.json") -> Path:
        """Get full path for trust file"""
        return self.storage_path / filename
    
    def get_tasks_file_path(self, filename: str = "enhanced_tasks.json") -> Path:
        """Get full path for tasks file"""
        return self.storage_path / filename
    
    def get_backup_path(self) -> Path:
        """Get backup directory path"""
        backup_path = self.storage_path / "backups"
        backup_path.mkdir(exist_ok=True)
        return backup_path
    
    def get_config(self) -> Dict[str, Any]:
        """Get storage configuration"""
        return {
            "storage_path": str(self.storage_path),
            "thumb_drive": self.thumb_drive,
            "thumb_drive_available": self._is_drive_available(self.thumb_drive),
            "fallback_local": self.fallback_local,
            "memory_file": str(self.get_memory_file_path()),
            "trust_file": str(self.get_trust_file_path()),
            "tasks_file": str(self.get_tasks_file_path())
        }
    
    def sync_to_backup(self) -> bool:
        """Sync memory files to backup location"""
        try:
            backup_path = self.get_backup_path()
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Backup memory files
            for file_type in ["memory", "trust", "tasks"]:
                source_file = getattr(self, f"get_{file_type}_file_path")()
                if source_file.exists():
                    backup_file = backup_path / f"{file_type}_{timestamp}.json"
                    import shutil
                    shutil.copy2(source_file, backup_file)
            
            logger.info(f"Backed up memory files to {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False


# Example usage
if __name__ == "__main__":
    config = MemoryStorageConfig(thumb_drive="F:")
    storage_config = config.get_config()
    
    print("Memory Storage Configuration:")
    for key, value in storage_config.items():
        print(f"  {key}: {value}")

