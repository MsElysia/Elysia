"""Example: call Elysia's Think-Decide-Act pipeline.

Run from the repository root:

    python examples/think_decide_act_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from pprint import pprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_guardian.orchestration import run_think_decide_act_pipeline


class DemoMemory:
    def __init__(self) -> None:
        self.entries = []

    def search_memories(self, query: str, limit: int = 10):
        return [{"thought": f"demo memory matching {query}", "category": "demo"}][:limit]

    def remember(self, thought: str, category: str = "general", priority: float = 0.5, metadata=None):
        self.entries.append(
            {
                "thought": thought,
                "category": category,
                "priority": priority,
                "metadata": metadata or {},
            }
        )


if __name__ == "__main__":
    memory = DemoMemory()
    trace = run_think_decide_act_pipeline(
        {"source": "user_request", "raw_input": "search memory for launch notes"},
        context={"relevant_context_ids": ["demo-session"], "memory_search_limit": 3},
        memory=memory,
    )
    pprint(trace.to_dict())
