# Human-signal and thread-quality heuristics (selection only; no browser changes).

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .filters import sponsored_risk_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_INSIGHT_MARKERS = (
    "however",
    "actually",
    "disagree",
    "counterpoint",
    "worked for us",
    "we tried",
    "benchmark",
    "lesson learned",
    "mistake",
    "wrong",
    "tradeoff",
    "feedback",
    "in practice",
    "edge case",
    "nuance",
)
_DISAGREE_MARKERS = (
    "but ",
    "although ",
    "on the other hand",
    "i disagree",
    "push back",
    "respectfully",
)
_PERSONAL_MARKERS = (
    " i ",
    " i'm",
    " i've",
    " we ",
    " my ",
    " our ",
    "in my experience",
    "imo",
    "personally",
    "i think",
)
_BOT_PHRASES = (
    "great content",
    "nice post",
    "follow me",
    "check my",
    "dm me",
    "link in bio",
    "crypto",
    "100x",
)
_GENERIC_SPAM = ("🔥🔥", "!!!", "???", "free money", "guaranteed")


def handle_from_moltbook_url(url: str) -> Optional[str]:
    m = re.search(r"/@([\w\-]+)", (url or ""), re.I)
    if not m:
        return None
    return "@" + m.group(1).lower()


def extract_handles_from_urls(urls: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for u in urls:
        h = handle_from_moltbook_url(u)
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def extract_speaker_names(text: str) -> List[str]:
    blob = text or ""
    names: List[str] = []
    for m in re.finditer(
        r"\b([A-Z][a-z]{2,})\s+(?:said|writes|asks|replied|notes|added|argues|thinks|wonders|disagrees)\b",
        blob,
    ):
        names.append(m.group(1))
    for m in re.finditer(r"(?:^|\n)\s*([A-Z][a-z]{2,})\s*:", blob):
        names.append(m.group(1))
    # "Alice and Bob debate"
    for m in re.finditer(r"\b([A-Z][a-z]{2,})\s+and\s+([A-Z][a-z]{2,})\s+\w+", blob):
        names.extend([m.group(1), m.group(2)])
    seen: Set[str] = set()
    uniq: List[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return uniq


def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))


def _sentence_count(s: str) -> int:
    t = (s or "").strip()
    if not t:
        return 0
    return max(1, len(re.split(r"(?<=[.!?])\s+", t)))


def _question_density(text: str) -> float:
    t = text or ""
    if not t.strip():
        return 0.0
    q = t.count("?")
    return min(1.0, q / max(2, _sentence_count(t)))


def personal_wording_score(text: str) -> float:
    low = (text or "").lower()
    if not low.strip():
        return 0.0
    hits = sum(1 for m in _PERSONAL_MARKERS if m in low)
    return min(1.0, hits * 0.22)


def bot_like_penalty(text: str) -> float:
    """0..~0.45 subtractive penalty for bot/spam styling."""
    t = text or ""
    if not t.strip():
        return 0.0
    low = t.lower()
    pen = 0.0
    for ph in _BOT_PHRASES:
        if ph in low:
            pen += 0.12
    for g in _GENERIC_SPAM:
        if g in t or g in low:
            pen += 0.1
    # emoji / symbol density (rough)
    sym = len(re.findall(r"[\U0001F300-\U0001FAFF]", t))
    if sym >= 4:
        pen += min(0.2, sym * 0.03)
    if len(re.findall(r"(.)\1{4,}", t)) >= 1:
        pen += 0.12
    caps = len(re.findall(r"\b[A-Z]{3,}\b", t))
    if caps >= 3:
        pen += 0.08
    return min(0.45, pen)


def insight_disagreement_score(chunks: List[str]) -> float:
    if not chunks:
        return 0.0
    joined = "\n".join(chunks).lower()
    hits = sum(1 for m in _INSIGHT_MARKERS if m in joined)
    hits += sum(1 for m in _DISAGREE_MARKERS if m in joined)
    return min(1.0, hits / max(3, len(chunks) * 1.2))


