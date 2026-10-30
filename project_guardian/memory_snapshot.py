# project_guardian/memory_snapshot.py
# Memory Snapshot and Backup System
# Provides daily snapshots and backup shards for memory recovery

import os
import json
import shutil
import logging
from typing import Dict, Any, List, Optional, Tuple
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
        # Diagnostics for the last restore_from_snapshot() call (never user memory).
        self.last_restore_report: Dict[str, Any] = {}
        
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
            True only when the restored history is on disk.

        Entries are restored verbatim (original ``time``, ``metadata`` /
        provenance, ``category``, ``priority`` and any extra keys) rather than
        replayed through ``remember()``, which re-stamps every entry, drops
        metadata, applies the startup/noise/pressure write filters and rewrites
        the file once per entry. The target is not cleared until the snapshot
        has been validated, and the previous in-memory log is put back if the
        single persist step fails.
        """
        report: Dict[str, Any] = {
            "snapshot_path": str(snapshot_path),
            "restored": 0,
            "skipped": 0,
            "truncated": 0,
            "persisted": False,
            "error": None,
        }
        self.last_restore_report = report

        snapshot_data = self.load_snapshot(snapshot_path)
        if not snapshot_data:
            report["error"] = "snapshot_unreadable"
            return False

        memories = snapshot_data.get("memories") if isinstance(snapshot_data, dict) else None
        if not isinstance(memories, list):
            report["error"] = "snapshot_malformed"
            logger.error(f"Snapshot {snapshot_path} has no 'memories' list; target memory left untouched")
            return False

        restored, skipped = self._normalize_snapshot_entries(
            memories, default_time=str(snapshot_data.get("timestamp") or "")
        )
        report["skipped"] = skipped

        try:
            load_if_needed = getattr(target_memory, "load_if_needed", None)
            if callable(load_if_needed):
                try:
                    load_if_needed()
                except Exception as e:
                    logger.debug(f"restore_from_snapshot: load_if_needed failed: {e}")
            previous_log = list(getattr(target_memory, "memory_log", None) or [])

            max_memories = getattr(target_memory, "max_memories", None)
            if isinstance(max_memories, int) and max_memories > 0 and len(restored) > max_memories:
                report["truncated"] = len(restored) - max_memories
                restored = restored[-max_memories:]

            target_memory.memory_log = restored
            if hasattr(target_memory, "loaded"):
                target_memory.loaded = True

            persisted = self._persist_target(target_memory)
            if not persisted:
                target_memory.memory_log = previous_log
                report["error"] = "persist_failed"
                logger.error(
                    f"Restore from {snapshot_path} not persisted; previous in-memory log "
                    f"({len(previous_log)} entries) kept, disk state unchanged by this call"
                )
                return False

            report["persisted"] = True
            report["restored"] = len(restored)
            # Vector ids embed the entry timestamp; force a lazy rebuild on next semantic query.
            if hasattr(target_memory, "_vector_index_built"):
                target_memory._vector_index_built = False

            logger.info(
                f"Restored {len(restored)} memories from snapshot "
                f"(skipped {skipped} malformed, truncated {report['truncated']})"
            )
            return True

        except Exception as e:
            report["error"] = f"{type(e).__name__}: {e}"
            logger.error(f"Failed to restore from snapshot: {e}")
            return False

    @staticmethod
    def _normalize_snapshot_entries(
        memories: List[Any], default_time: str = ""
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Keep every dict entry with a non-empty string ``thought`` as-is, filling only the
        four keys MemoryCore readers index directly. Anything else is skipped and counted.
        """
        restored: List[Dict[str, Any]] = []
        skipped = 0
        for memory in memories:
            if not isinstance(memory, dict):
                skipped += 1
                continue
            thought = memory.get("thought")
            if not isinstance(thought, str) or not thought.strip():
                skipped += 1
                continue
            entry = dict(memory)
            entry.setdefault("time", default_time)
            entry.setdefault("category", "general")
            entry.setdefault("priority", 0.5)
            metadata = entry.get("metadata")
            entry["metadata"] = metadata if isinstance(metadata, dict) else {}
            restored.append(entry)
        return restored, skipped

    @staticmethod
    def _persist_target(target_memory: Any) -> bool:
        """
        Persist ``target_memory.memory_log`` once. ``_save`` returning True/False is
        honoured; the legacy ``_save`` (returns None, prints on failure) is verified by
        re-reading ``filepath``. Unknown outcome counts as not persisted.
        """
        save = getattr(target_memory, "_save", None)
        if not callable(save):
            return False
        try:
            result = save()
        except Exception as e:
            logger.error(f"restore_from_snapshot: _save raised: {e}")
            return False
        if result is True:
            return True
        if result is False:
            return False

        filepath = getattr(target_memory, "filepath", None)
        if not filepath:
            return False
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
        except Exception as e:
            logger.error(f"restore_from_snapshot: could not verify {filepath}: {e}")
            return False
        return isinstance(on_disk, list) and len(on_disk) == len(target_memory.memory_log)

