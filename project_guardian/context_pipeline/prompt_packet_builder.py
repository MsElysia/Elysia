# project_guardian/context_pipeline/prompt_packet_builder.py
"""Local Ollama (MistralEngine) builds strict prompt packets; optional online structured reasoning."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from .schemas import PROMPT_PACKET_JSON_SCHEMA, STRUCTURED_ONLINE_RESPONSE_SCHEMA
from .structured_response_validator import repair_json_candidate, validate_structured_online_response

logger = logging.getLogger(__name__)


def retrieval_to_brief(
    top_facts: List[str],
    top_constraints: List[str],
    top_risks: List[str],
    top_unknowns: List[str],
    evidence_snippets: List[Dict[str, Any]],
) -> str:
    return json.dumps(
        {
            "top_facts": top_facts[:12],
            "top_constraints": top_constraints[:12],
            "top_risks": top_risks[:10],
            "top_unknowns": top_unknowns[:10],
            "evidence": evidence_snippets[:16],
        },
        ensure_ascii=False,
        indent=0,
    )[:14000]


def build_local_prompt_packet(
    *,
    objective: str,
    task_type: str,
    retrieval_brief: str,
    model: Optional[str] = None,
    timeout_sec: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Calls local Ollama via MistralEngine._post_ollama with JSON schema format.
    Returns (packet_or_none, error_reason).
    """
    try:
        from ..mistral_engine import MistralEngine

        eng = MistralEngine(model=model)
        if not eng._ensure_ollama().ok:
            try:
                from ..api_usage_meter import record_transport

                record_transport("ollama_prompt_packet", False, detail="ollama_unavailable")
            except Exception:
                pass
            return None, "ollama_unavailable"
        system = (
            "You compress INTERNAL_RETRIEVAL into a compact PROMPT PACKET for a remote LLM. "
            "Return ONLY JSON matching the schema. No markdown. "
            "Do not invent facts; only use retrieval. Keep evidence.snippet <= 240 chars each."
        )
        user = (
            f"OBJECTIVE:\n{objective[:2000]}\n\nTASK_TYPE:\n{task_type}\n\nINTERNAL_RETRIEVAL:\n{retrieval_brief}"
        )
        payload = {
            "model": eng.model,
            "stream": False,
            "format": PROMPT_PACKET_JSON_SCHEMA,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.15},
        }
        if timeout_sec is None:
            try:
                local_timeout = float(os.environ.get("ELYSIA_CONTEXT_PIPELINE_LOCAL_TIMEOUT_SEC", "60"))
            except (TypeError, ValueError):
                local_timeout = 60.0
        else:
            local_timeout = float(timeout_sec)
        local_timeout = max(20.0, min(local_timeout, 180.0))
        data = eng._post_ollama(payload, timeout=eng._ollama_http_timeout(local_timeout))
        content = data.get("message", {}).get("content", "{}")
        if isinstance(content, dict):
            pkt = content
        else:
            pkt = json.loads(content) if isinstance(content, str) else {}
        if not isinstance(pkt, dict) or not pkt.get("objective"):
            return None, "invalid_packet"
        logger.info(
            "[PromptPacket] local_ok facts=%s constraints=%s",
            len(pkt.get("facts") or []),
            len(pkt.get("constraints") or []),
        )
        try:
            from ..api_usage_meter import record_transport

            record_transport("ollama_prompt_packet", True)
        except Exception:
            pass
        return pkt, ""
    except Exception as e:
        logger.info("[PromptPacket] local_fail %s", e)
        try:
            from ..api_usage_meter import record_transport

            record_transport("ollama_prompt_packet", False, detail=str(e)[:200])
        except Exception:
            pass
        return None, str(e)[:200]


def run_online_structured_reasoning(
    packet: Dict[str, Any],
    *,
    model: Optional[str] = None,
    timeout_sec: float = 75.0,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    Optional OpenAI chat.completions with response_format json_object.
    Returns (normalized_response, issues).
    """
    issues: List[str] = []
    try:
        from ..llm.openai_http_chat import post_openai_chat_completion_sync
    except Exception:
        issues.append("httpx_missing")
        return None, issues

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        try:
            from ..api_key_manager import get_api_key_manager

            api_key = (get_api_key_manager().keys.openai or "").strip()
        except Exception:
            pass
    if not api_key:
        issues.append("no_openai_key")
        return None, issues

    try:
        from ..unified_api_budget import can_spend, effective_structured_preflight, enabled as _ub

        if _ub() and not can_spend(effective_structured_preflight()):
            issues.append("unified_budget_exhausted")
            return None, issues
    except Exception:
        pass

    mdl = (model or os.environ.get("ELYSIA_CONTEXT_PIPELINE_ONLINE_MODEL") or "gpt-4o-mini").strip()
    base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    schema_hint = json.dumps(STRUCTURED_ONLINE_RESPONSE_SCHEMA, ensure_ascii=False)[:4000]
    sys = (
        "You are a planning assistant. Return ONLY one JSON object matching the required keys. "
        "Schema hint:\n" + schema_hint
    )
    user = (
        "PROMPT_PACKET:\n"
        + json.dumps(packet, ensure_ascii=False, indent=0)[:10000]
        + "\n\nSynthesize: decision (short imperative), reasoning, confidence 0-1, "
        "missing_info[], next_steps[], risks[]."
    )
    body = {
        "model": mdl,
        "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    t0 = time.perf_counter()
    try:
        data = post_openai_chat_completion_sync(
            base_url=base,
            api_key=api_key,
            body=body,
            timeout_sec=timeout_sec,
        )
        usage = data.get("usage") if isinstance(data, dict) else None
        try:
            from ..api_usage_meter import record_transport

            record_transport("openai_structured", True, usage=usage if isinstance(usage, dict) else None)
        except Exception:
            pass
        txt = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        parsed, rep_notes = repair_json_candidate(txt)
        issues.extend(rep_notes)
        if not parsed:
            return None, issues
        ok, norm, vissues = validate_structured_online_response(parsed)
        issues.extend(vissues)
        if not ok:
            return None, issues
        logger.info(
            "[StructuredResponse] online_ok latency_ms=%.0f model=%s",
            (time.perf_counter() - t0) * 1000,
            mdl,
        )
        return norm, issues
    except Exception as e:
        issues.append(f"http_error:{e}")
        logger.info("[StructuredResponse] online_fail %s", str(e)[:160])
        try:
            from ..api_usage_meter import record_transport

            record_transport("openai_structured", False, detail=str(e)[:200])
        except Exception:
            pass
        return None, issues