def token_overlap(a: str, b: str) -> float:
    ta = {w for w in re.findall(r"[a-z]{3,}", (a or "").lower()) if len(w) > 2}
    tb = {w for w in re.findall(r"[a-z]{3,}", (b or "").lower()) if len(w) > 2}
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return min(1.0, inter / max(4, min(len(ta), len(tb))))


def load_campaign_corpus_text() -> str:
    p = PROJECT_ROOT / "config" / "mission_autonomy.json"
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts: List[str] = []
    for c in data.get("campaigns") or []:
        if not isinstance(c, dict):
            continue
        for k in ("title", "purpose", "success_metric"):
            v = c.get(k)
            if isinstance(v, str):
                parts.append(v)
    for sp in data.get("standing_priorities") or []:
        if isinstance(sp, dict) and isinstance(sp.get("title"), str):
            parts.append(sp["title"])
    return " ".join(parts)[:8000]


def recurrence_counts_for_handles(max_lines: int = 120) -> Dict[str, int]:
    from .memory import read_tail_jsonl

    counts: Dict[str, int] = {}
    for rec in read_tail_jsonl("profiles.jsonl", max_lines=max_lines):
        u = rec.get("url") or ""
        h = handle_from_moltbook_url(str(u))
        if h:
            counts[h] = counts.get(h, 0) + 1
    return counts


