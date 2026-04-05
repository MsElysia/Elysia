# project_guardian/digital_safehouse.py
# Digital Safehouse: Encrypted Backup System
# Based on elysia 4 (Main Consolidation) designs

import logging
import json
import os
import zipfile
import shutil
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
    logger.warning("cryptography library not available - encryption disabled")

logger = logging.getLogger(__name__)


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
                self._generate_key()
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
    
    def create_backup(
        self,
        backup_name: Optional[str] = None,
        files: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create an encrypted backup.
        
        Args:
            backup_name: Optional custom backup name
            files: Optional list of files to back up (defaults to backup_files)
            metadata: Optional metadata to include
            
        Returns:
            Path to backup file or None if failed
        """
        files_to_backup = files or self.backup_files
        
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_filename = f"{backup_name}.zip"
        backup_path = self.safehouse_dir / backup_filename
        
        try:
            # Create ZIP archive
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add files
                for filepath in files_to_backup:
                    file_path = Path(filepath)
                    if file_path.exists():
                        # Add file to archive (preserve relative paths)
                        zipf.write(filepath, arcname=file_path.name)
                        logger.debug(f"Added to backup: {filepath}")
                    else:
                        logger.warning(f"File not found, skipping: {filepath}")
                
                # Add metadata
                if metadata:
                    metadata_json = json.dumps(metadata, indent=2)
                    zipf.writestr("_metadata.json", metadata_json)
            
            # Encrypt backup if encryption available
            if CRYPTO_AVAILABLE and self.encryption_key:
                encrypted_path = self.safehouse_dir / f"{backup_name}.encrypted"
                fernet = self._get_fernet()
                if fernet:
                    with open(backup_path, 'rb') as f:
                        data = f.read()
                    
                    encrypted_data = fernet.encrypt(data)
                    
                    with open(encrypted_path, 'wb') as f:
                        f.write(encrypted_data)
                    
                    # Remove unencrypted backup
                    backup_path.unlink()
                    backup_path = encrypted_path
                    
                    logger.info(f"Created encrypted backup: {backup_path}")
                else:
                    logger.warning("Encryption failed, backup not encrypted")
            else:
                logger.info(f"Created backup: {backup_path}")
            
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None
    
    def restore_backup(
        self,
        backup_path: str,
        restore_dir: str = ".",
        overwrite: bool = False
    ) -> bool:
        """
        Restore files from a backup.
        
        Args:
            backup_path: Path to backup file
            restore_dir: Directory to restore files to
            overwrite: Whether to overwrite existing files
            
        Returns:
            True if successful
        """
        backup_file = Path(backup_path)
        if not backup_file.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        restore_path = Path(restore_dir)
        restore_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Decrypt if needed
            temp_zip = None
            if backup_file.suffix == '.encrypted' or backup_file.name.endswith('.encrypted'):
                if not CRYPTO_AVAILABLE or not self.encryption_key:
                    logger.error("Encrypted backup but encryption not available")
                    return False
                
                fernet = self._get_fernet()
                if not fernet:
                    logger.error("Failed to initialize encryption")
                    return False
                
                # Decrypt to temporary file
                temp_zip = backup_file.with_suffix('.zip.tmp')
                with open(backup_file, 'rb') as f:
                    encrypted_data = f.read()
                
                try:
                    decrypted_data = fernet.decrypt(encrypted_data)
                except Exception as e:
                    logger.error(f"Decryption failed: {e}")
                    return False
                
                with open(temp_zip, 'wb') as f:
                    f.write(decrypted_data)
                
                zip_file = temp_zip
            else:
                zip_file = backup_file
            
            # Extract files
            with zipfile.ZipFile(zip_file, 'r') as zipf:
                # List files
                file_list = zipf.namelist()
                
                for filename in file_list:
                    if filename == '_metadata.json':
                        continue
                    
                    # Extract file
                    dest_path = restore_path / filename
                    
                    if dest_path.exists() and not overwrite:
                        logger.warning(f"File exists, skipping: {dest_path}")
                        continue
                    
                    # Ensure parent directory exists
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Extract
                    with zipf.open(filename) as source:
                        with open(dest_path, 'wb') as target:
                            target.write(source.read())
                    
                    logger.info(f"Restored: {filename} -> {dest_path}")
            
            # Clean up temp file
            if temp_zip and temp_zip.exists():
                temp_zip.unlink()
            
            logger.info(f"Restore complete from: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            
            # Clean up temp file
            if temp_zip and temp_zip.exists():
                temp_zip.unlink()
            
            return False
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups."""
        backups = []
        
        for backup_file in self.safehouse_dir.iterdir():
            if backup_file.is_file():
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
        """Get metadata from a backup."""
        backup_file = Path(backup_path)
        if not backup_file.exists():
            return None
        
        try:
            # Decrypt if needed
            temp_zip = None
            if backup_file.suffix == '.encrypted' or backup_file.name.endswith('.encrypted'):
                if not CRYPTO_AVAILABLE or not self.encryption_key:
                    return None
                
                fernet = self._get_fernet()
                if not fernet:
                    return None
                
                temp_zip = backup_file.with_suffix('.zip.tmp')
                with open(backup_file, 'rb') as f:
                    encrypted_data = f.read()
                
                decrypted_data = fernet.decrypt(encrypted_data)
                with open(temp_zip, 'wb') as f:
                    f.write(decrypted_data)
                
                zip_file = temp_zip
            else:
                zip_file = backup_file
            
            # Read metadata
            with zipfile.ZipFile(zip_file, 'r') as zipf:
                if '_metadata.json' in zipf.namelist():
                    metadata_json = zipf.read('_metadata.json').decode('utf-8')
                    metadata = json.loads(metadata_json)
                    
                    # Clean up
                    if temp_zip and temp_zip.exists():
                        temp_zip.unlink()
                    
                    return metadata
            
            # Clean up
            if temp_zip and temp_zip.exists():
                temp_zip.unlink()
            
            return None
            
        except Exception as e:
            logger.error(f"Error reading backup metadata: {e}")
            if temp_zip and temp_zip.exists():
                temp_zip.unlink()
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

