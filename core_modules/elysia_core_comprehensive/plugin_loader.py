# plugin_loader.py

import os
import importlib.util

class PluginLoader:
    def __init__(self, plugin_dir="elysia_core/plugins"):
        self.plugin_dir = plugin_dir
        self.plugins = {}

    def load_plugins(self):
        if not os.path.exists(self.plugin_dir):
            print("[PluginLoader] No plugin folder found.")
            return

        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py"):
                name = filename[:-3]
                path = os.path.join(self.plugin_dir, filename)
                spec = importlib.util.spec_from_file_location(name, path)

                try:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.plugins[name] = module

                    print(f"[PluginLoader] Loaded plugin: {name}")
                    if hasattr(module, "activate"):
                        module.activate()
                        print(f"[PluginLoader] Activated: {name}")

                except Exception as e:
                    print(f"[PluginLoader] Failed to load {name}: {e}")

    def list_plugins(self):
        return list(self.plugins.keys())
