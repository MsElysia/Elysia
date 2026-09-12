# project_guardian/prompt_contracts/controls.py
"""Operator-visible prompt-contract config and read-only status (no LLM calls)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from project_guardian.brain.config import BrainPipelineConfig, get_brain_pipeline_config
from project_guardian.brain.trace_visibility import redact_sensitive
from project_guardian.prompt_contracts.registry import list_prompt_contracts

logger = logging.getLogger(__name__)

_ALLOWED_RESULT_KEYS = frozenset(
    {
        "module_name",
        "contract_id",
        "valid",
        "blocked",
        "mode",
        "errors",
        "warnings",
    }
)
_FORBIDDEN_EXPOSURE_SUBSTRINGS = (
    "system_prompt",
    "input_schema",
    "output_schema",
    "rendered_prompt",
    "raw_prompt",
    "raw_output",
    "raw_model_output",
    "llm_output",
    "chain_of_thought",
    "private_reasoning",
    "hidden_reasoning",
    "scratchpad",
    "model_output",
)


@dataclass(frozen=True)
class PromptContractValidationConfig:
    enabled: bool = False
    mode: str = "warn"
    modules: Tuple[str, ...] = (
        "planner",
        "tool_router",
        "llm_router",
        "risk_checker",
        "think_decide_act_thinker",
        "think_decide_act_proposer",
    )
    operator_chat: bool = False


def get_prompt_contract_validation_config(
    brain_cfg: Optional[BrainPipelineConfig] = None,
) -> PromptContractValidationConfig:
    cfg = brain_cfg or get_brain_pipeline_config()
    raw = cfg.prompt_contract_validation or {}
    mode = str(raw.get("mode") or "warn").strip().lower()
    if mode not in {"warn", "strict", "off"}:
        mode = "warn"
    mods = raw.get("modules")
    modules: Tuple[str, ...]
    if isinstance(mods, list) and mods:
        modules = tuple(str(m) for m in mods if str(m).strip())
    else:
        modules = PromptContractValidationConfig().modules
    return PromptContractValidationConfig(
        enabled=bool(raw.get("enabled")),
        mode=mode,
        modules=modules,
        operator_chat=bool(raw.get("operator_chat")),
    )


def apply_prompt_contract_config_to_context(
    context: Dict[str, Any],
    *,
    source_entrypoint: str,
    brain_cfg: Optional[BrainPipelineConfig] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Merge validation flags for operator chat when config allows (never enables LLMs)."""
    warnings: List[str] = []
    pc = get_prompt_contract_validation_config(brain_cfg)
    if not pc.enabled:
        return context, warnings
    if source_entrypoint != "operator_chat" or not pc.operator_chat:
        return context, warnings

    out = dict(context)
    if pc.mode == "off":
        return out, warnings
    mode = pc.mode if pc.mode in {"warn", "strict"} else "warn"
    dry_run = bool(out.get("dry_run"))
    if mode == "strict" and not dry_run:
        warnings.append("strict_mode_downgraded_to_warn:dry_run_required")
        mode = "warn"

    out["validate_prompt_contracts"] = True
    out["prompt_contract_mode"] = mode
    out["prompt_contract_modules"] = list(pc.modules)
    return out, warnings


def _scrub_public_text(value: Any, *, limit: int = 240) -> str:
    text = str(redact_sensitive(value))
    for key in _FORBIDDEN_EXPOSURE_SUBSTRINGS:
        text = re.sub(re.escape(key), "[REDACTED_FIELD]", text, flags=re.I)
    return text[:limit]


def _compact_module_result(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    row: Dict[str, Any] = {}
    for key in _ALLOWED_RESULT_KEYS:
        if key not in raw:
            continue
        val = raw[key]
        if key in ("errors", "warnings") and isinstance(val, list):
            row[key] = [_scrub_public_text(x) for x in val[:8]]
        elif key in {"module_name", "contract_id", "mode"}:
            row[key] = _scrub_public_text(val, limit=120)
        else:
            row[key] = val
    if not row.get("module_name"):
        return None
    return row


def compact_prompt_contract_validation_for_persist(
    run_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Sanitized per-module validation map for trace JSON persistence."""
    ctx = run_context or {}
    raw = ctx.get("prompt_contract_validation")
    if not isinstance(raw, dict) or not raw:
        return {}
    out: Dict[str, Any] = {}
    for mod, entry in raw.items():
        compact = _compact_module_result(entry)
        if compact:
            out[str(mod)] = compact
    return out


def _summarize_validation_map(raw: Any) -> Dict[str, Any]:
    empty = {
        "exists": False,
        "valid_count": 0,
        "invalid_count": 0,
        "blocked_count": 0,
        "results": [],
    }
    if not isinstance(raw, dict) or not raw:
        return empty
    results: List[Dict[str, Any]] = []
    valid_count = invalid_count = blocked_count = 0
    for entry in raw.values():
        compact = _compact_module_result(entry)
        if not compact:
            continue
        if compact.get("valid"):
            valid_count += 1
        else:
            invalid_count += 1
        if compact.get("blocked"):
            blocked_count += 1
        results.append(compact)
    return {
        "exists": bool(results),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "blocked_count": blocked_count,
        "results": results,
    }


def _load_trace_validation(trace_path: Path) -> Dict[str, Any]:
    if not trace_path.is_file():
        return _summarize_validation_map({})
    try:
        data = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("prompt contract status: trace read failed: %s", exc)
        return _summarize_validation_map({})
    if not isinstance(data, dict):
        return _summarize_validation_map({})
    raw = data.get("prompt_contract_validation")
    if raw is None and isinstance(data.get("run_context"), dict):
        raw = data["run_context"].get("prompt_contract_validation")
    if raw is None and isinstance(data.get("unified_export"), dict):
        unified = data["unified_export"]
        if isinstance(unified.get("run_context"), dict):
            raw = unified["run_context"].get("prompt_contract_validation")
        if raw is None:
            raw = unified.get("prompt_contract_validation")
    if raw is None and isinstance(data.get("think_decide_act_trace"), dict):
        raw = data["think_decide_act_trace"].get("prompt_contract_validation")
    return _summarize_validation_map(raw)


def _list_contract_catalog() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for c in list_prompt_contracts():
        rows.append(
            {
                "contract_id": str(c.contract_id),
                "module_name": str(c.module_name),
                "version": str(c.version),
            }
        )
    rows.sort(key=lambda r: (r["module_name"], r["contract_id"]))
    return rows


def build_prompt_contract_status(
    *,
    brain_cfg: Optional[BrainPipelineConfig] = None,
    trace_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only status for API / control panel (no prompts or model outputs)."""
    cfg = brain_cfg or get_brain_pipeline_config()
    pc = get_prompt_contract_validation_config(cfg)
    contracts = _list_contract_catalog()
    warnings: List[str] = []
    if pc.mode == "strict":
        warnings.append("strict_mode_only_blocks_when_dry_run_true")
    latest = _load_trace_validation(trace_path or cfg.trace_path)
    return {
        "available": True,
        "enabled": pc.enabled,
        "mode": pc.mode,
        "operator_chat": pc.operator_chat,
        "operator_chat_enabled": pc.operator_chat,
        "contract_count": len(contracts),
        "contracts": contracts,
        "modules": list(pc.modules),
        "latest_validation": latest,
        "warnings": warnings,
    }


def summarize_validation_bucket(bucket: Any) -> Dict[str, Any]:
    """Public alias used by the status compatibility module."""
    return _summarize_validation_map(bucket)
