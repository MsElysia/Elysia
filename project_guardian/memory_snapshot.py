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
        # Outcome of the most recent create_snapshot()/create_daily_snapshot() call.
        self.last_snapshot_report: Dict[str, Any] = {}
        
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
            Snapshot file path, or "" when no durable snapshot was written.

        Durability contract: the snapshot is serialized fully before any file
        is created, staged beside its final name, fsynced and renamed into
        place. A failed write therefore never leaves a partial
        ``snapshot_*.json`` that ``get_latest_snapshot``/``list_snapshots``
        (and the error-handler recovery path built on them) would pick over
        the previous healthy snapshot. Two snapshots within one second get
        distinct names instead of overwriting each other. The shard copy is a
        best-effort secondary: its failure is recorded in
        ``last_snapshot_report`` but does not turn a durable primary snapshot
        into a reported failure.
        """
        report = self._new_snapshot_report("snapshot")
        if not isinstance(memory_data, (list, tuple)):
            report["error"] = f"memory_data must be a list, got {type(memory_data).__name__}"
            logger.error("Failed to create snapshot: %s", report["error"])
            return ""
        memory_data = list(memory_data)
        now = datetime.now()
        snapshot_data = {
            "timestamp": now.isoformat(),
            "memory_count": len(memory_data),
            "memories": memory_data,
            "metadata": metadata or {},
            "vector_index_path": vector_index_path
        }
        report["memory_count"] = len(memory_data)

        try:
            text = json.dumps(snapshot_data, indent=2)
        except (TypeError, ValueError) as e:
            report["error"] = f"snapshot not serializable: {e}"[:200]
            logger.error("Failed to create snapshot: %s", report["error"])
            return ""

        try:
            snapshot_file = self._unique_snapshot_path("snapshot_", now.strftime("%Y%m%d_%H%M%S"))
            self._write_text_durably(snapshot_file, text)
        except Exception as e:
            report["error"] = f"{type(e).__name__}: {e}"[:200]
            logger.error(f"Failed to create snapshot: {e}")
            return ""
        report["path"] = str(snapshot_file)
        report["persisted"] = True

        shard_idx = self._select_backup_shard()
        if shard_idx is None:
            logger.info(f"Snapshot created: {snapshot_file} (no backup shards configured)")
        else:
            report["shard"] = shard_idx + 1
            shard_file = self.shard_dirs[shard_idx] / snapshot_file.name
            try:
                self._copy_file_durably(snapshot_file, shard_file)
                report["shard_copied"] = True
                logger.info(f"Snapshot created: {snapshot_file} (backed to shard {shard_idx+1})")
            except Exception as e:
                report["shard_copied"] = False
                report["error"] = f"shard copy failed: {type(e).__name__}: {e}"[:200]
                logger.warning(
                    "Snapshot created: %s but backup copy to shard %d failed: %s",
                    snapshot_file, shard_idx + 1, e,
                )
        return str(snapshot_file)
            
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
            Snapshot file path, or "" when no durable snapshot was written.

        The new daily file is written durably first (an atomic replace when
        today's file already exists); only then are earlier ``daily_*.json``
        files removed. A failed write leaves the previous daily snapshot
        intact instead of deleting it and leaving a partial file behind.
        """
        report = self._new_snapshot_report("daily")
        if not isinstance(memory_data, (list, tuple)):
            report["error"] = f"memory_data must be a list, got {type(memory_data).__name__}"
            logger.error("Failed to create daily snapshot: %s", report["error"])
            return ""
        memory_data = list(memory_data)
        now = datetime.now()
        snapshot_file = self.snapshot_dir / f"daily_{now.strftime('%Y%m%d')}.json"
        snapshot_data = {
            "timestamp": now.isoformat(),
            "memory_count": len(memory_data),
            "memories": memory_data,
            "snapshot_type": "daily",
            "vector_index_path": vector_index_path
        }
        report["memory_count"] = len(memory_data)

        try:
            text = json.dumps(snapshot_data, indent=2)
        except (TypeError, ValueError) as e:
            report["error"] = f"snapshot not serializable: {e}"[:200]
            logger.error("Failed to create daily snapshot: %s", report["error"])
            return ""

        try:
            self._write_text_durably(snapshot_file, text)
        except Exception as e:
            report["error"] = f"{type(e).__name__}: {e}"[:200]
            logger.error(f"Failed to create daily snapshot: {e}")
            return ""
        report["path"] = str(snapshot_file)
        report["persisted"] = True

        # Only now is it safe to drop earlier daily snapshots.
        for old_snapshot in self.snapshot_dir.glob("daily_*.json"):
            if old_snapshot.name == snapshot_file.name:
                continue
            try:
                old_snapshot.unlink()
                report["removed_previous"] += 1
            except Exception as e:
                logger.warning(f"Failed to remove previous daily snapshot {old_snapshot}: {e}")

        logger.info(f"Daily snapshot created: {snapshot_file}")
        return str(snapshot_file)

    def _new_snapshot_report(self, kind: str) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "kind": kind,
            "path": None,
            "memory_count": None,
            "persisted": False,
            "shard": None,
            "shard_copied": None,
            "removed_previous": 0,
            "error": None,
        }
        self.last_snapshot_report = report
        return report

    def _unique_snapshot_path(self, prefix: str, stamp: str) -> Path:
        """``<prefix><stamp>.json``, with ``_<n>`` inserted if that name is taken.

        Checked against the snapshot dir and every shard so a shard copy never
        overwrites an earlier snapshot's copy either.
        """
        candidate = self.snapshot_dir / f"{prefix}{stamp}.json"
        n = 1
        while candidate.exists() or any((d / candidate.name).exists() for d in self.shard_dirs):
            candidate = self.snapshot_dir / f"{prefix}{stamp}_{n}.json"
            n += 1
        return candidate

    def _select_backup_shard(self) -> Optional[int]:
        """Index of the least-loaded shard (lowest index on ties); None if no shards."""
        if not self.shard_dirs:
            return None
        counts = [len(list(d.glob("snapshot_*.json"))) for d in self.shard_dirs]
        return counts.index(min(counts))

    @staticmethod
    def _write_text_durably(target: Path, text: str) -> None:
        """Stage ``text`` in a temp file next to ``target``, fsync, then rename into place."""
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _copy_file_durably(source: Path, target: Path) -> None:
        """Copy ``source`` to ``target`` without ever exposing a partial ``target``."""
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp", dir=str(target.parent))
        os.close(fd)
        try:
            shutil.copy2(source, tmp_path)
            with open(tmp_path, "rb+") as handle:
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
            
    def load_snapshot(self, snapshot_path: str) -> Optional[Dict[str, Any]]:
        """
        Load a snapshot from file.
        
        Args:
            snapshot_path: Path to snapshot file
            
        Returns:
            Snapshot data or None if failed

        A snapshot is only "loaded" when it parses to a dict whose
        ``memories`` is a list. When the named file fails that check, the
        same-named copies in the backup shards (or in the snapshot dir, if a
        shard path was given) are tried in order, so a damaged primary copy
        no longer shadows an intact backup. The damaged file is left as-is.
        """
        snapshot_data, _source, _reason = self._load_snapshot_with_source(snapshot_path)
        return snapshot_data

    def _load_snapshot_with_source(
        self, snapshot_path: str
    ) -> "tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]":
        """``(data, path actually read, reason the requested file was rejected)``.

        ``data``/source are None when no copy is readable; the reason is None
        when the requested file itself was the one loaded.
        """
        requested = Path(snapshot_path)
        requested_reason: Optional[str] = None
        for candidate in self._snapshot_copies(requested):
            snapshot_data, reason = self._read_snapshot_file(candidate)
            if candidate == requested:
                requested_reason = reason
            if snapshot_data is None:
                continue
            if candidate != requested:
                logger.warning(
                    "Snapshot %s %s; using backup copy %s", snapshot_path, requested_reason, candidate
                )
            else:
                logger.info(f"Snapshot loaded: {snapshot_path}")
            return snapshot_data, str(candidate), requested_reason
        logger.error("Failed to load snapshot: no readable copy of %s (%s)", snapshot_path, requested_reason)
        return None, None, requested_reason

    def _snapshot_copies(self, snapshot_path: Path) -> List[Path]:
        """``snapshot_path`` first, then every other existing same-named copy.

        Copies live in the snapshot dir and the backup shards; the order is
        snapshot dir, shard_1, shard_2, ... with the requested path moved to
        the front.
        """
        copies = [snapshot_path]
        for location in [self.snapshot_dir, *self.shard_dirs]:
            candidate = location / snapshot_path.name
            if candidate != snapshot_path and candidate not in copies and candidate.exists():
                copies.append(candidate)
        return copies

    @staticmethod
    def _read_snapshot_file(path: Path) -> "tuple[Optional[Dict[str, Any]], Optional[str]]":
        """``(data, None)`` for a dict with a ``memories`` list, else ``(None, reason)``."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                snapshot_data = json.load(f)
        except Exception as e:
            reason = f"unreadable: {type(e).__name__}: {e}"[:200]
            logger.warning("Snapshot copy %s %s", path, reason)
            return None, reason
        if not isinstance(snapshot_data, dict) or not isinstance(snapshot_data.get("memories"), list):
            reason = "snapshot 'memories' is not a list"
            logger.warning("Snapshot copy %s malformed: %s", path, reason)
            return None, reason
        return snapshot_data, None

    def _snapshot_names_newest_first(self, pattern: str, include_shards: bool) -> List[str]:
        """Distinct file names matching ``pattern`` ordered by the newest existing copy."""
        newest: Dict[str, float] = {}
        locations = [self.snapshot_dir, *(self.shard_dirs if include_shards else [])]
        for location in locations:
            for path in location.glob(pattern):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime > newest.get(path.name, float("-inf")):
                    newest[path.name] = mtime
        return sorted(newest, key=lambda name: newest[name], reverse=True)

    def _latest_readable(self, pattern: str, include_shards: bool) -> Optional[str]:
        for name in self._snapshot_names_newest_first(pattern, include_shards):
            for candidate in self._snapshot_copies(self.snapshot_dir / name):
                if not candidate.exists():
                    continue
                if self._read_snapshot_file(candidate)[0] is not None:
                    return str(candidate)
            logger.warning("Skipping snapshot %s: no readable copy", name)
        return None

    def get_latest_snapshot(self) -> Optional[str]:
        """Path of the newest snapshot that has a readable copy.

        Candidates are ordered by modification time across the snapshot dir
        and the backup shards. A file that is unreadable or malformed is
        skipped in favour of its intact shard copy, or failing that the next
        older snapshot, so a damaged newest backup never masks a good one.
        The returned path is the copy that was actually verified readable.
        """
        return self._latest_readable("snapshot_*.json", include_shards=True)
        
    def get_latest_daily_snapshot(self) -> Optional[str]:
        """Path of the newest readable daily snapshot (daily files have no shard copies)."""
        return self._latest_readable("daily_*.json", include_shards=False)
        
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
                created = datetime.fromtimestamp(stat.st_mtime).isoformat()
                snapshot_info.append({
                    "path": str(snapshot_file),
                    "created": created,
                    # Alias consumed by error_handler._recover_memory_error,
                    # which picks the restore candidate with max("timestamp").
                    "timestamp": created,
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

        * The snapshot is validated before the target is touched. When the
          named file is unreadable or malformed its same-named backup-shard
          copy is used instead (``last_restore_report["source_path"]`` names
          the copy actually read). With no readable copy at all, the primary
          store and the target are left untouched.
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
            "source_path": None,
            "restored": 0,
            "skipped": 0,
            "truncated": 0,
            "changed": False,
            "persisted": False,
            "preserved_original": None,
            "error": None,
        }
        self.last_restore_report = report

        snapshot_data, source_path, rejected_reason = self._load_snapshot_with_source(snapshot_path)
        if not isinstance(snapshot_data, dict):
            report["error"] = f"snapshot unreadable ({rejected_reason or 'missing'})"[:200]
            logger.error("Snapshot %s has no readable copy; target untouched", snapshot_path)
            return False
        report["source_path"] = source_path
        memories = snapshot_data.get("memories")
        if not isinstance(memories, list):
            # Unreachable with the loader above; kept so the method stays
            # self-contained if the loader contract ever loosens.
            report["error"] = "snapshot 'memories' is not a list"
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

