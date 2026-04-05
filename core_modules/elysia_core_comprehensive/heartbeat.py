# heartbeat.py

import time
import threading

class Heartbeat:
    def __init__(self, memory, interval=30):
        self.memory = memory
        self.interval = interval
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._beat, daemon=True).start()

    def stop(self):
        self.running = False

    def _beat(self):
        while self.running:
            self.memory.remember("[Heartbeat] Pulse")
            print("[Heartbeat] Tick")
            time.sleep(self.interval)
