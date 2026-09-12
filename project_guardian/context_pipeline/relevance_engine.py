# project_guardian/context_pipeline/relevance_engine.py
"""Two-stage relevance: rules + semantic (embeddings preferred, TF-IDF fallback)."""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from .embedding_backend import embed_texts, max_cosine_to_queries
from .models import ContradictionRecord
from .schemas import TOPIC_BUCKETS, IngestedRecordDict

logger = logging.getLogger(__name__)

_NEG_HINTS = re.compile(
    r"\b(no|not|never|cannot|can't|won't|false|incorrect|disagree|contradict)\b",
    re.I,
)
_INFERRED_MARKERS = re.compile(
    r"\b(likely|probably|maybe|perhaps|guess|unclear|uncertain|seems|appears)\b",
    re.I,
)


def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-z0-9]{2,}", (s or "").lower())


def tfidf_cosine(a: str, b: str) -> float:
    ca, cb = Counter(_tokens(a)), Counter(_tokens(b))
    if not ca or not cb:
        return 0.0
    vocab = set(ca) | set(cb)
    dot = sum(ca.get(t, 0) * cb.get(t, 0) for t in vocab)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    if not na or not nb:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def build_semantic_query_texts(
    objective_text: str,
    campaign_text: str,
    user_directives: str,
    decision_objective: str,
) -> List[str]:
    parts: List[str] = []
    for blob, label in (
        (objective_text, "objective"),
        (campaign_text, "campaign"),
        (user_directives, "user"),
        (decision_objective, "decision"),
    ):
        s = (blob or "").strip()
        if len(s) >= 12:
            parts.append(s[:6000])
    if not parts:
        parts.append("autonomy operations safety")
    return parts


def source_priority_weight(source_type: str, priorities: Dict[str, float]) -> float:
    key = (source_type or "unknown").lower()
    return float(priorities.get(key, priorities.get("unknown", 0.55)))


def recency_weight(ts: float, now: float, half_life_hours: float) -> float:
    if ts <= 0:
        return 0.5
    age_h = max(0.0, (now - ts) / 3600.0)
    hl = max(1.0, half_life_hours)
    return 0.5 ** (age_h / hl)


def rule_keyword_score(text: str, rules: List[Dict[str, Any]]) -> float:
    low = (text or "").lower()
    score = 0.0
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        w = float(r.get("weight") or 0.15)
        for kw in r.get("keywords") or []:
            if str(kw).lower() in low:
                score += w
        for ph in r.get("phrases") or []:
            if str(ph).lower() in low:
                score += w * 1.2
    return max(0.0, min(1.0, score))


def detect_contradiction_penalty(records: List[IngestedRecordDict], window: int = 24) -> Dict[str, float]:
    pen: Dict[str, float] = {}
    texts = [(r.get("id") or "", r.get("raw_text") or "") for r in records[-window:]]
    for i, (id_a, ta) in enumerate(texts):
        if not id_a or len(ta) < 40:
            continue
        na = len(_NEG_HINTS.findall(ta))
        if na < 1:
            continue
        for j in range(i + 1, min(i + 6, len(texts))):
            id_b, tb = texts[j]
            if not id_b or id_a == id_b:
                continue
            nb = len(_NEG_HINTS.findall(tb))
            if nb < 1:
                continue
            sim = tfidf_cosine(ta, tb)
            if sim > 0.35 and sim < 0.72:
                pen[id_a] = max(pen.get(id_a, 0.0), 0.08)
                pen[id_b] = max(pen.get(id_b, 0.0), 0.08)
    return pen


def frequency_keys(records: List[IngestedRecordDict]) -> Counter:
    c: Counter = Counter()
    for r in records:
        for t in _tokens(r.get("raw_text") or "")[:80]:
            c[t] += 1
    return c


def novelty_for_record(text: str, freq: Counter) -> float:
    toks = _tokens(text)[:60]
    if not toks:
        return 0.5
    scores = [1.0 / (1.0 + math.log1p(freq.get(t, 0))) for t in toks]
    return float(sum(scores) / max(1, len(scores)))


