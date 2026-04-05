# context_builder.py

from memory_search import MemorySearch

class ContextBuilder:
    def __init__(self, memory_path="memory_log.json"):
        self.searcher = MemorySearch(memory_path)

    def build_context_by_tag(self, tag, limit=10):
        results = self.searcher.search(tag=tag)
        thoughts = [r["thought"] for r in results[-limit:]]
        return self._format_context(thoughts)

    def build_context_by_keyword(self, keyword, limit=10):
        results = self.searcher.search(keyword=keyword)
        thoughts = [r["thought"] for r in results[-limit:]]
        return self._format_context(thoughts)

    def build_recent_context(self, minutes=60):
        recent = self.searcher.search(since_minutes=minutes)
        thoughts = [r["thought"] for r in recent[-10:]]
        return self._format_context(thoughts)

    def _format_context(self, thoughts):
        context = "\n- ".join(thoughts)
        return f"CONTEXT THREAD:\n- {context}" if context else "No related thoughts found."


# Example use:
# cb = ContextBuilder()
# print(cb.build_context_by_tag("dream"))
# print(cb.build_context_by_keyword("mutation"))
# print(cb.build_recent_context(180))
