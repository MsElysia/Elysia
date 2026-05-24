# project_guardian/prompt_contracts/registry.py
"""Lookup, render, and module-level helpers for prompt contracts."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from . import validation
from .contracts import PromptContract
from .default_contracts import build_default_contract_map, default_module_to_contract_id

_REGISTRY: Optional[Dict[str, PromptContract]] = None
_MODULE_TO_ID: Optional[Dict[str, str]] = None


def _registry() -> Dict[str, PromptContract]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_default_contract_map()
    return _REGISTRY


def _module_map() -> Dict[str, str]:
    global _MODULE_TO_ID
    if _MODULE_TO_ID is None:
        _MODULE_TO_ID = default_module_to_contract_id()
    return _MODULE_TO_ID


def get_prompt_contract(contract_id: str) -> PromptContract:
    r = _registry()
    if contract_id not in r:
        raise KeyError(f"unknown prompt contract: {contract_id}")
    return r[contract_id]


def list_prompt_contracts() -> List[PromptContract]:
    return list(_registry().values())


def render_prompt(contract_id: str, input_payload: Dict[str, Any]) -> str:
    c = get_prompt_contract(contract_id)
    keys = ", ".join(c.expected_json_keys)
    body = json.dumps(input_payload, ensure_ascii=False, indent=2)
    return (
        f"{c.system_prompt}\n\n"
        f"INPUT_JSON:\n{body}\n\n"
        f"OUTPUT: single JSON object with keys: {keys}. "
        f"Do not include keys: {', '.join(sorted(set(c.forbidden_json_keys) | set(c.extra_forbidden_keys)))}."
    )


def get_module_contract(module_name: str) -> PromptContract:
    cid = _module_map().get(module_name)
    if not cid:
        raise KeyError(f"unknown module_name for contract: {module_name}")
    return get_prompt_contract(cid)


def _resolve_contract_ref(contract: Union[PromptContract, str]) -> PromptContract:
    if isinstance(contract, PromptContract):
        return contract
    s = str(contract)
    if "." in s:
        return get_prompt_contract(s)
    return get_module_contract(s)


def validate_contract_output(
    contract: Union[PromptContract, str],
    model_output: Union[str, Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Validate model output (JSON string or dict) against a contract or module/contract id string."""
    c = _resolve_contract_ref(contract)
    if isinstance(model_output, dict):
        return validation.validate_contract_object(c, model_output)
    return validation.validate_contract_text(c, str(model_output))


def validate_module_llm_response(module_name: str, response: Union[str, Dict[str, Any]]) -> Tuple[bool, List[str]]:
    cid = _module_map().get(module_name)
    if not cid:
        return False, [f"unknown_module:{module_name}"]
    return validate_contract_output(get_prompt_contract(cid), response)


def reload_default_contracts_for_tests() -> None:
    """Clear cached registry (tests only)."""
    global _REGISTRY, _MODULE_TO_ID
    _REGISTRY = None
    _MODULE_TO_ID = None