def extract_contradictions(
    records: List[IngestedRecordDict],
    rel_map: Dict[str, Dict[str, Any]],
    *,
    min_score: float = 0.42,
) -> List[ContradictionRecord]:
    """Surface high-scoring conflicting pairs (negation + overlapping topic)."""
    out: List[ContradictionRecord] = []
    seen_pairs: Set[Any] = set()
    ranked = sorted(
        records,
        key=lambda r: float((rel_map.get(str(r.get("id") or "")) or {}).get("total_score") or 0.0),
        reverse=True,
    )[:20]
    for i, ra in enumerate(ranked):
        ida = str(ra.get("id") or "")
        ta = (ra.get("raw_text") or "")[:900]
        if len(ta) < 50 or not ida:
            continue
        na = len(_NEG_HINTS.findall(ta))
        for rb in ranked[i + 1 : i + 7]:
            idb = str(rb.get("id") or "")
            tb = (rb.get("raw_text") or "")[:900]
            if not idb or ida == idb:
                continue
            nb = len(_NEG_HINTS.findall(tb))
            if na < 1 and nb < 1:
                continue
            sim = tfidf_cosine(ta, tb)
            sca = float((rel_map.get(ida) or {}).get("total_score") or 0.0)
            scb = float((rel_map.get(idb) or {}).get("total_score") or 0.0)
            if sim > 0.28 and sim < 0.78 and sca >= min_score and scb >= min_score:
                key = frozenset((ida, idb))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                conf = min(0.95, 0.35 + sim * 0.55 + (0.05 if na and nb else 0.0))
                out.append(
                    ContradictionRecord(
                        topic="semantic_overlap_negation",
                        record_ids=(ida, idb),
                        snippets=(ta[:220], tb[:220]),
                        confidence=round(conf, 3),
                    )
                )
    return out[:8]


