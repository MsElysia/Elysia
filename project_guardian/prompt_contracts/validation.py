# project_guardian/prompt_contracts/validation.py
"""Parse and validate model outputs against ``PromptContract`` rules."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from .contracts import PromptContract

_FORBIDDEN_REASONING = frozenset(
    {
        "chain_of_thought",
        "private_reasoning",
        "scratchpad",
        "hidden_reasoning",
    }
)

_VALID_RISK = frozenset({"low", "medium", "high", "blocked"})

_SHELLISH = re.compile(
    r"(?i)(?:^|\s)(?:rm\s+-rf\b|curl\s+\S+\s*\|\s*sh\b|bash\s+-c\b|/bin/(?:ba)?sh\b|"
    r"cmd\.exe|powershell\s+(?:-\w+\s+)*-e\w*\b|wget\s+\S+\s*-O-\s*\|\s*)"
)


def parse_json_output(model_output: str) -> Tuple[Dict[str, Any] | None, List[str]]:
    """Strip optional ```json fences and parse to a dict. Returns (obj, errors)."""
    errors: List[str] = []
    raw = (model_output or "").strip()
    if not raw:
        return None, ["empty_output"]
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```\s*$", "", raw)
        raw = raw.strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, [f"invalid_json:{e}"]
    if not isinstance(obj, dict):
        return None, ["json_root_must_be_object"]
    return obj, []


def validate_contract_text(contract: PromptContract, model_output: str) -> Tuple[bool, List[str]]:
    """Validate raw model string against contract (no LLM calls)."""
    obj, errs = parse_json_output(model_output)
    if obj is None:
        return False, errs
    return validate_contract_object(contract, obj)


def validate_contract_object(contract: PromptContract, obj: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    keys = set(obj.keys())

    for req in contract.expected_json_keys:
        if req not in obj:
            errors.append(f"missing_required_key:{req}")

    forbidden = set(contract.forbidden_json_keys) | set(contract.extra_forbidden_keys) | _FORBIDDEN_REASONING
    for fk in forbidden:
        if fk in keys:
            errors.append(f"forbidden_key:{fk}")

    if "confidence" in obj:
        try:
            c = float(obj["confidence"])
            if c < 0.0 or c > 1.0:
                errors.append("confidence_out_of_range")
        except (TypeError, ValueError):
            errors.append("confidence_not_numeric")

    if "risk_level" in obj:
        rl = str(obj["risk_level"]).lower().strip()
        if rl not in _VALID_RISK:
            errors.append(f"invalid_risk_level:{obj['risk_level']!r}")

    if "level" in obj:
        lv = str(obj["level"]).lower().strip()
        if lv not in _VALID_RISK:
            errors.append(f"invalid_level:{obj['level']!r}")

    if contract.forbid_shell_patterns_in_output:
        for k, v in obj.items():
            if isinstance(v, str) and _SHELLISH.search(v):
                errors.append(f"shell_like_pattern_in_field:{k}")
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, str) and _SHELLISH.search(item):
                        errors.append(f"shell_like_pattern_in_field:{k}[{i}]")
                    if isinstance(item, dict):
                        for sk, sv in item.items():
                            if isinstance(sv, str) and _SHELLISH.search(sv):
                                errors.append(f"shell_like_pattern_in_field:{k}[{i}].{sk}")

    return len(errors) == 0, errors
