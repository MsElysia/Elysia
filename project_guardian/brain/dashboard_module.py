# project_guardian/brain/dashboard_module.py

from __future__ import annotations

from typing import Any, Dict

from .contracts import BrainPipelineTrace, DashboardModule
from .tda_trace_fields import get_think_decide_act_trace


class DefaultDashboardModule(DashboardModule):
    def snapshot(self, trace: BrainPipelineTrace) -> Dict[str, Any]:
        tda_detail = get_think_decide_act_trace(trace)
        return {
            "brain_pipeline_id": trace.brain_pipeline_id,
            "use_think_decide_act": bool((trace.run_context or {}).get("use_think_decide_act")),
            "dry_run": bool((trace.run_context or {}).get("dry_run")),
            "think_decide_act_trace_present": tda_detail is not None,
            "think_decide_act_trace": tda_detail,
            "tda_trace": tda_detail,
            "transitions": list(trace.transitions),
            "context_preview": trace.context_preview[:400],
            "memory_snippets": trace.memory_snippets[:8],
            "plan_goal": (trace.plan.goal_summary if trace.plan else "")[:200],
            "llm_backend": trace.llm_backend,
            "llm_reason": trace.llm_reason,
            "risk": trace.risk.level.value if trace.risk else None,
            "risk_reason": trace.risk.reason if trace.risk else None,
            "tool_selected": trace.tool_route.selected if trace.tool_route else None,
            "tool_fallback": trace.tool_route.used_fallback if trace.tool_route else None,
            "execution_ok": trace.execution.success if trace.execution else None,
            "execution_error": trace.execution.error if trace.execution else None,
            "lesson": trace.learning.lesson[:200] if trace.learning else None,
        }
