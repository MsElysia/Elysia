# reality_mapper.py

class RealityMapper:
    def __init__(self, memory):
        self.memory = memory
        self.facts = []

    def absorb_fact(self, statement):
        self.facts.append(statement)
        self.memory.remember(f"[Mapped Fact] {statement}")

    def map_summary(self, limit=10):
        return self.facts[-limit:]
