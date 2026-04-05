# project_guardian/global_priority_registry.py
# GlobalPriorityRegistry: System-Wide Priority and Configuration Management
# Based on Conversation 3 (elysia 4 sub a) design specifications

import logging
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from threading import Lock
import copy

logger = logging.getLogger(__name__)


@dataclass
class PriorityEntry:
    """A priority entry with metadata."""
    key: str
    value: Any
    priority: float = 0.5  # 0.0-1.0
    module: str = "system"
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "value": self.value,
            "priority": self.priority,
            "module": self.module,
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriorityEntry":
        """Create PriorityEntry from dictionary."""
        return cls(
            key=data["key"],
            value=data["value"],
            priority=data.get("priority", 0.5),
            module=data.get("module", "system"),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
            metadata=data.get("metadata", {})
        )


class GlobalPriorityRegistry:
    """
    System-wide priority and configuration management.
    Provides a global key-value store for priorities, settings, and cross-module communication.
    """
    
    def __init__(self, storage_path: str = "data/global_priority_registry.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe storage
        self._entries: Dict[str, PriorityEntry] = {}
        self._lock = Lock()
        
        # Configuration namespaces
        self._namespaces: Dict[str, Dict[str, Any]] = {}
        
        # History tracking
        self._history: List[Dict[str, Any]] = []
        
        self.load()
    
    def set(
        self,
        key: str,
        value: Any,
        priority: float = 0.5,
        module: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Set a priority/configuration value.
        
        Args:
            key: Configuration key
            value: Value to store
            priority: Priority level (0.0-1.0)
            module: Module name that set this value
            metadata: Optional metadata
        """
        with self._lock:
            # Check if value changed
            old_entry = self._entries.get(key)
            old_value = old_entry.value if old_entry else None
            
            entry = PriorityEntry(
                key=key,
                value=value,
                priority=priority,
                module=module,
                metadata=metadata or {}
            )
            
            self._entries[key] = entry
            
            # Record history if value changed
            if old_value != value:
                self._history.append({
                    "key": key,
                    "old_value": old_value,
                    "new_value": value,
                    "module": module,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Keep only last 1000 history entries
                if len(self._history) > 1000:
                    self._history = self._history[-1000:]
            
            self.save()
            logger.debug(f"Set priority: {key} = {value} (priority: {priority}, module: {module})")
    
    def get(
        self,
        key: str,
        default: Any = None,
        filter_by_priority: Optional[float] = None
    ) -> Any:
        """
        Get a priority/configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            filter_by_priority: Minimum priority threshold (optional)
            
        Returns:
            Value or default
        """
        with self._lock:
            entry = self._entries.get(key)
            
            if not entry:
                return default
            
            # Filter by priority if specified
            if filter_by_priority is not None:
                if entry.priority < filter_by_priority:
                    return default
            
            return entry.value
    
    def get_entry(self, key: str) -> Optional[PriorityEntry]:
        """Get the full priority entry for a key."""
        with self._lock:
            return self._entries.get(key)
    
    def get_all_keys(self, module: Optional[str] = None) -> List[str]:
        """Get all keys, optionally filtered by module."""
        with self._lock:
            if module:
                return [
                    key for key, entry in self._entries.items()
                    if entry.module == module
                ]
            return list(self._entries.keys())
    
    def get_by_priority_range(
        self,
        min_priority: float = 0.0,
        max_priority: float = 1.0
    ) -> Dict[str, Any]:
        """
        Get all entries within a priority range.
        
        Args:
            min_priority: Minimum priority
            max_priority: Maximum priority
            
        Returns:
            Dictionary of key -> value
        """
        with self._lock:
            result = {}
            for key, entry in self._entries.items():
                if min_priority <= entry.priority <= max_priority:
                    result[key] = entry.value
            return result
    
    def get_high_priority(self, threshold: float = 0.7) -> Dict[str, Any]:
        """Get all high-priority entries."""
        return self.get_by_priority_range(min_priority=threshold, max_priority=1.0)
    
    def increment_priority(self, key: str, amount: float = 0.1):
        """Increment priority for a key."""
        with self._lock:
            entry = self._entries.get(key)
            if entry:
                entry.priority = min(1.0, entry.priority + amount)
                entry.updated_at = datetime.now()
                self.save()
    
    def decrement_priority(self, key: str, amount: float = 0.1):
        """Decrement priority for a key."""
        with self._lock:
            entry = self._entries.get(key)
            if entry:
                entry.priority = max(0.0, entry.priority - amount)
                entry.updated_at = datetime.now()
                self.save()
    
    def delete(self, key: str) -> bool:
        """Delete a priority entry."""
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                self.save()
                logger.info(f"Deleted priority entry: {key}")
                return True
            return False
    
    def clear_module(self, module: str) -> int:
        """Clear all entries for a module."""
        with self._lock:
            keys_to_delete = [
                key for key, entry in self._entries.items()
                if entry.module == module
            ]
            
            for key in keys_to_delete:
                del self._entries[key]
            
            if keys_to_delete:
                self.save()
                logger.info(f"Cleared {len(keys_to_delete)} entries for module: {module}")
            
            return len(keys_to_delete)
    
    # Namespace management
    def create_namespace(self, namespace: str, defaults: Optional[Dict[str, Any]] = None):
        """Create a configuration namespace."""
        with self._lock:
            if namespace not in self._namespaces:
                self._namespaces[namespace] = defaults or {}
                self.save()
    
    def get_namespace(self, namespace: str) -> Dict[str, Any]:
        """Get all values in a namespace."""
        with self._lock:
            return self._namespaces.get(namespace, {}).copy()
    
    def set_namespace_value(self, namespace: str, key: str, value: Any):
        """Set a value in a namespace."""
        with self._lock:
            if namespace not in self._namespaces:
                self._namespaces[namespace] = {}
            self._namespaces[namespace][key] = value
            self.save()
    
    def get_namespace_value(self, namespace: str, key: str, default: Any = None) -> Any:
        """Get a value from a namespace."""
        with self._lock:
            namespace_data = self._namespaces.get(namespace, {})
            return namespace_data.get(key, default)
    
    # Export/Import
    def export_config(
        self,
        filepath: Optional[str] = None,
        include_history: bool = False
    ) -> str:
        """
        Export configuration to JSON file.
        
        Args:
            filepath: Optional custom file path
            include_history: Whether to include change history
            
        Returns:
            Path to exported file
        """
        path = Path(filepath) if filepath else self.storage_path.parent / "priority_registry_export.json"
        
        with self._lock:
            data = {
                "entries": {
                    key: entry.to_dict()
                    for key, entry in self._entries.items()
                },
                "namespaces": self._namespaces.copy(),
                "exported_at": datetime.now().isoformat()
            }
            
            if include_history:
                data["history"] = self._history[-100:]  # Last 100 changes
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Exported {len(self._entries)} entries to {path}")
        return str(path)
    
    def import_config(self, filepath: str, merge: bool = True):
        """
        Import configuration from JSON file.
        
        Args:
            filepath: Path to JSON file
            merge: If True, merge with existing config. If False, replace.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        with self._lock:
            if not merge:
                self._entries.clear()
                self._namespaces.clear()
            
            # Import entries
            for key, entry_data in data.get("entries", {}).items():
                entry = PriorityEntry.from_dict(entry_data)
                self._entries[key] = entry
            
            # Import namespaces
            for namespace, namespace_data in data.get("namespaces", {}).items():
                if merge and namespace in self._namespaces:
                    self._namespaces[namespace].update(namespace_data)
                else:
                    self._namespaces[namespace] = namespace_data
        
        self.save()
        logger.info(f"Imported config from {filepath}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with self._lock:
            module_counts = {}
            priority_distribution = {
                "high": 0,      # >= 0.7
                "medium": 0,    # 0.3-0.69
                "low": 0        # < 0.3
            }
            
            for entry in self._entries.values():
                # Count by module
                module_counts[entry.module] = module_counts.get(entry.module, 0) + 1
                
                # Priority distribution
                if entry.priority >= 0.7:
                    priority_distribution["high"] += 1
                elif entry.priority >= 0.3:
                    priority_distribution["medium"] += 1
                else:
                    priority_distribution["low"] += 1
            
            return {
                "total_entries": len(self._entries),
                "modules": module_counts,
                "priority_distribution": priority_distribution,
                "namespaces": len(self._namespaces),
                "history_entries": len(self._history)
            }
    
    def get_change_history(
        self,
        key: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get change history, optionally filtered."""
        with self._lock:
            history = self._history[-limit:]
            
            if key:
                history = [h for h in history if h["key"] == key]
            
            if module:
                history = [h for h in history if h.get("module") == module]
            
            return history
    
    def save(self):
        """Save registry to disk."""
        with self._lock:
            data = {
                "entries": {
                    key: entry.to_dict()
                    for key, entry in self._entries.items()
                },
                "namespaces": self._namespaces.copy(),
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
    
    def load(self):
        """Load registry from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                # Load entries
                for key, entry_data in data.get("entries", {}).items():
                    entry = PriorityEntry.from_dict(entry_data)
                    self._entries[key] = entry
                
                # Load namespaces
                self._namespaces = data.get("namespaces", {})
            
            logger.info(f"Loaded {len(self._entries)} priority entries from registry")
        except Exception as e:
            logger.error(f"Error loading priority registry: {e}")


# Example usage
if __name__ == "__main__":
    registry = GlobalPriorityRegistry()
    
    # Set some priorities
    registry.set("task.max_concurrent", 10, priority=0.8, module="runtime_loop")
    registry.set("memory.cache_size_mb", 512, priority=0.6, module="memory_core")
    registry.set("api.rate_limit", 100, priority=0.9, module="api_manager")
    
    # Get values
    max_concurrent = registry.get("task.max_concurrent")
    print(f"Max concurrent tasks: {max_concurrent}")
    
    # Get high-priority entries
    high_priority = registry.get_high_priority(threshold=0.7)
    print(f"High priority entries: {high_priority}")
    
    # Create namespace
    registry.create_namespace("runtime_config", {
        "enable_caching": True,
        "log_level": "INFO"
    })
    
    # Get statistics
    stats = registry.get_statistics()
    print(f"Registry statistics: {stats}")
    
    # Export config
    export_path = registry.export_config(include_history=True)
    print(f"Exported to: {export_path}")

