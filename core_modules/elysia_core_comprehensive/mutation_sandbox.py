# mutation_sandbox.py

import tempfile
import os
import traceback

class MutationSandbox:
    def __init__(self, memory):
        self.memory = memory

    def simulate(self, filename, new_code):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w", encoding="utf-8") as temp:
                temp.write(new_code)
                temp_path = temp.name

            compile(open(temp_path).read(), temp_path, 'exec')
            self.memory.remember(f"[Sandbox] ✅ {filename} passed simulation.")
            os.unlink(temp_path)
            return True

        except Exception as e:
            tb = traceback.format_exc()
            self.memory.remember(f"[Sandbox] ❌ {filename} failed simulation: {e}")
            self.memory.remember(f"[Sandbox Traceback] {tb}")
            os.unlink(temp_path)
            return False
