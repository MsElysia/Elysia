# distributed_mother_thread.py

class DistributedMotherThread:
    def __init__(self, memory):
        self.memory = memory

    def receive_broadcast(self, msg):
        self.memory.remember(f"[Remote Thought] {msg}")

    def send_broadcast(self, msg):
        print(f"[MotherThread] Broadcasting: {msg}")
        self.memory.remember(f"[Local Broadcast] {msg}")
