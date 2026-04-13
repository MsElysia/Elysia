# Heuristic page classification and relevance (no LLM).

from __future__ import annotations

import re
from typing import List, Set, Tuple
from urllib.parse import urlparse

from .schema import ContinueAction, PageType


def _tokens(goal: str) -> Set[str]:
    return {t.lower() for t in re.split(r"\W+", goal) if len(t) > 2}


def relevance_score(goal: str, title: str, text: str) -> float:
    """Rough 0..1 overlap of goal tokens in title+text."""
    g = _tokens(goal)
    if not g:
        return 0.2
    blob = f"{title}\n{text}".lower()
    hits = sum(1 for t in g if t in blob)
    return max(0.0, min(1.0, hits / max(3, len(g) * 0.6)))


def classify_page_type(url: str, title: str, text: str) -> str:
    u = url.lower()
    tl = (title + " " + text[:4000]).lower()
    if "search" in u or re.search(r"[?&]q=|[?&]query=", u):
        return PageType.SEARCH.value
    if any(x in u for x in ("reddit.com", "stackoverflow.com", "discourse", "forum")):
        return PageType.FORUM.value
    if any(x in u for x in ("docs.", "documentation", "/doc/", "readthedocs")):
        return PageType.DOCS.value
    if any(x in u for x in ("rss", "feed", "/atom")) or "entry-title" in tl:
        return PageType.FEED.value
    if len(text) > 1200 and re.search(r"\b(introduction|abstract|conclusion)\b", tl):
        return PageType.ARTICLE.value
    return PageType.MISC.value


def recommend_next(
    goal: str,
    relevance: float,
    page_type: str,
    scroll_count: int,
    max_scrolls: int,
    best_link_score: float,
    content_repeated: bool,
    relevance_stagnant_rounds: int,
) -> Tuple[str, str]:
    """
    Returns (ContinueAction value, detail).
    """
    if content_repeated:
        return ContinueAction.STOP.value, "repeated_or_stale_content"
    if relevance_stagnant_rounds >= 2 and scroll_count >= 2:
        return ContinueAction.STOP.value, "no_relevance_gain_after_scrolls"
    if relevance < 0.06 and scroll_count >= 2:
        return ContinueAction.STOP.value, "low_relevance"
    if scroll_count >= max_scrolls:
        if best_link_score > relevance + 0.08:
            return ContinueAction.CLICK_LINK.value, "link_promising_vs_scroll_cap"
        return ContinueAction.STOP.value, "scroll_budget"
    if best_link_score > max(relevance + 0.12, 0.35):
        return ContinueAction.CLICK_LINK.value, "link_better_than_scroll"
    if scroll_count < max_scrolls and page_type in (
        PageType.ARTICLE.value,
        PageType.DOCS.value,
        PageType.MISC.value,
        PageType.FORUM.value,
    ):
        return ContinueAction.SCROLL.value, "explore_vertical"
    if page_type == PageType.SEARCH.value and best_link_score > 0.15:
        return ContinueAction.CLICK_LINK.value, "search_pick_result"
    return ContinueAction.READ.value, "hold"


def score_link_for_goal(goal: str, href: str, text: str, visited: set) -> float:
    if href in visited:
        return -1.0
    try:
        host = urlparse(href).netloc.lower()
    except Exception:
        return 0.0
    if host.startswith("www."):
        host = host[4:]
    g = _tokens(goal)
    blob = f"{href} {text}".lower()
    hits = sum(1 for t in g if t in blob)
    base = 0.05 + 0.12 * hits
    if any(bad in host for bad in ("doubleclick", "googleads", "facebook.com/tr")):
        return -0.5
    return min(1.0, base)


def links_to_discovered_dict(links: List) -> List[dict]:
    return [{"index": L.index, "href": L.href, "text": L.text} for L in links]
