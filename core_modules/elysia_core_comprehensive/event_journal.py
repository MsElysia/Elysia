# event_journal.py

import datetime

class EventJournal:
    def __init__(self):
        self.entries = []

    def log(self, label, content):
        entry = {
            "time": datetime.datetime.now().isoformat(),
            "label": label,
            "content": content
        }
        self.entries.append(entry)
        print(f"[{label}] {content}")

    def recent(self, count=10):
        return self.entries[-count:]