def build_participant_rows(
    *,
    urls: List[str],
    chunks: List[str],
    recurrence: Dict[str, int],
    campaign_corpus: str,
    goal: str,
    contact_priors: Optional[Dict[str, Dict[str, Any]]] = None,
    continuity_cfg: Optional[Dict[str, Any]] = None,
    now_ts: Optional[float] = None,
) -> List[Dict[str, Any]]:
    handles = extract_handles_from_urls(urls)
    names = extract_speaker_names("\n\n".join(chunks))
    rows: List[Dict[str, Any]] = []

    def chunk_blob_for(pid: str, is_handle: bool) -> str:
        parts: List[str] = []
        if is_handle:
            key = pid.lstrip("@").lower()
            for c in chunks:
                cl = c.lower()
                if f"@{key}" in cl or re.search(rf"\b{re.escape(key)}\b", cl):
                    parts.append(c)
        else:
            for c in chunks:
                if re.search(rf"\b{re.escape(pid)}\b", c):
                    parts.append(c)
        return "\n\n".join(parts) if parts else ""

    for h in handles:
        blob = chunk_blob_for(h, True)
        rows.append({"id": h, "display": h, "url_profile_hint": True, "mention_blob": blob})
    for n in names:
        nid = f"name:{n}"
        if any(r["id"] == nid for r in rows):
            continue
        blob = chunk_blob_for(n, False)
        if blob or any(n in c for c in chunks):
            rows.append({"id": nid, "display": n, "url_profile_hint": False, "mention_blob": blob})

    # score each row
    goal_topics = f"{goal} {campaign_corpus}"
    out: List[Dict[str, Any]] = []
    for r in rows:
        pid = r["id"]
        blob = r["mention_blob"] or ""
        if not blob.strip():
            # handle with no text: still score from recurrence + profile URL
            prior_ic0 = int((contact_priors or {}).get(pid, {}).get("interaction_count") or 0)
            base_rec = min(
                1.0,
                (recurrence.get(pid, 0) + (1 if r.get("url_profile_hint") else 0)) / 3.0,
                prior_ic0 / 4.0 + 0.15,
            )
            recurring = 0.25 * base_rec
            promo = 0.15 * (1.0 - sponsored_risk_score(" ".join(chunks)[:2000]))
            person_score = round(0.35 * recurring + 0.4 * promo + 0.25 * 0.35, 3)
            likely = round(max(0.0, min(1.0, person_score * 0.95)), 3)
            reasons = ["recurrence_or_profile_only", "no_inline_mentions_yet"]
            out.append(
                {
                    "id": pid,
                    "display": r["display"],
                    "person_score": person_score,
                    "likely_human": likely,
                    "relevance_reasons": reasons,
                    "suggested_next_interaction": "Read profile thread later to validate voice before outreach.",
                }
            )
            continue

        rec_n = recurrence.get(pid, 0)
        prior_ic = int((contact_priors or {}).get(pid, {}).get("interaction_count") or 0)
        recurring_part = min(1.0, max(rec_n / 3.0, prior_ic / 5.0))
        reciprocity = _question_density(blob)
        promo_clean = 1.0 - sponsored_risk_score(blob)
        personal = personal_wording_score(blob)
        topical = token_overlap(blob, goal_topics)
        follow = min(1.0, reciprocity * 0.55 + min(1.0, _word_count(blob) / 120.0) * 0.45)
        bot_pen = bot_like_penalty(blob)

        person_score = (
            0.22 * recurring_part
            + 0.14 * reciprocity
            + 0.20 * max(0.0, promo_clean)
            + 0.14 * personal
            + 0.15 * topical
            + 0.15 * follow
        )
        person_score = min(1.0, person_score)
        likely_human = max(0.0, min(1.0, person_score * (1.0 - bot_pen) - 0.05 * max(0, sponsored_risk_score(blob) - 0.35)))

        reasons: List[str] = []
        if recurring_part >= 0.34:
            reasons.append("recurring_participation")
        if reciprocity >= 0.25:
            reasons.append("conversational_reciprocity")
        if promo_clean >= 0.65:
            reasons.append("low_promo_language")
        if personal >= 0.22:
            reasons.append("specific_personal_wording")
        if topical >= 0.18:
            reasons.append("campaign_topical_overlap")
        if follow >= 0.35:
            reasons.append("follow_up_potential")

        suggested = "Draft a narrow follow-up question on their stated constraint; avoid promo tone."
        if reciprocity >= 0.3:
            suggested = "Answer their open question briefly, then ask one clarifying question back."
        elif topical >= 0.25:
            suggested = "Connect their point to active campaign themes; invite concrete example."

        out.append(
            {
                "id": pid,
                "display": r["display"],
                "person_score": round(person_score, 3),
                "likely_human": round(likely_human, 3),
                "relevance_reasons": reasons or ["baseline_social_signal"],
                "suggested_next_interaction": suggested,
            }
        )
    out.sort(key=lambda x: (-x["person_score"] * x["likely_human"], -x["person_score"]))

    if contact_priors is not None and continuity_cfg is not None:
        import time as _time

        from .continuity import adjust_person_for_continuity

        ts = float(now_ts or _time.time())
        for row in out:
            pid = str(row.get("id") or "")
            adjust_person_for_continuity(
                row,
                prior=contact_priors.get(pid, {}),
                now_ts=ts,
                cfg=continuity_cfg,
            )
        out.sort(key=lambda x: (-x["person_score"] * x["likely_human"], -x["person_score"]))
    return out


