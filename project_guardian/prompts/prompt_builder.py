# project_guardian/prompts/prompt_builder.py
"""Assemble layered prompts: core + module + agent + task context + optional output contract."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from . import prompt_registry

logger = logging.getLogger(__name__)


def validate_prompt_profile(*, module_name: str, agent_name: Optional[str] = None) -> tuple[str, Optional[str]]:
    """
    Require an explicit prompt module (and optional agent) for LLM entry points.
    Returns stripped module_name and agent_name (None if absent/blank).
    """
    m = (module_name or "").strip()
    if not m:
        raise ValueError(
            "module_name is required: pass a registered prompt module (e.g. 'router', 'planner')."
        )
    a_raw = (agent_name or "").strip()
    return m, a_raw or None

# Soft guardrail: set True to log when legacy callers bypass the builder (opt-in).
LOG_LEGACY_LLM_HINTS = bool(__import__("os").environ.get("ELYSIA_LOG_LEGACY_LLM_PROMPTS", "").strip())

# Invariant: prefer build_prompt / build_prompt_bundle for any new LLM call site; legacy paths may use
# log_legacy_llm_call(). See prompts/DEVELOPER_NOTE.md for migrated vs remaining routes.


def _format_context(context: Optional[Dict[str, Any]]) -> str:
    if not context:
        return ""
    try:
        return json.dumps(context, ensure_ascii=False, indent=0)[:12000]
    except Exception:
        return str(context)[:2000]


def _format_extra_rules(extra_rules: Optional[List[str]]) -> str:
    if not extra_rules:
        return ""
    lines = [str(r).strip() for r in extra_rules if str(r).strip()]
    if not lines:
        return ""
    return "Additional rules:\n" + "\n".join(f"- {x}" for x in lines)


def _format_output_schema(output_schema: Optional[Dict[str, Any]]) -> str:
    if not output_schema:
        return ""
    try:
        body = json.dumps(output_schema, ensure_ascii=False, indent=2)
    except Exception:
        body = str(output_schema)
    return (
        "OUTPUT CONTRACT (host-requested; produce output consistent with this shape when applicable):\n"
        + body[:8000]
    )


def build_prompt(
    module_name: str,
    agent_name: Optional[str] = None,
    task_text: str = "",
    context: Optional[Dict[str, Any]] = None,
    extra_rules: Optional[List[str]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Concatenate: core + module + agent (optional) + task/context + extra rules + output contract.
    """
    parts: List[str] = []
    core_meta, core_txt = prompt_registry.get_core()
    parts.append(core_txt)

    m_meta, m_txt = prompt_registry.get_module(module_name)
    parts.append(m_txt)

    if agent_name:
        _a_meta, a_txt = prompt_registry.get_agent(agent_name)
        parts.append(a_txt)

    tt = (task_text or "").strip()
    if tt:
        parts.append("TASK / INSTRUCTIONS:\n" + tt)

    ctx = _format_context(context)
    if ctx:
        parts.append("CONTEXT (structured):\n" + ctx)

    er = _format_extra_rules(extra_rules)
    if er:
        parts.append(er)

    oc = _format_output_schema(output_schema)
    if oc:
        parts.append(oc)

    return "\n\n".join(p for p in parts if p).strip()


def build_prompt_bundle(
    module_name: str,
    agent_name: Optional[str] = None,
    task_text: str = "",
    context: Optional[Dict[str, Any]] = None,
    extra_rules: Optional[List[str]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return assembled prompt plus metadata for logging and tracing."""
    core_meta, _ = prompt_registry.get_core()
    mod_meta, _ = prompt_registry.get_module(module_name)
    agent_meta: Optional[Dict[str, str]] = None
    if agent_name:
        agent_meta, _ = prompt_registry.get_agent(agent_name)

    text = build_prompt(
        module_name=module_name,
        agent_name=agent_name,
        task_text=task_text,
        context=context,
        extra_rules=extra_rules,
        output_schema=output_schema,
    )
    return {
        "prompt_text": text,
        "meta": {
            "core": dict(core_meta),
            "module": dict(mod_meta),
            "agent": dict(agent_meta) if agent_meta else None,
        },
    }


def log_llm_prompt_usage(
    *,
    module_name: str,
    agent_name: Optional[str],
    task_type: Optional[str],
    provider: Optional[str],
    model: Optional[str],
    bundle_meta: Optional[Dict[str, Any]] = None,
    prompt_length: Optional[int] = None,
) -> None:
    """Log prompt lineage without dumping full bodies. Delegates to llm.prompted_call.log_prompted_call."""
    from ..llm.prompted_call import log_prompted_call

    log_prompted_call(
        module_name=module_name,
        agent_name=agent_name,
        task_type=task_type,
        provider=provider,
        model=model,
        bundle_meta=bundle_meta,
        prompt_length=prompt_length,
        legacy_prompt_path=False,
    )


def log_legacy_llm_call(
    hint: str = "",
    *,
    caller: Optional[str] = None,
    reason: str = "inline_prompt_not_migrated",
) -> None:
    """Mark call sites that bypass the Guardian prompt stack (always one INFO line; optional WARNING if env set)."""
    parts = [f"reason={reason}"]
    if caller:
        parts.append(f"caller={caller}")
    if hint:
        parts.append(f"detail={hint}")
    msg = " ".join(parts)
    logger.info("[PromptStack][legacy] %s", msg)
    if LOG_LEGACY_LLM_HINTS:
        logger.warning("[PromptStack][legacy_verbose] %s", msg)


def prepend_system_message(
    messages: List[Dict[str, str]],
    system_content: str,
) -> List[Dict[str, str]]:
    """Insert a system message at the front when none is present, else prepend after first system merge."""
    if not system_content.strip():
        return list(messages)
    out = list(messages)
    if out and (out[0].get("role") or "").lower() == "system":
        merged = system_content.strip() + "\n\n" + (out[0].get("content") or "").strip()
        out[0] = {"role": "system", "content": merged.strip()}
        return out
    return [{"role": "system", "content": system_content.strip()}] + out
