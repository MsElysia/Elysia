# project_guardian/llm/prompted_call.py
"""Prompt-profile wrapper: validate profiles, build bundles, prepend system messages, standardized logs.

This module does not choose providers or orchestrate pipelines — only prompt stack + audit fields.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..prompts.prompt_builder import (
    build_prompt,
    build_prompt_bundle,
    log_legacy_llm_call,
    prepend_system_message,
    validate_prompt_profile,
)

logger = logging.getLogger(__name__)


def flatten_bundle_meta(bundle_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Turn nested prompt registry meta into flat keys for structured logs."""
    meta = bundle_meta or {}
    core = meta.get("core") or {}
    mod = meta.get("module") or {}
    ag = meta.get("agent") or {}
    return {
        "prompt_core_name": str(core.get("name") or ""),
        "prompt_core_version": str(core.get("version") or ""),
        "prompt_module_name": str(mod.get("name") or ""),
        "prompt_module_version": str(mod.get("version") or ""),
        "prompt_agent_name": str(ag.get("name") or "") if isinstance(ag, dict) and ag else "",
        "prompt_agent_version": str(ag.get("version") or "") if isinstance(ag, dict) and ag else "",
    }


def require_prompt_profile(
    module_name: Optional[str],
    agent_name: Optional[str] = None,
    *,
    allow_legacy: bool = False,
    caller: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Enforce explicit prompt profile for LLM entrypoints.

    Returns (module_name, agent_name, legacy_prompt_path).
    When legacy_prompt_path is True, module/agent may be None — caller must not use prepare_* without a bundle.

    If module_name is blank and allow_legacy is False, raises ValueError.
    If blank and allow_legacy is True, logs and returns (None, None, True).
    """
    raw = (module_name or "").strip()
    if not raw:
        if allow_legacy:
            log_legacy_llm_call(
                "blank_module_name",
                caller=caller,
                reason="legacy_prompt_allow_legacy",
            )
            return None, None, True
        raise ValueError(
            "module_name is required for prompt-profile LLM calls (set allow_legacy=True only for documented legacy paths)."
        )
    mod, ag = validate_prompt_profile(module_name=raw, agent_name=agent_name)
    return mod, ag, False


def log_prompted_call(
    *,
    module_name: str,
    agent_name: Optional[str],
    task_type: Optional[str],
    provider: Optional[str],
    model: Optional[str],
    bundle_meta: Optional[Dict[str, Any]],
    prompt_length: Optional[int],
    legacy_prompt_path: bool = False,
) -> None:
    """
    Single structured audit line for prompt-profile LLM usage (no full prompt bodies).
    """
    flat = flatten_bundle_meta(bundle_meta)
    parts = [
        f"module_name={module_name}",
        f"agent_name={agent_name or '-'}",
        f"task_type={task_type or '-'}",
        f"provider={provider or '-'}",
        f"model={model or '-'}",
        f"prompt_core_name={flat['prompt_core_name'] or '-'}",
        f"prompt_core_version={flat['prompt_core_version'] or '-'}",
        f"prompt_module_name={flat['prompt_module_name'] or '-'}",
        f"prompt_module_version={flat['prompt_module_version'] or '-'}",
        f"prompt_agent_name={flat['prompt_agent_name'] or '-'}",
        f"prompt_agent_version={flat['prompt_agent_version'] or '-'}",
        f"prompt_length={prompt_length if prompt_length is not None else '-'}",
        f"legacy_prompt_path={legacy_prompt_path}",
    ]
    logger.info("[PromptStack] %s", " ".join(parts))


def prepare_prompted_bundle(
    *,
    module_name: str,
    agent_name: Optional[str] = None,
    task_text: str = "",
    context: Optional[Dict[str, Any]] = None,
    extra_rules: Optional[List[str]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    caller: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate profile, build prompt bundle, return text + meta + flat logging fields.
    """
    mod, ag, _legacy = require_prompt_profile(module_name, agent_name, caller=caller, allow_legacy=False)
    bundle = build_prompt_bundle(
        mod,
        ag,
        task_text=task_text,
        context=context,
        extra_rules=extra_rules,
        output_schema=output_schema,
    )
    flat = flatten_bundle_meta(bundle.get("meta"))
    return {
        "prompt_text": bundle["prompt_text"],
        "meta": bundle["meta"],
        "logging_fields": flat,
        "module_name": mod,
        "agent_name": ag,
    }


def prepare_prompted_system(
    *,
    module_name: str,
    agent_name: Optional[str] = None,
    task_text: str = "",
    context: Optional[Dict[str, Any]] = None,
    extra_rules: Optional[List[str]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    caller: Optional[str] = None,
) -> Dict[str, Any]:
    """Same as prepare_prompted_bundle but key `system_text` aliases `prompt_text` for system-string APIs."""
    b = prepare_prompted_bundle(
        module_name=module_name,
        agent_name=agent_name,
        task_text=task_text,
        context=context,
        extra_rules=extra_rules,
        output_schema=output_schema,
        caller=caller,
    )
    out = dict(b)
    out["system_text"] = b["prompt_text"]
    return out


def prepare_prompted_messages(
    messages: List[Dict[str, str]],
    *,
    module_name: str,
    agent_name: Optional[str] = None,
    task_text: str = "",
    context: Optional[Dict[str, Any]] = None,
    extra_rules: Optional[List[str]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    caller: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build prompt stack and merge as leading system message(s) for chat APIs.
    Returns messages list + meta + logging_fields.
    """
    prep = prepare_prompted_system(
        module_name=module_name,
        agent_name=agent_name,
        task_text=task_text,
        context=context,
        extra_rules=extra_rules,
        output_schema=output_schema,
        caller=caller,
    )
    merged = prepend_system_message(messages, prep["system_text"])
    return {
        "messages": merged,
        "meta": prep["meta"],
        "logging_fields": prep["logging_fields"],
        "system_text": prep["system_text"],
        "module_name": prep["module_name"],
        "agent_name": prep["agent_name"],
    }