def score_thread_quality(
    *,
    all_chunks: List[str],
    step_scores: List[float],
    topics: List[str],
    goal: str,
    sponsored_skipped: int,
    total_raw_chunks: int,
    participant_count: int,
    campaign_corpus: str,
    thread_prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not all_chunks:
        discussion_density = 0.15
        promo_avg = 0.55
    else:
        wc = sum(_word_count(c) for c in all_chunks) / max(1, len(all_chunks))
        discussion_density = min(1.0, (len(all_chunks) / 5.0) * min(1.0, wc / 42.0))
        risks = [sponsored_risk_score(c) for c in all_chunks]
        promo_avg = sum(risks) / max(1, len(risks))

    participants_score = min(1.0, max(participant_count, 1) / 3.5)
    campaign_overlap = token_overlap(f"{goal} {' '.join(topics)}", campaign_corpus)
    insight = insight_disagreement_score(all_chunks)
    rel_steps = sum(step_scores) / max(1, len(step_scores)) if step_scores else 0.4

    skip_ratio = sponsored_skipped / max(1, total_raw_chunks) if total_raw_chunks else 0.0
    promo_recovery = min(1.0, (1.0 - promo_avg) + 0.15 * min(1.0, skip_ratio))

    thread_score = (
        0.22 * discussion_density
        + 0.22 * participants_score
        + 0.22 * promo_recovery
        + 0.18 * campaign_overlap
        + 0.10 * insight
        + 0.06 * min(1.0, rel_steps + 0.15)
    )
    thread_score = round(min(1.0, thread_score), 3)

    likely_discussion_human_mix = round(
        0.42 * (1.0 - promo_avg) + 0.28 * participants_score + 0.18 * insight + 0.12 * discussion_density,
        3,
    )

    rank_reasons: List[str] = []
    if discussion_density >= 0.35:
        rank_reasons.append("real_discussion_density")
    if participants_score >= 0.4:
        rank_reasons.append("multiple_distinct_participants")
    if promo_recovery >= 0.55:
        rank_reasons.append("low_promotional_risk")
    if campaign_overlap >= 0.15:
        rank_reasons.append("campaign_relevance")
    if insight >= 0.25:
        rank_reasons.append("insight_or_disagreement_signal")

    suggested_next = "Prioritize replies to ranked humans; skim low-score handles for spam only."
    if thread_score >= 0.55:
        suggested_next = "Strong thread: draft one thoughtful reply to top-ranked participant."
    elif thread_score < 0.32:
        suggested_next = "Thin thread: observe more before outreach; deprioritize promo-like voices."

    out_rank = {
        "thread_score": thread_score,
        "likely_discussion_human_mix": likely_discussion_human_mix,
        "thread_rank_reasons": rank_reasons or ["baseline_thread_signal"],
        "suggested_next_interaction": suggested_next,
        "components": {
            "discussion_density": round(discussion_density, 3),
            "participants_score": round(participants_score, 3),
            "promo_avg": round(promo_avg, 3),
            "campaign_overlap": round(campaign_overlap, 3),
            "insight_signal": round(insight, 3),
        },
    }
    if thread_prior is not None and int(thread_prior.get("revisit_count") or 0) > 0:
        from .continuity import apply_thread_prior_to_rank

        out_rank = apply_thread_prior_to_rank(out_rank, thread_prior=thread_prior, cfg={})
    return out_rank


def build_rank_context_for_draft(
    *,
    thread_rank: Dict[str, Any],
    participants: List[Dict[str, Any]],
    top_n: int = 3,
    contact_priors: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    top = participants[:top_n]
    primary = top[0] if top else {}
    deprio = [p for p in participants[top_n:] if p.get("likely_human", 1) < 0.38 or p.get("person_score", 1) < 0.22]
    continuity_hints: List[str] = []
    for p in top:
        pid = str(p.get("id") or "")
        pri = (contact_priors or {}).get(pid) if pid else None
        if isinstance(pri, dict) and pri:
            continuity_hints.append(
                f"{p.get('display')}: stage={pri.get('relationship_stage')} prior_visits={pri.get('interaction_count')}"
            )
    return {
        "thread_score": thread_rank.get("thread_score"),
        "likely_discussion_human_mix": thread_rank.get("likely_discussion_human_mix"),
        "primary_contact": {"display": primary.get("display"), "reasons": primary.get("relevance_reasons", [])},
        "prioritize_displays": [p.get("display") for p in top if p.get("display")],
        "deprioritize_note": f"Skip or skim {len(deprio)} low-signal identities" if deprio else None,
        "continuity_hints": continuity_hints or None,
    }
