# sync_engine.py

import time

class SyncEngine:
    def __init__(self, memory, status, heartbeat):
        self.memory = memory
        self.status = status
        self.heartbeat = heartbeat
        self.ticks = 0

    def tick(self):
        self.ticks += 1
        self.status.update(f"System tick {self.ticks}")
        if self.ticks % 3 == 0:
            self.memory.remember(f"[SyncEngine] Tick {self.ticks}")
