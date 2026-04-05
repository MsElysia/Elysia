# project_guardian/auto_learning.py
"""
Auto-Learning: Background data gathering on AI, income, and other topics.
Stores learned and compressed content on the thumb drive.
Quality gates: only high-quality items are admitted to long-term memory;
all items may be archived to disk for reference.
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Source trust tiers: higher = more trusted, lower admission threshold
SOURCE_TRUST_TIERS = {
    "chatgpt": "high",
    "web": "medium",
    "rss": "medium",
    "wikipedia": "medium",
    "reddit": "low",
    "facebook": "low",
    "twitter": "low",
}
# Default trust for unknown sources
DEFAULT_TRUST = "low"

# Generic RSS/spam title patterns (reject)
TITLE_SPAM_PATTERNS = [
    r"^\[.*\]\s*$",
    r"^\.\.\.$",
    r"^(untitled|no title|n/a|---)$",
    r"^\s*https?://",
]

# Generic titles: do not use for title-based cross-session dedup (too many false positives)
GENERIC_TITLE_FOR_DEDUP = frozenset({
    "untitled", "no title", "n/a", "---", "...", "untitled document",
    "new post", "article", "blog post", "rss item", "feed item",
})
DEDUP_SNIPPET_LEN = 80

# Memory categories for admission gating (only operational + selected strategic admitted by default)
MEMORY_CATEGORY_OPERATIONAL = "operational"
MEMORY_CATEGORY_STRATEGIC = "strategic"
MEMORY_CATEGORY_CONVERSATIONAL = "conversational"
MEMORY_CATEGORY_CREATIVE = "creative"
MEMORY_CATEGORY_SPECULATIVE = "speculative"

# Patterns that indicate non-operational content (reject unless explicitly strategic/operational)
REJECT_LOW_VALUE_PATTERNS = [
    (r"\b(image|img|prompt|style|generate|dall-e|midjourney|stablediffusion)\b", "image_prompt"),
    (r"\b(chat summary|conversation summary|discussion about|we discussed|we talked)\b", "chat_summary"),
    (r"\b(what if|hypothetically|imagine|suppose|speculative|in theory)\b", "speculative"),
    (r"\b(style generation|art style|visual style|aesthetic)\b", "style_generation"),
    (r"\b(broad summary|general discussion|off-topic chat)\b", "generic_conversation"),
]
# Patterns that boost operational score (code, failures, fixes, module behavior, task outcomes)
OPERATIONAL_BOOST_PATTERNS = [
    (r"\b(code|bug|fix|failure|error|exception|runtime|deploy)\b", 2),
    (r"\b(module|guardian|elysia|memory|consolidat|trim)\b", 1),
    (r"\b(task outcome|task complete|mission progress)\b", 2),
    (r"\b(user priority|operator said|critical for)\b", 1),
]
WEAK_CONTENT_THRESHOLD = 60  # compressed < this = "weak content", title is main signal
MIN_LEXICAL_OVERLAP_RATIO = 0.5  # for snippet overlap check

# Default topics and sources
DEFAULT_TOPICS = ["AI", "artificial intelligence", "machine learning", "income", "passive income", "automation", "technology"]
DEFAULT_REDDIT_SUBS = ["MachineLearning", "ArtificialIntelligence", "passive_income", "SideProject", "Entrepreneur", "automation"]
DEFAULT_RSS_FEEDS = [
    "https://feeds.feedburner.com/TechCrunch",
    "https://www.wired.com/feed/rss",
    "https://machinelearningmastery.com/feed/",
]
# Facebook: page IDs or usernames (e.g. "Meta", "TechCrunch"). Requires facebook_access_token in config or FACEBOOK_ACCESS_TOKEN env.
DEFAULT_FACEBOOK_PAGES: List[str] = []
# X (Twitter): search queries for recent tweets. Requires twitter_bearer_token in config or TWITTER_BEARER_TOKEN env.
DEFAULT_TWITTER_SEARCH_QUERIES: List[str] = []


def get_learned_storage_path(config: Optional[Dict] = None) -> Path:
    """Resolve learned data path on thumb drive; falls back to LOCALAPPDATA if drive unavailable."""
    try:
        from .external_storage import normalize_storage_root
        cfg_path = Path(__file__).parent.parent / "config" / "external_storage.json"
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                ext = json.load(f)
            base = normalize_storage_root((ext.get("external_drive") or "").strip())
            if base and Path(base).exists():
                out = Path(base) / "ProjectGuardian" / "memory" / "learned"
                out.mkdir(parents=True, exist_ok=True)
                return out
            if base:
                logger.debug(f"[Auto-Learning] External drive {base} not available, using local storage")
    except Exception as e:
        logger.debug(f"External storage config: {e}")
    fallback = Path(os.environ.get("LOCALAPPDATA", ".")) / "ProjectGuardian" / "learned"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_chatlogs_path() -> Path:
    """ChatGPT/personal conversation files; falls back to LOCALAPPDATA if drive unavailable."""
    try:
        from .external_storage import normalize_storage_root
        cfg_path = Path(__file__).parent.parent / "config" / "external_storage.json"
        if cfg_path.exists():
            with open(cfg_path, "r") as f:
                ext = json.load(f)
            base = normalize_storage_root((ext.get("external_drive") or "").strip())
            if base and Path(base).exists():
                out = Path(base) / "ProjectGuardian" / "memory" / "personal" / "chatlogs"
                return out
    except Exception:
        pass
    return Path(os.environ.get("LOCALAPPDATA", ".")) / "ProjectGuardian" / "personal" / "chatlogs"


def fetch_chatlogs(chatlogs_path: Path, max_files: int = 20, processed_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read ChatGPT conversation .txt files from personal/chatlogs. Tracks processed to avoid duplicates."""
    items = []
    if not chatlogs_path.exists():
        return items
    processed = set()
    if processed_path and processed_path.exists():
        try:
            with open(processed_path, "r") as f:
                processed = set(json.load(f))
        except Exception:
            pass
    files = sorted(chatlogs_path.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    new_processed = []
    count = 0
    for fpath in files:
        if count >= max_files:
            break
        if str(fpath.name) in processed:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
            if len(text.strip()) < 50:
                continue
            items.append({
                "source": "chatgpt",
                "title": fpath.stem,
                "text": text[:15000],
                "url": "",
                "file": str(fpath.name),
            })
            new_processed.append(str(fpath.name))
            count += 1
        except Exception as e:
            logger.debug(f"Chatlog read failed {fpath.name}: {e}")
    if new_processed and processed_path:
        try:
            processed.update(new_processed)
            processed_path.parent.mkdir(parents=True, exist_ok=True)
            with open(processed_path, "w") as f:
                json.dump(list(processed)[-2000:], f)
        except Exception as e:
            logger.debug(f"Save processed list: {e}")
    return items


def fetch_reddit(subreddit: str, limit: int = 5, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Fetch posts from Reddit (public JSON API, no auth). Retries on transient failure."""
    items = []
    for attempt in range(max_retries + 1):
        try:
            import httpx
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                r = client.get(url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for child in data.get("data", {}).get("children", [])[:limit]:
                post = child.get("data", {})
                title = post.get("title", "")
                selftext = (post.get("selftext") or "")[:2000]
                items.append({
                    "source": "reddit",
                    "subreddit": subreddit,
                    "title": title,
                    "text": selftext or title,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "created_utc": post.get("created_utc"),
                })
            return items
        except Exception as e:
            logger.warning(f"Reddit fetch failed for r/{subreddit} (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                time.sleep(1 + attempt)
            else:
                return items
    return items


def peek_chatlogs_context(chatlogs_path: Path, max_files: int = 5, max_chars_per_file: int = 2500) -> str:
    """Read recent ChatGPT export .txt files for LLM planning context (does not touch processed markers)."""
    if not chatlogs_path.exists():
        return ""
    files = sorted(chatlogs_path.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    chunks: List[str] = []
    for fpath in files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")[:max_chars_per_file]
            if len(text.strip()) >= 40:
                chunks.append(f"--- {fpath.name} ---\n{text.strip()}")
        except Exception as e:
            logger.debug("peek_chatlogs_context %s: %s", fpath.name, e)
    return "\n\n".join(chunks)[:14000]


def fetch_reddit_search(subreddit: str, query: str, limit: int = 5, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Search within a subreddit (public JSON)."""
    items: List[Dict[str, Any]] = []
    subreddit = re.sub(r"[^A-Za-z0-9_]", "", (subreddit or "").strip())[:50]
    q = (query or "").strip()[:300]
    if not subreddit or not q:
        return items
    q_enc = quote(q, safe="")
    for attempt in range(max_retries + 1):
        try:
            import httpx
            url = f"https://www.reddit.com/r/{subreddit}/search.json?q={q_enc}&restrict_sr=on&sort=relevance&limit={limit}"
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                r = client.get(url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for child in data.get("data", {}).get("children", [])[:limit]:
                post = child.get("data", {})
                title = post.get("title", "")
                selftext = (post.get("selftext") or "")[:2000]
                items.append({
                    "source": "reddit",
                    "subreddit": subreddit,
                    "title": title,
                    "text": selftext or title,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                    "created_utc": post.get("created_utc"),
                    "reddit_mode": "search",
                    "reddit_query": q,
                })
            return items
        except Exception as e:
            logger.warning("Reddit search failed r/%s q=%s (attempt %d): %s", subreddit, q[:40], attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return items


def fetch_wikipedia_summary(title: str, max_retries: int = 2) -> Optional[Dict[str, Any]]:
    """Fetch English Wikipedia extract for one page title (MediaWiki Action API)."""
    raw = (title or "").strip()
    if not raw or len(raw) > 200:
        return None
    slug = raw.replace(" ", "_")
    path_enc = quote(slug, safe="")
    ua = "ElysiaGuardian/1.0 (local learning; Python httpx)"
    for attempt in range(max_retries + 1):
        try:
            import httpx
            api = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exintro": "true",
                "explaintext": "true",
                "titles": raw,
            }
            with httpx.Client(timeout=12, follow_redirects=True) as client:
                r = client.get(api, params=params, headers={"User-Agent": ua})
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return None
                data = r.json()
            pages = (data.get("query") or {}).get("pages") or {}
            if not pages:
                return None
            page = next(iter(pages.values()))
            if page.get("missing") or "invalid" in page:
                return None
            extract = (page.get("extract") or "").strip()
            if not extract:
                return None
            resolved_title = page.get("title") or raw
            page_url = f"https://en.wikipedia.org/wiki/{path_enc}"
            return {
                "source": "wikipedia",
                "title": resolved_title,
                "text": extract[:12000],
                "url": page_url,
            }
        except Exception as e:
            logger.warning("Wikipedia fetch failed for %s (attempt %d): %s", raw[:60], attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return None


def _element_text(el) -> str:
    """Extract all text from an XML element (including children). Handles CDATA and nested content."""
    if el is None:
        return ""
    return "".join(el.itertext()).strip() if hasattr(el, "itertext") else (el.text or "").strip()


def _find_by_local_name(parent, local_name: str):
    """Find child element by local name, ignoring XML namespace. Handles namespaced feeds."""
    if parent is None:
        return None
    for child in parent:
        tag = getattr(child, "tag", "")
        name = tag.split("}")[-1] if "}" in str(tag) else tag
        if name == local_name:
            return child
    return None


def _iter_entries(root) -> list:
    """Find item/entry elements regardless of namespace."""
    result = []
    for elem in root.iter():
        tag = getattr(elem, "tag", "")
        name = tag.split("}")[-1] if "}" in str(tag) else tag
        if name in ("item", "entry"):
            result.append(elem)
    return result


def _strip_html(text: str, max_len: int = 2000) -> str:
    """Remove HTML tags and normalize whitespace. Fallback: regex if no BeautifulSoup."""
    if not text:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text[:max_len * 2], "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        out = soup.get_text(separator=" ", strip=True)
    except ImportError:
        import re
        out = re.sub(r"<[^>]+>", " ", text)
        out = re.sub(r"\s+", " ", out).strip()
    return out[:max_len]


def fetch_rss(feed_url: str, limit: int = 5, max_retries: int = 2) -> List[Dict[str, Any]]:
    """Fetch items from RSS feed. Retries on transient failure.
    Extracts text from nested/HTML content so entries are not empty."""
    items = []
    for attempt in range(max_retries + 1):
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                r = client.get(feed_url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if r.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                xml = r.text
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml)
            entries = _iter_entries(root)
            for item in entries[:limit]:
                title_el = _find_by_local_name(item, "title")
                link_el = _find_by_local_name(item, "link")
                desc_el = _find_by_local_name(item, "encoded") or _find_by_local_name(item, "description") or _find_by_local_name(item, "summary") or _find_by_local_name(item, "content")
                title = _element_text(title_el)
                link = (link_el.text or "").strip() if link_el is not None else ""
                if not link and link_el is not None:
                    link = (link_el.get("href") or "").strip()
                raw_desc = _element_text(desc_el)
                desc = _strip_html(raw_desc) if raw_desc else ""
                text = (desc or title or f"RSS item from {feed_url[:50]}")[:2000]
                items.append({
                    "source": "rss",
                    "feed": feed_url[:80],
                    "title": title or "Untitled",
                    "text": text,
                    "url": link,
                })
            return items
        except Exception as e:
            logger.warning(f"RSS fetch failed for {feed_url[:50]} (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                time.sleep(1 + attempt)
            else:
                return items
    return items


def fetch_facebook(
    page_id_or_username: str,
    access_token: str,
    limit: int = 5,
    max_retries: int = 2,
) -> List[Dict[str, Any]]:
    """Fetch public posts from a Facebook Page via Graph API.
    page_id_or_username: Page ID or username (e.g. 'Meta', 'TechCrunch').
    access_token: App access token (app_id|app_secret) or user/page token with pages_read_engagement.
    """
    items: List[Dict[str, Any]] = []
    if not access_token or not page_id_or_username.strip():
        return items
    page = page_id_or_username.strip()
    url = (
        f"https://graph.facebook.com/v18.0/{page}/published_posts"
        f"?fields=message,created_time,permalink_url&limit={min(limit, 25)}&access_token={access_token}"
    )
    for attempt in range(max_retries + 1):
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                r = client.get(url, headers={"User-Agent": "Elysia-Learning/1.0"})
                if r.status_code != 200:
                    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    err = data.get("error", {}).get("message", r.text[:200])
                    logger.warning("Facebook fetch failed for %s: %s", page, err)
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for node in data.get("data", [])[:limit]:
                msg = (node.get("message") or "").strip()
                if not msg:
                    continue
                items.append({
                    "source": "facebook",
                    "page": page,
                    "title": msg[:80] + ("..." if len(msg) > 80 else ""),
                    "text": msg[:15000],
                    "url": node.get("permalink_url") or "",
                    "created_time": node.get("created_time", ""),
                })
            return items
        except Exception as e:
            logger.warning("Facebook fetch error for %s (attempt %d): %s", page, attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return items


_TWITTER_LOGGED_MAX_RESULTS = False


def fetch_twitter(
    query: str,
    bearer_token: str,
    limit: int = 10,
    max_retries: int = 2,
) -> List[Dict[str, Any]]:
    """Fetch recent public tweets from X (Twitter) via API v2 search. Requires Bearer Token (App-only)."""
    global _TWITTER_LOGGED_MAX_RESULTS
    items: List[Dict[str, Any]] = []
    if not bearer_token or not query.strip():
        return items
    q = query.strip()
    # Recent search requires max_results between 10 and 100 (API rejects e.g. 3).
    max_results = max(10, min(int(limit), 100))
    if not _TWITTER_LOGGED_MAX_RESULTS:
        _TWITTER_LOGGED_MAX_RESULTS = True
        logger.info("[Twitter] Recent search clamping max_results to %s (API v2 valid range 10–100)", max_results)
    url = (
        "https://api.twitter.com/2/tweets/search/recent"
        f"?query={quote(q)}"
        f"&max_results={max_results}"
        "&tweet.fields=created_at,public_metrics"
    )
    for attempt in range(max_retries + 1):
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                r = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {bearer_token.strip()}",
                        "User-Agent": "Elysia-Learning/1.0",
                    },
                )
                if r.status_code != 200:
                    err_msg = r.text[:200]
                    try:
                        data = r.json()
                        err_msg = data.get("errors", [{}])[0].get("detail", err_msg) if data.get("errors") else err_msg
                    except Exception:
                        pass
                    logger.warning("Twitter fetch failed for query %s: %s", q[:50], err_msg)
                    if attempt < max_retries:
                        time.sleep(1 + attempt)
                        continue
                    return items
                data = r.json()
            for node in data.get("data", [])[:limit]:
                text = (node.get("text") or "").strip()
                if not text:
                    continue
                items.append({
                    "source": "twitter",
                    "query": q[:80],
                    "title": text[:80] + ("..." if len(text) > 80 else ""),
                    "text": text[:15000],
                    "url": f"https://twitter.com/i/status/{node.get('id', '')}",
                    "created_at": node.get("created_at", ""),
                })
            return items
        except Exception as e:
            logger.warning("Twitter fetch error for %s (attempt %d): %s", q[:50], attempt + 1, e)
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return items


def _playwright_available() -> bool:
    """Return True if Playwright is installed (import-only check)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_web_url_headless(url: str, max_length: int = 15000, timeout_ms: int = 15000) -> Optional[Dict[str, Any]]:
    """Fetch and extract text from a web URL using a headless browser (Playwright). Use for JS-heavy or bot-blocking sites."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed; cannot use headless browser")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                time.sleep(1.5)  # Allow basic JS to run
                text = page.evaluate("() => document.body ? document.body.innerText : ''")
                if not text or len(text.strip()) < 50:
                    text = page.content() or ""
                    import re
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = re.sub(r"\s+", " ", text).strip()
                browser.close()
            except Exception as e:
                try:
                    browser.close()
                except Exception:
                    pass
                raise e
        text = (text or "")[:max_length]
        if len(text.strip()) < 50:
            return None
        title = url.split("/")[-1].split("?")[0] or "Web page"
        return {"source": "web", "url": url, "title": title, "text": text}
    except Exception as e:
        logger.warning("Headless fetch failed for %s: %s", url[:60], e)
        return None


def fetch_web_url(url: str, max_length: int = 15000, max_retries: int = 2, use_headless: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch and extract text from a web URL. If use_headless=True and Playwright is available, use headless browser."""
    if use_headless:
        try:
            if _playwright_available():
                result = fetch_web_url_headless(url, max_length=max_length)
                if result:
                    return result
        except Exception as e:
            logger.debug("Headless fetch failed, falling back to HTTP: %s", e)
    for attempt in range(max_retries + 1):
        try:
            import httpx
            r = httpx.get(url, headers={"User-Agent": "Elysia-Learning/1.0"}, timeout=15, follow_redirects=True)
            if r.status_code != 200:
                if attempt < max_retries:
                    time.sleep(1 + attempt)
                    continue
                return None
            html = r.text
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)[:max_length]
            except ImportError:
                import re
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()[:max_length]
            if len(text.strip()) < 50:
                return None
            return {"source": "web", "url": url, "title": url.split("/")[-1] or "Web page", "text": text}
        except Exception as e:
            logger.warning(f"Web fetch failed for {url[:60]} (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                time.sleep(1 + attempt)
    return None


def _classify_content_category(combined: str) -> Tuple[str, int]:
    """
    Classify content into operational, strategic, conversational, creative, speculative.
    Returns (category, rejection_penalty). Penalty > 0 means likely reject.
    Operational/strategic content overrides low-value patterns (e.g. "we discussed the code fix").
    """
    lower = combined.lower()
    operational_score = sum(b for p, b in OPERATIONAL_BOOST_PATTERNS if re.search(p, lower, re.I))
    # Prioritize operational: if clearly operational, admit even if it mentions chat/conversation
    if operational_score >= 2:
        return MEMORY_CATEGORY_OPERATIONAL, 0
    if operational_score >= 1:
        return MEMORY_CATEGORY_STRATEGIC, 0
    for pat, tag in REJECT_LOW_VALUE_PATTERNS:
        if re.search(pat, lower, re.I):
            if tag in ("image_prompt", "style_generation"):
                return MEMORY_CATEGORY_CREATIVE, 3
            if tag in ("chat_summary", "generic_conversation"):
                return MEMORY_CATEGORY_CONVERSATIONAL, 2
            if tag == "speculative":
                return MEMORY_CATEGORY_SPECULATIVE, 2
    return MEMORY_CATEGORY_CONVERSATIONAL, 1


def _topic_overlap(text: str, topics: List[str]) -> int:
    """Count how many topic keywords appear in text (case-insensitive)."""
    if not text or not topics:
        return 0
    lower = text.lower()
    return sum(1 for t in topics if t.lower() in lower)


def _fingerprint(text: str, max_len: int = 200) -> str:
    """Short fingerprint for deduplication."""
    normalized = re.sub(r"\s+", " ", (text or "").strip())[:max_len]
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]


def _normalize_title(title: str, max_len: int = 100) -> str:
    """Normalize title for cross-session dedup (lower, trim, truncate)."""
    return re.sub(r"\s+", " ", (title or "").strip())[:max_len].lower()


def _snippet_norm(text: str, max_len: int = DEDUP_SNIPPET_LEN) -> str:
    """Normalized prefix of compressed text for secondary dedup comparison."""
    return re.sub(r"\s+", " ", (text or "").strip())[:max_len].lower()


def _is_generic_title_for_dedup(title_norm: str) -> bool:
    """Return True if title should not be used for title-based cross-session dedup."""
    if not title_norm or len(title_norm) < 15:
        return True
    if title_norm in GENERIC_TITLE_FOR_DEDUP:
        return True
    if re.match(r"^\[.*\]\s*$", title_norm) or re.match(r"^\s*https?://", title_norm):
        return True
    return False


def _utc_now() -> datetime:
    """Current UTC time for dedup timestamps."""
    return datetime.now(timezone.utc)


def _parse_utc(s: str) -> Optional[datetime]:
    """Parse ISO timestamp to UTC datetime. Handles Z suffix and naive strings."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


DEDUP_INDEX_FILENAME = ".learning_dedup_index.json"
DEDUP_LOCK_FILENAME = ".learning_dedup_index.lock"
DEFAULT_DEDUP_WINDOW_DAYS = 30
MIN_TITLE_LEN_FOR_DEDUP = 15
STALE_LOCK_SECONDS = 300


def _acquire_dedup_lock(storage_path: Path) -> bool:
    """Acquire advisory lock for dedup index. Returns True if acquired."""
    lock_path = storage_path / DEDUP_LOCK_FILENAME
    storage_path.mkdir(parents=True, exist_ok=True)
    for _ in range(30):
        try:
            if lock_path.exists():
                age = time.time() - lock_path.stat().st_mtime
                if age > STALE_LOCK_SECONDS:
                    lock_path.unlink(missing_ok=True)
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            time.sleep(0.2)
        except OSError:
            break
    return False


def _release_dedup_lock(storage_path: Path) -> None:
    """Release advisory lock."""
    lock_path = storage_path / DEDUP_LOCK_FILENAME
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def load_dedup_index(
    storage_path: Path,
    dedup_window_days: int,
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """
    Load the persisted dedup index, prune records outside the window.
    Uses UTC timestamps and datetime arithmetic for pruning.
    Returns (by_fingerprint, pruned_count).
    """
    path = storage_path / DEDUP_INDEX_FILENAME
    by_fp: Dict[str, Dict[str, Any]] = {}
    pruned = 0
    if not path.exists():
        return by_fp, 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.debug(f"[Auto-Learning] Dedup index load failed: {e}")
        return by_fp, 0
    records = data.get("records", data) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    if not isinstance(records, list):
        return by_fp, 0
    cutoff = _utc_now() - timedelta(days=dedup_window_days)
    for r in records:
        if not isinstance(r, dict):
            continue
        fp = r.get("fp") or r.get("fingerprint")
        if not fp:
            continue
        last_seen = _parse_utc(r.get("last_seen") or "")
        if last_seen is not None and last_seen < cutoff:
            pruned += 1
            continue
        last_str = r.get("last_seen", "")
        first_str = r.get("first_seen", "")
        by_fp[fp] = {
            "fp": fp,
            "title_norm": (r.get("title_norm") or "")[:100],
            "snippet_norm": (r.get("snippet_norm") or "")[:DEDUP_SNIPPET_LEN],
            "first_seen": first_str,
            "last_seen": last_str,
            "source": (r.get("source") or "unknown")[:50],
            "admitted_to_memory": bool(r.get("admitted_to_memory")),
        }
    return by_fp, pruned


def save_dedup_index(
    storage_path: Path,
    by_fp: Dict[str, Dict[str, Any]],
    dedup_window_days: int,
) -> int:
    """
    Prune old records, write the dedup index atomically.
    Uses file lock when available; re-reads latest state before final write to reduce lost updates.
    Returns number of records pruned.
    """
    cutoff = _utc_now() - timedelta(days=dedup_window_days)
    to_keep: Dict[str, Dict[str, Any]] = {}
    pruned = 0
    for fp, r in by_fp.items():
        last_seen = _parse_utc(r.get("last_seen") or "")
        if last_seen is not None and last_seen < cutoff:
            pruned += 1
            continue
        to_keep[fp] = r

    path = storage_path / DEDUP_INDEX_FILENAME
    locked = _acquire_dedup_lock(storage_path)
    try:
        if locked and path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    fresh = json.load(f)
                fresh_records = fresh.get("records", [])
                if isinstance(fresh_records, list):
                    for r in fresh_records:
                        if not isinstance(r, dict):
                            continue
                        fp = r.get("fp") or r.get("fingerprint")
                        if not fp:
                            continue
                        ls = _parse_utc(r.get("last_seen") or "")
                        if ls is not None and ls < cutoff:
                            pruned += 1
                            continue
                        if fp not in to_keep:
                            to_keep[fp] = r
                        else:
                            ls_ours = _parse_utc(to_keep[fp].get("last_seen") or "")
                            if ls and ls_ours and ls > ls_ours:
                                to_keep[fp]["last_seen"] = r["last_seen"]
                            to_keep[fp]["admitted_to_memory"] = to_keep[fp].get("admitted_to_memory", False) or r.get("admitted_to_memory", False)
            except Exception as e:
                logger.debug(f"[Auto-Learning] Dedup re-read before save: {e}")
        storage_path.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 2, "records": list(to_keep.values())}, f, ensure_ascii=False, indent=None)
            tmp.replace(path)
        except Exception as e:
            logger.debug(f"[Auto-Learning] Dedup index save failed: {e}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
        return pruned
    finally:
        if locked:
            _release_dedup_lock(storage_path)


def _build_dedup_lookup(by_fp: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build lookup structures for cross-session duplicate detection.
    Returns dict with: fp_set, by_source_title (source -> {title_norm -> record}), by_fp.
    """
    fp_set = set(by_fp.keys())
    by_source_title: Dict[str, Dict[str, Any]] = {}
    for r in by_fp.values():
        src = (r.get("source") or "unknown")[:50]
        tn = (r.get("title_norm") or "").strip()
        if tn and len(tn) >= MIN_TITLE_LEN_FOR_DEDUP and tn not in GENERIC_TITLE_FOR_DEDUP:
            if src not in by_source_title:
                by_source_title[src] = {}
            by_source_title[src][tn] = r
    return {"fp_set": fp_set, "by_source_title": by_source_title, "by_fp": by_fp}


def _lexical_overlap_ratio(a: str, b: str) -> float:
    """Simple word overlap ratio (Jaccard-like) between two normalized strings."""
    if not a or not b:
        return 0.0
    wa = set(re.split(r"\s+", a))
    wb = set(re.split(r"\s+", b))
    if not wa:
        return 0.0
    return len(wa & wb) / len(wa)


def is_cross_session_duplicate(
    fp: str,
    title_norm: str,
    snippet_norm: str,
    source: str,
    compressed_len: int,
    dedup_lookup: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Check if item is a cross-session duplicate.
    Returns (is_duplicate, match_type) where match_type is "fingerprint", "title_source", "weak_content", "snippet_overlap", or "".
    Fingerprint match is high-confidence. Title-based only when stricter conditions hold.
    """
    fp_set = dedup_lookup.get("fp_set") or set()
    by_source_title = dedup_lookup.get("by_source_title") or {}
    by_fp = dedup_lookup.get("by_fp") or {}

    if fp and fp in fp_set:
        return True, "fingerprint"

    if _is_generic_title_for_dedup(title_norm):
        return False, ""

    weak_content = compressed_len < WEAK_CONTENT_THRESHOLD
    src = (source or "unknown").lower()

    if src in by_source_title and title_norm in by_source_title[src]:
        rec = by_source_title[src][title_norm]
        if weak_content:
            return True, "title_source_weak"
        snippet_prev = (rec.get("snippet_norm") or "").strip()
        if snippet_norm and snippet_prev and _lexical_overlap_ratio(snippet_norm, snippet_prev) >= MIN_LEXICAL_OVERLAP_RATIO:
            return True, "title_source_snippet"
        return True, "title_source"

    if weak_content and title_norm:
        for src2, titles in by_source_title.items():
            if title_norm in titles:
                return True, "weak_content"

    return False, ""


def score_learned_item(
    item: Dict[str, Any],
    topics: List[str],
    session_titles: set,
    session_fingerprints: set,
) -> Dict[str, Any]:
    """
    Score a learned item for admission to long-term memory.
    Returns structured result: {admit, reason, score, trust_tier, relevance, ...}
    """
    compressed = (item.get("compressed") or item.get("text") or "").strip()
    title = (item.get("title") or "").strip()
    source = (item.get("source") or "unknown").lower()
    trust_tier = SOURCE_TRUST_TIERS.get(source, DEFAULT_TRUST)

    result: Dict[str, Any] = {
        "admit": False,
        "reason": "",
        "trust_tier": trust_tier,
        "relevance": 0,
        "reuse_potential": 0,
        "content_ok": False,
        "topic_ok": False,
        "trust_ok": False,
        "not_duplicate": False,
        "category": "",
    }

    # A. Minimum content quality
    combined = f"{title} {compressed}"
    if len(compressed) < 30:
        result["reason"] = "too_short"
        result["category"], _ = _classify_content_category(combined)
        return result
    if title and len(compressed) < 80 and compressed.lower().replace(title.lower(), "").strip() in ("", "...", "-"):
        result["reason"] = "title_only"
        result["category"], _ = _classify_content_category(combined)
        return result
    for pat in TITLE_SPAM_PATTERNS:
        if re.match(pat, (title or "").strip(), re.I):
            result["reason"] = "generic_title"
            result["category"], _ = _classify_content_category(combined)
            return result
    result["content_ok"] = True

    # B. Topic relevance (skip check if no topics configured)
    category, rejection_penalty = _classify_content_category(combined)
    result["category"] = category
    relevance = _topic_overlap(combined, topics) if topics else 1
    result["relevance"] = relevance
    if not topics or relevance >= 1:
        result["topic_ok"] = True
    else:
        result["reason"] = "low_relevance"
        return result

    # Bb. Low-value rejection (category already set above for logging)
    result["rejection_penalty"] = rejection_penalty
    operational_boost = sum(b for p, b in OPERATIONAL_BOOST_PATTERNS if re.search(p, combined.lower(), re.I))
    result["reuse_potential"] = min(3, relevance + (2 if operational_boost >= 2 else 1 if operational_boost >= 1 else 0))
    if rejection_penalty >= 2:
        result["reason"] = f"low_value_{category}"
        return result

    # C. Source trust (stricter for low-trust sources)
    result["trust_ok"] = True
    result["trust_tier"] = trust_tier

    # D. Deduplication
    fp = _fingerprint(compressed)
    title_norm = (title or "")[:100].lower()
    if title_norm in session_titles or fp in session_fingerprints:
        result["reason"] = "duplicate"
        return result
    result["not_duplicate"] = True

    # E. Reuse potential / execution value (penalize generic, one-off, no execution value)
    if result["reuse_potential"] < 1 and rejection_penalty >= 1:
        result["reason"] = "no_execution_value"
        return result
    result["admit"] = True
    result["reason"] = "passed"
    return result


def should_ingest_learned_item(
    item: Dict[str, Any],
    topics: List[str],
    config: Dict[str, Any],
    session_titles: set,
    session_fingerprints: set,
    caps: Dict[str, int],
    dedup_lookup: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Determine if an item should be admitted to long-term memory.
    Returns (admit, rejection_reason, score_info).
    dedup_lookup: from _build_dedup_lookup() for cross-session duplicate check.
    """
    score_info = score_learned_item(item, topics, session_titles, session_fingerprints)

    if not score_info["admit"]:
        return False, score_info["reason"], score_info

    # Cross-session duplicate check (fingerprint = high confidence; title-based = stricter rules)
    if dedup_lookup:
        compressed = (item.get("compressed") or item.get("text") or "").strip()
        fp = _fingerprint(compressed)
        title_norm = _normalize_title(item.get("title") or "")
        snippet_norm = _snippet_norm(compressed)
        source = (item.get("source") or "unknown").lower()
        is_dup, match_type = is_cross_session_duplicate(
            fp, title_norm, snippet_norm, source, len(compressed), dedup_lookup
        )
        if is_dup:
            return False, "cross_session_duplicate", {**score_info, "dedup_match_type": match_type}

    source = (item.get("source") or "unknown").lower()
    trust = score_info["trust_tier"]

    # Config gates
    allow_reddit_social = config.get("allow_reddit_into_memory", False)
    if trust == "low" and not allow_reddit_social:
        return False, "low_trust", score_info

    min_relevance = config.get("min_relevance_score", 2)
    if score_info["relevance"] < min_relevance:
        return False, "low_relevance", score_info

    min_reuse = config.get("min_reuse_potential", 1)
    if score_info.get("reuse_potential", 0) < min_reuse:
        return False, "low_reuse_potential", score_info

    # Category gating: only operational and (optionally) strategic admitted by default
    allow_strategic = config.get("allow_strategic_into_memory", False)
    category = score_info.get("category", MEMORY_CATEGORY_CONVERSATIONAL)
    if category not in (MEMORY_CATEGORY_OPERATIONAL, MEMORY_CATEGORY_STRATEGIC):
        return False, f"category_{category}", score_info
    if category == MEMORY_CATEGORY_STRATEGIC and not allow_strategic:
        return False, "strategic_not_allowed", score_info

    # Session caps
    if caps.get("memory_admitted", 0) >= caps.get("max_memory_per_session", 20):
        return False, "session_cap", score_info
    per_source = caps.get("per_source", {})
    if per_source.get(source, 0) >= caps.get("max_per_source_memory", 5):
        return False, "source_cap", score_info

    return True, "passed", score_info


def _priority_for_admitted(trust_tier: str, relevance: int) -> float:
    """Assign priority by trust and relevance. Higher = more important."""
    base = {"high": 0.65, "medium": 0.55, "low": 0.45}.get(trust_tier, 0.45)
    if relevance >= 3:
        base += 0.1
    elif relevance >= 2:
        base += 0.05
    return min(0.9, max(0.35, base))


def compress_with_llm(
    text: str,
    llm_callback: Optional[Callable[[str], tuple]],
    *,
    module_name: str,
    agent_name: Optional[str] = None,
) -> str:
    """Compress/summarize text via LLM if available."""
    if not llm_callback or len(text) <= 400:
        return text[:500] + ("..." if len(text) > 500 else "")
    try:
        from .llm.prompted_call import log_prompted_call, prepare_prompted_bundle, require_prompt_profile

        mod, ag, _ = require_prompt_profile(
            module_name, agent_name, caller="compress_with_llm", allow_legacy=False
        )

        _b = prepare_prompted_bundle(
            module_name=mod,
            agent_name=ag,
            task_text="Summarize in 2-4 sentences; preserve key facts about AI, income, or technology.",
            context={"source_excerpt": text[:3000]},
            caller="compress_with_llm",
        )
        prompt = _b["prompt_text"]
        log_prompted_call(
            module_name=mod,
            agent_name=ag,
            task_type="compress_with_llm",
            provider="callback",
            model=None,
            bundle_meta=_b["meta"],
            prompt_length=len(prompt),
            legacy_prompt_path=False,
        )
        reply, err = llm_callback(prompt)
        if reply and not err:
            return reply.strip()[:800]
    except Exception as e:
        logger.debug(f"LLM compress failed: {e}")
    return text[:500] + ("..." if len(text) > 500 else "")


def finalize_learned_collection(
    collected: List[Dict[str, Any]],
    storage_path: Path,
    topics: List[str],
    memory: Optional[Any] = None,
    sources_count: int = 1,
) -> Dict[str, Any]:
    """Archive learned items, run admission gates, update dedup index and memory."""
    cfg = load_learning_config()
    max_archived = int(cfg.get("max_archived_per_session", 100))
    max_memory_per_session = int(cfg.get("max_memory_per_session", 20))
    max_per_source_memory = int(cfg.get("max_per_source_memory", 5))
    dedup_window_days = int(cfg.get("dedup_window_days", DEFAULT_DEDUP_WINDOW_DAYS))

    fetched = len(collected)
    if not collected:
        logger.info("[Auto-Learning] Session complete: fetched=0 (no items collected)")
        return {
            "fetched": 0,
            "archived": 0,
            "admitted": 0,
            "rejected": 0,
            "cross_session_duplicates": 0,
            "fingerprint_duplicates": 0,
            "title_match_duplicates": 0,
            "dedup_records_pruned": 0,
            "rejection_breakdown": {},
            "sources": 0,
            "memory": 0,
            "file": "",
            "message": "No items collected",
        }

    to_archive = collected[:max_archived] if fetched > max_archived else collected
    archived_count = len(to_archive)

    storage_path.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_file = storage_path / f"learned_{date_str}.jsonl"

    dedup_by_fp, dedup_load_pruned = load_dedup_index(storage_path, dedup_window_days)
    dedup_lookup = _build_dedup_lookup(dedup_by_fp)

    session_titles: set = set()
    session_fingerprints: set = set()
    caps: Dict[str, Any] = {
        "memory_admitted": 0,
        "max_memory_per_session": max_memory_per_session,
        "max_per_source_memory": max_per_source_memory,
        "per_source": {},
    }
    rejection_breakdown: Dict[str, int] = {}
    admitted_count = 0
    cross_session_duplicates = 0
    fingerprint_duplicates = 0
    title_match_duplicates = 0
    records_to_add: List[Tuple[str, str, str, str, bool]] = []

    with open(out_file, "a", encoding="utf-8") as f:
        for item in to_archive:
            item["learned_at"] = datetime.now().isoformat()
            src = (item.get("source") or "unknown").lower()
            title = (item.get("title") or "Untitled")[:80]
            compressed = (item.get("compressed") or item.get("text") or "")[:1200]
            fp = _fingerprint(compressed)
            title_norm = _normalize_title(title)
            snippet_norm = _snippet_norm(compressed)

            admit, reject_reason, score_info = should_ingest_learned_item(
                item, topics, cfg, session_titles, session_fingerprints, caps, dedup_lookup
            )

            if reject_reason == "cross_session_duplicate":
                cross_session_duplicates += 1
                match_type = score_info.get("dedup_match_type", "")
                if match_type == "fingerprint":
                    fingerprint_duplicates += 1
                elif match_type:
                    title_match_duplicates += 1

            arch_meta = {
                "learned_at": item["learned_at"],
                "source": src,
                "source_type": src,
                "source_trust_tier": score_info.get("trust_tier", "low"),
                "relevance": score_info.get("relevance", 0),
                "archived_only": not admit,
            }
            if admit:
                cat = score_info.get("category", MEMORY_CATEGORY_OPERATIONAL)
                arch_meta["ingestion_reason"] = "operational" if cat == MEMORY_CATEGORY_OPERATIONAL else "strategic"
                arch_meta["category"] = cat
                arch_meta["archived_only"] = False
                session_titles.add((title or "")[:100].lower())
                session_fingerprints.add(fp)
                caps["memory_admitted"] += 1
                caps["per_source"][src] = caps["per_source"].get(src, 0) + 1
                logger.info("[Auto-Learning] Admitted (category=%s): %.60s...", cat, (title or compressed)[:60])
            else:
                arch_meta["rejection_reason"] = reject_reason
                arch_meta["category"] = score_info.get("category", "")
                rejection_breakdown[reject_reason] = rejection_breakdown.get(reject_reason, 0) + 1
                logger.info(
                    "[Auto-Learning] Rejected (category=%s, reason=%s): %.60s...",
                    score_info.get("category", ""), reject_reason, (title or compressed)[:60],
                )

            item["_arch_meta"] = arch_meta
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            records_to_add.append((fp, title_norm, snippet_norm, src, admit))

            if admit and memory and hasattr(memory, "remember"):
                try:
                    priority = _priority_for_admitted(
                        score_info.get("trust_tier", "low"),
                        score_info.get("relevance", 1),
                    )
                    thought = f"[Learned/{src}] {title}: {compressed}"
                    ing_reason = arch_meta.get("ingestion_reason", "operational")
                    memory.remember(
                        thought,
                        category="learning",
                        priority=priority,
                        metadata={
                            "source": src,
                            "source_type": src,
                            "source_trust_tier": score_info.get("trust_tier", "low"),
                            "relevance_score": score_info.get("relevance", 0),
                            "ingestion_reason": ing_reason,
                            "content_category": score_info.get("category", MEMORY_CATEGORY_OPERATIONAL),
                            "learned_at": item["learned_at"],
                            "archived_only": False,
                            "previously_unseen": True,
                        },
                    )
                    admitted_count += 1
                except Exception as e:
                    logger.debug("Memory pipe failed: %s", e)
                    rejection_breakdown["memory_error"] = rejection_breakdown.get("memory_error", 0) + 1

    now_iso = _utc_now().strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    for fp, title_norm, snippet_norm, src, admitted in records_to_add:
        if fp in dedup_by_fp:
            dedup_by_fp[fp]["last_seen"] = now_iso
            dedup_by_fp[fp]["admitted_to_memory"] = dedup_by_fp[fp].get("admitted_to_memory", False) or admitted
            if snippet_norm:
                dedup_by_fp[fp]["snippet_norm"] = snippet_norm
        else:
            dedup_by_fp[fp] = {
                "fp": fp,
                "title_norm": title_norm,
                "snippet_norm": snippet_norm,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "source": src,
                "admitted_to_memory": admitted,
            }
    dedup_save_pruned = save_dedup_index(storage_path, dedup_by_fp, dedup_window_days)
    dedup_records_pruned = dedup_load_pruned + dedup_save_pruned

    rejected_count = archived_count - admitted_count
    top_rejections = ", ".join(
        f"{k}:{v}" for k, v in sorted(rejection_breakdown.items(), key=lambda x: -x[1])[:5]
    )
    logger.info(
        "[Auto-Learning] Session complete: fetched=%d archived=%d admitted=%d rejected=%d cross_session_duplicates=%d (fp=%d title=%d) dedup_pruned=%d top_rejections=%s",
        fetched, archived_count, admitted_count, rejected_count, cross_session_duplicates,
        fingerprint_duplicates, title_match_duplicates, dedup_records_pruned, top_rejections or "none",
    )

    web_count = sum(1 for i in to_archive if i.get("source") == "web")
    return {
        "fetched": fetched,
        "archived": archived_count,
        "admitted": admitted_count,
        "rejected": rejected_count,
        "cross_session_duplicates": cross_session_duplicates,
        "fingerprint_duplicates": fingerprint_duplicates,
        "title_match_duplicates": title_match_duplicates,
        "dedup_records_pruned": dedup_records_pruned,
        "rejection_breakdown": rejection_breakdown,
        "sources": sources_count,
        "chatlogs": sum(1 for i in to_archive if i.get("source") == "chatgpt"),
        "web_pages": web_count,
        "memory": admitted_count,
        "file": str(out_file),
        "saved": archived_count,
        "memory_count": admitted_count,
    }


def run_learning_session(
    storage_path: Path,
    topics: List[str],
    reddit_subs: List[str],
    rss_feeds: List[str],
    chatlogs_path: Optional[Path] = None,
    web_urls: Optional[List[str]] = None,
    facebook_pages: Optional[List[str]] = None,
    facebook_access_token: Optional[str] = None,
    twitter_search_queries: Optional[List[str]] = None,
    twitter_bearer_token: Optional[str] = None,
    use_headless_for_web: Optional[bool] = None,
    max_per_source: int = 5,
    max_chatlogs: int = 20,
    llm_callback: Optional[Callable[[str], tuple]] = None,
    memory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run one learning session: fetch Reddit, RSS, ChatGPT chatlogs, web URLs, Facebook, X (Twitter); compress; store.
    Items are archived to disk; only those passing quality gates are admitted to long-term memory.
    When use_headless_for_web is True and Playwright is available, web URLs are fetched via headless browser.
    """
    cfg = load_learning_config()
    if use_headless_for_web is None:
        use_headless_for_web = bool(cfg.get("use_headless_browser", False))
    vol = float(cfg.get("learning_query_volume_scale", 0.65))
    vol = max(0.25, min(1.0, vol))
    max_per_source = max(1, int(max_per_source * vol))

    collected = []
    if web_urls:
        for url in web_urls[:5]:
            item = fetch_web_url(url.strip(), use_headless=use_headless_for_web and _playwright_available())
            if item:
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                collected.append(item)
    # ChatGPT conversation files (from import_chatgpt_export)
    if chatlogs_path:
        processed_marker = storage_path / ".processed_chatlogs.json"
        for item in fetch_chatlogs(chatlogs_path, max_files=max_chatlogs, processed_path=processed_marker):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)
    # Reddit
    for sub in reddit_subs:
        for item in fetch_reddit(sub, limit=max_per_source):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)
    # RSS
    for feed in rss_feeds:
        for item in fetch_rss(feed, limit=max_per_source):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)
    # Facebook (requires facebook_access_token in config or FACEBOOK_ACCESS_TOKEN env)
    if facebook_pages and facebook_access_token:
        for page in facebook_pages:
            page = page.strip()
            if not page:
                continue
            for item in fetch_facebook(page, facebook_access_token, limit=max_per_source):
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                collected.append(item)
    # X (Twitter) – requires twitter_bearer_token in config or TWITTER_BEARER_TOKEN env
    if twitter_search_queries and twitter_bearer_token:
        for q in twitter_search_queries:
            q = q.strip()
            if not q:
                continue
            for item in fetch_twitter(q, twitter_bearer_token, limit=max_per_source):
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                collected.append(item)
    sources_count = (
        (1 if chatlogs_path else 0)
        + len(reddit_subs)
        + len(rss_feeds)
        + (1 if web_urls else 0)
        + (len(facebook_pages) if (facebook_pages and facebook_access_token) else 0)
        + (len(twitter_search_queries) if (twitter_search_queries and twitter_bearer_token) else 0)
    )
    return finalize_learned_collection(collected, storage_path, topics, memory, sources_count=sources_count or 1)


def run_mistral_chained_learning_session(
    storage_path: Path,
    topics: List[str],
    memory: Optional[Any],
    llm_callback: Optional[Callable[[str], tuple]],
    chatlogs_path: Optional[Path],
    twitter_bearer_token: Optional[str],
    default_reddit_subs: List[str],
    max_rounds: Optional[int] = None,
    per_source_cap: Optional[int] = None,
    seed_twitter_queries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Use local Mistral (Ollama) to choose X, Reddit, and Wikipedia targets round-by-round.
    Starts from ChatGPT export text (peek + ingested chatlog files), optional memory snippets,
    then each round's fetches are summarized for the next plan.
    """
    cfg = load_learning_config()
    rounds = int(max_rounds if max_rounds is not None else cfg.get("mistral_chained_max_rounds", 3))
    rounds = max(1, min(8, rounds))
    cap = int(per_source_cap if per_source_cap is not None else cfg.get("mistral_chained_per_source_cap", 3))
    cap = max(1, min(10, cap))

    try:
        from .mistral_engine import MistralEngine
        from .ollama_model_config import get_canonical_ollama_model
        from .planner_readiness import should_short_circuit_verify_ollama_for_bad_tag

        _cm = get_canonical_ollama_model(log_once=False)
        if should_short_circuit_verify_ollama_for_bad_tag(_cm)[0]:
            logger.info(
                "[Chained learning] Skipping Mistral chain (canonical tag not an exact installed model; fix ELYSIA_OLLAMA_MODEL)",
            )
            return {
                "fetched": 0,
                "archived": 0,
                "admitted": 0,
                "rejected": 0,
                "cross_session_duplicates": 0,
                "mistral_chained_error": "skipped_bad_local_ollama_tag",
                "file": "",
                "memory_count": 0,
            }

        engine = MistralEngine(model=_cm)
    except Exception as e:
        logger.warning("[Chained learning] Mistral unavailable (%s); use flat learning session instead.", e)
        return {
            "fetched": 0,
            "archived": 0,
            "admitted": 0,
            "rejected": 0,
            "cross_session_duplicates": 0,
            "mistral_chained_error": str(e),
            "file": "",
            "memory_count": 0,
        }

    collected: List[Dict[str, Any]] = []
    if chatlogs_path:
        processed_marker = storage_path / ".processed_chatlogs.json"
        max_cf = int(cfg.get("max_chatlogs", 15))
        for item in fetch_chatlogs(chatlogs_path, max_files=max_cf, processed_path=processed_marker):
            item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
            collected.append(item)

    parts: List[str] = []
    if chatlogs_path:
        peek = peek_chatlogs_context(chatlogs_path, max_files=5)
        if peek:
            parts.append("ChatGPT exports (snippets for planning):\n" + peek)
    if topics:
        parts.append("Config topics: " + ", ".join(str(t) for t in topics[:24]))
    if memory:
        try:
            if hasattr(memory, "recall_last"):
                rm = memory.recall_last(14)
                lines = []
                for m in (rm or [])[:14]:
                    if isinstance(m, dict):
                        lines.append(str(m.get("thought", ""))[:220])
                    else:
                        lines.append(str(m)[:220])
                if lines:
                    parts.append("Recent memory:\n" + "\n".join(lines))
        except Exception as e:
            logger.debug("Chained learning memory context: %s", e)

    context = "\n\n".join(parts)[:12000]
    seen_tw: set = set()
    seen_rd: set = set()
    seen_wiki: set = set()
    seeds_tw = [s.strip() for s in (seed_twitter_queries or []) if s.strip()][:cap]
    seeds_sub = [re.sub(r"[^A-Za-z0-9_]", "", s.strip())[:50] for s in (default_reddit_subs or []) if s.strip()][:5]

    for r in range(rounds):
        plan = engine.suggest_learning_targets(
            context,
            r,
            {
                "twitter": list(seen_tw)[-35:],
                "reddit_search": list(seen_rd)[-35:],
                "wikipedia": list(seen_wiki)[-35:],
            },
            module_name="planner",
        )
        reasoning = (plan.get("reasoning") or "")[:500]
        logger.info("[Chained learning] round %d/%d Mistral: %s", r + 1, rounds, reasoning)

        empty_plan = not plan or not any([
            plan.get("twitter_queries"),
            plan.get("reddit_subreddits_new"),
            plan.get("reddit_searches"),
            plan.get("wikipedia_titles"),
        ])
        if empty_plan:
            if r == 0:
                plan = {
                    "twitter_queries": seeds_tw[:cap] if twitter_bearer_token else [],
                    "reddit_subreddits_new": seeds_sub[:cap] if seeds_sub else ["MachineLearning"],
                    "reddit_searches": [],
                    "wikipedia_titles": ["Artificial intelligence", "Large language model"][:cap],
                    "reasoning": "fallback: config seeds / defaults",
                }
                logger.info("[Chained learning] using seed fallback for round 1")
            else:
                logger.info("[Chained learning] empty plan after round 1 — stopping early")
                break

        for q in (plan.get("twitter_queries") or [])[:cap]:
            qn = (q or "").strip()[:200]
            if not qn or not twitter_bearer_token:
                continue
            kl = qn.lower()
            if kl in seen_tw:
                continue
            seen_tw.add(kl)
            for item in fetch_twitter(qn, twitter_bearer_token, limit=cap):
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                item["mistral_round"] = r
                collected.append(item)

        for sub in (plan.get("reddit_subreddits_new") or [])[:cap]:
            subn = re.sub(r"[^A-Za-z0-9_]", "", (sub or "").strip())[:50]
            if not subn:
                continue
            key = f"new:{subn.lower()}"
            if key in seen_rd:
                continue
            seen_rd.add(key)
            for item in fetch_reddit(subn, limit=cap):
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                item["mistral_round"] = r
                collected.append(item)

        for spec in (plan.get("reddit_searches") or [])[:cap]:
            if not isinstance(spec, dict):
                continue
            subn = re.sub(r"[^A-Za-z0-9_]", "", str(spec.get("subreddit", "")).strip())[:50]
            qn = str(spec.get("q", "")).strip()[:300]
            if not subn or not qn:
                continue
            key = f"search:{subn.lower()}:{qn.lower()}"
            if key in seen_rd:
                continue
            seen_rd.add(key)
            for item in fetch_reddit_search(subn, qn, limit=cap):
                item["compressed"] = compress_with_llm(item.get("text", ""), llm_callback, module_name="summarizer")
                item["mistral_round"] = r
                collected.append(item)

        for title in (plan.get("wikipedia_titles") or [])[:cap]:
            tn = (title or "").strip()[:200]
            if not tn:
                continue
            if tn.lower() in seen_wiki:
                continue
            seen_wiki.add(tn.lower())
            witem = fetch_wikipedia_summary(tn)
            if witem:
                witem["compressed"] = compress_with_llm(witem.get("text", ""), llm_callback, module_name="summarizer")
                witem["mistral_round"] = r
                collected.append(witem)

        tail = collected[-40:]
        summ = "; ".join(
            f'{i.get("source")}:{str(i.get("title") or "")[:48]}'
            for i in tail
        )
        context = (context + f"\n\n--- After round {r + 1} (titles) ---\n" + summ)[:12000]

    sc = max(1, rounds + (1 if chatlogs_path else 0))
    out = finalize_learned_collection(collected, storage_path, topics or [], memory, sources_count=sc)
    out["mistral_chained_rounds"] = rounds
    out["mistral_chained"] = True
    return out


# In-memory normalization ranges (aligned with config_validator)
_LEARNING_CONFIG_INT_DEFAULTS = {
    "min_relevance_score": (2, 0, 10),
    "min_reuse_potential": (1, 0, 5),
    "max_archived_per_session": (100, 10, 500),
    "max_memory_per_session": (20, 1, 100),
    "max_per_source_memory": (5, 1, 50),
    "dedup_window_days": (30, 1, 365),
    "max_chatlogs": (20, 0, 500),
    "max_per_source": (3, 1, 50),
    "mistral_chained_max_rounds": (3, 1, 8),
    "mistral_chained_per_source_cap": (3, 1, 10),
}
_LEARNING_CONFIG_FLOAT_DEFAULTS = {
    "interval_hours": (6.0, 0.5, 24),
    "learning_query_volume_scale": (0.65, 0.25, 1.0),
}
_LEARNING_CONFIG_BOOL_SAFE_DEFAULTS = {
    "allow_reddit_into_memory": False,
    "allow_strategic_into_memory": False,
    "mistral_chained_learning": False,
}


def _normalize_learning_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Apply safe normalization in-memory. Never returns values that weaken quality gates.
    Invalid booleans use safe default (no truthy coercion)."""
    out = dict(cfg)
    for key, (default, min_val, max_val) in _LEARNING_CONFIG_INT_DEFAULTS.items():
        try:
            v = int(out.get(key)) if out.get(key) is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            out[key] = default
        elif v < min_val or v > max_val:
            out[key] = max(min_val, min(max_val, v))
    for key, (default, min_val, max_val) in _LEARNING_CONFIG_FLOAT_DEFAULTS.items():
        try:
            v = float(out.get(key)) if out.get(key) is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            out[key] = default
        elif v < min_val or v > max_val:
            out[key] = max(min_val, min(max_val, v))
    for key, default in _LEARNING_CONFIG_BOOL_SAFE_DEFAULTS.items():
        v = out.get(key)
        if v is None or not isinstance(v, bool):
            out[key] = default
    return out


def load_learning_config() -> Dict[str, Any]:
    """Load auto_learning.json if present. Returns normalized config with safe defaults."""
    cfg_path = Path(__file__).parent.parent / "config" / "auto_learning.json"
    cfg: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            with open(cfg_path, "r") as f:
                cfg = json.load(f)
        except Exception as e:
            logger.debug(f"auto_learning.json: {e}")
    return _normalize_learning_config(cfg)


class AutoLearningScheduler:
    """Background scheduler for auto-learning."""

    def __init__(
        self,
        system_ref=None,
        interval_hours: float = 6.0,
        storage_path: Optional[Path] = None,
        chatlogs_path: Optional[Path] = None,
        topics: Optional[List[str]] = None,
        reddit_subs: Optional[List[str]] = None,
        rss_feeds: Optional[List[str]] = None,
        max_chatlogs: int = 20,
    ):
        cfg = load_learning_config()
        self.system_ref = system_ref
        iv = interval_hours if interval_hours and interval_hours != 6 else (cfg.get("interval_hours") or 6)
        self.interval_sec = max(3600, iv * 3600)  # min 1 hour
        self.storage_path = storage_path or get_learned_storage_path()
        self.chatlogs_path = chatlogs_path or get_chatlogs_path()
        self.max_chatlogs = cfg.get("max_chatlogs") or max_chatlogs
        self.topics = topics or cfg.get("topics") or DEFAULT_TOPICS
        self.reddit_subs = reddit_subs or cfg.get("reddit_subs") or DEFAULT_REDDIT_SUBS
        self.rss_feeds = rss_feeds or cfg.get("rss_feeds") or DEFAULT_RSS_FEEDS
        self.facebook_pages = cfg.get("facebook_page_ids") or DEFAULT_FACEBOOK_PAGES
        self.facebook_access_token = cfg.get("facebook_access_token") or os.environ.get("FACEBOOK_ACCESS_TOKEN") or ""
        self.twitter_search_queries = cfg.get("twitter_search_queries") or DEFAULT_TWITTER_SEARCH_QUERIES
        self.twitter_bearer_token = cfg.get("twitter_bearer_token") or os.environ.get("TWITTER_BEARER_TOKEN") or ""
        raw_web = cfg.get("web_urls") or []
        self.web_urls = [u.strip() for u in raw_web if isinstance(u, str) and u.strip().startswith(("http://", "https://"))][:5]
        self.max_per_source = cfg.get("max_per_source", 3)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_run: Optional[datetime] = None
        self._bad_session_cooldown_until: Optional[float] = None
        self._bad_session_streak: int = 0

    def _get_llm_callback(self) -> Optional[Callable[[str], tuple]]:
        if not self.system_ref:
            return None
        if hasattr(self.system_ref, "chat_with_llm"):
            return lambda msg: self.system_ref.chat_with_llm(msg)
        if hasattr(self.system_ref, "_llm_completion"):
            return lambda msg: self.system_ref._llm_completion([{"role": "user", "content": msg}], max_tokens=300)
        return None

    def _get_memory(self):
        """Get GuardianCore memory from system_ref so learned content flows into the main system."""
        if not self.system_ref:
            return None
        guardian = getattr(self.system_ref, "guardian", None)
        return getattr(guardian, "memory", None) if guardian else None

    def _run_once(self) -> None:
        try:
            now = time.time()
            if self._bad_session_cooldown_until is not None and now < self._bad_session_cooldown_until:
                logger.debug("[Auto-Learning] Skipping session (bad-session cooldown)")
                return
            llm = self._get_llm_callback()
            memory = self._get_memory()
            cfg = load_learning_config()
            if cfg.get("mistral_chained_learning") is True:
                result = run_mistral_chained_learning_session(
                    storage_path=self.storage_path,
                    topics=self.topics,
                    memory=memory,
                    llm_callback=llm,
                    chatlogs_path=self.chatlogs_path,
                    twitter_bearer_token=self.twitter_bearer_token or None,
                    default_reddit_subs=self.reddit_subs,
                    seed_twitter_queries=self.twitter_search_queries,
                )
                if result.get("mistral_chained_error"):
                    logger.info("[Auto-Learning] Chained learning unavailable; running standard session")
                    result = run_learning_session(
                        storage_path=self.storage_path,
                        topics=self.topics,
                        reddit_subs=self.reddit_subs,
                        rss_feeds=self.rss_feeds,
                        chatlogs_path=self.chatlogs_path,
                        web_urls=self.web_urls if self.web_urls else None,
                        facebook_pages=self.facebook_pages if self.facebook_access_token else None,
                        facebook_access_token=self.facebook_access_token or None,
                        twitter_search_queries=self.twitter_search_queries if self.twitter_bearer_token else None,
                        twitter_bearer_token=self.twitter_bearer_token or None,
                        max_per_source=self.max_per_source,
                        max_chatlogs=self.max_chatlogs,
                        llm_callback=llm,
                        memory=memory,
                    )
            else:
                result = run_learning_session(
                    storage_path=self.storage_path,
                    topics=self.topics,
                    reddit_subs=self.reddit_subs,
                    rss_feeds=self.rss_feeds,
                    chatlogs_path=self.chatlogs_path,
                    web_urls=self.web_urls if self.web_urls else None,
                    facebook_pages=self.facebook_pages if self.facebook_access_token else None,
                    facebook_access_token=self.facebook_access_token or None,
                    twitter_search_queries=self.twitter_search_queries if self.twitter_bearer_token else None,
                    twitter_bearer_token=self.twitter_bearer_token or None,
                    max_per_source=self.max_per_source,
                    max_chatlogs=self.max_chatlogs,
                    llm_callback=llm,
                    memory=memory,
                )
            self._last_run = datetime.now()
            if result.get("fetched", 0) == 0:
                logger.info("[Auto-Learning] Session complete: no items fetched")
            else:
                logger.debug(
                    "[Auto-Learning] Result: fetched=%d archived=%d admitted=%d rejected=%d",
                    result.get("fetched", 0), result.get("archived", 0),
                    result.get("admitted", 0), result.get("rejected", 0),
                )
            # Event-driven adversarial: bad learning session (high rejection, noisy)
            try:
                guardian = getattr(self.system_ref, "guardian", None) if self.system_ref else None
                if guardian:
                    from .adversarial_self_learning import trigger_adversarial_on_event
                    from .adversarial_self_learning import TRIGGER_BAD_LEARNING_SESSION
                    adv_result = trigger_adversarial_on_event(guardian, TRIGGER_BAD_LEARNING_SESSION, result)
                    if adv_result and result.get("fetched", 0) > 0:
                        ratio = result.get("rejected", 0) / max(1, result["fetched"])
                        if ratio >= 0.7 or (result.get("admitted", 0) == 0 and result["fetched"] >= 3):
                            cfg_path = Path(__file__).parent.parent / "config" / "memory_pressure.json"
                            cooldown_min = 90
                            mult = 1.0
                            if cfg_path.exists():
                                try:
                                    with open(cfg_path, "r") as f:
                                        pc = json.load(f)
                                    cooldown_min = pc.get("bad_learning_session_cooldown_minutes", 90)
                                    mult = float(pc.get("bad_learning_streak_cooldown_multiplier", 3.0))
                                except Exception:
                                    pass
                            self._bad_session_streak = getattr(self, "_bad_session_streak", 0) + 1
                            if self._bad_session_streak >= 2:
                                cooldown_min = int(cooldown_min * mult)
                            self._bad_session_cooldown_until = time.time() + (cooldown_min * 60)
                            logger.info(
                                "[Auto-Learning] Bad session cooldown: %d min (streak=%s)",
                                cooldown_min,
                                self._bad_session_streak,
                            )
                        else:
                            self._bad_session_streak = 0
            except Exception as ae:
                logger.debug("Adversarial learning trigger: %s", ae)
        except Exception as e:
            logger.warning("[Auto-Learning] Session failed: %s", e)

    def _loop(self) -> None:
        while self._running:
            self._run_once()
            for _ in range(int(self.interval_sec)):
                if not self._running:
                    break
                time.sleep(1)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AutoLearning")
        self._thread.start()
        logger.info("[Auto-Learning] Started (interval=%.1fh, storage=%s)", self.interval_sec / 3600, self.storage_path)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[Auto-Learning] Stopped")
