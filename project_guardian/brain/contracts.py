# project_guardian/brain/contracts.py
# Shared types and Protocols for the modular Elysia brain pipeline.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass
class Observation:
    """Inbound signal: user goal, system note, or mixed payload."""

    source: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanStep:
    """Single planner step (descriptive only; planner must not execute)."""

    description: str
    capability_hint: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """Structured plan from the planner module."""

    goal_summary: str
    steps: List[PlanStep] = field(default_factory=list)
    router_task_type: str = "simple"


@dataclass
class ToolRouteDecision:
    """Structured routing decision (no side effects in the router itself)."""

    primary: str
    selected: str
    used_fallback: bool
    reason: str
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskAssessment:
    level: RiskLevel
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredCommand:
    """What the execution module is allowed to run after risk approval."""

    capability_ref: str
    payload: Dict[str, Any] = field(default_factory=dict)
    audit_label: str = ""


@dataclass
class ExecutionResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class LearningOutcome:
    worked: bool
    lesson: str
    improvement_hints: List[str] = field(default_factory=list)


@dataclass
class BrainPipelineTrace:
    """Runtime trace for BrainPipeline; ``unified_export`` is filled at end of ``run``."""

    transitions: List[str] = field(default_factory=list)
    brain_pipeline_id: str = ""
    started_at: str = ""
    input_source: str = ""
    observation_preview: str = ""
    context_preview: str = ""
    memory_snippets: List[str] = field(default_factory=list)
    plan: Optional[Plan] = None
    llm_backend: Optional[str] = None
    llm_reason: Optional[str] = None
    risk: Optional[RiskAssessment] = None
    tool_route: Optional[ToolRouteDecision] = None
    execution: Optional[ExecutionResult] = None
    learning: Optional[LearningOutcome] = None
    think_decide_act_trace: Optional[Dict[str, Any]] = None
    run_context: Dict[str, Any] = field(default_factory=dict)
    unified_export: Optional[Dict[str, Any]] = None

    @property
    def tda_trace(self) -> Optional[Dict[str, Any]]:
        """Compatibility alias for :attr:`think_decide_act_trace` (same payload)."""
        return self.think_decide_act_trace

    @tda_trace.setter
    def tda_trace(self, value: Optional[Dict[str, Any]]) -> None:
        self.think_decide_act_trace = value


class MemoryModule(Protocol):
    def retrieve(self, query: str, *, limit: int = 12) -> List[str]: ...

    def remember(self, thought: str, **kwargs: Any) -> None: ...

    def search(self, keyword: str, limit: int = 8) -> List[str]: ...


class PlannerModule(Protocol):
    def plan(
        self,
        observation: Observation,
        memory_snippets: List[str],
        context_text: str,
    ) -> Plan: ...


class ToolRouterModule(Protocol):
    def route(
        self,
        observation: Observation,
        plan: Plan,
        *,
        guardian: Any,
    ) -> ToolRouteDecision: ...


class LLMRouterModule(Protocol):
    def choose_backend(
        self,
        *,
        user_text: str,
        router_task_type: str,
        risk_level: RiskLevel,
        registry: Any = None,
    ) -> Tuple[str, str]: ...


class RiskCheckerModule(Protocol):
    def review(
        self,
        observation: Observation,
        plan: Plan,
        proposed_command: StructuredCommand,
    ) -> RiskAssessment: ...


class ExecutionModule(Protocol):
    def execute(
        self,
        guardian: Any,
        command: StructuredCommand,
        *,
        risk: RiskAssessment,
        route: ToolRouteDecision,
    ) -> ExecutionResult: ...


class LearningModule(Protocol):
    def review_outcome(
        self,
        observation: Observation,
        plan: Plan,
        execution: ExecutionResult,
        memory: MemoryModule,
    ) -> LearningOutcome: ...


class SelfImprovementModule(Protocol):
    def enqueue(self, outcome: LearningOutcome, trace: BrainPipelineTrace) -> None: ...


class DashboardModule(Protocol):
    def snapshot(self, trace: BrainPipelineTrace) -> Dict[str, Any]: ...


class ContextBuilderModule(Protocol):
    def build(self, observation: Observation, memory: MemoryModule) -> str: ...
