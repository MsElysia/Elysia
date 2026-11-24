# project_guardian/memory_snapshot.py
# Memory Snapshot and Backup System
# Provides daily snapshots and backup shards for memory recovery

import os
import json
import shutil
import logging
import hashlib
import tempfile
from contextlib import nullcontext
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Suffix for the byte-for-byte copy of the primary taken before a restore
# replaces it. Deliberately not ``.json`` so nothing treats it as a store.
PRE_RESTORE_SUFFIX = ".pre-restore."


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
        # Outcome of the most recent restore_from_snapshot() call.
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
            True only when the restored history is on disk and the target has
            reloaded it (``persistence_blocked`` cleared).

        Recovery contract:

        * The snapshot is validated before the target is touched. An
          unreadable snapshot, or one whose ``memories`` is not a list,
          leaves the primary store and the target untouched.
        * Entries are restored verbatim (original ``time`` and ``metadata``,
          so provenance and correction links survive); only entries that are
          not a dict with a string ``thought`` are skipped.
        * The current primary bytes, readable or not, are copied to a
          ``<primary>.pre-restore.<UTC stamp>`` sidecar before being replaced.
          Originals are preserved, never deleted.
        * The primary is replaced atomically under the MemoryCore process
          lock, then the target performs an explicit ``load()``. This is the
          only sanctioned way past the ``persistence_blocked`` fence that a
          corrupt primary raises, which is exactly the case recovery is for.
        * Replaying through ``remember()`` is not used: it re-stamps time,
          drops metadata, applies startup/noise/pressure write filters and
          refuses outright while persistence is blocked.
        """
        report: Dict[str, Any] = {
            "snapshot_path": snapshot_path,
            "restored": 0,
            "skipped": 0,
            "truncated": 0,
            "changed": False,
            "persisted": False,
            "preserved_original": None,
            "error": None,
        }
        self.last_restore_report = report

        snapshot_data = self.load_snapshot(snapshot_path)
        if not isinstance(snapshot_data, dict):
            report["error"] = "snapshot unreadable"
            return False
        memories = snapshot_data.get("memories")
        if not isinstance(memories, list):
            report["error"] = "snapshot 'memories' is not a list"
            logger.error("Snapshot %s has no memory list; target untouched", snapshot_path)
            return False

        json_memory = getattr(target_memory, "json_memory", target_memory)
        filepath = getattr(json_memory, "filepath", None)
        if not isinstance(filepath, str) or not filepath or not callable(getattr(json_memory, "load", None)):
            report["error"] = "target does not expose a JSON primary (filepath/load)"
            logger.error("Restore target unsupported: %s", type(target_memory).__name__)
            return False

        default_time = snapshot_data.get("timestamp") or datetime.now().isoformat()
        entries: List[Dict[str, Any]] = []
        for memory in memories:
            if not isinstance(memory, dict) or not isinstance(memory.get("thought"), str):
                report["skipped"] += 1
                continue
            entry = dict(memory)
            if not isinstance(entry.get("time"), str) or not entry["time"]:
                entry["time"] = default_time
            if not isinstance(entry.get("category"), str) or not entry["category"]:
                entry["category"] = "general"
            if not isinstance(entry.get("priority"), (int, float)) or isinstance(entry["priority"], bool):
                entry["priority"] = 0.5
            if not isinstance(entry.get("metadata"), dict):
                entry["metadata"] = {}
            entries.append(entry)

        max_memories = getattr(json_memory, "max_memories", None)
        if isinstance(max_memories, int) and max_memories >= 0 and len(entries) > max_memories:
            report["truncated"] = len(entries) - max_memories
            entries = entries[len(entries) - max_memories:]

        try:
            staged_text = json.dumps(entries, indent=2)
        except (TypeError, ValueError) as exc:
            report["error"] = f"snapshot entries not serializable: {exc}"[:200]
            logger.error("Restore aborted, %s", report["error"])
            return False

        instance_lock = getattr(json_memory, "_save_file_lock", None)
        process_lock = getattr(json_memory, "_primary_process_lock", None)
        try:
            with (instance_lock if instance_lock is not None else nullcontext()):
                with (process_lock() if callable(process_lock) else nullcontext()):
                    tmp_path, staged = self._stage_primary(filepath, staged_text)
                    try:
                        current = self._read_primary_bytes(filepath)
                        if current is not None and hashlib.sha256(current).digest() == hashlib.sha256(staged).digest():
                            logger.info("Restore no-op: primary already matches snapshot %s", snapshot_path)
                        else:
                            if current is not None:
                                report["preserved_original"] = self._preserve_primary_copy(filepath)
                            os.replace(tmp_path, filepath)
                            tmp_path = None
                            report["changed"] = True
                    finally:
                        if tmp_path:
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass
                json_memory.load()
                if getattr(json_memory, "persistence_blocked", False):
                    report["error"] = (
                        getattr(json_memory, "last_load_error", None) or "target still fenced after reload"
                    )
                    logger.error("Restore wrote primary but reload stayed fenced: %s", report["error"])
                    return False
                if getattr(json_memory, "loaded", True) is False:
                    json_memory.loaded = True
                if hasattr(json_memory, "_vector_index_built"):
                    json_memory._vector_index_built = False
        except Exception as e:
            report["error"] = f"{type(e).__name__}: {e}"[:200]
            logger.error(f"Failed to restore from snapshot: {e}")
            return False

        report["restored"] = len(entries)
        report["persisted"] = True
        logger.info(
            "Restored %d memories from snapshot %s (skipped=%d, truncated=%d, changed=%s)",
            len(entries), snapshot_path, report["skipped"], report["truncated"], report["changed"],
        )
        return True

    @staticmethod
    def _read_primary_bytes(filepath: str) -> Optional[bytes]:
        """Exact current primary bytes; None only when the file is absent."""
        try:
            with open(filepath, "rb") as source:
                return source.read()
        except FileNotFoundError:
            return None

    @staticmethod
    def _preserve_primary_copy(filepath: str) -> str:
        """Copy the primary (readable or not) to a unique pre-restore sidecar."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = f"{filepath}{PRE_RESTORE_SUFFIX}{stamp}"
        candidate = base
        n = 1
        while os.path.exists(candidate):
            candidate = f"{base}.{n}"
            n += 1
        shutil.copy2(filepath, candidate)
        return candidate

    @staticmethod
    def _stage_primary(filepath: str, text: str) -> "tuple[str, bytes]":
        """Write text to a fsynced temp file beside the primary.

        Uses the same text-mode encoding as ``MemoryCore._save`` so the bytes
        compare equal to a store the core itself wrote (including platform
        newline translation). Returns (temp path, exact staged bytes).
        """
        directory = os.path.dirname(os.path.abspath(filepath)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".guardian_memory_restore_", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            with open(tmp_path, "rb") as staged:
                return tmp_path, staged.read()
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

