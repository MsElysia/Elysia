# project_guardian/memory_snapshot.py
# Memory Snapshot and Backup System
# Provides daily snapshots and backup shards for memory recovery

import os
import json
import shutil
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class MemorySnapshot:
    """
    Manages memory snapshots and backups.
    Provides daily snapshots + 3 backup shards for recovery.
    """
    
    def __init__(
        self,
        snapshot_dir: str = "memory/snapshots",
        backup_shards: int = 3,
        retention_days: int = 30
    ):
        self.snapshot_dir = Path(snapshot_dir)
        self.backup_shards = backup_shards
        self.retention_days = retention_days
        
        # Ensure directories exist
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Create shard directories
        self.shard_dirs = []
        for i in range(backup_shards):
            shard_dir = self.snapshot_dir / f"shard_{i+1}"
            shard_dir.mkdir(parents=True, exist_ok=True)
            self.shard_dirs.append(shard_dir)
            
    def create_snapshot(
        self,
        memory_data: List[Dict[str, Any]],
        vector_index_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a snapshot of current memory state.
        
        Args:
            memory_data: Memory entries to snapshot
            vector_index_path: Optional path to vector index
            metadata: Optional snapshot metadata
            
        Returns:
            Snapshot file path
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_file = self.snapshot_dir / f"snapshot_{timestamp}.json"
        
        snapshot_data = {
            "timestamp": datetime.now().isoformat(),
            "memory_count": len(memory_data),
            "memories": memory_data,
            "metadata": metadata or {},
            "vector_index_path": vector_index_path
        }
        
        try:
            with open(snapshot_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, indent=2)
                
            # Copy to one of the backup shards (round-robin)
            shard_idx = len(list(self.shard_dirs[0].glob("*.json"))) % self.backup_shards
            shard_file = self.shard_dirs[shard_idx] / f"snapshot_{timestamp}.json"
            shutil.copy2(snapshot_file, shard_file)
            
            logger.info(f"Snapshot created: {snapshot_file} (backed to shard {shard_idx+1})")
            return str(snapshot_file)
            
        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            return ""
            
    def create_daily_snapshot(
        self,
        memory_data: List[Dict[str, Any]],
        vector_index_path: Optional[str] = None
    ) -> str:
        """
        Create daily snapshot (replaces previous daily snapshot).
        
        Args:
            memory_data: Memory entries
            vector_index_path: Optional vector index path
            
        Returns:
            Snapshot file path
        """
        # Remove old daily snapshot
        daily_snapshots = list(self.snapshot_dir.glob("daily_*.json"))
        for old_snapshot in daily_snapshots:
            try:
                old_snapshot.unlink()
            except Exception:
                pass
                
        # Create new daily snapshot
        timestamp = datetime.now().strftime("%Y%m%d")
        snapshot_file = self.snapshot_dir / f"daily_{timestamp}.json"
        
        snapshot_data = {
            "timestamp": datetime.now().isoformat(),
            "memory_count": len(memory_data),
            "memories": memory_data,
            "snapshot_type": "daily",
            "vector_index_path": vector_index_path
        }
        
        try:
            with open(snapshot_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, indent=2)
                
            logger.info(f"Daily snapshot created: {snapshot_file}")
            return str(snapshot_file)
            
        except Exception as e:
            logger.error(f"Failed to create daily snapshot: {e}")
            return ""
            
    def load_snapshot(self, snapshot_path: str) -> Optional[Dict[str, Any]]:
        """
        Load a snapshot from file.
        
        Args:
            snapshot_path: Path to snapshot file
            
        Returns:
            Snapshot data or None if failed
        """
        try:
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                snapshot_data = json.load(f)
            logger.info(f"Snapshot loaded: {snapshot_path}")
            return snapshot_data
        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
            return None
            
    def get_latest_snapshot(self) -> Optional[str]:
        """Get path to latest snapshot."""
        snapshots = list(self.snapshot_dir.glob("snapshot_*.json"))
        if not snapshots:
            return None
            
        # Sort by modification time
        snapshots.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(snapshots[0])
        
    def get_latest_daily_snapshot(self) -> Optional[str]:
        """Get path to latest daily snapshot."""
        daily_snapshots = list(self.snapshot_dir.glob("daily_*.json"))
        if not daily_snapshots:
            return None
            
        # Sort by modification time
        daily_snapshots.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(daily_snapshots[0])
        
    def list_snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        List available snapshots.
        
        Args:
            limit: Maximum number to return
            
        Returns:
            List of snapshot info
        """
        snapshots = list(self.snapshot_dir.glob("snapshot_*.json"))
        snapshots.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        snapshot_info = []
        for snapshot_file in snapshots[:limit]:
            try:
                stat = snapshot_file.stat()
                snapshot_info.append({
                    "path": str(snapshot_file),
                    "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size": stat.st_size
                })
            except Exception:
                pass
                
        return snapshot_info
        
    def cleanup_old_snapshots(self):
        """Remove snapshots older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        removed_count = 0
        for snapshot_file in self.snapshot_dir.glob("snapshot_*.json"):
            try:
                file_date = datetime.fromtimestamp(snapshot_file.stat().st_mtime)
                if file_date < cutoff_date:
                    snapshot_file.unlink()
                    removed_count += 1
            except Exception as e:
                logger.warning(f"Failed to remove old snapshot {snapshot_file}: {e}")
                
        # Also cleanup shard snapshots
        for shard_dir in self.shard_dirs:
            for snapshot_file in shard_dir.glob("snapshot_*.json"):
                try:
                    file_date = datetime.fromtimestamp(snapshot_file.stat().st_mtime)
                    if file_date < cutoff_date:
                        snapshot_file.unlink()
                        removed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove old shard snapshot {snapshot_file}: {e}")
                    
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old snapshots")
            
        return removed_count
        
    def restore_from_snapshot(
        self,
        snapshot_path: str,
        target_memory: Any
    ) -> bool:
        """
        Restore memory from snapshot.
        
        Args:
            snapshot_path: Path to snapshot file
            target_memory: MemoryCore instance to restore into
            
        Returns:
            True if successful
        """
        snapshot_data = self.load_snapshot(snapshot_path)
        if not snapshot_data:
            return False
            
        try:
            memories = snapshot_data.get("memories", [])
            
            # Clear existing memory
            target_memory.forget()
            
            # Restore memories
            for memory in memories:
                target_memory.remember(
                    thought=memory.get("thought", ""),
                    category=memory.get("category", "general"),
                    priority=memory.get("priority", 0.5)
                )
                
            logger.info(f"Restored {len(memories)} memories from snapshot")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore from snapshot: {e}")
            return False