def build_relevance_map(
    records: List[IngestedRecordDict],
    objective_text: str,
    *,
    cfg: Dict[str, Any],
    now_ts: Optional[float] = None,
    campaign_text: str = "",
    user_directives: str = "",
    decision_objective: str = "",
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    now = float(now_ts or time.time())
    freq = frequency_keys(records)
    contra_pen = detect_contradiction_penalty(records)
    priorities = dict(cfg.get("source_priority_weights") or {})
    half_life = float(cfg.get("recency_half_life_hours") or 48.0)
    rules = list(cfg.get("keyword_rules") or [])

    query_texts = build_semantic_query_texts(
        objective_text, campaign_text, user_directives, decision_objective
    )

    semantic_backend = str(cfg.get("semantic_backend") or "tfidf").lower().strip()
    embed_thr = float(cfg.get("embedding_similarity_threshold") or 0.0)

    query_embs: List[Optional[List[float]]] = [None]
    record_embs: List[Optional[List[float]]] = [None] * len(records)
    embed_kind = "none"

    if semantic_backend == "embeddings":
        q_backend, q_vecs = embed_texts(query_texts[:6], cfg=cfg)
        rtexts = [(r.get("raw_text") or "")[:8000] for r in records]
        r_backend, r_vecs = embed_texts(rtexts, cfg=cfg)
        embed_kind = q_backend if q_backend != "none" else r_backend
        query_embs = q_vecs
        record_embs = r_vecs
        if embed_kind == "none":
            embed_kind = "embeddings_fallback_tfidf"
            logger.info(
                "[RelevanceMap] backend=embeddings_fallback_tfidf records=%s queries=%s",
                len(records),
                len(query_texts),
            )
        else:
            logger.info(
                "[RelevanceMap] backend=%s records=%s queries=%s",
                embed_kind,
                len(records),
                len(query_texts),
            )
    else:
        logger.info("[RelevanceMap] backend=tfidf records=%s", len(records))

    out: Dict[str, Dict[str, Any]] = {}
    semantic_scores: List[Tuple[str, float]] = []

    for idx, r in enumerate(records):
        rid = str(r.get("id") or "")
        if not rid:
            continue
        raw = r.get("raw_text") or ""

        rules_score = rule_keyword_score(raw, rules)
        recency_score = recency_weight(float(r.get("timestamp") or 0), now, half_life)
        trust_s = float(r.get("trust_score") or 0.65)
        novelty_score = novelty_for_record(raw, freq)
        cpen = float(contra_pen.get(rid, 0.0))

        sem_tfidf = max(tfidf_cosine(raw, q) for q in query_texts) if query_texts else 0.0
        sem_emb = 0.0
        re = record_embs[idx] if idx < len(record_embs) else None
        if re and any(query_embs):
            sem_emb = max_cosine_to_queries(re, query_embs, embed_thr)
        if embed_kind != "none" and sem_emb > 0:
            semantic_score = float(max(sem_emb, sem_tfidf * 0.35))
        else:
            semantic_score = float(sem_tfidf)

        sp = source_priority_weight(str(r.get("source_type") or ""), priorities)
        imp0 = float(r.get("initial_importance") or 0.5)
        user_boost = 0.1 if str(r.get("source_type")) == "user_input" else 0.0

        blend_core = (
            0.5 * semantic_score
            + 0.22 * rules_score
            + 0.12 * min(1.0, len(_tokens(raw)) / 80.0)
            + 0.08 * novelty_score
        )
        total_score = blend_core * (0.32 + 0.68 * sp) * (0.38 + 0.62 * recency_score) * (0.48 + 0.52 * trust_s)
        total_score = total_score * (0.55 + 0.45 * imp0) + user_boost + 0.06 * semantic_score - cpen
        total_score = max(0.0, min(1.0, total_score))

        out[rid] = {
            "rules_score": round(rules_score, 4),
            "semantic_score": round(semantic_score, 4),
            "recency_score": round(recency_score, 4),
            "trust_score": round(trust_s, 4),
            "novelty_score": round(novelty_score, 4),
            "contradiction_penalty": round(cpen, 4),
            "total_score": round(total_score, 4),
            # backward compat keys
            "score": round(total_score, 4),
            "semantic_to_objective": round(semantic_score, 4),
            "rule_signal": round(rules_score, 4),
            "novelty": round(novelty_score, 4),
            "recency_weight": round(recency_score, 4),
        }
        semantic_scores.append((rid, semantic_score))

    semantic_scores.sort(key=lambda x: -x[1])
    top_matches = [{"id": a[:20], "semantic": round(b, 4)} for a, b in semantic_scores[:8]]
    reported_backend = embed_kind if embed_kind != "none" else semantic_backend
    meta = {
        "semantic_backend": reported_backend,
        "top_semantic_matches": top_matches,
        "query_text_count": len(query_texts),
    }
    logger.info("[RelevanceMap] top_semantic_matches=%s", top_matches[:5])
    return out, meta


def infer_topic_bucket(text: str, tags: List[str]) -> str:
    low = (text or "").lower()
    joined = " ".join(tags or []).lower()
    if any(k in low for k in ("password", "secret key", "api key", "ssn", "my name is")):
        return "identity"
    if any(k in low for k in ("must not", "constraint", "blocked", "illegal", "forbidden")):
        return "constraints"
    if "?" in (text or "") and any(k in low for k in ("why", "how", "what if", "unknown")):
        return "unresolved_questions"
    if any(k in low for k in ("risk", "danger", "exploit", "harm")):
        return "risks"
    if any(k in low for k in ("revenue", "money", "paid", "customer")):
        return "monetization"
    if any(k in low for k in ("autonom", "agent loop", "decision")):
        return "autonomy"
    if any(k in low for k in ("refactor", "module", "architecture", "service")):
        return "architecture"
    if any(k in low for k in ("goal", "objective", "milestone")) or "goals" in joined:
        return "goals"
    if any(k in low for k in ("prefer", "like", "dislike")):
        return "preferences"
    if any(k in low for k in ("project", "sprint", "ticket")):
        return "projects"
    return "goals" if "goal" in joined else "architecture"


def topic_bucket_for_record(r: IngestedRecordDict) -> str:
    b = infer_topic_bucket(r.get("raw_text") or "", list(r.get("tags") or []))
    return b if b in TOPIC_BUCKETS else "architecture"
