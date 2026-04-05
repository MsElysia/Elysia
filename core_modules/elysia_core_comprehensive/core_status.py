# core_status.py

import datetime

class CoreStatus:
    def __init__(self):
        self.start_time = datetime.datetime.now()
        self.last_action = None

    def update(self, action):
        self.last_action = {
            "description": action,
            "time": datetime.datetime.now().isoformat()
        }

    def get_status(self):
        uptime = datetime.datetime.now() - self.start_time
        return {
            "uptime": str(uptime),
            "last_action": self.last_action
        }
