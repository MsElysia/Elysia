"""Unit tests for bounded browser (fake backend, no Playwright)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_guardian.bounded_browser.agent import browse_task, _infer_start_url  # noqa: E402
from project_guardian.bounded_browser.allowlist import url_matches_allowlist  # noqa: E402
from project_guardian.bounded_browser.backends import BrowserBackend  # noqa: E402
from project_guardian.bounded_browser.moltbook import browse_moltbook  # noqa: E402
from project_guardian.bounded_browser.schema import LinkInfo  # noqa: E402


class FakeBackend(BrowserBackend):
    def __init__(self) -> None:
        self._url = ""
        self._title = "Asyncio"
        self._body = (
            "The asyncio module provides infrastructure for writing single-threaded concurrent code. "
            * 5
        )
        self._links = [
            LinkInfo(0, "https://example.test/page2", "asyncio tasks"),
            LinkInfo(1, "https://evil.test/ad", "click here"),
        ]

    def open_url(self, url: str, timeout_ms: int = 25_000) -> None:
        self._url = url

    def extract_visible_content(self) -> str:
        return self._body

    def scroll_once(self) -> None:
        self._body += " more asyncio context. "

    def list_links(self) -> list:
        return list(self._links)

    def click_link(self, target) -> bool:
        return False

    def summarize_current_page(self, goal: str) -> str:
        return "asyncio concurrency overview"

    def current_title(self) -> str:
        return self._title

    def current_url(self) -> str:
        return self._url or "https://example.test/start"

    def close(self) -> None:
        pass


def test_infer_start_url_from_goal() -> None:
    assert _infer_start_url("", "https://a.com/x") == "https://a.com/x"
    assert _infer_start_url("https://b.com q", None) == "https://b.com"


def test_infer_start_url_requires_url() -> None:
    with pytest.raises(ValueError):
        _infer_start_url("no url here", None)


def test_browse_task_fake_backend() -> None:
    r = browse_task(
        "asyncio concurrency",
        start_url="https://example.test/start",
        max_pages=2,
        max_scrolls_per_page=1,
        max_depth=0,
        backend=FakeBackend(),
    )
    assert len(r.steps) >= 1
    assert r.visited_urls
    assert all(s.url for s in r.steps)


def test_url_matches_allowlist_moltbook() -> None:
    ax = frozenset({"moltbook.com"})
    assert url_matches_allowlist("https://www.moltbook.com/", ax)
    assert url_matches_allowlist("https://moltbook.com/x", ax)
    assert not url_matches_allowlist("https://evil.com/", ax)


def test_browse_task_allowlist_blocks_off_domain_links() -> None:
    r = browse_task(
        "asyncio tasks",
        start_url="https://example.test/start",
        max_pages=3,
        max_scrolls_per_page=1,
        max_depth=2,
        allowed_hosts=["example.test"],
        backend=FakeBackend(),
    )
    assert all("evil.test" not in u for u in r.visited_urls)
    assert all("example.test" in u for u in r.visited_urls)


def test_browse_moltbook_rejects_wrong_start_url() -> None:
    with pytest.raises(ValueError, match="moltbook_start_url"):
        browse_moltbook("read posts", start_url="https://evil.com/", backend=FakeBackend())


def test_browse_moltbook_fake_backend() -> None:
    r = browse_moltbook(
        "read homepage",
        start_url="https://www.moltbook.com/",
        backend=FakeBackend(),
    )
    assert r.start_url.startswith("https://")
    assert "moltbook" in r.start_url.lower()
