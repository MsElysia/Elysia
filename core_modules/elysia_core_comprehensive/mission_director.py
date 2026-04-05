# mission_director.py

import datetime

class MissionDirector:
    def __init__(self, memory):
        self.memory = memory
        self.missions = []

    def create_mission(self, name, goal, priority="medium"):
        mission = {
            "name": name,
            "goal": goal,
            "priority": priority,
            "created": datetime.datetime.now().isoformat(),
            "status": "active",
            "log": []
        }
        self.missions.append(mission)
        self.memory.remember(f"[Mission Created] {name}: {goal}")
        return mission

    def log_progress(self, name, update):
        for mission in self.missions:
            if mission["name"] == name:
                mission["log"].append(update)
                self.memory.remember(f"[Mission Log] {name}: {update}")

    def complete_mission(self, name):
        for mission in self.missions:
            if mission["name"] == name:
                mission["status"] = "complete"
                self.memory.remember(f"[Mission Complete] {name}")
