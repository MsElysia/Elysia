# Domain allowlist helpers for bounded browser (apex / www normalization).

from __future__ import annotations

from typing import Collection, Iterable, List, Optional
from urllib.parse import urlparse

# Log / docs: human-facing hostnames allowed for Moltbook preset
MOLTBOOK_ALLOWED_DOMAINS_DISPLAY: tuple[str, ...] = ("moltbook.com", "www.moltbook.com")

# Normalized apex set used for matching (www.moltbook.com → moltbook.com)
MOLTBOOK_ALLOWED_APEX: frozenset[str] = frozenset({"moltbook.com"})

MOLTBOOK_DEFAULT_START_URL = "https://www.moltbook.com/"


def normalize_apex_host(host: str) -> str:
    """Lowercase hostname without port; strip a single leading www."""
    h = (host or "").strip().lower()
    if not h:
        return ""
    h = h.split("@")[-1]
    h = h.split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    return h


def normalize_allowed_hosts_entries(entries: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for e in entries:
        s = normalize_apex_host(str(e))
        if s:
            out.add(s)
    return frozenset(out)


def url_matches_allowlist(url: str, allowed_apex: Collection[str]) -> bool:
    """True if URL is http(s) and host (after www strip) is in allowed_apex."""
    if not allowed_apex:
        return True
    try:
        p = urlparse((url or "").strip())
        if p.scheme not in ("http", "https") or not p.netloc:
            return False
        host = normalize_apex_host(p.netloc)
        return bool(host) and host in allowed_apex
    except Exception:
        return False


def parse_payload_allowed_hosts(
    raw: Optional[object],
    *,
    max_hosts: int = 8,
) -> Optional[frozenset[str]]:
    """
    Build normalized apex set from payload list, or None if unset / empty.
    Caller may pass allow_any_domain to skip restriction (see capability layer).
    """
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        return None
    items: List[str] = []
    for x in raw[:max_hosts]:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            items.append(s)
    if not items:
        return None
    return normalize_allowed_hosts_entries(items)
