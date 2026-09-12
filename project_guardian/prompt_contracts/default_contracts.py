# project_guardian/prompt_contracts/default_contracts.py
"""Default ``PromptContract`` definitions for brain / TDA / memory LLM surfaces."""

from __future__ import annotations

from typing import Dict, List

from .contracts import PromptContract

_COMMON_JSON_RULE = (
    "Respond with exactly one JSON object (no markdown fences). "
    "Use short reason_summary (max ~400 chars), not chain-of-thought. "
    "Include confidence in [0,1] when the schema lists it."
)


def _all_contracts() -> List[PromptContract]:
    return [
        PromptContract(
            contract_id="planner.v1",
            module_name="planner",
            purpose="Convert a user goal or observation into a structured plan.",
            system_prompt=(
                "You are the Planner Module for a safety-first assistant. "
                + _COMMON_JSON_RULE
                + " Propose steps only; never execute tools or shell."
            ),
            input_schema={"observation": "str", "memory_snippets": "list[str]", "context_text": "str"},
            output_schema={
                "goal": "str",
                "steps": "list[dict]",
                "constraints": "list[str]",
                "risk_level": "low|medium|high|blocked",
                "reason_summary": "str",
                "confidence": "float",
            },
            expected_json_keys=(
                "goal",
                "steps",
                "constraints",
                "risk_level",
                "reason_summary",
                "confidence",
            ),
            allowed_actions=("propose_steps", "request_missing_info"),
            forbidden_actions=("execute_tools", "call_shell", "modify_files", "network_egress"),
            risk_notes=("Planner must not execute actions.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="tool_router.v1",
            module_name="tool_router",
            purpose="Select a capability route without executing it.",
            system_prompt="You are the Tool Router. " + _COMMON_JSON_RULE + " Return routing metadata only.",
            input_schema={"observation": "str", "plan": "object"},
            output_schema={
                "primary": "str",
                "selected": "str",
                "reason_summary": "str",
                "confidence": "float",
                "risk_level": "str",
            },
            expected_json_keys=("primary", "selected", "reason_summary", "confidence", "risk_level"),
            allowed_actions=("select_route", "request_fallback"),
            forbidden_actions=("execute_tools", "call_shell", "modify_files"),
            risk_notes=("Router selects labels only; execution is downstream.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="llm_router.v1",
            module_name="llm_router",
            purpose="Choose an LLM backend label for a task class and risk.",
            system_prompt="You are the LLM Router. " + _COMMON_JSON_RULE,
            input_schema={"user_text": "str", "router_task_type": "str", "risk_level": "str"},
            output_schema={"backend": "str", "reason_summary": "str", "confidence": "float"},
            expected_json_keys=("backend", "reason_summary", "confidence"),
            allowed_actions=("choose_backend", "explain_choice"),
            forbidden_actions=("invoke_model", "call_shell", "modify_files"),
            risk_notes=("Router returns labels for an orchestrator; no direct API calls here.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="risk_checker.v1",
            module_name="risk_checker",
            purpose="Classify risk of a proposed structured command.",
            system_prompt="You are the Risk Checker. " + _COMMON_JSON_RULE,
            input_schema={"observation": "str", "plan": "object", "proposed_command": "object"},
            output_schema={"level": "str", "reason_summary": "str", "confidence": "float", "details": "object"},
            expected_json_keys=("level", "reason_summary", "confidence", "details"),
            allowed_actions=("classify_risk", "cite_policy"),
            forbidden_actions=("execute_tools", "call_shell", "modify_files"),
            risk_notes=("Output is advisory to a human-in-the-loop or hard gate.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="memory_ranker.v1",
            module_name="memory_ranker",
            purpose="Rank or score memories for retrieval; deterministic core may bypass LLM.",
            system_prompt="You are the Memory Ranker (optional LLM assist). " + _COMMON_JSON_RULE,
            input_schema={"candidates": "list[object]", "goal_text": "str"},
            output_schema={"scores": "list[object]", "reason_summary": "str", "confidence": "float"},
            expected_json_keys=("scores", "reason_summary", "confidence"),
            allowed_actions=("score_items", "reorder"),
            forbidden_actions=("delete_memory", "mutate_store", "call_shell"),
            risk_notes=("Prefer project_guardian.memory_ranking heuristics for production defaults.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="memory_compressor.v1",
            module_name="memory_compressor",
            purpose="Propose compressed text preserving entities and decisions.",
            system_prompt="You are the Memory Compressor. " + _COMMON_JSON_RULE,
            input_schema={"memory_text": "str", "max_chars": "int"},
            output_schema={
                "summary": "str",
                "preserved_entities": "list[str]",
                "reason_summary": "str",
                "confidence": "float",
            },
            expected_json_keys=("summary", "preserved_entities", "reason_summary", "confidence"),
            allowed_actions=("summarize", "list_entities"),
            forbidden_actions=("delete_memory", "mutate_store", "call_shell"),
            risk_notes=("Output is advisory until a separate apply step exists.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="learning_reviewer.v1",
            module_name="learning_reviewer",
            purpose="Review execution outcome and suggest lesson improvements.",
            system_prompt="You are the Learning Reviewer. " + _COMMON_JSON_RULE,
            input_schema={"observation": "str", "plan": "object", "execution": "object"},
            output_schema={
                "improvement_hints": "list[str]",
                "confidence": "float",
                "reason_summary": "str",
                "risk_level": "str",
            },
            expected_json_keys=("improvement_hints", "confidence", "reason_summary", "risk_level"),
            allowed_actions=("suggest_hints", "flag_risk"),
            forbidden_actions=("execute_tools", "call_shell", "modify_files"),
            risk_notes=("Hints are consumed by policy, not auto-executed.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="self_improvement_reviewer.v1",
            module_name="self_improvement_reviewer",
            purpose="Review queued self-improvement proposals without applying them.",
            system_prompt="You are the Self-Improvement Reviewer. " + _COMMON_JSON_RULE,
            input_schema={"queue_row": "object", "trace_excerpt": "object"},
            output_schema={
                "suggestions": "list[str]",
                "confidence": "float",
                "reason_summary": "str",
                "risk_level": "str",
            },
            expected_json_keys=("suggestions", "confidence", "reason_summary", "risk_level"),
            allowed_actions=("review", "defer", "reject"),
            forbidden_actions=("apply_patch", "call_shell", "modify_files", "execute_tools"),
            risk_notes=("JsonlSelfImprovementQueue remains append-only; no auto-apply.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="think_decide_act_thinker.v1",
            module_name="think_decide_act_thinker",
            purpose="TDA think phase: distill goal and candidates.",
            system_prompt="You are the Think-Decide-Act Thinker. " + _COMMON_JSON_RULE,
            input_schema={"observation": "object", "context": "object"},
            output_schema={
                "goal_candidates": "list[object]",
                "reason_summary": "str",
                "confidence": "float",
                "risk_level": "str",
            },
            expected_json_keys=("goal_candidates", "reason_summary", "confidence", "risk_level"),
            allowed_actions=("propose_goals",),
            forbidden_actions=("execute_tools", "call_shell", "modify_files"),
            risk_notes=("Think output feeds validate/propose only.",),
            version="1.0.0",
        ),
        PromptContract(
            contract_id="think_decide_act_proposer.v1",
            module_name="think_decide_act_proposer",
            purpose="TDA propose phase: emit a structured action proposal.",
            system_prompt="You are the Think-Decide-Act Proposer. " + _COMMON_JSON_RULE,
            input_schema={"thought": "object", "context": "object"},
            output_schema={
                "action_type": "str",
                "target": "str",
                "reason_summary": "str",
                "confidence": "float",
                "risk_level": "str",
            },
            expected_json_keys=("action_type", "target", "reason_summary", "confidence", "risk_level"),
            allowed_actions=("propose_action",),
            forbidden_actions=("execute_tools", "call_shell", "modify_files"),
            risk_notes=("Proposal must pass validation before execution in TDA.",),
            version="1.0.0",
        ),
    ]


def build_default_contract_map() -> Dict[str, PromptContract]:
    out: Dict[str, PromptContract] = {}
    for c in _all_contracts():
        if c.contract_id in out:
            raise ValueError(f"duplicate contract_id: {c.contract_id}")
        out[c.contract_id] = c
    return out


def default_module_to_contract_id() -> Dict[str, str]:
    m: Dict[str, str] = {}
    for c in _all_contracts():
        m[c.module_name] = c.contract_id
    return m
