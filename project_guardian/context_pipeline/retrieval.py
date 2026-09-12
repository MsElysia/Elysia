# project_guardian/context_pipeline/retrieval.py
"""Source-balanced retrieval + contradiction-fed unknowns/risks."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from .models import ContradictionRecord, RetrievedContextBundle
from .schemas import IngestedRecordDict

logger = logging.getLogger(__name__)

_DEFAULT_CAPS: Dict[str, int] = {
    "user_input": 5,
    "memory": 6,
    "chat_history": 3,
    "log": 3,
    "browser_finding": 3,
    "planner_snapshot": 4,
    "task_snapshot": 4,
    "monitor_snapshot": 2,
    "unknown": 2,
}


def _norm_source(st: str) -> str:
    s = (st or "unknown").lower().strip()
    if s in _DEFAULT_CAPS:
        return s
    if "planner" in s:
        return "planner_snapshot"
    if "monitor" in s:
        return "monitor_snapshot"
    if "task" in s:
        return "task_snapshot"
    return s if s in _DEFAULT_CAPS else "unknown"


def balanced_retrieve(
    records: List[IngestedRecordDict],
    rel_map: Dict[str, Dict[str, Any]],
    contradictions: List[ContradictionRecord],
    *,
    cfg: Dict[str, Any],
) -> RetrievedContextBundle:
    caps = dict(_DEFAULT_CAPS)
    caps.update(cfg.get("source_retrieval_caps") or {})
    max_total = int(cfg.get("max_total_retrieved_items") or 36)

    def _total(rec: IngestedRecordDict) -> float:
        rid = str(rec.get("id") or "")
        m = rel_map.get(rid) or {}
        return float(m.get("total_score") or m.get("score") or 0.0)

    ranked = sorted(records, key=_total, reverse=True)

    per_source: Dict[str, List[IngestedRecordDict]] = {}
    for r in ranked:
        st = _norm_source(str(r.get("source_type") or ""))
        per_source.setdefault(st, []).append(r)

    picked: List[IngestedRecordDict] = []
    counts: Dict[str, int] = {k: 0 for k in caps}
    # Phase 1: top within each bucket
    for src, cap in caps.items():
        pool = per_source.get(src, [])
        for r in pool:
            if counts.get(src, 0) >= cap:
                break
            if r in picked:
                continue
            picked.append(r)
            counts[src] = counts.get(src, 0) + 1
            if len(picked) >= max_total:
                break
        if len(picked) >= max_total:
            break

    # Phase 2: fill by global score
    if len(picked) < max_total:
        for r in ranked:
            if len(picked) >= max_total:
                break
            if r in picked:
                continue
            st = _norm_source(str(r.get("source_type") or ""))
            if counts.get(st, 0) >= caps.get(st, 99):
                continue
            picked.append(r)
            counts[st] = counts.get(st, 0) + 1

    # Hard overrides: always include top user_input and top risk-tagged if not present
    for r in ranked:
        if str(r.get("source_type")) == "user_input" and r not in picked and len(picked) < max_total:
            picked.insert(0, r)
            break
    for r in ranked:
        raw = (r.get("raw_text") or "").lower()
        if any(k in raw for k in ("critical risk", "data loss", "security breach")) and r not in picked and len(picked) < max_total:
            picked.append(r)

    facts: List[str] = []
    constraints: List[str] = []
    risks: List[str] = []
    unknowns: List[str] = []
    evidence: List[Dict[str, Any]] = []
    source_mix: Dict[str, int] = {}

    for r in picked[:max_total]:
        st = str(r.get("source_type") or "")
        source_mix[st] = source_mix.get(st, 0) + 1
        rid = str(r.get("id") or "")
        raw = (r.get("raw_text") or "")[:900]
        sc = float((rel_map.get(rid) or {}).get("total_score") or (rel_map.get(rid) or {}).get("score") or 0.0)
        if "constraint" in raw.lower() or "task_snapshot" in st:
            constraints.append(f"[{st}|{rid[:8]}] {raw[:320]}")
        elif any(k in raw.lower() for k in ("risk", "danger", "fail", "breach")):
            risks.append(f"[{st}] {raw[:320]}")
        elif "?" in raw[:200]:
            unknowns.append(f"[{st}] {raw[:320]}")
        else:
            facts.append(f"[{st}] {raw[:360]}")
        evidence.append(
            {
                "record_id": rid,
                "snippet": raw[:240],
                "source_type": st,
                "relevance": round(sc, 4),
            }
        )

    for c in contradictions:
        if c.confidence >= float(cfg.get("contradiction_surface_confidence", 0.55) or 0.55):
            unknowns.append(
                f"[contradiction:{c.topic}|conf={c.confidence}] "
                f"A:{c.snippets[0][:140]} … vs B:{c.snippets[1][:140] if len(c.snippets)>1 else ''}"
            )
            risks.append(f"[contradiction] unresolved conflict ids={','.join(c.record_ids)[:80]}")

    lim_f = int(cfg.get("max_facts") or 10)
    lim_c = int(cfg.get("max_constraints") or 8)
    lim_r = int(cfg.get("max_risks") or 8)
    lim_u = int(cfg.get("max_unknowns") or 8)
    lim_e = int(cfg.get("max_evidence") or 16)

    logger.info("[Retrieve] source_mix=%s total=%s", source_mix, len(picked))

    return RetrievedContextBundle(
        top_facts=facts[:lim_f],
        top_constraints=constraints[:lim_c],
        top_risks=risks[:lim_r],
        top_unknowns=unknowns[:lim_u],
        evidence_snippets=evidence[:lim_e],
        contradictions=list(contradictions),
        source_mix=source_mix,
        total_retrieved=len(picked),
    )
