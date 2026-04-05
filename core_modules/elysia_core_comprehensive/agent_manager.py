# agent_manager.py

class AgentManager:
    def __init__(self):
        self.agents = {}

    def register(self, name, capabilities):
        self.agents[name] = {
            "name": name,
            "capabilities": capabilities,
            "status": "idle",
            "history": []
        }

    def log_result(self, name, result):
        if name in self.agents:
            self.agents[name]["history"].append(result)
            self.agents[name]["status"] = "updated"
