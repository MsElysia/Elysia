# project_guardian/prompt_contracts/contracts.py
"""Dataclass definitions for standardized LLM prompt contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Tuple


@dataclass
class PromptContract:
    """One versioned contract: role, I/O shape, safety, and validation rules."""

    contract_id: str
    module_name: str
    purpose: str
    system_prompt: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    expected_json_keys: Tuple[str, ...]
    allowed_actions: Tuple[str, ...]
    forbidden_actions: Tuple[str, ...]
    risk_notes: Tuple[str, ...]
    version: str
    forbidden_json_keys: Tuple[str, ...] = field(
        default_factory=lambda: (
            "chain_of_thought",
            "private_reasoning",
            "scratchpad",
            "hidden_reasoning",
        )
    )
    extra_forbidden_keys: Tuple[str, ...] = ()
    forbid_shell_patterns_in_output: bool = True


def contract_to_dict(contract: PromptContract) -> Dict[str, Any]:
    """JSON-serializable view."""
    return asdict(contract)
