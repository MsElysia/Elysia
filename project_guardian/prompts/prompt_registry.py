# project_guardian/prompts/prompt_registry.py
"""Central registry of module and agent prompt metadata and body text."""

from __future__ import annotations

from typing import Any, Dict, Final, Tuple

from .core.base import CORE_META, render_core_text
from .modules import debugger, memory, planner, router, summarizer, tool_selection
from .agents import critic, executor, orchestrator

ModuleRecord = Tuple[Dict[str, str], str]
AgentRecord = Tuple[Dict[str, str], str]

MODULES: Final[Dict[str, ModuleRecord]] = {
    "router": (router.MODULE_META, router.MODULE_TEXT),
    "memory": (memory.MODULE_META, memory.MODULE_TEXT),
    "planner": (planner.MODULE_META, planner.MODULE_TEXT),
    "debugger": (debugger.MODULE_META, debugger.MODULE_TEXT),
    "tool_selection": (tool_selection.MODULE_META, tool_selection.MODULE_TEXT),
    "summarizer": (summarizer.MODULE_META, summarizer.MODULE_TEXT),
}

AGENTS: Final[Dict[str, AgentRecord]] = {
    "orchestrator": (orchestrator.AGENT_META, orchestrator.AGENT_TEXT),
    "critic": (critic.AGENT_META, critic.AGENT_TEXT),
    "executor": (executor.AGENT_META, executor.AGENT_TEXT),
}


def get_core() -> Tuple[Dict[str, str], str]:
    return CORE_META, render_core_text()


def get_module(module_name: str) -> Tuple[Dict[str, str], str]:
    key = (module_name or "").strip().lower()
    if key not in MODULES:
        raise KeyError(
            f"Unknown prompt module '{module_name}'. Known: {sorted(MODULES.keys())}"
        )
    meta, text = MODULES[key]
    return dict(meta), text


def get_agent(agent_name: str) -> Tuple[Dict[str, str], str]:
    key = (agent_name or "").strip().lower()
    if key not in AGENTS:
        raise KeyError(f"Unknown prompt agent '{agent_name}'. Known: {sorted(AGENTS.keys())}")
    meta, text = AGENTS[key]
    return dict(meta), text


def list_module_names() -> list[str]:
    return sorted(MODULES.keys())


def list_agent_names() -> list[str]:
    return sorted(AGENTS.keys())
