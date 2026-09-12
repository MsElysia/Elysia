from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .prompts import (
    adversarial_ai_prompts,
    autonomy_prompts,
    command_executor_prompts,
    decision_gate_prompts,
    external_research_prompts,
    implementer_prompts,
    memory_prompts,
    mutation_engine_prompts,
    parallel_processing_prompts,
    self_improvement_prompts,
    sequential_processing_prompts,
    social_intelligence_prompts,
    tool_registry_prompts,
)
from .memory_condense_helpers import strip_json_fences
from .prompt_evolution import log_prompt_performance

logger = logging.getLogger(__name__)

ALLOWED_ACTION_TYPES = {
    "NO_ACTION",
    "CALL_TOOL",
    "ASK_USER",
    "STORE_MEMORY",
    "RETRIEVE_MEMORY",
    "RUN_ANALYSIS",
    "PROPOSE_CODE_CHANGE",
    "ESCALATE_TO_HUMAN",
}

RISKY_ACTION_TYPES = {"CALL_TOOL", "PROPOSE_CODE_CHANGE"}
HUMAN_APPROVAL_TARGET_HINTS = ("file", "fs", "network", "credential", "account", "shell", "git")

_SOURCES = (
    memory_prompts,
    tool_registry_prompts,
    autonomy_prompts,
    social_intelligence_prompts,
    self_improvement_prompts,
    mutation_engine_prompts,
    adversarial_ai_prompts,
    external_research_prompts,
    implementer_prompts,
    command_executor_prompts,
    parallel_processing_prompts,
    sequential_processing_prompts,
    decision_gate_prompts,
)


def _build_registry() -> Dict[str, Dict[str, Dict[str, Any]]]:
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for src in _SOURCES:
        block = getattr(src, "PROMPT_PROFILES", {})
        if not isinstance(block, dict):
            continue
        for _, profile in block.items():
            if not isinstance(profile, dict):
                continue
            mod = str(profile.get("module_name") or "").strip()
            fn = str(profile.get("function_name") or "").strip()
            if not mod or not fn:
                continue
            out.setdefault(mod, {})[fn] = deepcopy(profile)
    return out


_PROMPT_REGISTRY = _build_registry()


def get_module_prompt_profile(
    module_name: str,
    function_name: str | None = None,
    mode: str | None = None,
) -> dict:
    mod = (module_name or "").strip()
    if mod not in _PROMPT_REGISTRY:
        raise KeyError(f"Unknown module prompt '{module_name}'.")
    fns = _PROMPT_REGISTRY[mod]
    if function_name:
        fn = (function_name or "").strip()
        if fn not in fns:
            raise KeyError(f"Unknown function prompt '{mod}.{fn}'.")
        prof = deepcopy(fns[fn])
    else:
        # deterministic fallback to first function profile
        fn = sorted(fns.keys())[0]
        prof = deepcopy(fns[fn])
    if mode is not None:
        prof["mode"] = mode
    return prof


