# Callable capability entry: tight defaults, structured result, session logging.

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .allowlist import parse_payload_allowed_hosts
from .backends import is_safe_http_url
from .schema import BrowseTaskResult

logger = logging.getLogger(__name__)

# Conservative production defaults (override via payload only within caps below)
DEFAULT_MAX_PAGES = 3
DEFAULT_MAX_SCROLLS = 2
DEFAULT_MAX_DEPTH = 1
_CAP_MAX_PAGES = 8
_CAP_MAX_SCROLLS = 6
_CAP_MAX_DEPTH = 3


def _clamp_int(v: Any, default: int, cap: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(1, min(cap, n))


def _unsafe_scheme_in_text(text: str) -> bool:
    t = (text or "").lower()
    return bool(
        re.search(
            r"\b(javascript|data|file|vbscript):",
            t,
            re.I,
        )
    )


def build_compact_browser_result(r: BrowseTaskResult, scrolls_used: int) -> Dict[str, Any]:
    top_findings: List[str] = []
    for s in r.steps:
        k = (s.key_findings or "").strip()
        if k and k not in top_findings:
            top_findings.append(k[:600])
        if len(top_findings) >= 8:
            break

    next_links: List[Dict[str, str]] = []
    seen: set = set()
    for s in reversed(r.steps):
        for L in s.discovered_links or []:
            href = (L.get("href") or "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            next_links.append(
                {
                    "href": href[:800],
                    "text": (L.get("text") or "")[:160],
                }
            )
            if len(next_links) >= 25:
                break

    lines = [
        f"stop={r.stop_reason} pages={len(r.steps)} scrolls≈{scrolls_used}",
    ]
    for s in r.steps[:4]:
        lines.append(f"- [{s.relevance_score:.2f}] {s.page_type} {s.url[:100]}")

    return {
        "summary": "\n".join(lines)[:4000],
        "visited_urls": list(r.visited_urls),
        "top_findings": top_findings,
        "next_links_considered": list(reversed(next_links)),
        "stop_reason": r.stop_reason,
        "goal": r.goal[:2000],
        "start_url": r.start_url[:2000],
        "pages_visited": len(r.steps),
        "scrolls_used": scrolls_used,
        "truncated_by_budget": r.truncated_by_budget,
    }


def run_bounded_browser_for_capability(
    guardian: Any,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute bounded browser session (read-only). Used by:
    - execute_capability_kind(tool, 'elysia_bounded_browser', ...)
    - execute_capability_kind(module, 'bounded_browser', ...)

    Optional payload:
    - allowed_hosts: list of apex hostnames (e.g. ["moltbook.com"]); www. is normalized.
    - allow_any_domain: if true, ignore allowed_hosts (operator override).
    """
    p = dict(payload or {})
    goal = str(p.get("goal") or p.get("task") or p.get("query") or p.get("objective") or "").strip()
    if not goal:
        return {"success": False, "error": "missing_goal", "result": {}}

    if _unsafe_scheme_in_text(goal):
        return {"success": False, "error": "unsafe_scheme_in_goal", "result": {}}

    start_url = p.get("start_url") or p.get("url")
    if start_url is not None:
        start_url = str(start_url).strip()
        if start_url and not is_safe_http_url(start_url):
            return {
                "success": False,
                "error": "unsafe_url_scheme",
                "result": {"refused": start_url[:200]},
            }

    max_pages = _clamp_int(p.get("max_pages"), DEFAULT_MAX_PAGES, _CAP_MAX_PAGES)
    max_scrolls = _clamp_int(p.get("max_scrolls_per_page"), DEFAULT_MAX_SCROLLS, _CAP_MAX_SCROLLS)
    max_depth = _clamp_int(p.get("max_depth"), DEFAULT_MAX_DEPTH, _CAP_MAX_DEPTH)

    memory_core = getattr(guardian, "memory", None) if guardian is not None else None

    allowed_hosts_set = None
    if not bool(p.get("allow_any_domain")):
        allowed_hosts_set = parse_payload_allowed_hosts(p.get("allowed_hosts"))

    from .agent import browse_task

    try:
        r: BrowseTaskResult = browse_task(
            goal,
            start_url=start_url if start_url else None,
            max_pages=max_pages,
            max_scrolls_per_page=max_scrolls,
            max_depth=max_depth,
            memory_core=memory_core,
            **({"allowed_hosts": allowed_hosts_set} if allowed_hosts_set is not None else {}),
        )
    except RuntimeError as e:
        return {"success": False, "error": "playwright_unavailable", "result": {"detail": str(e)[:500]}}
    except ValueError as e:
        return {"success": False, "error": str(e), "result": {}}

    scrolls_used = sum(s.scroll_index for s in r.steps)
    compact = build_compact_browser_result(r, scrolls_used=scrolls_used)
    if allowed_hosts_set is not None:
        compact["allowed_domains"] = sorted(allowed_hosts_set)

    return {"success": True, "result": compact}
