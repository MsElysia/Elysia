# project_guardian/prompt_contracts/integration.py
"""Opt-in prompt-contract validation for BrainPipeline and Think-Decide-Act traces.

No LLM calls. Default ``contract_mode_from_context`` is **off** unless explicitly enabled.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, MutableMapping, Optional, Union

from .registry import get_module_contract, validate_contract_output

__all__ = [
    "add_prompt_contract_result_to_trace",
    "brain_learning_outcome_to_projection",
    "brain_llm_router_choice_to_projection",
    "brain_plan_to_contract_projection",
    "brain_risk_to_contract_projection",
    "brain_tool_route_to_projection",
    "contract_mode_from_context",
    "memory_ranking_run_context_to_projection",
    "resolve_prompt_contract_payload",
    "should_validate_prompt_contracts",
    "validate_module_output_for_trace",
]

_MODES_FALSE = frozenset({"", "off", "false", "0", "no", "none"})


def contract_mode_from_context(context: Optional[Dict[str, Any]]) -> str:
    ctx = context or {}
    if ctx.get("validate_prompt_contracts"):
        mode = str(ctx.get("prompt_contract_mode") or "warn").strip().lower()
        if mode in _MODES_FALSE:
            return "off"
        return mode if mode in {"warn", "strict"} else "warn"
    if ctx.get("dry_validate_planner_contract"):
        return "warn"
    return "off"


def should_validate_prompt_contracts(context: Optional[Dict[str, Any]], module_name: str) -> bool:
    ctx = context or {}
    if ctx.get("dry_validate_planner_contract") and module_name == "planner":
        return True
    if contract_mode_from_context(ctx) == "off":
        return False
    mods = ctx.get("prompt_contract_modules")
    if mods is None:
        return True
    if isinstance(mods, (list, tuple, set, frozenset)):
        return module_name in set(str(x) for x in mods)
    return False


def _strict_may_block(context: Optional[Dict[str, Any]]) -> bool:
    ctx = context or {}
    return contract_mode_from_context(ctx) == "strict" and bool(ctx.get("dry_run"))


def validate_module_output_for_trace(
    module_name: str,
    output: Union[str, Dict[str, Any], None],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    mode = contract_mode_from_context(context or {})
    errors: List[str] = []
    warnings: List[str] = []
    contract_id = ""
    valid = True
    try:
        contract_id = get_module_contract(module_name).contract_id
    except KeyError:
        return {
            "module_name": module_name,
            "contract_id": "",
            "valid": False,
            "errors": [f"unknown_module:{module_name}"],
            "warnings": [],
            "mode": mode,
            "blocked": False,
        }

    if output is None:
        warnings.append("skipped:null_output")
    else:
        ok, errs = validate_contract_output(module_name, output)
        valid = bool(ok)
        errors = list(errs)
        warnings.extend(errs)

    blocked = (not valid) and _strict_may_block(context)
    return {
        "module_name": module_name,
        "contract_id": contract_id,
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "mode": mode,
        "blocked": blocked,
    }


def add_prompt_contract_result_to_trace(
    trace_or_bucket: Any,
    module_name: str,
    result: Dict[str, Any],
) -> None:
    if hasattr(trace_or_bucket, "run_context"):
        bucket = trace_or_bucket.run_context.setdefault("prompt_contract_validation", {})
    elif isinstance(trace_or_bucket, MutableMapping):
        bucket = trace_or_bucket.setdefault("prompt_contract_validation", {})
    else:
        raise TypeError("trace_or_bucket must provide run_context or be a mutable mapping")
    bucket[module_name] = result


def resolve_prompt_contract_payload(
    context: Optional[Dict[str, Any]],
    module_name: str,
    default_factory: Callable[[], Any],
) -> Union[str, Dict[str, Any], None]:
    ctx = context or {}
    overrides = ctx.get("prompt_contract_overrides") or {}
    if module_name in overrides:
        return overrides[module_name]
    legacy = ctx.get("prompt_contract_validation_outputs") or ctx.get("prompt_contract_output_overrides")
    if isinstance(legacy, dict):
        aliases_map = {
            "think_decide_act_thinker": ("think_decide_act_thinker", "tda_thinker", "thinker", "think"),
            "think_decide_act_proposer": ("think_decide_act_proposer", "tda_proposer", "proposer", "propose"),
        }
        check_keys = (module_name,) + aliases_map.get(module_name, ())
        for key in check_keys:
            if key in legacy:
                return legacy[key]
    if module_name == "planner" and ctx.get("dry_validate_planner_contract"):
        sample = ctx.get("dry_validate_planner_contract_sample")
        if isinstance(sample, (str, dict)):
            return sample
    return default_factory()


def brain_plan_to_contract_projection(plan: Any) -> Dict[str, Any]:
    steps_out: List[Dict[str, Any]] = []
    for step in getattr(plan, "steps", None) or []:
        desc = str(getattr(step, "description", "") or "")
        row: Dict[str, Any] = {"description": desc}
        hint = getattr(step, "capability_hint", None)
        if hint:
            row["capability_hint"] = str(hint)
        steps_out.append(row)
    goal = str(getattr(plan, "goal_summary", "") or "")
    return {
        "goal": goal,
        "steps": steps_out,
        "constraints": [],
        "risk_level": "low",
        "reason_summary": goal[:400],
        "confidence": 0.72,
    }


def brain_llm_router_choice_to_projection(backend: str, reason: str) -> Dict[str, Any]:
    return {
        "backend": str(backend or ""),
        "reason_summary": str(reason or "")[:400],
        "confidence": 0.68,
    }


def brain_tool_route_to_projection(route: Any) -> Dict[str, Any]:
    extras = getattr(route, "extras", None) or {}
    conf = extras.get("confidence")
    try:
        confidence = float(conf) if conf is not None else 0.71
    except (TypeError, ValueError):
        confidence = 0.71
    rl = str(extras.get("risk_level") or "low").lower().strip()
    if rl not in {"low", "medium", "high", "blocked"}:
        rl = "low"
    return {
        "primary": str(getattr(route, "primary", "") or ""),
        "selected": str(getattr(route, "selected", "") or ""),
        "reason_summary": str(getattr(route, "reason", "") or "")[:400],
        "confidence": confidence,
        "risk_level": rl,
    }


def brain_risk_to_contract_projection(risk: Any) -> Dict[str, Any]:
    details_src = getattr(risk, "details", None) or {}
    details: Dict[str, Any] = {}
    if isinstance(details_src, dict):
        for k, v in details_src.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                details[str(k)[:120]] = v
    conf = details.get("confidence")
    try:
        confidence = float(conf) if conf is not None else 0.65
    except (TypeError, ValueError):
        confidence = 0.65
    lvl = getattr(risk, "level", None)
    level_str = str(getattr(lvl, "value", lvl) or "")
    return {
        "level": level_str,
        "reason_summary": str(getattr(risk, "reason", "") or "")[:400],
        "confidence": confidence,
        "details": details,
    }


def brain_learning_outcome_to_projection(outcome: Any) -> Dict[str, Any]:
    hints = list(getattr(outcome, "improvement_hints", None) or [])
    lesson = str(getattr(outcome, "lesson", "") or "")
    return {
        "improvement_hints": hints,
        "confidence": 0.66,
        "reason_summary": lesson[:400],
        "risk_level": "low",
    }


def memory_ranking_run_context_to_projection(memory_ranking: Dict[str, Any]) -> Dict[str, Any]:
    ids = list(memory_ranking.get("top_ids") or [])
    scores_raw = list(memory_ranking.get("top_scores") or [])
    scores: List[Dict[str, Any]] = []
    for i, mid in enumerate(ids):
        sc = scores_raw[i] if i < len(scores_raw) else None
        row: Dict[str, Any] = {"memory_id": str(mid)}
        if sc is not None:
            row["score"] = sc
        scores.append(row)
    return {
        "scores": scores,
        "reason_summary": "memory_ranking_pipeline",
        "confidence": 0.6,
    }
