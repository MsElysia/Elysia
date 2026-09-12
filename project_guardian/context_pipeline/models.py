# project_guardian/context_pipeline/models.py
"""Typed dataclasses for the structured context pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ExtractedFact:
    source_type: str
    record_id: str
    text: str
    total_score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContradictionRecord:
    topic: str
    record_ids: Tuple[str, ...]
    snippets: Tuple[str, ...]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "record_ids": list(self.record_ids),
            "snippets": list(self.snippets),
            "confidence": self.confidence,
        }


@dataclass
class PromptPacket:
    task_type: str
    objective: str
    facts: List[str]
    constraints: List[str]
    risks: List[str]
    unknowns: List[str]
    evidence: List[Dict[str, Any]]
    requested_output_schema: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PromptPacket":
        return PromptPacket(
            task_type=str(d.get("task_type") or ""),
            objective=str(d.get("objective") or ""),
            facts=list(d.get("facts") or []),
            constraints=list(d.get("constraints") or []),
            risks=list(d.get("risks") or []),
            unknowns=list(d.get("unknowns") or []),
            evidence=[e for e in (d.get("evidence") or []) if isinstance(e, dict)],
            requested_output_schema=str(d.get("requested_output_schema") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StructuredOnlineResponse:
    decision: str
    reasoning: str
    confidence: float
    missing_info: List[str]
    next_steps: List[str]
    risks: List[str]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "StructuredOnlineResponse":
        return StructuredOnlineResponse(
            decision=str(d.get("decision") or ""),
            reasoning=str(d.get("reasoning") or ""),
            confidence=float(d.get("confidence") or 0.0),
            missing_info=[str(x) for x in (d.get("missing_info") or [])],
            next_steps=[str(x) for x in (d.get("next_steps") or [])],
            risks=[str(x) for x in (d.get("risks") or [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    supported_claims: List[str] = field(default_factory=list)
    inferred_claims: List[str] = field(default_factory=list)
    unsupported_claims: List[str] = field(default_factory=list)
    decision_safe: bool = True
    risk_safe: bool = True
    normalized: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    mergeable_next_steps: List[str] = field(default_factory=list)
    mergeable_missing_info: List[str] = field(default_factory=list)
    mergeable_risks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supported_claims": list(self.supported_claims),
            "inferred_claims": list(self.inferred_claims),
            "unsupported_claims": list(self.unsupported_claims),
            "decision_safe": self.decision_safe,
            "risk_safe": self.risk_safe,
            "normalized": dict(self.normalized),
            "issues": list(self.issues),
            "mergeable_next_steps": list(self.mergeable_next_steps),
            "mergeable_missing_info": list(self.mergeable_missing_info),
            "mergeable_risks": list(self.mergeable_risks),
        }

    def safe_guidance_dict(self) -> Dict[str, Any]:
        """Fields allowed to steer merges: supported + inferred-with-flag lists only."""
        if not self.decision_safe:
            return {}
        out: Dict[str, Any] = {}
        if self.mergeable_next_steps:
            out["next_steps"] = list(self.mergeable_next_steps)
        if self.mergeable_missing_info:
            out["missing_info"] = list(self.mergeable_missing_info)
        if self.risk_safe and self.mergeable_risks:
            out["risks"] = list(self.mergeable_risks)
        if self.decision_safe and self.normalized.get("decision"):
            out["decision"] = self.normalized.get("decision")
        return out


@dataclass
class RetrievedContextBundle:
    top_facts: List[str]
    top_constraints: List[str]
    top_risks: List[str]
    top_unknowns: List[str]
    evidence_snippets: List[Dict[str, Any]]
    contradictions: List[ContradictionRecord]
    source_mix: Dict[str, int]
    total_retrieved: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "top_facts": list(self.top_facts),
            "top_constraints": list(self.top_constraints),
            "top_risks": list(self.top_risks),
            "top_unknowns": list(self.top_unknowns),
            "evidence_snippets": list(self.evidence_snippets),
            "contradictions": [c.to_dict() for c in self.contradictions],
            "source_mix": dict(self.source_mix),
            "total_retrieved": self.total_retrieved,
        }


@dataclass
class DecisionPipelineTrace:
    used_context_pipeline_packet: bool = False
    used_structured_online_support: bool = False
    structured_support_changed_decision: bool = False
    decision_basis_summary: str = ""
    raw_state_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
