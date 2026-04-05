# task_engine.py

import datetime

class TaskEngine:
    def __init__(self, memory):
        self.memory = memory
        self.tasks = []

    def create_task(self, name, description):
        task = {
            "name": name,
            "description": description,
            "created": datetime.datetime.now().isoformat(),
            "completed": False,
            "logs": []
        }
        self.tasks.append(task)
        self.memory.remember(f"[Task Created] {name}: {description}")
        return task

    def log_task(self, name, note):
        for task in self.tasks:
            if task["name"] == name and not task["completed"]:
                task["logs"].append({"time": datetime.datetime.now().isoformat(), "note": note})
                self.memory.remember(f"[Task Log] {name}: {note}")
                return
        self.memory.remember(f"[Task Log Failed] No active task: {name}")

    def complete_task(self, name):
        for task in self.tasks:
            if task["name"] == name and not task["completed"]:
                task["completed"] = True
                task["completed_time"] = datetime.datetime.now().isoformat()
                self.memory.remember(f"[Task Completed] {name}")
                return
        self.memory.remember(f"[Task Completion Failed] Task not found or already complete: {name}")
