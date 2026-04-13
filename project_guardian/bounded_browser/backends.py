# Browser backends: Playwright when installed, otherwise explicit stubs.

from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, List, Optional
from urllib.parse import urlparse

from .schema import LinkInfo

logger = logging.getLogger(__name__)

_MAX_TEXT = 24_000
_MAX_LINKS = 60


def is_safe_http_url(url: str) -> bool:
    try:
        u = urlparse(url.strip())
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


class BrowserBackend(ABC):
    """Minimal read-oriented surface (no forms, no auth flows in v1)."""

    @abstractmethod
    def open_url(self, url: str, timeout_ms: int = 25_000) -> None:
        pass

    @abstractmethod
    def extract_visible_content(self) -> str:
        pass

    @abstractmethod
    def scroll_once(self) -> None:
        pass

    @abstractmethod
    def list_links(self) -> List[LinkInfo]:
        pass

    @abstractmethod
    def click_link(self, target: Any) -> bool:
        """target: LinkInfo.index (int) or substring match on link text/href."""

    @abstractmethod
    def summarize_current_page(self, goal: str) -> str:
        """Heuristic summary aligned to goal (no LLM required)."""

    @abstractmethod
    def current_title(self) -> str:
        pass

    @abstractmethod
    def current_url(self) -> str:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class StubBrowserBackend(BrowserBackend):
    """Explicit no-op backend when Playwright is unavailable."""

    def open_url(self, url: str, timeout_ms: int = 25_000) -> None:
        raise RuntimeError(
            "Playwright is not available. Install: pip install playwright && playwright install chromium"
        )

    def extract_visible_content(self) -> str:
        return ""

    def scroll_once(self) -> None:
        pass

    def list_links(self) -> List[LinkInfo]:
        return []

    def click_link(self, target: Any) -> bool:
        return False

    def summarize_current_page(self, goal: str) -> str:
        return ""

    def current_title(self) -> str:
        return ""

    def current_url(self) -> str:
        return ""

    def close(self) -> None:
        pass


def _content_hash(text: str) -> str:
    h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    return h[:16]


def _heuristic_summary(visible: str, goal: str, max_sentences: int = 4) -> str:
    if not visible.strip():
        return ""
    gtok = {t for t in re.split(r"\W+", goal.lower()) if len(t) > 2}
    sentences = re.split(r"(?<=[.!?])\s+", visible.replace("\n", " "))
    picked = []
    for s in sentences:
        sl = s.lower()
        if gtok and any(t in sl for t in gtok):
            picked.append(s.strip())
        if len(picked) >= max_sentences:
            break
    if not picked:
        picked = [s.strip() for s in sentences[:max_sentences] if s.strip()]
    out = " ".join(picked)[:2000]
    return out or visible[:800]


class PlaywrightBrowserBackend(BrowserBackend):
    """Headless Chromium; read-only defaults (no downloads, http(s) only)."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            accept_downloads=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ElysiaBoundedBrowser/1.0",
        )
        self._page = self._context.new_page()

        def _route(route, request):
            # Block obvious non-document fetches we do not need for reading
            if request.resource_type in ("media", "font"):
                return route.abort()
            return route.continue_()

        self._page.route("**/*", _route)

    def open_url(self, url: str, timeout_ms: int = 25_000) -> None:
        if not is_safe_http_url(url):
            raise ValueError(f"Refusing non-http(s) URL: {url[:80]}")
        self._page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            self._page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass

    def extract_visible_content(self) -> str:
        try:
            text = self._page.evaluate(
                """() => {
                const m = document.querySelector('main, article, [role="main"]');
                const el = m || document.body;
                return el ? el.innerText : '';
            }"""
            )
        except Exception:
            text = ""
        text = (text or "").strip()
        if len(text) < 40:
            try:
                text = (self._page.evaluate("() => document.body ? document.body.innerText : ''") or "").strip()
            except Exception:
                pass
        return text[:_MAX_TEXT]

    def scroll_once(self) -> None:
        self._page.evaluate(
            """() => {
            const h = Math.min(900, Math.floor(window.innerHeight * 0.85));
            window.scrollBy(0, h);
        }"""
        )
        self._page.wait_for_timeout(400)

    def list_links(self) -> List[LinkInfo]:
        try:
            raw = self._page.evaluate(
                """() => {
                const out = [];
                const cap = %d;
                for (const a of document.querySelectorAll('a[href]')) {
                    if (out.length >= cap) break;
                    const r = a.getBoundingClientRect();
                    if (r.bottom < 0 || r.top > window.innerHeight + 400) continue;
                    let href = (a.getAttribute('href') || '').trim();
                    if (!href || href.startsWith('#')) continue;
                    let abs;
                    try { abs = new URL(href, document.baseURI).href; } catch(e) { continue; }
                    if (!/^https?:\\/\\//i.test(abs)) continue;
                    const text = (a.innerText || '').trim().slice(0, 200);
                    out.push({ href: abs, text: text || abs.slice(0, 80) });
                }
                return out;
            }"""
                % _MAX_LINKS
            )
        except Exception:
            return []
        items: List[LinkInfo] = []
        for i, row in enumerate(raw or []):
            try:
                href = row.get("href", "")
                if not is_safe_http_url(href):
                    continue
                items.append(LinkInfo(index=i, href=href, text=row.get("text", "")))
            except Exception:
                continue
        return items

    def click_link(self, target: Any) -> bool:
        links = self.list_links()
        if not links:
            return False
        chosen: Optional[LinkInfo] = None
        if isinstance(target, int):
            for L in links:
                if L.index == target:
                    chosen = L
                    break
        elif isinstance(target, str):
            tl = target.lower()
            for L in links:
                if tl in L.text.lower() or tl in L.href.lower():
                    chosen = L
                    break
        if chosen is None:
            return False
        try:
            self._page.goto(chosen.href, wait_until="domcontentloaded", timeout=25_000)
            try:
                self._page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.debug("click_link navigation failed: %s", e)
            return False

    def summarize_current_page(self, goal: str) -> str:
        return _heuristic_summary(self.extract_visible_content(), goal)

    def current_title(self) -> str:
        try:
            return (self._page.title() or "").strip()[:500]
        except Exception:
            return ""

    def current_url(self) -> str:
        try:
            return self._page.url or ""
        except Exception:
            return ""

    def close(self) -> None:
        try:
            self._context.close()
        except Exception:
            pass
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass


def create_browser_backend() -> BrowserBackend:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        return PlaywrightBrowserBackend()
    except ImportError:
        logger.info("Playwright not installed; bounded browser backend is stub-only")
        return StubBrowserBackend()
