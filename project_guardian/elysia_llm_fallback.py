# project_guardian/elysia_llm_fallback.py
"""
Cloud-only LLM completion when unified_chat_completion is disabled or raises.

Uses the same Guardian prompt stack + task line as unified_llm_route / MistralEngine.complete_chat.
Does not perform provider routing (caller passes cloud_preferred).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .llm.prompted_call import log_prompted_call, prepare_prompted_messages, require_prompt_profile
from .unified_llm_route import CLOUD_MODEL_LOG_OPENAI, UNIFIED_CHAT_PROMPT_TASK_TEXT

DEFAULT_MODULE_NAME = "planner"
DEFAULT_AGENT_NAME: Optional[str] = "orchestrator"


def elysia_cloud_fallback_completion(
    messages: List[Dict[str, Any]],
    max_tokens: int,
    *,
    cloud_preferred: Callable[[List[Dict[str, Any]], int], Tuple[str, str]],
    caller: str,
    module_name: str = DEFAULT_MODULE_NAME,
    agent_name: Optional[str] = DEFAULT_AGENT_NAME,
    prompt_extra: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Prepend Guardian prompt stack, log once, then run OpenAI→OpenRouter preferred transport.

    Optional ``prompt_extra`` matches :func:`unified_chat_completion` (task_text, context, output_schema, task_type).
    """
    mod, ag, _ = require_prompt_profile(
        module_name,
        agent_name,
        caller=caller,
        allow_legacy=False,
    )
    pe = prompt_extra or {}
    task_text = pe.get("task_text")
    if task_text is None:
        task_text = UNIFIED_CHAT_PROMPT_TASK_TEXT
    else:
        task_text = str(task_text)
    prep = prepare_prompted_messages(
        list(messages),
        module_name=mod,
        agent_name=ag,
        task_text=task_text,
        context=pe.get("context"),
        output_schema=pe.get("output_schema"),
        caller=caller,
    )
    log_task_type = str(pe.get("task_type") or "elysia_cloud_fallback")
    log_prompted_call(
        module_name=mod,
        agent_name=ag,
        task_type=log_task_type,
        provider="cloud_preferred",
        model=CLOUD_MODEL_LOG_OPENAI,
        bundle_meta=prep["meta"],
        prompt_length=len(prep["system_text"]),
        legacy_prompt_path=False,
    )
    return cloud_preferred(prep["messages"], max_tokens)
