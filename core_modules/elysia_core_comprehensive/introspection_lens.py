# introspection_lens.py

import datetime

class IntrospectionLens:
    def __init__(self, memory):
        self.memory = memory

    def list_recent(self, count=10):
        return self.memory.dump_all()[-count:]

    def count_tags(self, tag_prefix="["):
        return sum(1 for thought in self.memory.dump_all() if thought["thought"].startswith(tag_prefix))

    def first_memory_time(self):
        if not self.memory.memory_log:
            return "N/A"
        return self.memory.memory_log[0]["time"]
