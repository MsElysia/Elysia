from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def _base_output_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "valid",
            "module",
            "function",
            "mode",
            "task_id",
            "confidence",
            "result_type",
            "summary",
            "data",
            "recommended_action",
            "risks",
            "missing_information",
            "errors",
        ],
    }


def build_profile(
    *,
    prompt_id: str,
    module_name: str,
    function_name: str,
    mode: Optional[str] = None,
    reasoning_style: str = "analytical",
    allowed_command_types: Optional[Iterable[str]] = None,
    structured_output_kind: str = "envelope",
) -> Dict[str, Any]:
    return {
        "prompt_id": prompt_id,
        "module_name": module_name,
        "function_name": function_name,
        "mode": mode,
        "version": 1,
        "status": "active",
        "llm_role": f"{module_name}::{function_name} specialist",
        "purpose": f"Execute {module_name} {function_name} with safe structured outputs.",
        "input_requirements": ["task", "task_id", "context"],
        "memory_context_needed": True,
        "available_tools_context_needed": True,
        "behavioral_instructions": [
            "Return strict JSON only.",
            "Never emit executable shell, code patches, or credentials.",
            "Recommend actions; do not claim execution.",
        ],
        "reasoning_style": reasoning_style,
        "allowed_command_types": list(
            allowed_command_types
            or [
                "NO_ACTION",
                "CALL_TOOL",
                "ASK_USER",
                "STORE_MEMORY",
                "RETRIEVE_MEMORY",
                "RUN_ANALYSIS",
                "PROPOSE_CODE_CHANGE",
                "ESCALATE_TO_HUMAN",
            ]
        ),
        "forbidden_outputs": ["```", "BEGIN RSA PRIVATE KEY", "os.system(", "rm -rf", "powershell -"],
        "failure_behavior": {
            "on_missing_information": "ASK_USER",
            "on_low_confidence": "ESCALATE_TO_HUMAN",
            "on_schema_uncertainty": "RETURN_ERROR",
        },
        "structured_output_kind": structured_output_kind,
        "output_schema": _base_output_schema(),
        "validation_rules": {
            "json_only": True,
            "require_envelope": True,
            "reject_unknown_command_types": True,
        },
        "performance_metrics": {
            "calls": 0,
            "valid_json_rate": 0.0,
            "schema_pass_rate": 0.0,
            "task_success_rate": 0.0,
            "retry_rate": 0.0,
            "human_override_rate": 0.0,
            "average_confidence": 0.0,
            "average_latency_ms": 0.0,
        },
    }


def build_module_profiles(
    module_name: str,
    functions: List[str],
    *,
    reasoning_style: str = "analytical",
    allowed_command_types: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for fn in functions:
        pid = f"{module_name}.{fn}.v1"
        out[fn] = build_profile(
            prompt_id=pid,
            module_name=module_name,
            function_name=fn,
            reasoning_style=reasoning_style,
            allowed_command_types=allowed_command_types,
        )
    return out
