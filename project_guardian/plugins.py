# project_guardian/plugins.py
# Plugin Management System for Project Guardian

import os
import importlib.util
import inspect
from typing import Dict, Any, List, Optional, Callable
from .memory import MemoryCore

class PluginLoader:
    """
    Dynamic plugin system for Project Guardian.
    Provides plugin loading, activation, and management capabilities.
    """
    
    def __init__(self, memory: MemoryCore, plugin_dir: str = "guardian_plugins"):
        self.memory = memory
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Any] = {}
        self.plugin_metadata: Dict[str, Dict[str, Any]] = {}
        self.loaded_plugins: List[str] = []
        
        # Ensure plugin directory exists
        os.makedirs(self.plugin_dir, exist_ok=True)
        
    def load_plugins(self) -> List[str]:
        """
        Load all available plugins from the plugin directory.
        
        Returns:
            List of loaded plugin names
        """
        if not os.path.exists(self.plugin_dir):
            self.memory.remember(
                f"[Guardian Plugin] No plugin folder found: {self.plugin_dir}",
                category="plugin",
                priority=0.6
            )
            return []
            
        loaded_plugins = []
        
        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                plugin_name = filename[:-3]
                plugin_path = os.path.join(self.plugin_dir, filename)
                
                try:
                    # Load plugin module
                    spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                    if spec is None or spec.loader is None:
                        raise ImportError(f"Could not load plugin {plugin_name}")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Store plugin
                    self.plugins[plugin_name] = module
                    
                    # Extract metadata
                    metadata = self._extract_plugin_metadata(module, plugin_name)
                    self.plugin_metadata[plugin_name] = metadata
                    
                    # Activate plugin if it has an activate function
                    if hasattr(module, "activate"):
                        try:
                            module.activate()
                            self.loaded_plugins.append(plugin_name)
                            self.memory.remember(
                                f"[Guardian Plugin] Activated: {plugin_name}",
                                category="plugin",
                                priority=0.7
                            )
                        except Exception as e:
                            self.memory.remember(
                                f"[Guardian Plugin] Failed to activate {plugin_name}: {str(e)}",
                                category="plugin",
                                priority=0.8
                            )
                    else:
                        self.loaded_plugins.append(plugin_name)
                        self.memory.remember(
                            f"[Guardian Plugin] Loaded: {plugin_name}",
                            category="plugin",
                            priority=0.6
                        )
                        
                    loaded_plugins.append(plugin_name)
                    
                except Exception as e:
                    self.memory.remember(
                        f"[Guardian Plugin] Failed to load {plugin_name}: {str(e)}",
                        category="plugin",
                        priority=0.8
                    )
                    
        return loaded_plugins
        
    def _extract_plugin_metadata(self, module: Any, plugin_name: str) -> Dict[str, Any]:
        """
        Extract metadata from a plugin module.
        
        Args:
            module: Plugin module
            plugin_name: Name of the plugin
            
        Returns:
            Plugin metadata dictionary
        """
        metadata = {
            "name": plugin_name,
            "version": getattr(module, "__version__", "1.0.0"),
            "description": getattr(module, "__description__", ""),
            "author": getattr(module, "__author__", ""),
            "functions": [],
            "classes": [],
            "has_activate": hasattr(module, "activate"),
            "has_deactivate": hasattr(module, "deactivate")
        }
        
        # Extract functions and classes
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and not name.startswith("_"):
                metadata["functions"].append(name)
            elif inspect.isclass(obj) and not name.startswith("_"):
                metadata["classes"].append(name)
                
        return metadata
        
    def get_plugin(self, plugin_name: str) -> Optional[Any]:
        """
        Get a specific plugin by name.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            Plugin module or None if not found
        """
        return self.plugins.get(plugin_name)
        
    def call_plugin_function(self, plugin_name: str, function_name: str, *args, **kwargs) -> Any:
        """
        Call a function from a specific plugin.
        
        Args:
            plugin_name: Name of the plugin
            function_name: Name of the function to call
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_name}' not found")
            
        if not hasattr(plugin, function_name):
            raise ValueError(f"Function '{function_name}' not found in plugin '{plugin_name}'")
            
        function = getattr(plugin, function_name)
        if not callable(function):
            raise ValueError(f"'{function_name}' is not callable in plugin '{plugin_name}'")
            
        try:
            result = function(*args, **kwargs)
            self.memory.remember(
                f"[Guardian Plugin] Called {plugin_name}.{function_name}",
                category="plugin",
                priority=0.6
            )
            return result
        except Exception as e:
            self.memory.remember(
                f"[Guardian Plugin] Error calling {plugin_name}.{function_name}: {str(e)}",
                category="plugin",
                priority=0.8
            )
            raise
            
    def activate_plugin(self, plugin_name: str) -> bool:
        """
        Activate a specific plugin.
        
        Args:
            plugin_name: Name of the plugin to activate
            
        Returns:
            True if successful
        """
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            return False
            
        if hasattr(plugin, "activate"):
            try:
                plugin.activate()
                if plugin_name not in self.loaded_plugins:
                    self.loaded_plugins.append(plugin_name)
                self.memory.remember(
                    f"[Guardian Plugin] Activated: {plugin_name}",
                    category="plugin",
                    priority=0.7
                )
                return True
            except Exception as e:
                self.memory.remember(
                    f"[Guardian Plugin] Failed to activate {plugin_name}: {str(e)}",
                    category="plugin",
                    priority=0.8
                )
                return False
        else:
            self.memory.remember(
                f"[Guardian Plugin] No activate function in {plugin_name}",
                category="plugin",
                priority=0.6
            )
            return False
            
    def deactivate_plugin(self, plugin_name: str) -> bool:
        """
        Deactivate a specific plugin.
        
        Args:
            plugin_name: Name of the plugin to deactivate
            
        Returns:
            True if successful
        """
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            return False
            
        if hasattr(plugin, "deactivate"):
            try:
                plugin.deactivate()
                if plugin_name in self.loaded_plugins:
                    self.loaded_plugins.remove(plugin_name)
                self.memory.remember(
                    f"[Guardian Plugin] Deactivated: {plugin_name}",
                    category="plugin",
                    priority=0.7
                )
                return True
            except Exception as e:
                self.memory.remember(
                    f"[Guardian Plugin] Failed to deactivate {plugin_name}: {str(e)}",
                    category="plugin",
                    priority=0.8
                )
                return False
        else:
            self.memory.remember(
                f"[Guardian Plugin] No deactivate function in {plugin_name}",
                category="plugin",
                priority=0.6
            )
            return False
            
    def list_plugins(self) -> List[str]:
        """
        Get list of all loaded plugins.
        
        Returns:
            List of plugin names
        """
        return list(self.plugins.keys())
        
    def list_active_plugins(self) -> List[str]:
        """
        Get list of active plugins.
        
        Returns:
            List of active plugin names
        """
        return self.loaded_plugins.copy()
        
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a plugin.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            Plugin information dictionary or None if not found
        """
        if plugin_name not in self.plugins:
            return None
            
        metadata = self.plugin_metadata.get(plugin_name, {})
        metadata["is_active"] = plugin_name in self.loaded_plugins
        metadata["module"] = self.plugins[plugin_name]
        
        return metadata
        
    def get_plugin_stats(self) -> Dict[str, Any]:
        """
        Get plugin system statistics.
        
        Returns:
            Plugin statistics dictionary
        """
        return {
            "total_plugins": len(self.plugins),
            "active_plugins": len(self.loaded_plugins),
            "plugin_directory": self.plugin_dir,
            "plugins": list(self.plugins.keys()),
            "active_plugins_list": self.loaded_plugins.copy()
        }
        
    def reload_plugin(self, plugin_name: str) -> bool:
        """
        Reload a specific plugin.
        
        Args:
            plugin_name: Name of the plugin to reload
            
        Returns:
            True if successful
        """
        if plugin_name not in self.plugins:
            return False
            
        # Deactivate if active
        if plugin_name in self.loaded_plugins:
            self.deactivate_plugin(plugin_name)
            
        # Remove from plugins
        del self.plugins[plugin_name]
        if plugin_name in self.plugin_metadata:
            del self.plugin_metadata[plugin_name]
            
        # Reload
        plugin_path = os.path.join(self.plugin_dir, f"{plugin_name}.py")
        if os.path.exists(plugin_path):
            try:
                spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not reload plugin {plugin_name}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                self.plugins[plugin_name] = module
                self.plugin_metadata[plugin_name] = self._extract_plugin_metadata(module, plugin_name)
                
                # Reactivate if it was active before
                if hasattr(module, "activate"):
                    module.activate()
                    self.loaded_plugins.append(plugin_name)
                    
                self.memory.remember(
                    f"[Guardian Plugin] Reloaded: {plugin_name}",
                    category="plugin",
                    priority=0.7
                )
                return True
                
            except Exception as e:
                self.memory.remember(
                    f"[Guardian Plugin] Failed to reload {plugin_name}: {str(e)}",
                    category="plugin",
                    priority=0.8
                )
                return False
                
        return False 