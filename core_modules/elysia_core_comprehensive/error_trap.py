# error_trap.py

import traceback

class ErrorTrap:
    def __init__(self, memory):
        self.memory = memory

    def wrap(self, func):
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                tb = traceback.format_exc()
                self.memory.remember(f"[Error] {e}")
                self.memory.remember(f"[Traceback] {tb}")
                print(f"[ErrorTrap] {e}\n{tb}")
                return None
        return wrapped
