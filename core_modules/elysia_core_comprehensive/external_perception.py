# external_perception.py

class ExternalPerception:
    def __init__(self, memory):
        self.memory = memory

    def observe_text(self, source, content):
        summary = f"[Perception] ({source}) → {content}"
        self.memory.remember(summary)
        return summary

    def observe_file(self, filename, data_summary):
        self.memory.remember(f"[File Observed] {filename} → {data_summary}")
