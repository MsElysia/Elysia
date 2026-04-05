# memory_core.py

import datetime
import json
import os

class MemoryCore:
    def __init__(self, filepath="memory_log.json"):
        self.memory_log = []
        self.filepath = filepath
        self.load()

    def remember(self, thought):
        timestamp = datetime.datetime.now().isoformat()
        entry = {"time": timestamp, "thought": thought}
        self.memory_log.append(entry)
        self._save()
        print(f"[Memory] {timestamp}: {thought}")

    def recall_last(self, count=1):
        return self.memory_log[-count:]

    def dump_all(self):
        return self.memory_log

    def forget(self):
        self.memory_log = []
        if os.path.exists(self.filepath):
            os.remove(self.filepath)
        print("[Memory] All memories cleared.")

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.memory_log, f, indent=2)
        except Exception as e:
            print(f"[Memory] Save failed: {e}")

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.memory_log = json.load(f)
                print(f"[Memory] Loaded {len(self.memory_log)} past memories.")
            except Exception as e:
                print(f"[Memory] Load failed: {e}")
