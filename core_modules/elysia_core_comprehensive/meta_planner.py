# meta_planner.py

import random

class MetaPlanner:
    def __init__(self, memory):
        self.memory = memory
        self.modes = ["dream", "reflect", "mutate", "speak", "idle"]

    def choose_action(self):
        action = random.choice(self.modes)
        self.memory.remember(f"[MetaPlanner] Chose action: {action}")
        return action
