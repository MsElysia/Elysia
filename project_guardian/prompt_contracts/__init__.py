"""Canonical standardized prompt contracts for LLM-assisted modules (advisory; no autonomy wiring).

Import from ``project_guardian.prompt_contracts``. No real LLM calls are performed here.
"""

from __future__ import annotations

from .contracts import PromptContract, contract_to_dict
from .default_contracts import build_default_contract_map, default_module_to_contract_id
from .registry import (
    get_module_contract,
    get_prompt_contract,
    list_prompt_contracts,
    reload_default_contracts_for_tests,
    render_prompt,
    validate_contract_output,
    validate_module_llm_response,
)
from .validation import parse_json_output, validate_contract_object, validate_contract_text
from . import integration

__all__ = [
    "PromptContract",
    "build_default_contract_map",
    "contract_to_dict",
    "default_module_to_contract_id",
    "get_module_contract",
    "get_prompt_contract",
    "list_prompt_contracts",
    "parse_json_output",
    "reload_default_contracts_for_tests",
    "render_prompt",
    "validate_contract_object",
    "validate_contract_output",
    "validate_contract_text",
    "validate_module_llm_response",
    "integration",
]
