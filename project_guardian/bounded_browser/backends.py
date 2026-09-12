# Browser backends: Playwright when installed, otherwise a read-only urllib fallback.

from __future__ import annotations

import hashlib
import html
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, List, Optional
from urllib.parse import urlparse

from .schema import LinkInfo

logger = logging.getLogger(__name__)

_MAX_TEXT = 24_000
_MAX_LINKS = 60
_MAX_HTML_BYTES = 300_000


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


def _timeout_seconds(timeout_ms: int) -> float:
    try:
        timeout = float(timeout_ms) / 1000.0
    except (TypeError, ValueError):
        timeout = 25.0
    return max(1.0, min(30.0, timeout))


def _decode_html(raw: bytes, content_type: str = "") -> str:
    charset = "utf-8"
    m = re.search(r"charset=([A-Za-z0-9._-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    return raw.decode(charset, errors="replace")


def _strip_tags(markup: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1>", " ", markup)
    cleaned = re.sub(r"(?is)<br\s*/?>|</(p|div|li|section|article|h[1-6])>", "\n", cleaned)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n\s+", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_title(markup: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", markup)
    if not m:
        return ""
    return _strip_tags(m.group(1))[:500]


def _extract_links(markup: str, base_url: str) -> List[LinkInfo]:
    links: List[LinkInfo] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"""(?is)<a\b[^>]*\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^'">\s]+))[^>]*>(.*?)</a>"""
    )
    for match in pattern.finditer(markup):
        if len(links) >= _MAX_LINKS:
            break
        href = html.unescape((match.group(1) or match.group(2) or match.group(3) or "").strip())
        if not href or href.startswith("#"):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        if not is_safe_http_url(absolute) or absolute in seen:
            continue
        seen.add(absolute)
        link_text = _strip_tags(match.group(4) or "")
        links.append(LinkInfo(index=len(links), href=absolute, text=(link_text or absolute[:80])[:200]))
    return links


class UrllibBrowserBackend(BrowserBackend):
    """Read-only static-page fallback for environments without Playwright."""

    def __init__(self) -> None:
        self._url = ""
        self._title = ""
        self._text = ""
        self._links: List[LinkInfo] = []

    def open_url(self, url: str, timeout_ms: int = 25_000) -> None:
        if not is_safe_http_url(url):
            raise ValueError(f"Refusing non-http(s) URL: {url[:80]}")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "ElysiaBoundedBrowser/1.0 urllib-fallback"
                ),
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.2",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=_timeout_seconds(timeout_ms)) as response:
                final_url = getattr(response, "url", url) or url
                if not is_safe_http_url(final_url):
                    raise ValueError(f"Refusing redirected non-http(s) URL: {str(final_url)[:80]}")
                raw = response.read(_MAX_HTML_BYTES + 1)
                content_type = ""
                headers = getattr(response, "headers", None)
                if headers is not None:
                    content_type = headers.get("Content-Type", "")
        except urllib.error.URLError as e:
            raise RuntimeError(f"urllib navigation failed: {e}") from e

        markup = _decode_html(raw[:_MAX_HTML_BYTES], content_type)
        self._url = str(final_url)
        self._title = _extract_title(markup)
        self._text = _strip_tags(markup)[:_MAX_TEXT]
        self._links = _extract_links(markup, self._url)

    def extract_visible_content(self) -> str:
        return self._text

    def scroll_once(self) -> None:
        return None

    def list_links(self) -> List[LinkInfo]:
        return list(self._links)

    def click_link(self, target: Any) -> bool:
        chosen: Optional[LinkInfo] = None
        if isinstance(target, int):
            chosen = next((link for link in self._links if link.index == target), None)
        elif isinstance(target, str):
            tl = target.lower()
            chosen = next(
                (link for link in self._links if tl in link.text.lower() or tl in link.href.lower()),
                None,
            )
        if chosen is None:
            return False
        try:
            self.open_url(chosen.href)
            return True
        except Exception as e:
            logger.debug("urllib click_link navigation failed: %s", e)
            return False

    def summarize_current_page(self, goal: str) -> str:
        return _heuristic_summary(self.extract_visible_content(), goal)

    def current_title(self) -> str:
        return self._title

    def current_url(self) -> str:
        return self._url

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
    except ImportError:
        logger.info("Playwright not installed; using urllib bounded browser fallback")
        return UrllibBrowserBackend()

    try:
        return PlaywrightBrowserBackend()
    except Exception as e:
        logger.warning("Playwright backend unavailable; using urllib fallback: %s", e)
        return UrllibBrowserBackend()
