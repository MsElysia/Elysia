# Bounded browser agent — structured I/O (read-only, budget-limited).

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PageType(str, Enum):
    SEARCH = "search_results"
    ARTICLE = "article"
    DOCS = "docs"
    FORUM = "forum"
    FEED = "feed"
    MISC = "misc"


class ContinueAction(str, Enum):
    STOP = "stop"
    SCROLL = "scroll"
    CLICK_LINK = "click_link"
    READ = "read"


@dataclass
class LinkInfo:
    index: int
    href: str
    text: str


@dataclass
class PageStepResult:
    """Structured output for one page / sub-step (e.g. after a scroll)."""

    url: str
    title: str
    page_type: str
    key_findings: str
    discovered_links: List[Dict[str, Any]]
    relevance_score: float
    continue_recommendation: str  # ContinueAction value
    continue_detail: str = ""
    content_hash: str = ""
    scroll_index: int = 0


@dataclass
class BrowseTaskResult:
    goal: str
    start_url: str
    steps: List[PageStepResult] = field(default_factory=list)
    visited_urls: List[str] = field(default_factory=list)
    stop_reason: str = ""
    truncated_by_budget: bool = False


def page_step_to_dict(p: PageStepResult) -> Dict[str, Any]:
    return {
        "url": p.url,
        "title": p.title,
        "page_type": p.page_type,
        "key_findings": p.key_findings,
        "discovered_links": p.discovered_links,
        "relevance_score": p.relevance_score,
        "continue_recommendation": p.continue_recommendation,
        "continue_detail": p.continue_detail,
        "content_hash": p.content_hash,
        "scroll_index": p.scroll_index,
    }
