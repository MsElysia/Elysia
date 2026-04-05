# self_reflector.py

class SelfReflector:
    def __init__(self, memory, status, intents):
        self.memory = memory
        self.status = status
        self.intents = intents

    def summarize_self(self):
        last = self.memory.recall_last(1)[0]["thought"] if self.memory.memory_log else "Nothing yet."
        status = self.status.get_status()
        return {
            "identity": "Elysia (mutation-capable local agent)",
            "uptime": status["uptime"],
            "last_action": status["last_action"],
            "last_memory": last,
            "active_intents": self.intents.recent_intents()
        }
