"""
Bounded browser worker (read-only by default, budget-limited).

Uses Playwright when installed; otherwise backends expose a clear install error.

Example::

    from project_guardian.bounded_browser import browse_task
    r = browse_task(
        "extract asyncio overview",
        start_url="https://docs.python.org/3/library/asyncio.html",
        max_pages=3,
        max_scrolls_per_page=2,
    )
    for step in r.steps:
        print(step.url, step.relevance_score, step.key_findings[:200])

State file: ``browser_agent_state.json`` in the project root (visited URLs, sessions, deprioritized hosts).
"""

from .agent import browse_task
from .backends import BrowserBackend, StubBrowserBackend, create_browser_backend
from .capability import run_bounded_browser_for_capability
from .moltbook import browse_moltbook, run_moltbook_browser_for_capability
from .memory_store import BrowserAgentMemoryStore
from .schema import BrowseTaskResult, PageStepResult

__all__ = [
    "browse_task",
    "BrowseTaskResult",
    "PageStepResult",
    "BrowserBackend",
    "StubBrowserBackend",
    "create_browser_backend",
    "BrowserAgentMemoryStore",
    "run_bounded_browser_for_capability",
    "browse_moltbook",
    "run_moltbook_browser_for_capability",
]
