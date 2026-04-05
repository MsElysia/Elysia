# memory_search.py

import json
from datetime import datetime, timedelta

class MemorySearch:
    def __init__(self, memory_path="memory_log.json"):
        self.memory_path = memory_path
        self.memories = self._load_memories()

    def _load_memories(self):
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []

    def search(self, keyword=None, tag=None, since_minutes=None):
        results = []
        now = datetime.utcnow()

        for mem in self.memories:
            content = mem.get("thought", "")
            timestamp = mem.get("timestamp", None)

            if since_minutes and timestamp:
                t = datetime.fromisoformat(timestamp)
                if now - t > timedelta(minutes=since_minutes):
                    continue

            if keyword and keyword.lower() not in content.lower():
                continue

            if tag and not content.strip().lower().startswith(f"[{tag.lower()}"):
                continue

            results.append(mem)

        return results

    def summarize_recent(self, minutes=60):
        recent = self.search(since_minutes=minutes)
        summary = "\n\n".join([m["thought"] for m in recent[-10:]])
        return f"Recent {len(recent)} memories:\n\n{summary}"


# Example use:
# searcher = MemorySearch()
# print(searcher.summarize_recent(120))
# thoughts = searcher.search(keyword="mutation", tag="mutation proposed")
