# thread_labeler.py

class ThreadLabeler:
    def __init__(self, memory):
        self.memory = memory
        self.threads = {}

    def label_thought(self, label, thought):
        if label not in self.threads:
            self.threads[label] = []
        self.threads[label].append(thought)
        self.memory.remember(f"[Thread:{label}] {thought}")

    def get_thread(self, label):
        return self.threads.get(label, [])
