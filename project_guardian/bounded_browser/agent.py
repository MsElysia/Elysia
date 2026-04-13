# Bounded browse loop: budget-limited, read-only by default.

from __future__ import annotations

import hashlib
import logging
from collections import deque
from typing import Any, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .allowlist import normalize_apex_host, url_matches_allowlist
from .backends import BrowserBackend, create_browser_backend
from .evaluate import (
    classify_page_type,
    links_to_discovered_dict,
    recommend_next,
    relevance_score,
    score_link_for_goal,
)
from .memory_store import BrowserAgentMemoryStore
from .schema import BrowseTaskResult, ContinueAction, PageStepResult, page_step_to_dict

logger = logging.getLogger(__name__)


def _infer_start_url(goal: str, start_url: Optional[str]) -> str:
    if start_url and str(start_url).strip():
        return str(start_url).strip()
    g = goal.strip()
    first = g.split()[0] if g else ""
    if first.startswith("http://") or first.startswith("https://"):
        return first
    raise ValueError(
        "browse_task needs start_url=... unless goal starts with an http(s) URL (first token)."
    )


def browse_task(
    goal: str,
    start_url: Optional[str] = None,
    max_pages: int = 5,
    max_scrolls_per_page: int = 3,
    max_depth: int = 2,
    relevance_floor: float = 0.06,
    memory_store: Optional[BrowserAgentMemoryStore] = None,
    memory_core: Optional[Any] = None,
    backend: Optional[BrowserBackend] = None,
    *,
    allowed_hosts: Optional[Iterable[str]] = None,
    allowed_domains_for_log: Optional[Iterable[str]] = None,
) -> BrowseTaskResult:
    """
    Read-only bounded exploration: scroll a little, optionally enqueue one best link per page.

    Safety: no form submit, no login flows; navigation uses direct goto (not in-page destructive clicks).

    allowed_hosts: optional collection of apex hostnames (e.g. moltbook.com); www. is normalized.
    When set, start_url and every followed URL must match. allowed_domains_for_log is for logging only.
    """
    start = _infer_start_url(goal, start_url)
    allowed_normalized: Optional[frozenset[str]] = None
    if allowed_hosts is not None:
        raw = {normalize_apex_host(str(h)) for h in allowed_hosts if str(h).strip()}
        allowed_normalized = frozenset(x for x in raw if x)
        if not allowed_normalized:
            allowed_normalized = None
    if allowed_normalized is not None and not url_matches_allowlist(start, allowed_normalized):
        raise ValueError("start_url_not_on_domain_allowlist")

    def _log_domains() -> List[str]:
        if allowed_domains_for_log is not None:
            return [str(x) for x in allowed_domains_for_log]
        if allowed_normalized is not None:
            return sorted(allowed_normalized)
        return ["*"]

    be = backend or create_browser_backend()
    store = memory_store or BrowserAgentMemoryStore()

    result = BrowseTaskResult(goal=goal, start_url=start, stop_reason="")
    visited: Set[str] = set()
    queue: deque[Tuple[str, int]] = deque([(start, 0)])

    try:
        while queue:
            if len(result.steps) >= max_pages:
                result.truncated_by_budget = True
                result.stop_reason = "page_budget"
                break

            url, depth = queue.popleft()
            if url in visited:
                continue
            if allowed_normalized is not None and not url_matches_allowlist(url, allowed_normalized):
                logger.info("Skipping URL outside domain allowlist: %s", url[:120])
                continue
            host = ""
            try:
                host = urlparse(url).netloc.lower()
            except Exception:
                pass
            if host.startswith("www."):
                host = host[4:]
            if store.is_host_deprioritized(host):
                logger.info("Skipping deprioritized host: %s", host)
                continue

            visited.add(url)
            store.record_visit(url)

            try:
                be.open_url(url)
            except Exception as e:
                logger.warning("open_url failed %s: %s", url[:80], e)
                result.stop_reason = f"navigation_error:{e}"[:200]
                break

            best_rel = 0.0
            best_findings = ""
            last_hash = ""
            stagnant_rounds = 0
            scroll_i = 0
            final_links: List = []
            final_title = ""
            page_type = "misc"
            content_repeated = False

            while True:
                title = be.current_title()
                text = be.extract_visible_content()
                final_title = title
                h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
                if h == last_hash and scroll_i > 0:
                    content_repeated = True
                last_hash = h

                rel = relevance_score(goal, title, text)
                if rel > best_rel + 0.02:
                    stagnant_rounds = 0
                elif scroll_i > 0:
                    stagnant_rounds += 1
                best_rel = max(best_rel, rel)
                summ = be.summarize_current_page(goal)
                if len(summ) > len(best_findings):
                    best_findings = summ

                page_type = classify_page_type(be.current_url(), title, text)
                links = be.list_links()
                final_links = links

                best_link_score = 0.0
                best_link_idx: Optional[int] = None
                for L in links:
                    if allowed_normalized is not None and not url_matches_allowlist(L.href, allowed_normalized):
                        continue
                    sc = score_link_for_goal(goal, L.href, L.text, visited)
                    if sc > best_link_score:
                        best_link_score = sc
                        best_link_idx = L.index

                rec, det = recommend_next(
                    goal=goal,
                    relevance=rel,
                    page_type=page_type,
                    scroll_count=scroll_i,
                    max_scrolls=max_scrolls_per_page,
                    best_link_score=best_link_score,
                    content_repeated=content_repeated,
                    relevance_stagnant_rounds=stagnant_rounds,
                )

                if rel < relevance_floor and len(text) < 250 and host:
                    store.mark_low_value_host(host, "thin_low_relevance")

                def _emit_step(rec_a: str, det_a: str) -> None:
                    result.steps.append(
                        PageStepResult(
                            url=be.current_url(),
                            title=final_title,
                            page_type=page_type,
                            key_findings=(best_findings or summ)[:2000],
                            discovered_links=links_to_discovered_dict(final_links),
                            relevance_score=best_rel,
                            continue_recommendation=rec_a,
                            continue_detail=det_a,
                            content_hash=h,
                            scroll_index=scroll_i,
                        )
                    )
                    store.append_finding(be.current_url(), best_findings, best_rel)

                if rec == ContinueAction.STOP.value:
                    _emit_step(rec, det)
                    break

                if rec == ContinueAction.CLICK_LINK.value and best_link_idx is not None and best_link_score > 0:
                    chosen = next((L for L in links if L.index == best_link_idx), None)
                    if chosen and chosen.href not in visited:
                        _emit_step(rec, det)
                        if depth < max_depth and len(result.steps) < max_pages:
                            queue.append((chosen.href, depth + 1))
                        break
                    rec = ContinueAction.SCROLL.value

                if rec == ContinueAction.SCROLL.value and scroll_i < max_scrolls_per_page:
                    be.scroll_once()
                    scroll_i += 1
                    continue

                _emit_step(rec, det)
                break

        if not result.stop_reason:
            result.stop_reason = "completed" if not result.truncated_by_budget else "page_budget"
        result.visited_urls = list(visited)

        summary = _session_summary(goal, result)
        store.record_session(
            goal,
            summary,
            [page_step_to_dict(s) for s in result.steps],
            result.stop_reason,
        )
        _maybe_remember(memory_core, goal, summary, result)

        logger.info(
            "[BoundedBrowser] session goal=%r start_url=%r allowed_domains=%s pages_visited=%d stop_reason=%r",
            goal[:500],
            start[:500],
            _log_domains(),
            len(result.visited_urls),
            result.stop_reason,
        )

    finally:
        try:
            be.close()
        except Exception:
            pass

    return result


def _session_summary(goal: str, result: BrowseTaskResult) -> str:
    lines = [
        f"[BoundedBrowser] goal={goal[:200]} stop={result.stop_reason} steps={len(result.steps)}",
    ]
    for s in result.steps[:8]:
        lines.append(
            f"  {s.relevance_score:.2f} | {s.page_type} | {s.url[:90]} | {s.key_findings[:160]}"
        )
    return "\n".join(lines)


def _maybe_remember(memory_core: Any, goal: str, summary: str, result: BrowseTaskResult) -> None:
    if memory_core is None:
        return
    remember = getattr(memory_core, "remember", None)
    if not callable(remember):
        return
    try:
        remember(
            thought=summary[:8000],
            category="bounded_browser",
            priority=min(0.9, 0.35 + 0.1 * len(result.steps)),
            metadata={
                "goal": goal[:500],
                "stop_reason": result.stop_reason,
                "visited": result.visited_urls[:20],
            },
        )
    except Exception as e:
        logger.debug("memory_core.remember skipped: %s", e)
