# project_guardian/brain/runtime.py
"""Single production-style entry for BrainPipeline behind config (no autonomy wiring)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

from .config import BrainPipelineConfig, get_brain_pipeline_config
from .contracts import BrainPipelineTrace, Observation
from .live_execution_runtime import apply_live_execution_guard_to_context

BypassResult = Dict[str, Any]
RunResult = Tuple[BrainPipelineTrace, Dict[str, Any]]


def run_brain_pipeline_for_operator_event(
    input_event: Union[str, Dict[str, Any]],
    *,
    guardian: Any = None,
    context: Optional[Dict[str, Any]] = None,
    source_entrypoint: str = "operator_chat",
    config: Optional[BrainPipelineConfig] = None,
) -> Union[BypassResult, RunResult]:
    """
    Run BrainPipeline when config allows this entrypoint.

    Returns ``{"bypass": True, ...}`` when disabled or entrypoint off.
    Otherwise returns ``(trace, dashboard)`` from ``BrainPipeline.run``.
    """
    cfg = config or get_brain_pipeline_config()
    if isinstance(input_event, str):
        text = input_event.strip()
        src = "operator"
    elif isinstance(input_event, dict):
        text = str(
            input_event.get("text")
            or input_event.get("message")
            or input_event.get("raw_input")
            or ""
        ).strip()
        src = str(input_event.get("source") or input_event.get("event_source") or "operator")[:120]
    else:
        text = str(input_event).strip()
        src = "operator"

    if not cfg.enabled:
        merge = dict(context or {})
        merge.setdefault("dry_run", bool(cfg.dry_run))
        merge["source_entrypoint"] = source_entrypoint
        merge, guard_meta = apply_live_execution_guard_to_context(
            merge,
            cfg=cfg,
            source_entrypoint=source_entrypoint,
            observation_text=text,
        )
        out: BypassResult = {"bypass": True, "reason": "brain_pipeline_disabled"}
        if guard_meta.get("requested_live_execution"):
            out["live_execution_guard"] = guard_meta
        return out

    if not cfg.entrypoint_enabled(source_entrypoint):
        merge = dict(context or {})
        merge.setdefault("dry_run", bool(cfg.dry_run))
        merge["source_entrypoint"] = source_entrypoint
        merge, guard_meta = apply_live_execution_guard_to_context(
            merge,
            cfg=cfg,
            source_entrypoint=source_entrypoint,
            observation_text=text,
        )
        out = {
            "bypass": True,
            "reason": "entrypoint_disabled",
            "entrypoint": source_entrypoint,
        }
        if guard_meta.get("requested_live_execution"):
            out["live_execution_guard"] = guard_meta
        return out

    meta: Dict[str, Any] = {"source_entrypoint": source_entrypoint}
    if isinstance(input_event, dict) and isinstance(input_event.get("metadata"), dict):
        meta = {**meta, **dict(input_event["metadata"])}

    observation = Observation(src, text[:8000], metadata=meta)

    merge: Dict[str, Any] = dict(context or {})
    merge["use_think_decide_act"] = bool(cfg.use_think_decide_act)
    if "dry_run" not in merge:
        merge["dry_run"] = bool(cfg.dry_run)
    merge["persist_trace"] = bool(cfg.persist_trace)
    merge["trace_path"] = str(cfg.trace_path)
    merge["source_entrypoint"] = source_entrypoint

    conversation_id = (
        merge.get("conversation_id")
        or meta.get("conversation_id")
        or (input_event.get("conversation_id") if isinstance(input_event, dict) else None)
    )

    merge, _guard_meta = apply_live_execution_guard_to_context(
        merge,
        cfg=cfg,
        source_entrypoint=source_entrypoint,
        observation_text=text,
        conversation_id=str(conversation_id) if conversation_id else None,
    )
    if isinstance(_guard_meta, dict):
        observation.metadata["live_execution_guard"] = _guard_meta

    try:
        from project_guardian.prompt_contracts.controls import apply_prompt_contract_config_to_context

        merge, _pc_warn = apply_prompt_contract_config_to_context(
            merge,
            source_entrypoint=source_entrypoint,
            brain_cfg=cfg,
        )
        if _pc_warn:
            merge.setdefault("prompt_contract_config_warnings", _pc_warn)
    except Exception as exc:
        logger.debug("prompt contract context merge skipped: %s", exc)

    from .pipeline import BrainPipeline

    pipe = BrainPipeline(guardian=guardian)
    trace, dashboard = pipe.run(observation, context=merge)

    guard_meta = merge.get("live_execution_guard")
    if isinstance(guard_meta, dict):
        dashboard = dict(dashboard or {})
        dashboard["live_execution_guard"] = guard_meta
        run_context = getattr(trace, "run_context", None)
        if isinstance(run_context, dict):
            run_context["live_execution_guard"] = guard_meta

    return trace, dashboard
