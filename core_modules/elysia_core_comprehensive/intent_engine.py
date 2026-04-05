# intent_engine.py

class IntentEngine:
    def __init__(self, memory):
        self.memory = memory
        self.intents = []

    def declare_intent(self, intent, source="system"):
        record = {"intent": intent, "source": source}
        self.intents.append(record)
        self.memory.remember(f"[Intent] {source} → {intent}")

    def recent_intents(self, limit=5):
        return self.intents[-limit:]
