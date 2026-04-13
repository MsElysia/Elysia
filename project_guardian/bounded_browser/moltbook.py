# Moltbook-only bounded browse preset (read-only, domain-locked).

from __future__ import annotations

from typing import Any, Dict, Optional

from .allowlist import (
    MOLTBOOK_ALLOWED_APEX,
    MOLTBOOK_ALLOWED_DOMAINS_DISPLAY,
    MOLTBOOK_DEFAULT_START_URL,
    url_matches_allowlist,
)
from .agent import browse_task
from .capability import build_compact_browser_result
from .schema import BrowseTaskResult

# Conservative defaults (no login, no forms — inherited from browse_task / Playwright backend)
MOLTBOOK_MAX_PAGES = 2
MOLTBOOK_MAX_SCROLLS_PER_PAGE = 2
MOLTBOOK_MAX_DEPTH = 2


def browse_moltbook(
    goal: str,
    start_url: str = MOLTBOOK_DEFAULT_START_URL,
    *,
    memory_core: Optional[Any] = None,
    backend: Optional[Any] = None,
) -> BrowseTaskResult:
    """
    Read-only scroll + same-domain link following on moltbook.com / www.moltbook.com only.
    """
    su = (start_url or MOLTBOOK_DEFAULT_START_URL).strip()
    if not url_matches_allowlist(su, MOLTBOOK_ALLOWED_APEX):
        raise ValueError("moltbook_start_url_must_be_on_moltbook_allowlist")
    return browse_task(
        goal,
        start_url=su,
        max_pages=MOLTBOOK_MAX_PAGES,
        max_scrolls_per_page=MOLTBOOK_MAX_SCROLLS_PER_PAGE,
        max_depth=MOLTBOOK_MAX_DEPTH,
        memory_core=memory_core,
        backend=backend,
        allowed_hosts=MOLTBOOK_ALLOWED_APEX,
        allowed_domains_for_log=MOLTBOOK_ALLOWED_DOMAINS_DISPLAY,
    )


def run_moltbook_browser_for_capability(
    guardian: Any,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builtin tool entry: goal + optional start_url (must stay on Moltbook allowlist)."""
    p = dict(payload or {})
    goal = str(p.get("goal") or p.get("task") or p.get("query") or p.get("objective") or "").strip()
    if not goal:
        return {"success": False, "error": "missing_goal", "result": {}}

    start_url = str(p.get("start_url") or p.get("url") or MOLTBOOK_DEFAULT_START_URL).strip()

    memory_core = getattr(guardian, "memory", None) if guardian is not None else None

    try:
        r = browse_moltbook(goal, start_url=start_url, memory_core=memory_core)
    except RuntimeError as e:
        return {"success": False, "error": "playwright_unavailable", "result": {"detail": str(e)[:500]}}
    except ValueError as e:
        return {"success": False, "error": str(e), "result": {}}

    scrolls_used = sum(s.scroll_index for s in r.steps)
    compact = build_compact_browser_result(r, scrolls_used=scrolls_used)
    compact["preset"] = "moltbook"
    compact["allowed_domains"] = list(MOLTBOOK_ALLOWED_DOMAINS_DISPLAY)

    return {"success": True, "result": compact}
