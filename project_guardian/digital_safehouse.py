# project_guardian/digital_safehouse.py
# Digital Safehouse: Encrypted Backup System
# Based on elysia 4 (Main Consolidation) designs

from __future__ import annotations

import io
import logging
import json
import os
import zipfile
import shutil
import tempfile
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from threading import Lock

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024


class DigitalSafehouse:
    """
    Encrypted backup system for Elysia's essential files.
    Provides secure storage and recovery capabilities.
    """
    
    def __init__(
        self,
        safehouse_dir: str = "safehouse",
        key_file: str = "safehouse.key"
    ):
        self.safehouse_dir = Path(safehouse_dir)
        self.key_file = Path(key_file)
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Ensure directories exist
        self.safehouse_dir.mkdir(parents=True, exist_ok=True)
        
        # Encryption key
        self.encryption_key: Optional[bytes] = None
        self._load_or_generate_key()
        
        # Files to back up (default list)
        self.backup_files: List[str] = [
            "config/elysia_core.yml",
            "data/corecredit_log.json",
            "data/trust_registry.json",
            "data/tasks.json",
            "data/mutations.json",
            "data/identity_ledger.json",
            "data/global_priority_registry.json",
            "data/asset_manager.json",
            "data/core_credits.json",
            "data/longterm_planner.json"
        ]
    
    def _load_or_generate_key(self):
        """Load encryption key or generate a new one."""
        if not CRYPTO_AVAILABLE:
            logger.warning("Encryption not available - backups will not be encrypted")
            return
        
        if self.key_file.exists():
            try:
                with open(self.key_file, 'rb') as f:
                    self.encryption_key = f.read()
                logger.info(f"Loaded encryption key from {self.key_file}")
            except Exception as e:
                logger.error(f"Error loading key: {e}")
                # Do not overwrite an existing key that may open prior backups.
                self.encryption_key = None
        else:
            self._generate_key()
    
    def _generate_key(self):
        """Generate a new encryption key."""
        if not CRYPTO_AVAILABLE:
            return
        
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.backends import default_backend
            import base64
            
            # Generate key using Fernet
            self.encryption_key = Fernet.generate_key()
            
            # Save key
            with open(self.key_file, 'wb') as f:
                f.write(self.encryption_key)
            
            logger.info(f"Generated new encryption key: {self.key_file}")
        except Exception as e:
            logger.error(f"Error generating key: {e}")
            self.encryption_key = None
    
    def _get_fernet(self) -> Optional[Fernet]:
        """Get Fernet cipher instance."""
        if not CRYPTO_AVAILABLE or not self.encryption_key:
            return None
        
        try:
            return Fernet(self.encryption_key)
        except Exception as e:
            logger.error(f"Error creating Fernet cipher: {e}")
            return None
    
    def add_backup_file(self, filepath: str):
        """Add a file to the backup list."""
        with self._lock:
            if filepath not in self.backup_files:
                self.backup_files.append(filepath)
                logger.info(f"Added to backup list: {filepath}")
    
    def remove_backup_file(self, filepath: str):
        """Remove a file from the backup list."""
        with self._lock:
            if filepath in self.backup_files:
                self.backup_files.remove(filepath)
                logger.info(f"Removed from backup list: {filepath}")
    
    def create_backup(self, backup_name: Optional[str] = None, files: Optional[List[str]] = None,
                      metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Encrypt in memory first; never publish or stage a plaintext backup ZIP."""
        temp_path = None
        try:
            cipher = self._get_fernet()
            if cipher is None:
                logger.error("Backup refused: encryption is unavailable or key invalid")
                return None
            sources = self.backup_files if files is None else files
            if not sources:
                logger.error("Backup refused: no source files")
                return None
            if backup_name is None:
                backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if (not isinstance(backup_name, str) or not backup_name or
                    any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in backup_name)):
                logger.error("Backup refused: invalid name")
                return None
            entries, names, size = [], set(), 0
            for source in sources:
                path = Path(source)
                if not path.is_file() or path.is_symlink() or path.name in names or path.name == "_metadata.json":
                    logger.error("Backup refused: source absent, linked, or duplicate: %s", path)
                    return None
                names.add(path.name)
                size += path.stat().st_size
                if size > MAX_ARCHIVE_BYTES:
                    logger.error("Backup refused: source size exceeds in-memory bound")
                    return None
                entries.append(path)
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as zipf:
                for path in entries:
                    zipf.write(path, arcname=path.name)
                if metadata is not None:
                    zipf.writestr("_metadata.json", json.dumps(metadata, indent=2))
            if payload.tell() > MAX_ARCHIVE_BYTES:
                logger.error("Backup refused: ZIP size exceeds in-memory bound")
                return None
            encrypted = cipher.encrypt(payload.getvalue())
            target = self.safehouse_dir / (backup_name + ".encrypted")
            with tempfile.NamedTemporaryFile("wb", prefix=".encrypted-", suffix=".part",
                                              dir=self.safehouse_dir, delete=False) as out:
                temp_path = Path(out.name)
                out.write(encrypted)
            os.replace(temp_path, target)
            temp_path = None
            logger.info("Created encrypted backup: %s", target)
            return str(target)
        except Exception as exc:
            logger.error("Encrypted backup failed: %s", exc)
            return None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    logger.error("Could not clean encrypted staging file")

    def restore_backup(self, backup_path: str, restore_dir: str = ".",
                       overwrite: bool = False) -> bool:
        """Restore a bounded archive; no decrypted ZIP is stored on disk."""
        try:
            source = Path(backup_path)
            if not source.is_file():
                return False
            if source.suffix == ".encrypted":
                cipher = self._get_fernet()
                if cipher is None or source.stat().st_size > 2 * MAX_ARCHIVE_BYTES:
                    return False
                payload = io.BytesIO(cipher.decrypt(source.read_bytes()))
            elif source.suffix == ".zip":
                payload = source  # Read-only compatibility with old unencrypted backups.
            else:
                return False
            destination = Path(restore_dir).resolve()
            with zipfile.ZipFile(payload) as zipf:
                members = [m for m in zipf.infolist() if m.filename != "_metadata.json"]
                if not members or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
                    return False
                names = set()
                for m in members:
                    name = m.filename
                    if (m.is_dir() or not name or name in {".", ".."} or
                            "/" in name or "\\" in name or ":" in name or name in names):
                        return False
                    names.add(name)
                    target = destination / name
                    if target.resolve() != target or target.is_symlink():
                        return False
                if zipf.testzip() is not None:
                    return False
                destination.mkdir(parents=True, exist_ok=True)
                for member in members:
                    target = destination / member.filename
                    if target.exists() and not overwrite:
                        logger.info("Restore skipped existing file: %s", target)
                        continue
                    staging = None
                    try:
                        with tempfile.NamedTemporaryFile("wb", prefix=".restore-", suffix=".part",
                                                          dir=destination, delete=False) as out:
                            staging = Path(out.name)
                            with zipf.open(member) as archived:
                                shutil.copyfileobj(archived, out)
                        os.replace(staging, target)
                        staging = None
                    finally:
                        if staging is not None:
                            staging.unlink(missing_ok=True)
            logger.info("Restore complete from: %s", source)
            return True
        except Exception as exc:
            logger.error("Restore failed: %s", exc)
            return False

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups."""
        backups = []
        
        for backup_file in self.safehouse_dir.iterdir():
            if backup_file.is_file() and backup_file.suffix in {'.encrypted', '.zip'}:
                # Check if encrypted or plain zip
                is_encrypted = backup_file.suffix == '.encrypted' or backup_file.name.endswith('.encrypted')
                
                stat = backup_file.stat()
                
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size_bytes": stat.st_size,
                    "size_mb": stat.st_size / (1024 * 1024),
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "encrypted": is_encrypted
                })
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        
        return backups
    
    def delete_backup(self, backup_path: str) -> bool:
        """Delete a backup file."""
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False
        
        try:
            backup_file.unlink()
            logger.info(f"Deleted backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting backup: {e}")
            return False
    
    def get_backup_metadata(self, backup_path: str) -> Optional[Dict[str, Any]]:
        """Read metadata without creating decrypted temporary files."""
        try:
            source = Path(backup_path)
            if not source.is_file():
                return None
            if source.suffix == ".encrypted":
                cipher = self._get_fernet()
                if cipher is None or source.stat().st_size > 2 * MAX_ARCHIVE_BYTES:
                    return None
                payload = io.BytesIO(cipher.decrypt(source.read_bytes()))
            elif source.suffix == ".zip":
                payload = source
            else:
                return None
            with zipfile.ZipFile(payload) as zipf:
                try:
                    entry = zipf.getinfo("_metadata.json")
                except KeyError:
                    return None
                if entry.file_size > 1024 * 1024:
                    return None
                value = json.loads(zipf.read(entry).decode("utf-8"))
                return value if isinstance(value, dict) else None
        except Exception as exc:
            logger.error("Backup metadata failed: %s", exc)
            return None

    def cleanup_old_backups(self, keep_count: int = 10):
        """
        Delete old backups, keeping only the most recent ones.
        
        Args:
            keep_count: Number of backups to keep
        """
        backups = self.list_backups()
        
        if len(backups) <= keep_count:
            logger.info(f"Only {len(backups)} backups exist, no cleanup needed")
            return
        
        # Delete oldest backups
        backups_to_delete = backups[keep_count:]
        
        deleted_count = 0
        for backup in backups_to_delete:
            if self.delete_backup(backup["path"]):
                deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} old backups")


# Example usage
if __name__ == "__main__":
    safehouse = DigitalSafehouse()
    
    # Create backup
    backup_path = safehouse.create_backup(
        metadata={
            "version": "1.0",
            "description": "Full system backup",
            "created_by": "Elysia"
        }
    )
    
    if backup_path:
        print(f"Backup created: {backup_path}")
    
    # List backups
    backups = safehouse.list_backups()
    print(f"Available backups: {len(backups)}")
    for backup in backups[:5]:  # Show first 5
        print(f"  - {backup['filename']} ({backup['size_mb']:.2f} MB, encrypted: {backup['encrypted']})")
    
    # Get metadata
    if backups:
        metadata = safehouse.get_backup_metadata(backups[0]["path"])
        if metadata:
            print(f"Metadata: {metadata}")

