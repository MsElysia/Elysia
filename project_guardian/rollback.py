# project_guardian/rollback.py
# Rollback and Recovery System for Project Guardian

import os
import datetime
from typing import List, Dict, Any, Optional
from .memory import MemoryCore

class RollbackEngine:
    """
    Safe rollback and recovery system for Project Guardian.
    Provides backup management and safe restoration capabilities.
    """
    
    def __init__(self, memory: MemoryCore, backup_folder: str = "guardian_backups"):
        self.memory = memory
        self.backup_folder = backup_folder
        self.rollback_history: List[Dict[str, Any]] = []
        
        # Ensure backup directory exists
        os.makedirs(self.backup_folder, exist_ok=True)
        
    def list_backups(self, filename_prefix: str) -> List[str]:
        """
        List available backups for a file.
        
        Args:
            filename_prefix: File name prefix to search for
            
        Returns:
            List of backup files (sorted by date, newest first)
        """
        if not os.path.exists(self.backup_folder):
            return []
            
        files = os.listdir(self.backup_folder)
        matching_files = [f for f in files if f.startswith(filename_prefix)]
        return sorted(matching_files, reverse=True)
        
    def restore_backup(self, filename_prefix: str, backup_name: str) -> str:
        """
        Restore a file from backup.
        
        Args:
            filename_prefix: Target file name
            backup_name: Backup file name
            
        Returns:
            Status message
        """
        target = filename_prefix
        backup_path = os.path.join(self.backup_folder, backup_name)
        
        if not os.path.exists(backup_path):
            error_msg = f"[Guardian Rollback] Backup not found: {backup_name}"
            self.memory.remember(error_msg, category="rollback", priority=0.8)
            return error_msg
            
        try:
            # Read backup content
            with open(backup_path, "r", encoding="utf-8") as f:
                restored_content = f.read()
                
            # Restore to target file
            with open(target, "w", encoding="utf-8") as f:
                f.write(restored_content)
                
            # Log rollback
            rollback_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "target_file": target,
                "backup_file": backup_name,
                "backup_path": backup_path
            }
            self.rollback_history.append(rollback_entry)
            
            success_msg = f"[Guardian Rollback] Restored {backup_name} to {target}"
            self.memory.remember(success_msg, category="rollback", priority=0.7)
            return success_msg
            
        except Exception as e:
            error_msg = f"[Guardian Rollback] Failed to restore {backup_name}: {str(e)}"
            self.memory.remember(error_msg, category="rollback", priority=0.9)
            return error_msg
            
    def create_backup(self, filename: str) -> str:
        """
        Create a backup of a file.
        
        Args:
            filename: File to backup
            
        Returns:
            Status message
        """
        if not os.path.exists(filename):
            error_msg = f"[Guardian Rollback] File not found: {filename}"
            self.memory.remember(error_msg, category="rollback", priority=0.8)
            return error_msg
            
        try:
            # Read file content
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Create backup filename
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"{filename}.bak.{timestamp}"
            backup_path = os.path.join(self.backup_folder, backup_name)
            
            # Write backup
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            success_msg = f"[Guardian Rollback] Created backup: {backup_name}"
            self.memory.remember(success_msg, category="rollback", priority=0.6)
            return success_msg
            
        except Exception as e:
            error_msg = f"[Guardian Rollback] Failed to create backup of {filename}: {str(e)}"
            self.memory.remember(error_msg, category="rollback", priority=0.8)
            return error_msg
            
    def auto_rollback(self, filename: str, reason: str = "auto") -> str:
        """
        Automatically rollback to the most recent backup.
        
        Args:
            filename: File to rollback
            reason: Reason for rollback
            
        Returns:
            Status message
        """
        backups = self.list_backups(filename)
        if not backups:
            error_msg = f"[Guardian Rollback] No backups found for {filename}"
            self.memory.remember(error_msg, category="rollback", priority=0.8)
            return error_msg
            
        # Use the most recent backup
        latest_backup = backups[0]
        return self.restore_backup(filename, latest_backup)
        
    def cleanup_old_backups(self, keep_count: int = 10) -> str:
        """
        Clean up old backups, keeping only the most recent ones.
        
        Args:
            keep_count: Number of backups to keep per file
            
        Returns:
            Status message
        """
        if not os.path.exists(self.backup_folder):
            return "[Guardian Rollback] No backup folder found."
            
        files = os.listdir(self.backup_folder)
        file_groups = {}
        
        # Group files by base name
        for file in files:
            if file.endswith('.bak.'):
                base_name = file.split('.bak.')[0]
                if base_name not in file_groups:
                    file_groups[base_name] = []
                file_groups[base_name].append(file)
                
        deleted_count = 0
        for base_name, backup_files in file_groups.items():
            # Sort by timestamp (newest first)
            sorted_files = sorted(backup_files, reverse=True)
            
            # Keep only the most recent backups
            files_to_delete = sorted_files[keep_count:]
            
            for file_to_delete in files_to_delete:
                file_path = os.path.join(self.backup_folder, file_to_delete)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    self.memory.remember(
                        f"[Guardian Rollback] Failed to delete {file_to_delete}: {str(e)}",
                        category="rollback",
                        priority=0.6
                    )
                    
        cleanup_msg = f"[Guardian Rollback] Cleaned up {deleted_count} old backups"
        self.memory.remember(cleanup_msg, category="rollback", priority=0.5)
        return cleanup_msg
        
    def get_backup_stats(self) -> Dict[str, Any]:
        """
        Get backup system statistics.
        
        Returns:
            Backup statistics
        """
        if not os.path.exists(self.backup_folder):
            return {"total_backups": 0, "backup_folder": self.backup_folder}
            
        files = os.listdir(self.backup_folder)
        backup_files = [f for f in files if f.endswith('.bak.')]
        
        # Group by base file
        file_groups = {}
        for file in backup_files:
            base_name = file.split('.bak.')[0]
            if base_name not in file_groups:
                file_groups[base_name] = []
            file_groups[base_name].append(file)
            
        return {
            "total_backups": len(backup_files),
            "backup_folder": self.backup_folder,
            "files_with_backups": len(file_groups),
            "backup_distribution": {name: len(files) for name, files in file_groups.items()},
            "total_rollbacks": len(self.rollback_history)
        }
        
    def get_rollback_history(self) -> List[Dict[str, Any]]:
        """
        Get rollback history.
        
        Returns:
            List of rollback entries
        """
        return self.rollback_history.copy()
        
    def validate_backup_integrity(self, backup_name: str) -> bool:
        """
        Validate that a backup file is readable and contains valid content.
        
        Args:
            backup_name: Name of backup file to validate
            
        Returns:
            True if backup is valid
        """
        backup_path = os.path.join(self.backup_folder, backup_name)
        
        if not os.path.exists(backup_path):
            return False
            
        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Basic validation - check if content is not empty
                return len(content.strip()) > 0
        except Exception:
            return False 