# project_guardian/context_pipeline/runner.py
"""Ingest → relevance (embeddings/tf-idf) → archive → balanced retrieve → contradictions → local packet → gated online → first-class snapshot.

Paid OpenAI structured reasoning is gated by confidence, contradictions, stagnation, memory pressure
(see context_pipeline.json), and optional maximize_free_tokens / ELYSIA_MAXIMIZE_FREE_TOKENS.
Use ELYSIA_USE_CLOUD_LLM_FIRST=1 to disable that reserve-paid behavior (same rule as
``multi_api_router.pipeline_maximize_free_tokens`` / chat routing).
Default autonomy task names no longer imply paid reasoning every cycle (decide_next substring removed).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .archive_manager import archive_matched_buckets, relevance_decay_multiplier, touch_retrieved_evidence
from .ingestion_normalizer import (
    load_text_file_tail,
    normalize_browser_findings,
    normalize_chat_history_lines,
    normalize_log_tail,
    normalize_memory_entries,
    normalize_task_snapshot,
    normalize_user_input,
    read_chat_export_paths,
)
from .memory_sidecar import project_root
from .models import PromptPacket, ValidationResult
from .prompt_packet_builder import build_local_prompt_packet, retrieval_to_brief, run_online_structured_reasoning
from .relevance_engine import build_relevance_map, extract_contradictions
from .retrieval import balanced_retrieve
from .schemas import IngestedRecordDict
from .structured_response_validator import classify_structured_online_response

logger = logging.getLogger(__name__)


def _pipeline_maximize_free_tokens(cfg: Dict[str, Any]) -> bool:
    """Delegate to multi_api_router so cloud-first / maximize-free stay one definition."""
    from ..multi_api_router import pipeline_maximize_free_tokens

    return pipeline_maximize_free_tokens(cfg)


def _load_pipeline_cfg(decider_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = project_root() / "config" / "context_pipeline.json"
    out: Dict[str, Any] = {}
    if base.is_file():
        try:
            out = json.loads(base.read_text(encoding="utf-8"))
        except Exception:
            pass
    if isinstance(decider_cfg, dict):
        if "use_context_pipeline" in decider_cfg:
            out["enabled"] = bool(decider_cfg.get("use_context_pipeline"))
        if "context_pipeline_run_online_reasoning" in decider_cfg:
            out["run_online_reasoning"] = bool(decider_cfg.get("context_pipeline_run_online_reasoning"))
        for k, v in decider_cfg.items():
            if not isinstance(k, str) or not k.startswith("context_pipeline_json_"):
                continue
            inner = k[len("context_pipeline_json_") :]
            if inner and isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        out.update(parsed)
                except Exception:
                    pass
    return out


def _campaign_corpus() -> str:
    try:
        from ..ranking import load_campaign_corpus_text

        return (load_campaign_corpus_text() or "")[:8000]
    except Exception:
        return ""


def _gather_records(guardian: Any, session_id: str, cfg: Dict[str, Any]) -> List[IngestedRecordDict]:
    recs: List[IngestedRecordDict] = []

    uq = str(getattr(guardian, "_pending_operator_question", None) or "").strip()
    if uq:
        recs.extend(normalize_user_input(uq[:8000], session_id))

    mem = getattr(guardian, "memory", None)
    if mem is not None:
        rows: List[Dict[str, Any]] = []
        try:
            for m in (mem.recall_last(int(cfg.get("memory_recall_limit") or 12)) or []):
                if isinstance(m, dict):
                    rows.append(m)
                else:
                    c = getattr(m, "content", None) or str(m)
                    rows.append({"content": c})
        except Exception:
            pass
        recs.extend(normalize_memory_entries(rows, session_id))

    pdc = getattr(guardian, "_pre_decision_context", None) or {}
    recs.extend(
        normalize_task_snapshot(
            {
                "task_context": (pdc.get("task_context") or "")[:4000],
                "relevant_capabilities": pdc.get("relevant_capabilities") or [],
                "memory_recall_lines": pdc.get("memory_recall_lines") or [],
            },
            session_id,
            "task_pre_decision",
        )
    )
    bf = pdc.get("browser_findings")
    if bf is None:
        bf = getattr(guardian, "_last_browser_findings", None)
    if isinstance(bf, list):
        recs.extend(normalize_browser_findings(bf, session_id))

    if bool(cfg.get("include_log_tail", True)):
        logp = Path(cfg.get("log_path") or (project_root() / "elysia_unified.log"))
        recs.extend(normalize_log_tail(load_text_file_tail(logp), session_id))

    paths = list(cfg.get("chat_export_paths") or [])
    if paths:
        lines = read_chat_export_paths(paths, max_lines_per_file=int(cfg.get("chat_export_max_lines") or 120))
        recs.extend(normalize_chat_history_lines(lines, session_id))

    mon = getattr(guardian, "_last_monitor_snapshot", None)
    if isinstance(mon, dict) and mon:
        recs.extend(normalize_task_snapshot(mon, session_id, "monitor_snapshot"))

    pln = getattr(guardian, "_last_planner_snapshot", None)
    if isinstance(pln, dict) and pln:
        recs.extend(normalize_task_snapshot(pln, session_id, "planner_snapshot"))

    return recs


def _user_directives(guardian: Any) -> str:
    parts = [str(getattr(guardian, "_pending_operator_question", None) or "")]
    pdc = getattr(guardian, "_pre_decision_context", None) or {}
    parts.append(str(pdc.get("task_context") or "")[:2000])
    return " ".join(p for p in parts if p.strip())[:4000]


def should_run_online_reasoning(
    cfg: Dict[str, Any],
    *,
    contradictions: List[Any],
    source_mix: Dict[str, int],
    pipeline_signals: Optional[Dict[str, Any]],
    packet_ok: bool,
    local_confidence: float = 0.0,
) -> Tuple[bool, str]:
    if not packet_ok:
        return False, "no_packet"
    if bool(cfg.get("run_online_reasoning", False)):
        return True, "legacy_run_online_reasoning_flag"
    if not bool(cfg.get("online_reasoning_enabled", False)):
        return False, "online_reasoning_disabled"

    sig = pipeline_signals or {}
    if bool(sig.get("provider_degraded")) and bool(cfg.get("online_skip_when_provider_degraded", True)):
        return False, "provider_degraded"

    ulev = str(sig.get("uncertainty_level") or "").lower()
    stag = int(sig.get("stagnation_count") or 0)
    mem_hi = bool(sig.get("memory_pressure_high"))

    default_task = str(cfg.get("default_task_type") or "autonomy_decide_next").lower()
    sig_task = str(sig.get("task_type") or "").lower().strip()
    active_task = sig_task or default_task
    if "compression" in active_task or "filter" in active_task:
        return False, "local_only_compression_task"

    if mem_hi and bool(cfg.get("online_skip_when_memory_pressure", False)):
        return False, "memory_pressure_remote_unlikely"

    # Reserve paid structured reasoning unless signals justify it (ELYSIA_MAXIMIZE_FREE_TOKENS / cfg).
    if _pipeline_maximize_free_tokens(cfg) and not bool(cfg.get("online_reasoning_force_when_maximize_free", False)):
        conf_lo_mf = float(cfg.get("online_reasoning_confidence_threshold") or 0.62)
        contra_thr_mf = int(cfg.get("online_reasoning_contradiction_threshold") or 1)
        stag_thr_mf = int(cfg.get("online_reasoning_stagnation_threshold") or 4)
        cross_ambiguous = bool(
            len(source_mix) >= 5 and source_mix and min(source_mix.values()) >= 1
        )
        needs_paid = (
            local_confidence < conf_lo_mf
            or len(contradictions) >= contra_thr_mf
            or ulev == "high"
            or stag >= stag_thr_mf
            or cross_ambiguous
        )
        if not needs_paid:
            return False, "maximize_free_reserve_paid_no_strong_signal"

    conf_hi = float(cfg.get("online_reasoning_confidence_ceiling_skip") or 0.92)
    if local_confidence >= conf_hi and bool(cfg.get("online_skip_when_local_confidence_high", True)):
        return False, "local_confidence_already_high"

    conf_lo = float(cfg.get("online_reasoning_confidence_threshold") or 0.62)
    if local_confidence < conf_lo:
        return True, "local_confidence_below_threshold"

    contra_thr = int(cfg.get("online_reasoning_contradiction_threshold") or 1)
    if len(contradictions) >= contra_thr:
        return True, "contradiction_threshold"

    if ulev == "high":
        return True, "uncertainty_high"

    if stag >= int(cfg.get("online_reasoning_stagnation_threshold") or 4):
        return True, "stagnation"

    if len(source_mix) >= 5 and min(source_mix.values()) >= 1:
        return True, "cross_source_ambiguity"

    allow_types = cfg.get("online_reasoning_task_types")
    if isinstance(allow_types, list) and allow_types:
        allowed_norm = [str(x).lower().strip() for x in allow_types if str(x).strip()]
        if any(t == active_task or t in active_task for t in allowed_norm):
            return True, "task_type_allowlist"
        return False, "task_type_not_allowlisted"

    # Do not match "decide_next" here: default_task_type autonomy_decide_next would force paid
    # reasoning on every autonomy cycle. Use online_reasoning_task_types allowlist when you want that.
    if any(
        k in active_task
        for k in ("reasoning", "planning", "synthesis", "high_stakes", "high-stakes")
    ):
        return True, "task_type_reasoning_or_planning"

    return False, "gates_not_met"


def format_planner_injection_fallback(summary: Dict[str, Any], max_chars: int = 900) -> str:
    try:
        blob = json.dumps(summary, ensure_ascii=False, indent=0)[:max_chars]
    except Exception:
        blob = str(summary)[:max_chars]
    return "CONTEXT_PIPELINE_LEGACY_FALLBACK:\n" + blob


def _fallback_prompt_packet(
    *,
    objective: str,
    task_type: str,
    bundle: Any,
) -> Dict[str, Any]:
    """Build a minimal local packet when Ollama packet generation is unavailable."""
    return {
        "task_type": str(task_type or "autonomy_decide_next"),
        "objective": str(objective or "")[:2000],
        "facts": [str(x)[:280] for x in list(getattr(bundle, "top_facts", []) or [])[:8]],
        "constraints": [str(x)[:260] for x in list(getattr(bundle, "top_constraints", []) or [])[:6]],
        "risks": [str(x)[:260] for x in list(getattr(bundle, "top_risks", []) or [])[:6]],
        "unknowns": [str(x)[:260] for x in list(getattr(bundle, "top_unknowns", []) or [])[:6]],
        "evidence": [e for e in list(getattr(bundle, "evidence_snippets", []) or [])[:12] if isinstance(e, dict)],
        "requested_output_schema": "decision_reasoning_confidence",
    }


def _classify_packet_error(err: str) -> str:
    blob = str(err or "").lower()
    if not blob:
        return "none"
    if "timed out" in blob or "timeout" in blob:
        return "timeout"
    if "ollama_unavailable" in blob:
        return "ollama_unavailable"
    if "invalid_packet" in blob:
        return "invalid_packet"
    if "memory_pressure_skip_local_packet" in blob:
        return "memory_pressure_skip"
    return "other"


def run_context_pipeline_for_decider(
    guardian: Any,
    *,
    active_goal: Optional[str],
    session_id: str,
    decider_cfg: Optional[Dict[str, Any]] = None,
    pipeline_signals: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = _load_pipeline_cfg(decider_cfg)
    if not bool(cfg.get("enabled", False)):
        return {"enabled": False}

    t0 = time.perf_counter()
    objective = (active_goal or "")[:2000]
    if not objective.strip():
        objective = "Maintain safe autonomous operation; choose the best next internal action."

    campaign = _campaign_corpus()
    directives = _user_directives(guardian)
    decision_objective = str((pipeline_signals or {}).get("decision_objective") or objective)[:2000]

    records = _gather_records(guardian, session_id, cfg)
    if not records:
        logger.info("[Ingest] no_records session=%s", session_id[:32])
        return {"enabled": True, "empty": True, "planner_injection": "", "context_pipeline_packet": None}

    rel_map, rel_meta = build_relevance_map(
        records,
        objective,
        cfg=cfg,
        campaign_text=campaign,
        user_directives=directives,
        decision_objective=decision_objective,
    )
    for rid, row in list(rel_map.items()):
        mult = relevance_decay_multiplier(rid, cfg)
        if mult != 1.0:
            ts = float(row.get("total_score") or row.get("score") or 0.0)
            ts2 = max(0.0, min(1.0, ts * mult))
            row["total_score"] = round(ts2, 4)
            row["score"] = row["total_score"]

    top_scores = sorted(
        (float(v.get("total_score") or v.get("score") or 0.0) for v in rel_map.values()),
        reverse=True,
    )
    local_confidence = float(top_scores[0]) if top_scores else 0.0

    thr = float(cfg.get("archive_relevance_threshold") or 0.52)
    archive_matched_buckets(records, rel_map, threshold=thr, session_id=session_id, cfg=cfg)

    contradictions = extract_contradictions(records, rel_map)
    bundle = balanced_retrieve(records, rel_map, contradictions, cfg=cfg)
    touch_retrieved_evidence([str(e.get("record_id") or "") for e in bundle.evidence_snippets])

    brief = retrieval_to_brief(
        bundle.top_facts,
        bundle.top_constraints,
        bundle.top_risks,
        bundle.top_unknowns,
        bundle.evidence_snippets,
    )

    model = (cfg.get("local_ollama_model") or None) if isinstance(cfg.get("local_ollama_model"), str) else None
    mem_hi = bool((pipeline_signals or {}).get("memory_pressure_high"))
    if mem_hi and bool(cfg.get("skip_local_packet_under_memory_pressure", True)):
        packet, err = None, "memory_pressure_skip_local_packet"
        logger.info("[PromptPacket] local_skip reason=memory_pressure_high")
    else:
        packet, err = build_local_prompt_packet(
            objective=objective,
            task_type=str(cfg.get("default_task_type") or "autonomy_decide_next"),
            retrieval_brief=brief,
            model=model,
            timeout_sec=float(cfg.get("local_timeout_sec") or 60.0),
        )
    used_packet_fallback = False
    if not packet:
        packet = _fallback_prompt_packet(
            objective=objective,
            task_type=str(cfg.get("default_task_type") or "autonomy_decide_next"),
            bundle=bundle,
        )
        used_packet_fallback = True
        logger.info("[PromptPacket] fallback_built reason=%s", _classify_packet_error(err))

    validation = ValidationResult(normalized={}, decision_safe=False, risk_safe=False)
    structured_raw: Optional[Dict[str, Any]] = None
    structured_safe: Optional[Dict[str, Any]] = None
    online_issues: List[str] = []

    run_on, run_reason = should_run_online_reasoning(
        cfg,
        contradictions=contradictions,
        source_mix=bundle.source_mix,
        pipeline_signals=pipeline_signals,
        packet_ok=bool(packet),
    )
    if run_on and packet:
        logger.info("[PromptPacket] online_reasoning=enabled reason=%s", run_reason)
        structured_raw, online_issues = run_online_structured_reasoning(
            packet,
            model=(cfg.get("online_model") or None),
            timeout_sec=float(cfg.get("online_timeout_sec") or 75.0),
        )
        if structured_raw:
            validation = classify_structured_online_response(
                packet,
                structured_raw,
                min_confidence_for_safe=float(cfg.get("online_claim_min_confidence") or 0.35),
            )
            if validation.decision_safe:
                structured_safe = validation.safe_guidance_dict()
            else:
                structured_safe = None
                logger.info(
                    "[StructuredResponse] gated_off decision_safe=%s risk_safe=%s",
                    validation.decision_safe,
                    validation.risk_safe,
                )
        else:
            logger.info("[PromptPacket] online_reasoning=skipped reason=http_or_validate issues=%s", online_issues[:4])
    else:
        logger.info("[PromptPacket] online_reasoning=skipped reason=%s", run_reason)

    summary = {
        "record_count": len(records),
        "local_confidence": round(local_confidence, 4),
        "relevance_backend": rel_meta.get("semantic_backend"),
        "top_semantic_matches": rel_meta.get("top_semantic_matches") or [],
        "contradictions": [c.to_dict() for c in contradictions],
        "retrieval": bundle.to_dict(),
        "prompt_packet_error": err or None,
        "prompt_packet_status": {
            "ok": bool(packet),
            "fallback_used": used_packet_fallback,
            "error_reason": _classify_packet_error(err),
        },
        "validation": validation.to_dict(),
        "online_reasoning": {"ran": bool(structured_raw), "reason": run_reason if run_on else run_reason},
    }

    injection = ""
    if bool(cfg.get("legacy_planner_injection", True)):
        injection = format_planner_injection_fallback(summary, max_chars=int(cfg.get("legacy_injection_max_chars") or 900))

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info("[DecisionLoop] pipeline_ms=%s records=%s packet=%s", elapsed_ms, len(records), bool(packet))

    pp_dict = packet if isinstance(packet, dict) else None
    try:
        if pp_dict:
            PromptPacket.from_dict(pp_dict)
    except Exception:
        pass

    return {
        "enabled": True,
        "session_id": session_id,
        "record_count": len(records),
        "relevance_map_size": len(rel_map),
        "relevance_meta": rel_meta,
        "retrieval": bundle.to_dict(),
        "prompt_packet": pp_dict,
        "context_pipeline_packet": pp_dict,
        "structured_online": structured_safe,
        "structured_online_raw": structured_raw,
        "context_pipeline_online": structured_safe,
        "context_pipeline_validation": validation.to_dict(),
        "context_pipeline_summary": summary,
        "prompt_packet_error": err or None,
        "structured_online_issues": online_issues,
        "planner_injection": injection,
        "pipeline_ms": elapsed_ms,
    }
