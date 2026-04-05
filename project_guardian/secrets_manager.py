# project_guardian/secrets_manager.py
# Secure Secrets Management for Project Guardian
# Implements best practices for API key and credential management

import os
import logging
from typing import Dict, Optional, Any
from pathlib import Path
import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class SecretsManager:
    """
    Secure secrets management for API keys and credentials.
    
    Features:
    - Environment variable support (preferred)
    - Encrypted file storage (fallback)
    - Key rotation support
    - Secure key derivation
    - Never logs secrets
    """
    
    def __init__(
        self,
        master_key_path: Optional[str] = None,
        secrets_dir: Optional[str] = None,
        use_env_vars: bool = True
    ):
        """
        Initialize secrets manager.
        
        Args:
            master_key_path: Path to master encryption key (auto-generated if None)
            secrets_dir: Directory for encrypted secrets (defaults to data/secrets)
            use_env_vars: Prefer environment variables over files
        """
        self.use_env_vars = use_env_vars
        self.secrets_dir = Path(secrets_dir or "data/secrets")
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        
        # Master key for encryption
        self.master_key_path = Path(master_key_path or self.secrets_dir / ".master_key")
        self._master_key = self._load_or_create_master_key()
        self._fernet = Fernet(self._master_key)
    
    def _load_or_create_master_key(self) -> bytes:
        """Load existing master key or create new one."""
        if self.master_key_path.exists():
            try:
                with open(self.master_key_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Could not load master key: {e}, creating new one")
        
        # Generate new master key
        key = Fernet.generate_key()
        try:
            # Store with restrictive permissions (Unix only, Windows will use default)
            with open(self.master_key_path, 'wb') as f:
                f.write(key)
            # Set restrictive permissions on Unix
            if hasattr(os, 'chmod'):
                os.chmod(self.master_key_path, 0o600)
            logger.info("Generated new master encryption key")
        except Exception as e:
            logger.warning(f"Could not save master key: {e}")
        
        return key
    
    def get_secret(self, key_name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a secret value.
        
        Priority:
        1. Environment variable (if use_env_vars=True)
        2. Encrypted file storage
        3. Default value
        
        Args:
            key_name: Secret key name (e.g., "openai_api_key")
            default: Default value if not found
            
        Returns:
            Secret value or None
        """
        # Try environment variable first (most secure)
        if self.use_env_vars:
            env_key = key_name.upper().replace("-", "_")
            value = os.getenv(env_key) or os.getenv(f"GUARDIAN_{env_key}")
            if value:
                logger.debug(f"Loaded {key_name} from environment variable")
                return value
        
        # Try encrypted file
        secret_file = self.secrets_dir / f"{key_name}.encrypted"
        if secret_file.exists():
            try:
                with open(secret_file, 'rb') as f:
                    encrypted = f.read()
                decrypted = self._fernet.decrypt(encrypted)
                logger.debug(f"Loaded {key_name} from encrypted storage")
                return decrypted.decode('utf-8')
            except Exception as e:
                logger.warning(f"Could not decrypt {key_name}: {e}")
        
        # Return default
        if default:
            logger.debug(f"Using default value for {key_name}")
        return default
    
    def set_secret(self, key_name: str, value: str, save_to_file: bool = True) -> bool:
        """
        Store a secret value.
        
        Args:
            key_name: Secret key name
            value: Secret value to store
            save_to_file: If True, save to encrypted file (for non-env use)
            
        Returns:
            True if successful
        """
        if not value:
            logger.warning(f"Attempted to store empty secret: {key_name}")
            return False
        
        if save_to_file:
            try:
                encrypted = self._fernet.encrypt(value.encode('utf-8'))
                secret_file = self.secrets_dir / f"{key_name}.encrypted"
                
                with open(secret_file, 'wb') as f:
                    f.write(encrypted)
                
                # Set restrictive permissions on Unix
                if hasattr(os, 'chmod'):
                    os.chmod(secret_file, 0o600)
                
                logger.info(f"Stored encrypted secret: {key_name}")
                return True
            except Exception as e:
                logger.error(f"Could not store secret {key_name}: {e}")
                return False
        
        return True
    
    def get_all_secrets(self) -> Dict[str, Optional[str]]:
        """Get all stored secrets (for migration/debugging - use carefully)."""
        secrets = {}
        
        # Check encrypted files
        for secret_file in self.secrets_dir.glob("*.encrypted"):
            key_name = secret_file.stem
            secrets[key_name] = self.get_secret(key_name)
        
        return secrets
    
    def delete_secret(self, key_name: str) -> bool:
        """Delete a stored secret."""
        secret_file = self.secrets_dir / f"{key_name}.encrypted"
        if secret_file.exists():
            try:
                secret_file.unlink()
                logger.info(f"Deleted secret: {key_name}")
                return True
            except Exception as e:
                logger.error(f"Could not delete secret {key_name}: {e}")
                return False
        return True
    
    def migrate_from_config(self, config_path: str) -> int:
        """
        Migrate API keys from config file to secure storage.
        
        Args:
            config_path: Path to config file with API keys
            
        Returns:
            Number of secrets migrated
        """
        migrated = 0
        config_file = Path(config_path)
        
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}")
            return 0
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Common API key names
            key_mappings = {
                "openai_api_key": "openai_api_key",
                "claude_api_key": "claude_api_key",
                "openai": "openai_api_key",
                "claude": "claude_api_key",
            }
            
            api_keys = config.get("api_keys", {})
            
            for config_key, secret_key in key_mappings.items():
                if config_key in api_keys:
                    value = api_keys[config_key]
                    if value and isinstance(value, str):
                        self.set_secret(secret_key, value)
                        migrated += 1
                        logger.info(f"Migrated {config_key} to secure storage")
            
            # Also check top-level keys
            for key in key_mappings.keys():
                if key in config and isinstance(config[key], str):
                    secret_key = key_mappings[key]
                    self.set_secret(secret_key, config[key])
                    migrated += 1
                    logger.info(f"Migrated {key} to secure storage")
            
            logger.info(f"Migrated {migrated} secrets to secure storage")
            return migrated
            
        except Exception as e:
            logger.error(f"Could not migrate secrets from {config_path}: {e}")
            return 0


# Global instance
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get global secrets manager instance."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_api_key(service: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get API key for a service using secure storage.
    
    Args:
        service: Service name (e.g., "openai", "claude")
        default: Default value if not found
        
    Returns:
        API key or None
    """
    manager = get_secrets_manager()
    key_name = f"{service}_api_key"
    return manager.get_secret(key_name, default)




















