# project_guardian/brain/__init__.py
"""Modular Elysia brain: memory, planner, routers, risk, execution, learning, dashboard."""

from project_guardian.memory_ranking import (
    MemoryCompressionProposal,
    MemoryRankingConfig,
    MemoryRankingInput,
    MemoryRankingReport,
    MemoryScores,
    RankedMemory,
    build_ranking_report,
    clear_memory_ranking_config_cache,
    get_memory_ranking_config,
    load_memory_ranking_config,
    optional_remember_extras_for_pipeline,
    propose_memory_compression,
    rank_memories,
    redact_memory_text,
    score_memory,
    should_retain_full_memory,
    summarize_memory_for_compression,
)
from .contracts import (
    BrainPipelineTrace,
    ExecutionResult,
    Observation,
    Plan,
    PlanStep,
    RiskLevel,
    ToolRouteDecision,
)
from .config import BrainPipelineConfig, clear_brain_pipeline_config_cache, get_brain_pipeline_config
from .memory_module import GuardianMemoryFacade, InMemoryBrainStore
from .pipeline import BrainPipeline, _TRACE_PATH
from .runtime import run_brain_pipeline_for_operator_event
from .trace_visibility import load_latest_brain_trace_summary, redact_sensitive, sanitize_brain_trace, summarize_trace
from .think_decide_act_adapter import (
    build_unified_export,
    is_brain_tda_adapter_available,
    is_think_decide_act_available,
)

__all__ = [
    "BrainPipeline",
    "BrainPipelineConfig",
    "BrainPipelineTrace",
    "ExecutionResult",
    "GuardianMemoryFacade",
    "InMemoryBrainStore",
    "MemoryCompressionProposal",
    "MemoryRankingConfig",
    "MemoryRankingInput",
    "MemoryRankingReport",
    "MemoryScores",
    "Observation",
    "Plan",
    "PlanStep",
    "RankedMemory",
    "RiskLevel",
    "ToolRouteDecision",
    "brain_last_trace_path",
    "build_ranking_report",
    "build_unified_export",
    "clear_brain_pipeline_config_cache",
    "clear_memory_ranking_config_cache",
    "get_brain_pipeline_config",
    "get_memory_ranking_config",
    "is_brain_tda_adapter_available",
    "is_think_decide_act_available",
    "load_latest_brain_trace_summary",
    "load_memory_ranking_config",
    "optional_remember_extras_for_pipeline",
    "propose_memory_compression",
    "rank_memories",
    "redact_sensitive",
    "redact_memory_text",
    "run_brain_pipeline_for_operator_event",
    "sanitize_brain_trace",
    "score_memory",
    "should_retain_full_memory",
    "summarize_memory_for_compression",
    "summarize_trace",
]

brain_last_trace_path = _TRACE_PATH
