# module_registry.py

import os
import importlib.util

class ModuleRegistry:
    def __init__(self, base_path="."):
        self.base_path = base_path
        self.modules = {}

    def scan_modules(self):
        self.modules = {}  # Reset

        for filename in os.listdir(self.base_path):
            if filename.endswith(".py"):
                name = filename[:-3]
                full_path = os.path.join(self.base_path, filename)
                exists = os.path.isfile(full_path)
                loaded = importlib.util.find_spec(name) is not None

                self.modules[name] = {
                    "filename": filename,
                    "path": full_path,
                    "exists": exists,
                    "loaded": loaded,
                    "status": "active" if loaded else "missing",
                    "purpose": "(unknown)",  # Can be set later
                    "dependencies": []       # Future: dependency graph
                }

    def set_purpose(self, name, description):
        if name in self.modules:
            self.modules[name]["purpose"] = description

    def list_all(self):
        return self.modules

    def list_active(self):
        return {k: v for k, v in self.modules.items() if v["status"] == "active"}

    def get(self, name):
        return self.modules.get(name, {"status": "unregistered"})