def parse_structured_role(structured_role: str | None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    raw = (structured_role or "").strip()
    if not raw:
        return None, None, None
    for sep in (":", "/", "|"):
        if sep in raw:
            parts = [p.strip() for p in raw.split(sep)]
            break
    else:
        parts = [raw]
    module_name = parts[0] if parts else None
    function_name = parts[1] if len(parts) > 1 and parts[1] else None
    mode = parts[2] if len(parts) > 2 and parts[2] else None
    return module_name, function_name, mode


def structured_messages_for_llm_call(
    base_messages: List[Dict[str, str]],
    prompt_extra: Optional[Dict[str, Any]],
    structured_role: str,
) -> Tuple[List[Dict[str, str]], Tuple[Optional[str], Optional[str], Optional[str]]]:
    """
    Same structured task packet shape as :func:`unified_chat_completion` when ``structured_role`` is set.
    Returns (messages, (module, function, mode)) for downstream validation.
    """
    pe = prompt_extra or {}
    s_mod, s_fn, s_mode = parse_structured_role(structured_role)
    if not s_mod:
        return list(base_messages), (None, None, None)
    user_text = ""
    for m in reversed(base_messages):
        if (m.get("role") or "").lower() == "user":
            user_text = str(m.get("content") or "")[:8000]
            break
    task_outer = {
        "task_id": pe.get("task_id") or f"task_{int(time.time())}",
        "task": pe.get("task") if isinstance(pe.get("task"), dict) else {"user_text": user_text},
        "context": pe.get("context") if isinstance(pe, dict) else None,
    }
    msgs = build_module_llm_messages(
        s_mod,
        s_fn,
        s_mode,
        task=task_outer,
        memory=pe.get("memory") if isinstance(pe, dict) else None,
        tools=pe.get("tools") if isinstance(pe, dict) else None,
        prior_outputs=pe.get("prior_outputs") if isinstance(pe, dict) else None,
    )
    return msgs, (s_mod, s_fn, s_mode)


def build_module_llm_messages(
    module_name: str,
    function_name: str | None,
    mode: str | None,
    task: dict,
    memory: dict | list | None = None,
    tools: list | None = None,
    prior_outputs: list | None = None,
) -> list[dict]:
    profile = get_module_prompt_profile(module_name, function_name, mode)
    output_schema = profile.get("output_schema") or {}
    behavioral = profile.get("behavioral_instructions") or []
    allowed = profile.get("allowed_command_types") or []
    kind = str(profile.get("structured_output_kind") or "envelope")
    system_lines = [
        f"Role: {profile.get('llm_role')}",
        f"Purpose: {profile.get('purpose')}",
        "You are a bounded processing unit. Return JSON only.",
        f"Reasoning style: {profile.get('reasoning_style')}",
        "Behavioral instructions:",
    ] + [f"- {x}" for x in behavioral]
    if kind == "memory_condense_array":
        system_lines += [
            "Output format: respond with a single JSON array only (no markdown fences, no surrounding object).",
            "Each array element must be an object matching:",
            json.dumps(output_schema, ensure_ascii=False),
        ]
    elif kind == "plain_object_keys":
        rules = profile.get("validation_rules") or {}
        req = list(rules.get("required_top_level_keys") or [])
        system_lines += [
            "Output format: a single JSON object only (no markdown code fences, no commentary).",
            "Required top-level keys: " + ", ".join(req),
        ]
        if output_schema:
            system_lines.append(
                "Shape hint: " + json.dumps(output_schema, ensure_ascii=False)[:3600],
            )
    else:
        system_lines += [
            "Allowed command types: " + ", ".join(str(x) for x in allowed),
            "Output must match this envelope schema shape:",
            json.dumps(output_schema, ensure_ascii=False),
        ]
    task_packet = {
        "task": task or {},
        "profile": {
            "prompt_id": profile.get("prompt_id"),
            "module_name": profile.get("module_name"),
            "function_name": profile.get("function_name"),
            "mode": profile.get("mode"),
            "version": profile.get("version"),
        },
        "memory": memory,
        "tools": tools or [],
        "prior_outputs": prior_outputs or [],
    }
    return [
        {"role": "system", "content": "\n".join(system_lines)},
        {"role": "user", "content": json.dumps(task_packet, ensure_ascii=False)},
    ]


def structured_reply_text(envelope: Dict[str, Any]) -> str:
    """Return wire-format reply for downstream parsers (envelope JSON or legacy normalized body)."""
    wk = str(envelope.get("structured_wire_reply_key") or "").strip()
    if wk:
        data = envelope.get("data")
        if isinstance(data, dict) and wk in data:
            val = data.get(wk)
            if isinstance(val, str):
                return val
            if isinstance(val, (list, dict)):
                return json.dumps(val, ensure_ascii=False)
    if envelope.get("normalized_text"):
        return str(envelope["normalized_text"])
    return json.dumps(envelope, ensure_ascii=False)


def _extract_json_object_blob(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    match = re.search(r"\{[\s\S]*\}", raw)
    return match.group(0) if match else ""


def _log_perf_line(profile: Dict[str, Any], env: Dict[str, Any], response_text: str, started: float) -> None:
    text = response_text or ""
    log_prompt_performance(
        {
            "prompt_id": profile.get("prompt_id"),
            "prompt_version": profile.get("version"),
            "module_name": profile.get("module_name"),
            "function_name": profile.get("function_name"),
            "task_id": env.get("task_id"),
            "llm_provider": "unknown",
            "llm_model": "unknown",
            "input_hash": hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:24],
            "output_valid_json": True,
            "output_schema_passed": bool(env.get("valid")),
            "task_success": bool(env.get("valid")),
            "retry_count": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "errors": env.get("errors") or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def _validate_memory_condense_array(
    profile: Dict[str, Any],
    module_name: str,
    function_name: str | None,
    mode: str | None,
    response_text: str,
    started: float,
) -> Dict[str, Any]:
    out = _default_envelope(module_name, function_name, mode)
    out["structured_output_kind"] = "memory_condense_array"
    text = strip_json_fences((response_text or "").strip())
    try:
        payload = json.loads(text)
    except Exception as e:
        out["errors"] = [f"invalid_json:{e}"]
        return out

    forbidden = [str(x) for x in profile.get("forbidden_outputs") or [] if str(x)]
    lower = text.lower()
    hits = [x for x in forbidden if x.lower() in lower]
    if hits:
        out["errors"] = [f"forbidden_output:{h}" for h in hits[:4]]
        return out

    if not isinstance(payload, list):
        out["errors"] = ["invalid_schema:expected_json_array"]
        return out

    norm: List[Dict[str, Any]] = []
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            out["errors"] = [f"invalid_schema:item_{i}_not_object"]
            return out
        if "thought" not in item:
            out["errors"] = [f"missing_required:thought@item_{i}"]
            return out
        cat = item.get("category", "consensus")
        try:
            pri = float(item.get("priority", 0.5))
        except (TypeError, ValueError):
            pri = 0.5
        pri = max(0.0, min(1.0, pri))
        norm.append(
            {
                "thought": str(item.get("thought") or "")[:4000],
                "category": str(cat)[:200],
                "priority": pri,
            }
        )

    normalized = json.dumps(norm, ensure_ascii=False)
    out["valid"] = True
    out["task_id"] = str(uuid.uuid4())
    out["result_type"] = "memory_condense"
    out["summary"] = f"condensed {len(norm)} memory rows"
    out["data"] = {"items": norm}
    out["normalized_text"] = normalized
    out["recommended_action"] = {"type": "STORE_MEMORY", "target": None, "arguments": {}, "needs_human_approval": False}
    _log_perf_line(profile, out, response_text, started)
    return out


def _validate_plain_object_keys(
    profile: Dict[str, Any],
    module_name: str,
    function_name: str | None,
    mode: str | None,
    response_text: str,
    started: float,
) -> Dict[str, Any]:
    out = _default_envelope(module_name, function_name, mode)
    out["structured_output_kind"] = "plain_object_keys"
    rules = profile.get("validation_rules") or {}
    required_keys = list(rules.get("required_top_level_keys") or [])
    list_keys = set(str(x) for x in (rules.get("list_keys") or []))

    text = strip_json_fences((response_text or "").strip())
    payload: Any = None
    try:
        payload = json.loads(text)
    except Exception:
        blob2 = _extract_json_object_blob(text)
        if not blob2:
            out["errors"] = ["invalid_json:no_json_object"]
            return out
        try:
            payload = json.loads(blob2)
        except Exception as e:
            out["errors"] = [f"invalid_json:{e}"]
            return out
    if not isinstance(payload, dict):
        out["errors"] = ["invalid_schema:root_not_object"]
        return out

    forb = [str(x) for x in profile.get("forbidden_outputs") or [] if str(x)]
    low = json.dumps(payload, ensure_ascii=False).lower()
    hits = [x for x in forb if x.lower() in low or x.lower() in (response_text or "").lower()]
    if hits:
        out["errors"] = [f"forbidden_output:{h}" for h in hits[:4]]
        return out

    missing = [k for k in required_keys if k not in payload]
    if missing:
        out["errors"] = [f"missing_required:{','.join(missing)}"]
        return out

    for lk in list_keys:
        val = payload.get(lk)
        if val is None:
            continue
        if not isinstance(val, list):
            out["errors"] = [f"must_be_list:{lk}"]
            return out

    normalized = json.dumps(payload, ensure_ascii=False)
    out["valid"] = True
    out["task_id"] = str(uuid.uuid4())
    out["result_type"] = profile.get("function_name") or "structured_object"
    out["summary"] = "plain_object_ok"
    out["data"] = payload
    out["normalized_text"] = normalized
    wk = str(profile.get("structured_wire_reply_key") or "").strip()
    if wk:
        out["structured_wire_reply_key"] = wk
    out["recommended_action"] = {"type": "NO_ACTION", "target": None, "arguments": {}, "needs_human_approval": False}
    _log_perf_line(profile, out, response_text, started)
    return out


def _default_envelope(module_name: str, function_name: str | None, mode: str | None, task_id: str | None = None) -> Dict[str, Any]:
    return {
        "valid": False,
        "module": module_name,
        "function": function_name or "",
        "mode": mode or "",
        "task_id": task_id or str(uuid.uuid4()),
        "confidence": 0.0,
        "result_type": "error",
        "summary": "",
        "data": {},
        "recommended_action": {"type": "NO_ACTION", "target": None, "arguments": {}, "needs_human_approval": False},
        "risks": [],
        "missing_information": [],
        "errors": [],
    }


def validate_module_llm_output(
    module_name: str,
    function_name: str | None,
    mode: str | None,
    response_text: str,
) -> dict:
    profile = get_module_prompt_profile(module_name, function_name, mode)
    started = time.perf_counter()
    kind = str(profile.get("structured_output_kind") or "envelope")
    if kind == "memory_condense_array":
        return _validate_memory_condense_array(profile, module_name, function_name, mode, response_text, started)
    if kind == "plain_object_keys":
        return _validate_plain_object_keys(profile, module_name, function_name, mode, response_text, started)

    out = _default_envelope(module_name, function_name, mode)
    text = (response_text or "").strip()
    try:
        payload = json.loads(text)
    except Exception as e:
        out["errors"] = [f"invalid_json:{e}"]
        return out
    if not isinstance(payload, dict):
        out["errors"] = ["invalid_schema:root_not_object"]
        return out

    forbidden = [str(x) for x in profile.get("forbidden_outputs") or [] if str(x)]
    lower = text.lower()
    hits = [x for x in forbidden if x.lower() in lower]
    if hits:
        out["errors"] = [f"forbidden_output:{h}" for h in hits[:4]]
        return out

    required = ("task_id", "result_type", "summary", "data", "recommended_action")
    missing = [k for k in required if k not in payload]
    if missing:
        out["errors"] = [f"missing_required:{','.join(missing)}"]
        return out

    ra = payload.get("recommended_action")
    if not isinstance(ra, dict):
        out["errors"] = ["invalid_schema:recommended_action_not_object"]
        return out

    action_type = str(ra.get("type") or "").strip().upper()
    if action_type not in ALLOWED_ACTION_TYPES:
        out["errors"] = [f"unknown_command_type:{action_type}"]
        return out

    allowed_for_profile = {str(x).upper() for x in (profile.get("allowed_command_types") or [])}
    if allowed_for_profile and action_type not in allowed_for_profile:
        out["errors"] = [f"command_type_not_allowed_for_profile:{action_type}"]
        return out

    env = _default_envelope(module_name, function_name, mode, task_id=str(payload.get("task_id") or ""))
    env["valid"] = True
    env["result_type"] = str(payload.get("result_type") or "analysis")
    env["summary"] = str(payload.get("summary") or "")[:4000]
    env["data"] = payload.get("data") if isinstance(payload.get("data"), dict) else {"value": payload.get("data")}
    env["confidence"] = float(payload.get("confidence") or 0.0)
    env["risks"] = payload.get("risks") if isinstance(payload.get("risks"), list) else []
    env["missing_information"] = payload.get("missing_information") if isinstance(payload.get("missing_information"), list) else []
    env["errors"] = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    env["recommended_action"] = {
        "type": action_type,
        "target": ra.get("target"),
        "arguments": ra.get("arguments") if isinstance(ra.get("arguments"), dict) else {},
        "needs_human_approval": False,
    }
    target_lower = str(env["recommended_action"].get("target") or "").lower()
    if action_type in RISKY_ACTION_TYPES or any(h in target_lower for h in HUMAN_APPROVAL_TARGET_HINTS):
        env["recommended_action"]["needs_human_approval"] = True

    _log_perf_line(profile, env, text, started)
    return env


def run_parallel_llm_analysis(task, llm_clients, context, memory):
    results = []
    for i, c in enumerate(llm_clients or []):
        fn = getattr(c, "complete", None) or c
        raw = fn(task=task, context=context, memory=memory)
        parsed = validate_module_llm_output("parallel_processing", "independent_analysis", None, raw)
        results.append({"index": i, "raw": raw, "parsed": parsed})
    valids = [r["parsed"] for r in results if r["parsed"].get("valid")]
    summaries = [str(v.get("summary") or "") for v in valids]
    uniq = {s.strip().lower() for s in summaries if s.strip()}
    return {
        "results": results,
        "agreement_ratio": (0.0 if not summaries else round((len(summaries) - max(0, len(uniq) - 1)) / len(summaries), 3)),
        "disagreement_detected": len(uniq) > 1,
        "consensus_summary": summaries[0] if summaries else "",
    }


def run_sequential_llm_chain(task, chain_roles, llm_clients, context, memory):
    history = []
    current = {"task": task}
    for idx, role in enumerate(chain_roles or []):
        client = llm_clients[idx]
        fn = getattr(client, "complete", None) or client
        raw = fn(task=current, context=context, memory=memory, role=role)
        parsed = validate_module_llm_output("sequential_processing", "stage_by_stage_transformation", role, raw)
        history.append({"role": role, "raw": raw, "parsed": parsed})
        if not parsed.get("valid"):
            return {"success": False, "stopped_at": idx, "history": history, "error": parsed.get("errors")}
        current = parsed.get("data") or {}
    return {"success": True, "history": history, "final": current}


def run_decision_gate(task, proposed_action, llm_client, context, memory):
    fn = getattr(llm_client, "complete", None) or llm_client
    raw = fn(task=task, proposed_action=proposed_action, context=context, memory=memory)
    parsed = validate_module_llm_output("decision_gate", "approve_reject_defer", None, raw)
    if not parsed.get("valid"):
        return {"decision": "needs_human_review", "reason": parsed.get("errors"), "parsed": parsed}
    summary = str(parsed.get("summary") or "").lower()
    if "reject" in summary:
        return {"decision": "rejected", "parsed": parsed}
    if parsed.get("recommended_action", {}).get("needs_human_approval"):
        return {"decision": "needs_human_review", "parsed": parsed}
    return {"decision": "approved", "parsed": parsed}
