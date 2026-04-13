# Heuristic sponsored / low-signal funnel detection for social reader text.

from __future__ import annotations

import re
from typing import List, Tuple

_SPONSORED_TERMS = (
    "sponsored",
    "promoted",
    "promotion",
    "boosted",
    "paid partnership",
    "affiliate",
    "affiliate link",
    "commission",
    "discount code",
    "use code",
    "promo code",
    "buy now",
    "limited time offer",
    "click here to buy",
    "sign up now",
    "free trial",
    "subscribe now",
    "dm me for",
    "link in bio",
    "my store",
    "checkout",
    "coupon",
)

_FUNNEL_URL_HINTS = (
    "utm_",
    "utm_source",
    "ref=",
    "affiliate",
    "click.",
    "/go/",
    "/offer",
    "/deal",
    "bit.ly/",
    "tinyurl.",
)

_LOW_SIGNAL_PHRASES = (
    "you won't believe",
    "doctors hate",
    "one weird trick",
    "make $",
    "passive income",
    "guaranteed returns",
)


def sponsored_risk_score(text: str) -> float:
    """
    Return 0..1 where higher means more likely sponsored / commercial bait.
    Used to downrank or skip chunks; not a classifier guarantee.
    """
    t = (text or "").lower()
    if not t.strip():
        return 0.0
    score = 0.0
    for term in _SPONSORED_TERMS:
        if term in t:
            score += 0.12
    for phrase in _LOW_SIGNAL_PHRASES:
        if phrase in t:
            score += 0.1
    for hint in _FUNNEL_URL_HINTS:
        if hint in t:
            score += 0.08
    # Many dollar amounts + urgency
    if len(re.findall(r"\$\d+", t)) >= 2 and any(x in t for x in ("today", "now", "hurry", "last chance")):
        score += 0.15
    return min(1.0, score)


def filter_text_chunks(
    chunks: List[str],
    *,
    threshold: float,
) -> Tuple[List[str], int]:
    """Keep chunks at or below risk threshold; return (kept, skipped_count)."""
    kept: List[str] = []
    skipped = 0
    for c in chunks:
        s = (c or "").strip()
        if not s:
            continue
        if sponsored_risk_score(s) >= threshold:
            skipped += 1
            continue
        kept.append(s)
    return kept, skipped


def split_findings_into_chunks(key_findings: str, *, max_chunk_chars: int = 900) -> List[str]:
    """Split long findings into paragraphs / sentences for per-chunk scoring."""
    raw = (key_findings or "").strip()
    if not raw:
        return []
    parts = re.split(r"\n\s*\n+", raw)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= max_chunk_chars:
            out.append(p)
            continue
        # long block: sentence-ish splits
        sentences = re.split(r"(?<=[.!?])\s+", p)
        buf = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(buf) + len(sent) + 1 > max_chunk_chars:
                if buf:
                    out.append(buf.strip())
                buf = sent
            else:
                buf = (buf + " " + sent).strip()
        if buf:
            out.append(buf)
    return out
