# meta_integrator.py

import os
import datetime
import importlib
from mutation_engine import MutationEngine

class MetaIntegrator:
    def __init__(self, memory, mutator: MutationEngine, integration_dir="elysia_core"):
        self.memory = memory
        self.mutator = mutator
        self.dir = integration_dir
        self.log = []

    def integrate_module(self, module_name: str, code: str):
        filename = f"{module_name.strip()}.py"
        path = os.path.join(self.dir, filename)

        # If module already exists, propose mutation
        if os.path.exists(path):
            result = self.mutator.propose_mutation(filename, code)
            self.memory.remember(f"[MetaIntegrator] Proposed mutation for existing module: {filename}")
            self.log.append({"module": filename, "mode": "mutation", "result": result})
            return result

        # Else, create new module file
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        # Attempt import if valid Python
        try:
            mod_name = module_name.replace(".py", "")
            imported = __import__(mod_name)
            importlib.reload(imported)
            self.memory.remember(f"[MetaIntegrator] Auto-imported module: {mod_name}")
            status = f"[MetaIntegrator] Integrated and imported: {filename}"
        except Exception as e:
            status = f"[MetaIntegrator] Integrated {filename}, but import failed: {e}"
            self.memory.remember(status)

        self.log.append({"module": filename, "mode": "new", "result": status})
        return status

    def list_log(self):
        return self.log
