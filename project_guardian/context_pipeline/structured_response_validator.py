# project_guardian/context_pipeline/structured_response_validator.py
"""Validate JSON, classify claims vs evidence, gate decision-loop merges."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .models import ValidationResult
from .schemas import STRUCTURED_ONLINE_RESPONSE_SCHEMA

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.strip()
    if t.startswith("{") and t.endswith("}"):
        return t
    m = re.search(r"\{[\s\S]*\}\s*$", t)
    if m:
        return m.group(0)
    m2 = re.search(r"\{[\s\S]*\}", t)
    return m2.group(0) if m2 else None


def repair_json_candidate(raw: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    notes: List[str] = []
    blob = _extract_json_object(raw)
    if not blob:
        notes.append("no_json_object_found")
        return None, notes
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as e:
        notes.append(f"json_decode_error:{e}")
        return None, notes
    if not isinstance(data, dict):
        notes.append("root_not_object")
        return None, notes
    return data, notes


def _coerce_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x)[:500] for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()[:500]]
    return []


def validate_structured_online_response(data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    issues: List[str] = []
    req = set(STRUCTURED_ONLINE_RESPONSE_SCHEMA.get("required") or [])
    for k in req:
        if k not in data or data.get(k) is None:
            issues.append(f"missing:{k}")

    decision = str(data.get("decision") or "").strip()
    reasoning = str(data.get("reasoning") or "").strip()
    conf = data.get("confidence")
    if not decision:
        issues.append("empty_decision")
    if not reasoning:
        issues.append("empty_reasoning")
    try:
        confidence = float(conf) if conf is not None else 0.5
    except (TypeError, ValueError):
        confidence = 0.5
        issues.append("confidence_coerced")
    confidence = max(0.0, min(1.0, confidence))

    out = {
        "decision": decision[:2000],
        "reasoning": reasoning[:8000],
        "confidence": confidence,
        "missing_info": _coerce_list(data.get("missing_info")),
        "next_steps": _coerce_list(data.get("next_steps")),
        "risks": _coerce_list(data.get("risks")),
    }

    ok = bool(decision) and bool(reasoning)
    if ok:
        logger.info("[StructuredResponse] ok confidence=%.2f decision_len=%s", confidence, len(decision))
    else:
        logger.info("[StructuredResponse] reject issues=%s", issues[:8])
    return ok, out, issues


def _evidence_corpus(packet: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    snippets: List[str] = []
    ids: List[str] = []
    for e in packet.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        sn = str(e.get("snippet") or "").strip().lower()
        if sn:
            snippets.append(sn)
        rid = str(e.get("record_id") or "").strip().lower()
        if rid:
            ids.append(rid)
    facts = [str(f).lower() for f in (packet.get("facts") or []) if str(f).strip()]
    snippets.extend(facts[:20])
    return snippets, ids


def _list_item_class(item: str, snippets: List[str], ids: List[str]) -> str:
    """Classify a bullet/list string for merge safety."""
    s = str(item).strip()
    if len(s) < 6:
        return "skip"
    return _sentence_supported(s, snippets, ids)


def _sentence_supported(sentence: str, snippets: List[str], ids: List[str]) -> str:
    s = sentence.strip()
    if len(s) < 10:
        return "skip"
    low = s.lower()
    if any(rid and rid in low for rid in ids):
        return "supported"
    if any(sn and len(sn) >= 14 and sn in low for sn in snippets):
        return "supported"
    if re.search(r"\b(likely|probably|maybe|perhaps|guess|unclear|i infer|in my opinion)\b", low):
        return "inferred"
    if re.search(r"\b(is always|must be|definitely is|proven that|guaranteed)\b", low):
        return "unsupported"
    return "inferred"


def classify_structured_online_response(
    packet: Dict[str, Any],
    normalized: Dict[str, Any],
    *,
    min_confidence_for_safe: float = 0.35,
) -> ValidationResult:
    """
    Classify claims; set decision_safe / risk_safe so unsupported content cannot steer merges.
    """
    snippets, ids = _evidence_corpus(packet)
    supported: List[str] = []
    inferred: List[str] = []
    unsupported: List[str] = []

    decision = str(normalized.get("decision") or "")
    for part in re.split(r"[.;]\s*", decision):
        if not part.strip():
            continue
        cl = _sentence_supported(part, snippets, ids)
        if cl == "supported":
            supported.append(f"decision:{part[:220]}")
        elif cl == "inferred":
            inferred.append(f"decision:{part[:220]}")
        elif cl == "unsupported":
            unsupported.append(f"decision:{part[:220]}")

    reasoning = str(normalized.get("reasoning") or "")
    for part in re.split(r"[.;\n]\s*", reasoning):
        if len(part.strip()) < 16:
            continue
        cl = _sentence_supported(part, snippets, ids)
        tag = f"reasoning:{part[:240]}"
        if cl == "supported":
            supported.append(tag)
        elif cl == "inferred":
            inferred.append(tag)
        elif cl == "unsupported":
            unsupported.append(tag)

    merge_next: List[str] = []
    merge_miss: List[str] = []
    merge_risks: List[str] = []
    for step in normalized.get("next_steps") or []:
        ss = str(step).strip()
        if not ss:
            continue
        cl = _list_item_class(ss, snippets, ids)
        tag = f"next_step:{ss[:220]}"
        if cl == "supported":
            supported.append(tag)
            merge_next.append(ss[:500])
        elif cl == "inferred":
            inferred.append(tag)
            merge_next.append(f"[inferred] {ss[:480]}")
        elif cl == "unsupported":
            unsupported.append(tag)

    for mi in normalized.get("missing_info") or []:
        ss = str(mi).strip()
        if not ss:
            continue
        cl = _list_item_class(ss, snippets, ids)
        tag = f"missing_info:{ss[:220]}"
        if cl == "supported":
            supported.append(tag)
            merge_miss.append(ss[:500])
        elif cl == "inferred":
            inferred.append(tag)
            merge_miss.append(f"[inferred] {ss[:480]}")
        elif cl == "unsupported":
            unsupported.append(tag)

    for rk in normalized.get("risks") or []:
        rs = str(rk).strip()
        if not rs:
            continue
        cl = _list_item_class(rs, snippets, ids)
        tag = f"risk:{rs[:220]}"
        if cl == "supported":
            supported.append(tag)
            merge_risks.append(rs[:500])
        elif cl == "inferred":
            inferred.append(tag)
            merge_risks.append(f"[inferred] {rs[:480]}")
        elif cl == "unsupported":
            unsupported.append(tag)

    conf = float(normalized.get("confidence") or 0.0)
    decision_unsupported = [u for u in unsupported if u.startswith("decision:")]
    risk_unsupported = [u for u in unsupported if u.startswith("risk:")]
    step_unsupported = [u for u in unsupported if u.startswith("next_step:")]
    miss_unsupported = [u for u in unsupported if u.startswith("missing_info:")]

    decision_safe = (
        len(decision_unsupported) == 0
        and len(step_unsupported) == 0
        and len(miss_unsupported) == 0
        and conf >= min_confidence_for_safe
    )
    risk_safe = len(risk_unsupported) == 0

    vr = ValidationResult(
        supported_claims=supported[:80],
        inferred_claims=inferred[:80],
        unsupported_claims=unsupported[:80],
        decision_safe=decision_safe,
        risk_safe=risk_safe,
        normalized=dict(normalized),
        issues=[],
        mergeable_next_steps=merge_next[:24],
        mergeable_missing_info=merge_miss[:24],
        mergeable_risks=merge_risks[:16],
    )
    _safe_flag = decision_safe and risk_safe
    logger.info(
        "[StructuredResponse] supported=%s inferred=%s unsupported=%s safe=%s decision_safe=%s risk_safe=%s",
        len(supported),
        len(inferred),
        len(unsupported),
        _safe_flag,
        decision_safe,
        risk_safe,
    )
    return vr


def flag_unsupported_claims(packet: Dict[str, Any], response: Dict[str, Any]) -> List[str]:
    ev = packet.get("evidence") or []
    ids = {str((e or {}).get("record_id") or "") for e in ev if isinstance(e, dict)}
    text = (response.get("reasoning") or "") + " " + (response.get("decision") or "")
    flags: List[str] = []
    if "execute_capability" in text.lower() and len(ids) < 1:
        flags.append("capability_claim_without_evidence")
    return flags
