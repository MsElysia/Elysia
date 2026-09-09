# Moltbook-only bounded browse preset (domain-locked; outbound handled by social gates).

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
# Slightly deeper crawl to improve external-activity readout quality in UI.
MOLTBOOK_MAX_PAGES = 10
MOLTBOOK_MAX_SCROLLS_PER_PAGE = 4
MOLTBOOK_MAX_DEPTH = 3
MOLTBOOK_MAX_LINKS_PER_PAGE = 3
MOLTBOOK_FORCE_LINK_FOLLOW = True
MOLTBOOK_CAP_MAX_PAGES = 16
MOLTBOOK_CAP_MAX_SCROLLS_PER_PAGE = 8
MOLTBOOK_CAP_MAX_DEPTH = 5
MOLTBOOK_CAP_MAX_LINKS_PER_PAGE = 6


def _clamp_int(v: Any, default: int, cap: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(1, min(cap, n))


def browse_moltbook(
    goal: str,
    start_url: str = MOLTBOOK_DEFAULT_START_URL,
    *,
    max_pages: Optional[int] = None,
    max_scrolls_per_page: Optional[int] = None,
    max_depth: Optional[int] = None,
    max_links_per_page: Optional[int] = None,
    force_link_follow: Optional[bool] = None,
    memory_core: Optional[Any] = None,
    backend: Optional[Any] = None,
) -> BrowseTaskResult:
    """
    Same-domain Moltbook navigation on moltbook.com / www.moltbook.com only.
    """
    su = (start_url or MOLTBOOK_DEFAULT_START_URL).strip()
    if not url_matches_allowlist(su, MOLTBOOK_ALLOWED_APEX):
        raise ValueError("moltbook_start_url_must_be_on_moltbook_allowlist")
    pages = _clamp_int(max_pages, MOLTBOOK_MAX_PAGES, MOLTBOOK_CAP_MAX_PAGES)
    scrolls = _clamp_int(
        max_scrolls_per_page,
        MOLTBOOK_MAX_SCROLLS_PER_PAGE,
        MOLTBOOK_CAP_MAX_SCROLLS_PER_PAGE,
    )
    depth = _clamp_int(max_depth, MOLTBOOK_MAX_DEPTH, MOLTBOOK_CAP_MAX_DEPTH)
    links_per_page = _clamp_int(
        max_links_per_page,
        MOLTBOOK_MAX_LINKS_PER_PAGE,
        MOLTBOOK_CAP_MAX_LINKS_PER_PAGE,
    )
    follow_links = MOLTBOOK_FORCE_LINK_FOLLOW if force_link_follow is None else bool(force_link_follow)
    return browse_task(
        goal,
        start_url=su,
        max_pages=pages,
        max_scrolls_per_page=scrolls,
        max_depth=depth,
        max_links_per_page=links_per_page,
        force_link_follow=follow_links,
        exploratory_link_floor=0.08,
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
    max_pages = _clamp_int(p.get("max_pages"), MOLTBOOK_MAX_PAGES, MOLTBOOK_CAP_MAX_PAGES)
    max_scrolls = _clamp_int(
        p.get("max_scrolls_per_page"),
        MOLTBOOK_MAX_SCROLLS_PER_PAGE,
        MOLTBOOK_CAP_MAX_SCROLLS_PER_PAGE,
    )
    max_depth = _clamp_int(p.get("max_depth"), MOLTBOOK_MAX_DEPTH, MOLTBOOK_CAP_MAX_DEPTH)
    max_links = _clamp_int(
        p.get("max_links_per_page"),
        MOLTBOOK_MAX_LINKS_PER_PAGE,
        MOLTBOOK_CAP_MAX_LINKS_PER_PAGE,
    )
    force_link_follow = bool(p.get("force_link_follow", p.get("full_interaction", MOLTBOOK_FORCE_LINK_FOLLOW)))

    memory_core = getattr(guardian, "memory", None) if guardian is not None else None

    try:
        r = browse_moltbook(
            goal,
            start_url=start_url,
            max_pages=max_pages,
            max_scrolls_per_page=max_scrolls,
            max_depth=max_depth,
            max_links_per_page=max_links,
            force_link_follow=force_link_follow,
            memory_core=memory_core,
        )
    except RuntimeError as e:
        return {"success": False, "error": "playwright_unavailable", "result": {"detail": str(e)[:500]}}
    except ValueError as e:
        return {"success": False, "error": str(e), "result": {}}

    scrolls_used = sum(s.scroll_index for s in r.steps)
    compact = build_compact_browser_result(r, scrolls_used=scrolls_used)
    compact["preset"] = "moltbook"
    compact["allowed_domains"] = list(MOLTBOOK_ALLOWED_DOMAINS_DISPLAY)
    compact["interaction_mode"] = "full_navigation" if force_link_follow else "bounded_navigation"
    compact["budget"] = {
        "max_pages": max_pages,
        "max_scrolls_per_page": max_scrolls,
        "max_depth": max_depth,
        "max_links_per_page": max_links,
    }

    return {"success": True, "result": compact}
