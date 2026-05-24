"""Compatibility helpers for read-only prompt-contract status.

The implementation lives in :mod:`project_guardian.prompt_contracts.controls`
so config-to-context controls and operator-visible status use one code path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from project_guardian.brain.config import BrainPipelineConfig

from .controls import build_prompt_contract_status as _build_prompt_contract_status
from .controls import summarize_validation_bucket


def summarize_prompt_contract_validation(trace_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize prompt-contract validation from a persisted trace-shaped dict."""
    if not isinstance(trace_dict, dict):
        return summarize_validation_bucket(None)
    bucket = trace_dict.get("prompt_contract_validation")
    if bucket is None and isinstance(trace_dict.get("run_context"), dict):
        bucket = trace_dict["run_context"].get("prompt_contract_validation")
    if bucket is None and isinstance(trace_dict.get("unified_export"), dict):
        unified = trace_dict["unified_export"]
        if isinstance(unified.get("run_context"), dict):
            bucket = unified["run_context"].get("prompt_contract_validation")
        if bucket is None:
            bucket = unified.get("prompt_contract_validation")
    if bucket is None and isinstance(trace_dict.get("think_decide_act_trace"), dict):
        bucket = trace_dict["think_decide_act_trace"].get("prompt_contract_validation")
    return summarize_validation_bucket(bucket)


def build_prompt_contract_status(
    config: Optional[BrainPipelineConfig] = None,
    trace_summary: Optional[Dict[str, Any]] = None,
    *,
    trace_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return the compact operator-visible prompt-contract status."""
    status = _build_prompt_contract_status(brain_cfg=config, trace_path=trace_path)
    if trace_summary is not None:
        status["latest_validation"] = summarize_prompt_contract_validation(trace_summary)
    return status


__all__ = [
    "build_prompt_contract_status",
    "summarize_prompt_contract_validation",
]
