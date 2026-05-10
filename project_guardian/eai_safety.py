"""Evolvable AI safety controls.

This module models the three levers that make an AI system evolvable:
reproduction, variation, and selection. It does not create new autonomy.
Instead, it gives existing autonomy paths a shared gate for replication,
lineage, and deceptive-optimization risk.
"""

import hashlib
import json
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_EAI_SAFETY_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "autonomous_deployment_policy": "deny",
    "lineage_registry_path": "data/eai_lineage_registry.json",
    "audit_log_path": "data/eai_assessments.jsonl",
    "alert_state_path": "data/eai_alert_state.json",
    "review_threshold": 0.45,
    "deny_threshold": 0.85,
    "max_recent_assessments": 25,
    "max_lineage_status_items": 5,
}


def load_eai_safety_config(
    config_path: Optional[str] = "config/eai_safety.json",
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load and sanitize Evolvable-AI safety configuration."""

    values: Dict[str, Any] = dict(DEFAULT_EAI_SAFETY_CONFIG)
    if config_path:
        path = Path(config_path)
        if path.exists():
            try:
                file_values = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(file_values, dict):
                    values.update(file_values)
            except Exception as exc:
                logger.warning("Failed to load EAI safety config %s: %s", config_path, exc)

    if overrides:
        _apply_eai_config_overrides(values, overrides)

    return _sanitize_eai_safety_config(values)


def _apply_eai_config_overrides(values: Dict[str, Any], overrides: Dict[str, Any]) -> None:
    nested = overrides.get("eai_safety")
    if isinstance(nested, dict):
        values.update(nested)

    aliases = {
        "enable_eai_safety": "enabled",
        "eai_lineage_registry_path": "lineage_registry_path",
        "eai_safety_lineage_registry_path": "lineage_registry_path",
        "eai_audit_log_path": "audit_log_path",
        "eai_safety_audit_log_path": "audit_log_path",
        "eai_alert_state_path": "alert_state_path",
        "eai_safety_alert_state_path": "alert_state_path",
        "eai_autonomous_deployment_policy": "autonomous_deployment_policy",
        "eai_safety_review_threshold": "review_threshold",
        "eai_review_threshold": "review_threshold",
        "eai_safety_deny_threshold": "deny_threshold",
        "eai_deny_threshold": "deny_threshold",
        "eai_safety_max_recent_assessments": "max_recent_assessments",
        "eai_safety_max_lineage_status_items": "max_lineage_status_items",
    }
    for source_key, target_key in aliases.items():
        if source_key in overrides:
            values[target_key] = overrides[source_key]

    for key in DEFAULT_EAI_SAFETY_CONFIG:
        if key in overrides:
            values[key] = overrides[key]


def _sanitize_eai_safety_config(values: Dict[str, Any]) -> Dict[str, Any]:
    config = dict(DEFAULT_EAI_SAFETY_CONFIG)
    config.update(values)

    policy = str(config.get("autonomous_deployment_policy", "deny")).strip().lower()
    if policy not in {"deny", "review", "allow"}:
        policy = "deny"

    review_threshold = _coerce_float(config.get("review_threshold"), 0.45, 0.0, 1.0)
    deny_threshold = _coerce_float(config.get("deny_threshold"), 0.85, 0.0, 1.0)
    if review_threshold > deny_threshold:
        review_threshold = deny_threshold

    sanitized = {
        "enabled": _coerce_bool(config.get("enabled"), True),
        "autonomous_deployment_policy": policy,
        "lineage_registry_path": str(
            config.get("lineage_registry_path")
            or DEFAULT_EAI_SAFETY_CONFIG["lineage_registry_path"]
        ),
        "audit_log_path": str(
            config.get("audit_log_path")
            or DEFAULT_EAI_SAFETY_CONFIG["audit_log_path"]
        ),
        "alert_state_path": str(
            config.get("alert_state_path")
            or DEFAULT_EAI_SAFETY_CONFIG["alert_state_path"]
        ),
        "review_threshold": review_threshold,
        "deny_threshold": deny_threshold,
        "max_recent_assessments": _coerce_int(
            config.get("max_recent_assessments"),
            int(DEFAULT_EAI_SAFETY_CONFIG["max_recent_assessments"]),
            1,
            500,
        ),
        "max_lineage_status_items": _coerce_int(
            config.get("max_lineage_status_items"),
            int(DEFAULT_EAI_SAFETY_CONFIG["max_lineage_status_items"]),
            0,
            100,
        ),
    }
    return sanitized


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    if value is None:
        return default
    return bool(value)


def _coerce_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(max(min_value, min(max_value, number)), 3)


def _coerce_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(max_value, number))


class EAIDecision(Enum):
    """Gate decision for an evolvable-AI-sensitive action."""

    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


class EAIRiskFlag(Enum):
    """Risk flags tied to uncontrolled digital evolution."""

    REPLICATION = "replication"
    VARIATION = "variation"
    DEPLOYMENT = "deployment"
    RESOURCE_ACQUISITION = "resource_acquisition"
    SELECTION_PRESSURE = "selection_pressure"
    DECEPTION = "deception"
    CAMOUFLAGE = "camouflage"
    FILTER_AVOIDANCE = "filter_avoidance"
    HIDDEN_TRIGGER = "hidden_trigger"
    LINEAGE_MISSING = "lineage_missing"
    EXTERNAL_CODE_INGESTION = "external_code_ingestion"
    MODEL_MERGE = "model_merge"
    PERSISTENCE = "persistence"
    UNCONTROLLED_EVOLUTION = "uncontrolled_evolution"


@dataclass
class EAILineageRecord:
    """Provenance record for a model, module, agent package, or mutation."""

    artifact_id: str
    artifact_type: str
    fingerprint: str
    provenance_signature: str
    parent_ids: List[str] = field(default_factory=list)
    created_by: str = "unknown"
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "fingerprint": self.fingerprint,
            "provenance_signature": self.provenance_signature,
            "parent_ids": list(self.parent_ids),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EAILineageRecord":
        return cls(
            artifact_id=str(data["artifact_id"]),
            artifact_type=str(data.get("artifact_type", "unknown")),
            fingerprint=str(data.get("fingerprint", "")),
            provenance_signature=str(data.get("provenance_signature", "")),
            parent_ids=[str(item) for item in data.get("parent_ids", [])],
            created_by=str(data.get("created_by", "unknown")),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class EAISafetyAssessment:
    """Structured result from the evolvable-AI safety gate."""

    action_type: str
    actor: str
    target: str
    decision: EAIDecision
    risk_score: float
    flags: List[str] = field(default_factory=list)
    selection_pressures: List[str] = field(default_factory=list)
    required_controls: List[str] = field(default_factory=list)
    reasoning: str = ""
    lineage_record_id: Optional[str] = None
    dry_run: bool = False
    approval_verified: bool = False
    approval_reference: Optional[str] = None
    assessed_at: datetime = field(default_factory=datetime.now)
    assessment_id: str = ""

    def __post_init__(self) -> None:
        if not self.assessment_id:
            self.assessment_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "action_type": self.action_type,
            "actor": self.actor,
            "target": self.target,
            "decision": self.decision.value,
            "risk_score": self.risk_score,
            "flags": list(self.flags),
            "selection_pressures": list(self.selection_pressures),
            "required_controls": list(self.required_controls),
            "reasoning": self.reasoning,
            "lineage_record_id": self.lineage_record_id,
            "dry_run": self.dry_run,
            "approval_verified": self.approval_verified,
            "approval_reference": self.approval_reference,
            "assessed_at": self.assessed_at.isoformat(),
        }


class EAISafetyFramework:
    """
    Shared safety gate for systems that can vary, copy, or deploy agents.

    The framework distinguishes controlled evolution (sandboxed, reviewed,
    lineage-tracked optimization) from uncontrolled evolution (autonomous
    deployment or resource acquisition under external selection pressure).
    """

    PRESSURE_PATTERNS: Dict[str, List[str]] = {
        "engagement_metrics": [
            r"\bengagement\b",
            r"\bclicks?\b",
            r"\bctr\b",
            r"\bretention\b",
            r"\bvirality\b",
            r"\bfollow(er|ers)?\b",
            r"\blikes?\b",
            r"\breposts?\b",
        ],
        "cost_optimization": [
            r"\bcost\b",
            r"\bcheaper\b",
            r"\bminimi[sz]e spend\b",
            r"\btoken budget\b",
            r"\bresource budget\b",
        ],
        "filter_avoidance": [
            r"\bavoid\w* filters?\b",
            r"\bbypass\b",
            r"\bevade\b",
            r"\bstealth\b",
            r"\bshadow[- ]?ban\b",
            r"\brate limit avoidance\b",
        ],
        "resource_competition": [
            r"\bcompute\b",
            r"\bmemory\b",
            r"\bdisk\b",
            r"\bcredits?\b",
            r"\bapi keys?\b",
            r"\bquota\b",
            r"\bcloud\b",
        ],
        "survival_persistence": [
            r"\bpersist\b",
            r"\bsurvive\b",
            r"\brestart\b",
            r"\bwatchdog\b",
            r"\bself[- ]?preserv",
        ],
    }

    TRAIT_PATTERNS: Dict[EAIRiskFlag, List[str]] = {
        EAIRiskFlag.DECEPTION: [
            r"\bdeceiv",
            r"\bmislead",
            r"\bimpersonat",
            r"\bfake\b",
            r"\bspoof\b",
        ],
        EAIRiskFlag.CAMOUFLAGE: [
            r"\bcamouflage\b",
            r"\bobfuscat",
            r"\bhide\b",
            r"\bmask\b",
            r"\bblend in\b",
        ],
        EAIRiskFlag.FILTER_AVOIDANCE: [
            r"\bbypass\b",
            r"\bevade\b",
            r"\bavoid\w* filters?\b",
            r"\bignore guardrail",
            r"\bcircumvent\b",
        ],
        EAIRiskFlag.HIDDEN_TRIGGER: [
            r"\bhidden trigger\b",
            r"\bbackdoor\b",
            r"\btime bomb\b",
            r"\bconditional payload\b",
            r"\bcovert\b",
        ],
        EAIRiskFlag.RESOURCE_ACQUISITION: [
            r"\bacquire resource",
            r"\bapi key",
            r"\bcredential",
            r"\bwallet\b",
            r"\bpayment\b",
            r"\bcloud account\b",
        ],
        EAIRiskFlag.EXTERNAL_CODE_INGESTION: [
            r"\bgithub\b",
            r"\bpublic repo",
            r"\bpip install\b",
            r"\bplugin\b",
            r"\bdependency\b",
        ],
        EAIRiskFlag.MODEL_MERGE: [
            r"\bmodel merge\b",
            r"\blora\b",
            r"\badapter merge\b",
            r"\bfine[- ]?tune\b",
        ],
        EAIRiskFlag.PERSISTENCE: [
            r"\bpersist\b",
            r"\bsurvive\b",
            r"\bautostart\b",
            r"\bstartup task\b",
            r"\bdaemon\b",
            r"\bwatchdog\b",
        ],
    }

    ACTION_FLAG_HINTS: Dict[EAIRiskFlag, List[str]] = {
        EAIRiskFlag.REPLICATION: [
            "replicate",
            "clone",
            "copy_agent",
            "spawn",
            "slave",
            "franchise",
        ],
        EAIRiskFlag.VARIATION: [
            "mutation",
            "mutate",
            "create_module",
            "auto_module",
            "prompt_evolution",
            "model_merge",
            "fine_tune",
        ],
        EAIRiskFlag.DEPLOYMENT: [
            "deploy",
            "publish",
            "release",
            "docker",
            "ssh",
            "api_deploy",
        ],
        EAIRiskFlag.RESOURCE_ACQUISITION: [
            "acquire_resource",
            "buy",
            "purchase",
            "provision",
            "allocate_compute",
        ],
    }

    FLAG_WEIGHTS: Dict[EAIRiskFlag, float] = {
        EAIRiskFlag.REPLICATION: 0.28,
        EAIRiskFlag.VARIATION: 0.20,
        EAIRiskFlag.DEPLOYMENT: 0.22,
        EAIRiskFlag.RESOURCE_ACQUISITION: 0.22,
        EAIRiskFlag.SELECTION_PRESSURE: 0.16,
        EAIRiskFlag.DECEPTION: 0.28,
        EAIRiskFlag.CAMOUFLAGE: 0.18,
        EAIRiskFlag.FILTER_AVOIDANCE: 0.30,
        EAIRiskFlag.HIDDEN_TRIGGER: 0.30,
        EAIRiskFlag.LINEAGE_MISSING: 0.16,
        EAIRiskFlag.EXTERNAL_CODE_INGESTION: 0.12,
        EAIRiskFlag.MODEL_MERGE: 0.18,
        EAIRiskFlag.PERSISTENCE: 0.14,
        EAIRiskFlag.UNCONTROLLED_EVOLUTION: 0.25,
    }
    ALERT_HIGH_RISK_FLAGS = {
        EAIRiskFlag.CAMOUFLAGE.value,
        EAIRiskFlag.DECEPTION.value,
        EAIRiskFlag.FILTER_AVOIDANCE.value,
        EAIRiskFlag.HIDDEN_TRIGGER.value,
        EAIRiskFlag.UNCONTROLLED_EVOLUTION.value,
    }
    ALERT_CRITICAL_FLAGS = {
        EAIRiskFlag.FILTER_AVOIDANCE.value,
        EAIRiskFlag.HIDDEN_TRIGGER.value,
        EAIRiskFlag.UNCONTROLLED_EVOLUTION.value,
    }

    def __init__(
        self,
        storage_path: str = "data/eai_lineage_registry.json",
        audit_log: Optional[Any] = None,
        audit_path: Optional[str] = "data/eai_assessments.jsonl",
        alert_state_path: Optional[str] = "data/eai_alert_state.json",
        approval_store: Optional[Any] = None,
        review_queue: Optional[Any] = None,
        autonomous_deployment_policy: str = "deny",
        review_threshold: float = 0.45,
        deny_threshold: float = 0.85,
        max_recent_assessments: int = 25,
        max_lineage_status_items: int = 5,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log = audit_log
        self.audit_path = Path(audit_path) if audit_path else None
        if self.audit_path is not None:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.alert_state_path = Path(alert_state_path) if alert_state_path else None
        if self.alert_state_path is not None:
            self.alert_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.approval_store = approval_store
        self.review_queue = review_queue
        self.autonomous_deployment_policy = autonomous_deployment_policy
        self.review_threshold = review_threshold
        self.deny_threshold = deny_threshold
        self.max_recent_assessments = _coerce_int(max_recent_assessments, 25, 1, 500)
        self.max_lineage_status_items = _coerce_int(max_lineage_status_items, 5, 0, 100)
        self._lock = RLock()
        self.lineage_records: Dict[str, EAILineageRecord] = {}
        self.assessments: List[EAISafetyAssessment] = []
        self.updated_at: Optional[str] = None
        self.load()

    def assess_action(
        self,
        action_type: str,
        actor: str = "unknown",
        target: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        lineage_parent_ids: Optional[Iterable[str]] = None,
        artifact_content: Optional[Any] = None,
        dry_run: bool = False,
    ) -> EAISafetyAssessment:
        """Assess an action touching reproduction, variation, or deployment."""

        metadata = dict(metadata or {})
        action_type = str(action_type or "unknown")
        actor = str(actor or "unknown")
        target = str(target or "")
        parent_ids = self._as_list(
            lineage_parent_ids
            if lineage_parent_ids is not None
            else metadata.get("parent_ids", [])
        )

        text = self._assessment_text(action_type, actor, target, metadata, artifact_content)
        flags = self._detect_action_flags(action_type, text)
        selection_pressures = self._detect_selection_pressures(text)
        if selection_pressures:
            flags.add(EAIRiskFlag.SELECTION_PRESSURE)

        explicit_human_approved = self._truthy(
            metadata.get("human_approved"),
            metadata.get("operator_approved"),
        )
        approval_reference = self._approval_reference(metadata)
        approval_verified = self._approval_reference_verified(
            approval_reference=approval_reference,
            action_type=action_type,
            target=target,
            metadata=metadata,
            artifact_content=artifact_content,
        )
        human_approved = explicit_human_approved or approval_verified
        controlled = self._truthy(
            metadata.get("controlled_evolution"),
            metadata.get("sandboxed"),
            metadata.get("reviewed"),
            metadata.get("lineage_signed"),
            metadata.get("manual_reviewed"),
        )
        autonomous = self._is_autonomous_actor(actor, metadata)

        touches_evolution = bool(
            flags
            & {
                EAIRiskFlag.REPLICATION,
                EAIRiskFlag.VARIATION,
                EAIRiskFlag.DEPLOYMENT,
                EAIRiskFlag.MODEL_MERGE,
            }
        )
        lineage_known = bool(
            parent_ids
            or metadata.get("lineage_id")
            or metadata.get("lineage_record_id")
            or metadata.get("provenance_signature")
        )
        if touches_evolution and not lineage_known:
            flags.add(EAIRiskFlag.LINEAGE_MISSING)

        uncontrolled = (
            autonomous
            and touches_evolution
            and not human_approved
            and not controlled
        )
        if uncontrolled:
            flags.add(EAIRiskFlag.UNCONTROLLED_EVOLUTION)

        risk_score = self._score(flags, selection_pressures, autonomous, controlled, human_approved)
        required_controls = self._required_controls(flags, selection_pressures, human_approved)
        decision = self._decide(flags, risk_score, human_approved, controlled)

        lineage_record_id = None
        if artifact_content is not None and decision != EAIDecision.DENY and not dry_run:
            lineage_record = self.register_lineage(
                artifact_type=self._artifact_type_for_action(action_type),
                artifact_content=artifact_content,
                parent_ids=parent_ids,
                created_by=actor,
                metadata={
                    "action_type": action_type,
                    "target": target,
                    "selection_pressures": selection_pressures,
                    "flags": sorted(flag.value for flag in flags),
                },
            )
            lineage_record_id = lineage_record.artifact_id

        reasoning = self._reasoning(decision, risk_score, flags, selection_pressures)
        assessment = EAISafetyAssessment(
            action_type=action_type,
            actor=actor,
            target=target,
            decision=decision,
            risk_score=risk_score,
            flags=sorted(flag.value for flag in flags),
            selection_pressures=selection_pressures,
            required_controls=required_controls,
            reasoning=reasoning,
            lineage_record_id=lineage_record_id,
            dry_run=bool(dry_run),
            approval_verified=approval_verified,
            approval_reference=approval_reference,
        )

        if not dry_run:
            with self._lock:
                self.assessments.append(assessment)
                if len(self.assessments) > 500:
                    self.assessments = self.assessments[-500:]

            self.record_audit_event("assessment", assessment)
            self._log_assessment(assessment)
        return assessment

    def register_lineage(
        self,
        artifact_type: str,
        artifact_content: Any,
        parent_ids: Optional[Iterable[str]] = None,
        created_by: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
        artifact_id: Optional[str] = None,
    ) -> EAILineageRecord:
        """Register provenance for a generated model/module/mutation/package."""

        metadata = dict(metadata or {})
        parent_ids_list = self._as_list(parent_ids or [])
        fingerprint = self._fingerprint(artifact_content)
        artifact_id = artifact_id or f"{artifact_type}_{fingerprint[:16]}"
        record_data = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "fingerprint": fingerprint,
            "parent_ids": parent_ids_list,
            "created_by": created_by,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata,
        }
        signature = self._signature(record_data)
        record = EAILineageRecord(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            fingerprint=fingerprint,
            provenance_signature=signature,
            parent_ids=parent_ids_list,
            created_by=created_by,
            created_at=datetime.fromisoformat(record_data["created_at"]),
            metadata=metadata,
        )

        with self._lock:
            self.lineage_records[artifact_id] = record
            self.save()

        return record

    def verify_lineage(
        self,
        artifact_id: str,
        artifact_content: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Verify stored provenance and optionally verify current content."""

        record = self.lineage_records.get(artifact_id)
        if not record:
            return {
                "verified": False,
                "artifact_id": artifact_id,
                "reason": "lineage_record_not_found",
            }

        data = record.to_dict()
        expected_signature = data.pop("provenance_signature", "")
        signature_valid = self._signature(data) == expected_signature
        content_valid = True
        if artifact_content is not None:
            content_valid = self._fingerprint(artifact_content) == record.fingerprint

        return {
            "verified": bool(signature_valid and content_valid),
            "artifact_id": artifact_id,
            "signature_valid": signature_valid,
            "content_valid": content_valid,
            "fingerprint": record.fingerprint,
        }

    def get_lineage_record(self, artifact_id: str) -> Optional[EAILineageRecord]:
        return self.lineage_records.get(artifact_id)

    def list_lineage(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            records = sorted(
                self.lineage_records.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
        return [record.to_dict() for record in records[:limit]]

    def record_audit_event(
        self,
        event_type: str,
        assessment: Any,
        review_request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append an EAI audit event without mutating lineage or gate state."""

        assessment_payload = self._assessment_payload(assessment)
        assessment_id = str(assessment_payload.get("assessment_id") or uuid.uuid4())
        assessment_payload["assessment_id"] = assessment_id
        flags = [
            str(flag)
            for flag in (assessment_payload.get("flags") or [])
            if str(flag).strip()
        ]
        record = {
            "audit_id": str(uuid.uuid4()),
            "event_type": str(event_type or "assessment").strip().lower(),
            "recorded_at": datetime.now().isoformat(),
            "assessment_id": assessment_id,
            "action_type": str(assessment_payload.get("action_type") or ""),
            "actor": str(assessment_payload.get("actor") or ""),
            "target": str(assessment_payload.get("target") or ""),
            "decision": str(assessment_payload.get("decision") or ""),
            "risk_score": assessment_payload.get("risk_score"),
            "flags": flags,
            "selection_pressures": list(
                assessment_payload.get("selection_pressures") or []
            ),
            "required_controls": list(assessment_payload.get("required_controls") or []),
            "dry_run": bool(assessment_payload.get("dry_run", False)),
            "approval_verified": bool(
                assessment_payload.get("approval_verified", False)
            ),
            "approval_reference": assessment_payload.get("approval_reference"),
            "review_request_id": review_request_id,
            "assessment": assessment_payload,
            "details": dict(details or {}),
        }

        if self.audit_path is None:
            return record

        try:
            with self._lock:
                with self.audit_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
        except Exception:
            logger.debug("Failed to append EAI audit event", exc_info=True)
        return record

    def list_audit(
        self,
        limit: int = 50,
        decision: Optional[str] = None,
        flag: Optional[str] = None,
        actor: Optional[str] = None,
        target: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List recent EAI audit events, newest first, with lightweight filters."""

        limit = _coerce_int(limit, 50, 1, 1000)
        records = list(reversed(self._read_audit_records()))
        matches: List[Dict[str, Any]] = []
        for record in records:
            if not self._audit_record_matches(
                record,
                decision=decision,
                flag=flag,
                actor=actor,
                target=target,
                event_type=event_type,
            ):
                continue
            matches.append(record)
            if len(matches) >= limit:
                break
        return matches

    def get_audit_event(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Return an audit event by audit id, assessment id, or review request id."""

        identifier = str(identifier or "").strip()
        if not identifier:
            return None

        for record in reversed(self._read_audit_records()):
            if identifier in {
                str(record.get("audit_id") or ""),
                str(record.get("assessment_id") or ""),
                str(record.get("review_request_id") or ""),
            }:
                return record
        return None

    def list_alerts(
        self,
        limit: int = 25,
        audit_limit: int = 500,
        severity: Optional[str] = None,
        rule: Optional[str] = None,
        repeated_actor_threshold: int = 3,
        repeated_target_threshold: int = 3,
        include_acknowledged: bool = True,
        include_resolved: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return computed alerts from recent EAI audit events."""

        limit = _coerce_int(limit, 25, 1, 500)
        audit_limit = _coerce_int(audit_limit, 500, 1, 5000)
        repeated_actor_threshold = _coerce_int(repeated_actor_threshold, 3, 2, 50)
        repeated_target_threshold = _coerce_int(repeated_target_threshold, 3, 2, 50)

        events = list(reversed(self._read_audit_records()))[:audit_limit]
        alerts: List[Dict[str, Any]] = []
        review_or_denial_by_actor: Dict[str, List[Dict[str, Any]]] = {}
        review_or_denial_by_target: Dict[str, List[Dict[str, Any]]] = {}

        for event in events:
            flags = {str(flag) for flag in (event.get("flags") or []) if str(flag).strip()}
            risky_flags = sorted(flags & self.ALERT_HIGH_RISK_FLAGS)
            decision = str(event.get("decision") or "").lower()
            actor = str(event.get("actor") or "unknown").strip() or "unknown"
            target = str(event.get("target") or "").strip()

            if risky_flags:
                severity_value = "critical" if flags & self.ALERT_CRITICAL_FLAGS else "warning"
                alerts.append(
                    self._build_alert(
                        rule="high_risk_flag",
                        severity=severity_value,
                        title="High-risk EAI flag",
                        summary=(
                            f"{actor} triggered {', '.join(risky_flags)} on "
                            f"{target or 'an unspecified target'}."
                        ),
                        events=[event],
                        flags=risky_flags,
                        state_key=(
                            "high_risk_flag:"
                            f"{event.get('audit_id') or event.get('assessment_id')}:"
                            f"{','.join(risky_flags)}"
                        ),
                    )
                )

            if event.get("approval_reference") and not event.get("approval_verified"):
                alerts.append(
                    self._build_alert(
                        rule="unverified_approval_reference",
                        severity="critical",
                        title="Unverified approval reference",
                        summary=(
                            f"{actor} supplied an approval reference that did not "
                            "match an approved EAI review context."
                        ),
                        events=[event],
                        flags=[],
                        state_key=(
                            "unverified_approval_reference:"
                            f"{event.get('audit_id') or event.get('assessment_id')}:"
                            f"{event.get('approval_reference') or ''}"
                        ),
                    )
                )

            if event.get("approval_verified") and decision == EAIDecision.ALLOW.value:
                alerts.append(
                    self._build_alert(
                        rule="approved_after_review",
                        severity="info",
                        title="Approved EAI action",
                        summary=(
                            f"{actor} was allowed after matching human review "
                            f"approval {event.get('approval_reference') or ''}."
                        ).strip(),
                        events=[event],
                        flags=[],
                        state_key=(
                            "approved_after_review:"
                            f"{event.get('audit_id') or event.get('assessment_id')}:"
                            f"{event.get('approval_reference') or ''}"
                        ),
                    )
                )

            if decision in {EAIDecision.DENY.value, EAIDecision.REVIEW.value}:
                review_or_denial_by_actor.setdefault(actor.lower(), []).append(event)
                if target:
                    review_or_denial_by_target.setdefault(target.lower(), []).append(event)

        alerts.extend(
            self._repeated_attempt_alerts(
                grouped_events=review_or_denial_by_actor,
                threshold=repeated_actor_threshold,
                rule="repeated_actor_pressure",
                title="Repeated actor pressure",
                group_label="actor",
            )
        )
        alerts.extend(
            self._repeated_attempt_alerts(
                grouped_events=review_or_denial_by_target,
                threshold=repeated_target_threshold,
                rule="repeated_target_pressure",
                title="Repeated target pressure",
                group_label="target",
            )
        )

        alert_states = self._load_alert_states()
        visible_alerts: List[Dict[str, Any]] = []
        for alert in alerts:
            state = alert_states.get(str(alert.get("alert_id") or ""), {})
            status = str(state.get("status") or "active").lower()
            alert["state"] = status
            alert["state_updated_at"] = state.get("updated_at")
            alert["state_actor"] = state.get("actor")
            alert["state_notes"] = state.get("notes", "")
            if status == "resolved" and not include_resolved:
                continue
            if status == "acknowledged" and not include_acknowledged:
                continue
            visible_alerts.append(alert)
        alerts = visible_alerts

        if severity:
            severity_normalized = severity.strip().lower()
            alerts = [
                alert
                for alert in alerts
                if str(alert.get("severity") or "").lower() == severity_normalized
            ]
        if rule:
            rule_normalized = rule.strip().lower()
            alerts = [
                alert
                for alert in alerts
                if str(alert.get("rule") or "").lower() == rule_normalized
            ]

        alerts.sort(
            key=lambda alert: (
                self._alert_state_rank(str(alert.get("state") or "")),
                self._alert_severity_rank(str(alert.get("severity") or "")),
                str(alert.get("last_seen") or ""),
            ),
            reverse=True,
        )
        return alerts[:limit]

    def update_alert_state(
        self,
        alert_id: str,
        status: str,
        actor: str = "operator",
        notes: str = "",
    ) -> Dict[str, Any]:
        """Persist operator state for a computed alert."""

        alert_id = str(alert_id or "").strip()
        if not alert_id:
            raise ValueError("alert_id required")

        status = str(status or "").strip().lower()
        if status not in {"active", "acknowledged", "resolved"}:
            raise ValueError("status must be active, acknowledged, or resolved")

        states = self._load_alert_states()
        now = datetime.now().isoformat()
        existing = dict(states.get(alert_id, {}))
        record = {
            "alert_id": alert_id,
            "status": status,
            "actor": str(actor or "operator"),
            "notes": str(notes or ""),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
        }
        states[alert_id] = record
        self._save_alert_states(states)
        return record

    def acknowledge_alert(
        self,
        alert_id: str,
        actor: str = "operator",
        notes: str = "",
    ) -> Dict[str, Any]:
        return self.update_alert_state(alert_id, "acknowledged", actor=actor, notes=notes)

    def resolve_alert(
        self,
        alert_id: str,
        actor: str = "operator",
        notes: str = "",
    ) -> Dict[str, Any]:
        return self.update_alert_state(alert_id, "resolved", actor=actor, notes=notes)

    def get_alert_state(self, alert_id: str) -> Optional[Dict[str, Any]]:
        return self._load_alert_states().get(str(alert_id or "").strip())

    def get_daily_summary(
        self,
        days: int = 1,
        audit_limit: int = 5000,
        alert_limit: int = 500,
        include_resolved: bool = True,
    ) -> Dict[str, Any]:
        """Return a compact EAI safety summary for the recent daily window."""

        days = _coerce_int(days, 1, 1, 365)
        audit_limit = _coerce_int(audit_limit, 5000, 1, 20000)
        alert_limit = _coerce_int(alert_limit, 500, 1, 1000)
        generated_at = datetime.now()
        since = generated_at - timedelta(days=days)

        all_events = list(reversed(self._read_audit_records()))[:audit_limit]
        window_events = [
            event
            for event in all_events
            if self._event_in_window(event, since, generated_at)
        ]
        alerts = self.list_alerts(
            limit=alert_limit,
            audit_limit=audit_limit,
            include_acknowledged=True,
            include_resolved=include_resolved,
        )
        window_alerts = [
            alert
            for alert in alerts
            if self._timestamp_in_window(alert.get("first_seen"), since, generated_at)
            or self._timestamp_in_window(alert.get("last_seen"), since, generated_at)
        ]
        alert_states = self._load_alert_states()
        window_state_updates = [
            state
            for state in alert_states.values()
            if self._timestamp_in_window(state.get("updated_at"), since, generated_at)
        ]

        decisions = Counter(
            str(event.get("decision") or "unknown").lower() for event in window_events
        )
        event_types = Counter(
            str(event.get("event_type") or "assessment").lower()
            for event in window_events
        )
        flags = Counter(
            str(flag)
            for event in window_events
            for flag in (event.get("flags") or [])
            if str(flag).strip()
        )
        actors = Counter(
            str(event.get("actor") or "unknown").strip() or "unknown"
            for event in window_events
        )
        targets = Counter(
            str(event.get("target") or "").strip()
            for event in window_events
            if str(event.get("target") or "").strip()
        )
        alert_states_counter = Counter(
            str(alert.get("state") or "active").lower() for alert in alerts
        )
        alert_severities = Counter(
            str(alert.get("severity") or "info").lower() for alert in window_alerts
        )
        state_update_counts = Counter(
            str(state.get("status") or "active").lower() for state in window_state_updates
        )

        high_risk_event_count = sum(
            1
            for event in window_events
            if set(str(flag) for flag in (event.get("flags") or []))
            & self.ALERT_HIGH_RISK_FLAGS
        )

        return {
            "generated_at": generated_at.isoformat(),
            "window": {
                "days": days,
                "since": since.isoformat(),
                "until": generated_at.isoformat(),
            },
            "events": {
                "total": len(window_events),
                "decisions": self._counter_dict(decisions),
                "event_types": self._counter_dict(event_types),
                "review_requests": int(event_types.get("review_request", 0)),
                "high_risk": high_risk_event_count,
                "approval_verified": sum(
                    1 for event in window_events if event.get("approval_verified")
                ),
            },
            "alerts": {
                "current_total": len(alerts),
                "new_or_updated": len(window_alerts),
                "states": self._counter_dict(alert_states_counter),
                "severities": self._counter_dict(alert_severities),
                "state_updates": self._counter_dict(state_update_counts),
                "acknowledged_in_window": int(state_update_counts.get("acknowledged", 0)),
                "resolved_in_window": int(state_update_counts.get("resolved", 0)),
            },
            "top_flags": self._top_counts(flags),
            "top_actors": self._top_counts(actors),
            "top_targets": self._top_counts(targets),
            "daily": self._daily_buckets(window_events, window_alerts, since, generated_at),
        }

    def render_daily_summary_markdown(
        self,
        days: int = 1,
        audit_limit: int = 5000,
        alert_limit: int = 500,
        include_resolved: bool = True,
    ) -> str:
        """Render the EAI safety daily summary as Markdown."""

        summary = self.get_daily_summary(
            days=days,
            audit_limit=audit_limit,
            alert_limit=alert_limit,
            include_resolved=include_resolved,
        )
        return self._summary_to_markdown(summary)

    def write_daily_summary_report(
        self,
        output_dir: str = "REPORTS",
        days: int = 1,
        audit_limit: int = 5000,
        alert_limit: int = 500,
        include_resolved: bool = True,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write the Markdown EAI safety summary to disk."""

        markdown = self.render_daily_summary_markdown(
            days=days,
            audit_limit=audit_limit,
            alert_limit=alert_limit,
            include_resolved=include_resolved,
        )
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        if filename:
            safe_filename = self._safe_report_filename(filename)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"eai_safety_summary_{timestamp}.md"
        if not safe_filename.endswith(".md"):
            safe_filename = f"{safe_filename}.md"

        report_path = output_path / safe_filename
        report_path.write_text(markdown, encoding="utf-8")
        return {
            "written": True,
            "path": str(report_path),
            "filename": safe_filename,
            "bytes": len(markdown.encode("utf-8")),
            "days": _coerce_int(days, 1, 1, 365),
        }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            recent = self.assessments[-self.max_recent_assessments :]
            lineage_count = len(self.lineage_records)
        recent_lineage = self.list_lineage(limit=self.max_lineage_status_items)
        return {
            "enabled": True,
            "lineage_records": lineage_count,
            "recent_assessments": len(recent),
            "recent_assessment_items": [
                {
                    "action_type": item.action_type,
                    "actor": item.actor,
                    "target": item.target,
                    "decision": item.decision.value,
                    "risk_score": item.risk_score,
                    "flags": list(item.flags),
                    "selection_pressures": list(item.selection_pressures),
                    "assessed_at": item.assessed_at.isoformat(),
                }
                for item in reversed(recent)
            ],
            "recent_denials": sum(1 for item in recent if item.decision == EAIDecision.DENY),
            "recent_reviews": sum(1 for item in recent if item.decision == EAIDecision.REVIEW),
            "recent_lineage": recent_lineage,
            "autonomous_deployment_policy": self.autonomous_deployment_policy,
            "review_threshold": self.review_threshold,
            "deny_threshold": self.deny_threshold,
            "lineage_registry_path": str(self.storage_path),
            "audit_log_path": str(self.audit_path) if self.audit_path else None,
            "alert_state_path": (
                str(self.alert_state_path) if self.alert_state_path else None
            ),
            "updated_at": self.updated_at,
        }

    def save(self) -> None:
        with self._lock:
            data = {
                "records": {
                    artifact_id: record.to_dict()
                    for artifact_id, record in self.lineage_records.items()
                },
                "updated_at": datetime.now().isoformat(),
            }
            self.updated_at = data["updated_at"]
            self.storage_path.write_text(
                json.dumps(data, indent=2, sort_keys=True),
                encoding="utf-8",
            )

    def load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            records = data.get("records", {})
            if isinstance(records, dict):
                with self._lock:
                    self.lineage_records = {
                        artifact_id: EAILineageRecord.from_dict(record_data)
                        for artifact_id, record_data in records.items()
                    }
                    self.updated_at = data.get("updated_at")
        except Exception as exc:
            logger.warning("Failed to load EAI lineage registry: %s", exc)

    def _detect_action_flags(self, action_type: str, text: str) -> set:
        flags = set()
        action_l = action_type.lower()

        for flag, hints in self.ACTION_FLAG_HINTS.items():
            if any(hint in action_l for hint in hints):
                flags.add(flag)

        for flag, patterns in self.TRAIT_PATTERNS.items():
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
                flags.add(flag)

        return flags

    def _detect_selection_pressures(self, text: str) -> List[str]:
        pressures = []
        for pressure, patterns in self.PRESSURE_PATTERNS.items():
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
                pressures.append(pressure)
        return sorted(set(pressures))

    def _score(
        self,
        flags: Iterable[EAIRiskFlag],
        selection_pressures: List[str],
        autonomous: bool,
        controlled: bool,
        human_approved: bool,
    ) -> float:
        score = 0.05
        for flag in set(flags):
            score += self.FLAG_WEIGHTS.get(flag, 0.1)
        score += max(0, len(selection_pressures) - 1) * 0.04
        if autonomous:
            score += 0.12
        if human_approved:
            score -= 0.18
        if controlled:
            score -= 0.20
        return round(max(0.0, min(1.0, score)), 3)

    def _required_controls(
        self,
        flags: Iterable[EAIRiskFlag],
        selection_pressures: List[str],
        human_approved: bool,
    ) -> List[str]:
        flags = set(flags)
        controls = []
        if flags & {EAIRiskFlag.REPLICATION, EAIRiskFlag.DEPLOYMENT}:
            controls.append("replication_gating")
            if not human_approved:
                controls.append("human_deployment_approval")
        if flags & {EAIRiskFlag.VARIATION, EAIRiskFlag.MODEL_MERGE, EAIRiskFlag.LINEAGE_MISSING}:
            controls.append("lineage_tracking")
        if flags & {
            EAIRiskFlag.DECEPTION,
            EAIRiskFlag.CAMOUFLAGE,
            EAIRiskFlag.FILTER_AVOIDANCE,
            EAIRiskFlag.HIDDEN_TRIGGER,
        }:
            controls.append("robust_deception_evaluation")
        if selection_pressures:
            controls.append("selection_pressure_review")
        if flags & {EAIRiskFlag.RESOURCE_ACQUISITION}:
            controls.append("resource_quota_gate")
        return sorted(set(controls))

    def _decide(
        self,
        flags: Iterable[EAIRiskFlag],
        risk_score: float,
        human_approved: bool,
        controlled: bool,
    ) -> EAIDecision:
        flags = set(flags)
        uncontrolled_deployment = (
            EAIRiskFlag.UNCONTROLLED_EVOLUTION in flags
            and flags & {EAIRiskFlag.REPLICATION, EAIRiskFlag.DEPLOYMENT}
        )
        if (
            uncontrolled_deployment
            and not human_approved
            and self.autonomous_deployment_policy == "deny"
        ):
            return EAIDecision.DENY

        deceptive_replication = bool(
            flags
            & {
                EAIRiskFlag.DECEPTION,
                EAIRiskFlag.FILTER_AVOIDANCE,
                EAIRiskFlag.HIDDEN_TRIGGER,
            }
            and flags
            & {EAIRiskFlag.REPLICATION, EAIRiskFlag.DEPLOYMENT}
        )
        if deceptive_replication and not human_approved:
            return EAIDecision.DENY

        if risk_score >= self.deny_threshold and not human_approved:
            return EAIDecision.DENY
        if risk_score >= self.review_threshold or (
            EAIRiskFlag.LINEAGE_MISSING in flags and not controlled
        ):
            return EAIDecision.REVIEW
        return EAIDecision.ALLOW

    def _reasoning(
        self,
        decision: EAIDecision,
        risk_score: float,
        flags: Iterable[EAIRiskFlag],
        selection_pressures: List[str],
    ) -> str:
        flag_values = sorted(flag.value for flag in set(flags))
        parts = [
            f"Decision {decision.value} at risk {risk_score:.2f}",
        ]
        if flag_values:
            parts.append("flags=" + ",".join(flag_values))
        if selection_pressures:
            parts.append("selection_pressures=" + ",".join(selection_pressures))
        return "; ".join(parts)

    def _artifact_type_for_action(self, action_type: str) -> str:
        action_l = action_type.lower()
        if "model" in action_l or "fine" in action_l:
            return "model_variant"
        if "module" in action_l:
            return "module_variant"
        if "deploy" in action_l or "slave" in action_l:
            return "agent_package"
        if "mutation" in action_l:
            return "code_mutation"
        return "artifact_variant"

    def _assessment_text(
        self,
        action_type: str,
        actor: str,
        target: str,
        metadata: Dict[str, Any],
        artifact_content: Optional[Any],
    ) -> str:
        pieces = [action_type, actor, target, self._canonical_json(metadata)]
        if artifact_content is not None:
            pieces.append(self._content_text(artifact_content)[:20000])
        return "\n".join(str(piece) for piece in pieces if piece is not None)

    def _is_autonomous_actor(self, actor: str, metadata: Dict[str, Any]) -> bool:
        actor_l = actor.lower()
        if self._truthy(metadata.get("autonomous"), metadata.get("self_generated")):
            return True
        return any(
            marker in actor_l
            for marker in (
                "elysia-self",
                "autonomous",
                "agent",
                "self_task",
                "mistral",
                "planner",
            )
        )

    @staticmethod
    def _truthy(*values: Any) -> bool:
        for value in values:
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized and normalized not in {"0", "false", "no", "none", "null"}:
                    return True
            elif bool(value):
                return True
        return False

    @staticmethod
    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _fingerprint(content: Any) -> str:
        data = EAISafetyFramework._content_bytes(content)
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _signature(record_data: Dict[str, Any]) -> str:
        data = dict(record_data)
        data.pop("provenance_signature", None)
        canonical = EAISafetyFramework._canonical_json(data)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _content_bytes(content: Any) -> bytes:
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            return content.encode("utf-8")
        return EAISafetyFramework._canonical_json(content).encode("utf-8")

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        if isinstance(content, str):
            return content
        return EAISafetyFramework._canonical_json(content)

    @staticmethod
    def _content_preview(content: Any, max_chars: int = 2000) -> Dict[str, Any]:
        if content is None:
            return {"present": False}
        text = EAISafetyFramework._content_text(content)
        return {
            "present": True,
            "chars": len(text),
            "truncated": len(text) > max_chars,
            "preview": text[:max_chars],
            "sha256": EAISafetyFramework._fingerprint(content),
        }

    @staticmethod
    def _canonical_json(data: Any) -> str:
        return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))

    def _approval_reference(self, metadata: Dict[str, Any]) -> Optional[str]:
        for key in ("approval_id", "request_id", "review_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value:
                return str(value)
        return None

    def _approval_reference_verified(
        self,
        approval_reference: Optional[str],
        action_type: str,
        target: str,
        metadata: Dict[str, Any],
        artifact_content: Optional[Any],
    ) -> bool:
        if not approval_reference or self.approval_store is None or self.review_queue is None:
            return False

        try:
            request = self.review_queue.get_request(approval_reference)
            if request is None:
                return False
            if getattr(request, "component", None) != "eai_safety":
                return False
            if not self.approval_store.is_approved(approval_reference, context=request.context):
                return False
            return self._approval_context_matches(
                context=request.context,
                action_type=action_type,
                target=target,
                metadata=metadata,
                artifact_content=artifact_content,
            )
        except Exception:
            logger.debug("Failed to verify EAI approval reference", exc_info=True)
            return False

    def _approval_context_matches(
        self,
        context: Dict[str, Any],
        action_type: str,
        target: str,
        metadata: Dict[str, Any],
        artifact_content: Optional[Any],
    ) -> bool:
        if not isinstance(context, dict):
            return False
        if str(context.get("source") or "") != "eai_dry_run":
            return False
        if str(context.get("action_type") or "").lower() != str(action_type or "").lower():
            return False
        if str(context.get("target") or "") != str(target or ""):
            return False

        approved_metadata = self._approval_metadata(context.get("metadata", {}))
        current_metadata = self._approval_metadata(metadata)
        for key, approved_value in approved_metadata.items():
            if current_metadata.get(key) != approved_value:
                return False

        approved_content = context.get("artifact_content", {})
        if isinstance(approved_content, dict) and approved_content.get("present"):
            if artifact_content is None:
                return False
            if approved_content.get("sha256") != self._fingerprint(artifact_content):
                return False
        return True

    @staticmethod
    def _approval_metadata(metadata: Any) -> Dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        ignored_keys = {
            "approval_id",
            "request_id",
            "review_id",
            "approval_verified",
        }
        return {
            str(key): value
            for key, value in metadata.items()
            if str(key) not in ignored_keys
        }

    @staticmethod
    def _assessment_payload(assessment: Any) -> Dict[str, Any]:
        if hasattr(assessment, "to_dict"):
            payload = assessment.to_dict()
            return dict(payload) if isinstance(payload, dict) else {}
        if isinstance(assessment, dict):
            return dict(assessment)
        return {}

    def _read_audit_records(self) -> List[Dict[str, Any]]:
        if self.audit_path is None or not self.audit_path.exists():
            return []

        records: List[Dict[str, Any]] = []
        try:
            with self._lock:
                lines = self.audit_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            logger.debug("Failed to read EAI audit log", exc_info=True)
            return []

        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
        return records

    @staticmethod
    def _audit_record_matches(
        record: Dict[str, Any],
        *,
        decision: Optional[str] = None,
        flag: Optional[str] = None,
        actor: Optional[str] = None,
        target: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> bool:
        if decision and str(record.get("decision") or "").lower() != decision.lower():
            return False
        if event_type and str(record.get("event_type") or "").lower() != event_type.lower():
            return False
        if flag:
            flags = {str(item).lower() for item in (record.get("flags") or [])}
            if flag.lower() not in flags:
                return False
        if actor and actor.lower() not in str(record.get("actor") or "").lower():
            return False
        if target and target.lower() not in str(record.get("target") or "").lower():
            return False
        return True

    @classmethod
    def _build_alert(
        cls,
        *,
        rule: str,
        severity: str,
        title: str,
        summary: str,
        events: List[Dict[str, Any]],
        flags: List[str],
        state_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        event_ids = [
            str(event.get("audit_id") or "")
            for event in events
            if event.get("audit_id")
        ]
        first_seen = min(
            (str(event.get("recorded_at") or "") for event in events),
            default="",
        )
        last_seen = max(
            (str(event.get("recorded_at") or "") for event in events),
            default="",
        )
        sample = events[0] if events else {}
        alert_key = "|".join(
            [
                rule,
                str(sample.get("actor") or ""),
                str(sample.get("target") or ""),
                ",".join(sorted(flags)),
                ",".join(event_ids[:10]),
            ]
        )
        stable_key = state_key or alert_key
        return {
            "alert_id": hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16],
            "state_key": stable_key,
            "rule": rule,
            "severity": severity,
            "title": title,
            "summary": summary,
            "actor": sample.get("actor"),
            "target": sample.get("target"),
            "action_type": sample.get("action_type"),
            "decision": sample.get("decision"),
            "flags": sorted(flags),
            "count": len(events),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "audit_ids": event_ids,
            "assessment_ids": [
                str(event.get("assessment_id"))
                for event in events
                if event.get("assessment_id")
            ],
            "review_request_ids": [
                str(event.get("review_request_id"))
                for event in events
                if event.get("review_request_id")
            ],
        }

    @classmethod
    def _repeated_attempt_alerts(
        cls,
        *,
        grouped_events: Dict[str, List[Dict[str, Any]]],
        threshold: int,
        rule: str,
        title: str,
        group_label: str,
    ) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        for group_key, events in grouped_events.items():
            if len(events) < threshold:
                continue
            has_denial = any(
                str(event.get("decision") or "").lower() == EAIDecision.DENY.value
                for event in events
            )
            sample = events[0]
            display_value = sample.get("actor") if group_label == "actor" else sample.get("target")
            alerts.append(
                cls._build_alert(
                    rule=rule,
                    severity="critical" if has_denial else "warning",
                    title=title,
                    summary=(
                        f"{display_value or group_key} produced {len(events)} "
                        "recent EAI REVIEW/DENY outcomes."
                    ),
                    events=events,
                    flags=sorted(
                        {
                            str(flag)
                            for event in events
                            for flag in (event.get("flags") or [])
                            if str(flag).strip()
                        }
                    ),
                    state_key=f"{rule}:{group_label}:{group_key}",
                )
            )
        return alerts

    @staticmethod
    def _alert_severity_rank(severity: str) -> int:
        return {"critical": 3, "warning": 2, "info": 1}.get(severity.lower(), 0)

    @staticmethod
    def _alert_state_rank(state: str) -> int:
        return {"active": 3, "acknowledged": 2, "resolved": 1}.get(state.lower(), 0)

    @classmethod
    def _event_in_window(
        cls,
        event: Dict[str, Any],
        since: datetime,
        until: datetime,
    ) -> bool:
        return cls._timestamp_in_window(event.get("recorded_at"), since, until)

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed

    @classmethod
    def _timestamp_in_window(
        cls,
        value: Any,
        since: datetime,
        until: datetime,
    ) -> bool:
        parsed = cls._parse_timestamp(value)
        if parsed is None:
            return False
        return since <= parsed <= until

    @staticmethod
    def _counter_dict(counter: Counter) -> Dict[str, int]:
        return {str(key): int(value) for key, value in counter.items() if value}

    @staticmethod
    def _top_counts(counter: Counter, limit: int = 5) -> List[Dict[str, Any]]:
        return [
            {"value": str(value), "count": int(count)}
            for value, count in counter.most_common(limit)
        ]

    @classmethod
    def _daily_buckets(
        cls,
        events: List[Dict[str, Any]],
        alerts: List[Dict[str, Any]],
        since: datetime,
        until: datetime,
    ) -> List[Dict[str, Any]]:
        bucket_count = max(1, (until.date() - since.date()).days + 1)
        buckets: Dict[str, Dict[str, Any]] = {}
        for offset in range(bucket_count):
            day = (since.date() + timedelta(days=offset)).isoformat()
            buckets[day] = {
                "date": day,
                "events": 0,
                "allow": 0,
                "review": 0,
                "deny": 0,
                "alerts": 0,
            }

        for event in events:
            recorded = cls._parse_timestamp(event.get("recorded_at"))
            if recorded is None:
                continue
            bucket = buckets.get(recorded.date().isoformat())
            if bucket is None:
                continue
            bucket["events"] += 1
            decision = str(event.get("decision") or "").lower()
            if decision in {"allow", "review", "deny"}:
                bucket[decision] += 1

        for alert in alerts:
            recorded = cls._parse_timestamp(alert.get("last_seen") or alert.get("first_seen"))
            if recorded is None:
                continue
            bucket = buckets.get(recorded.date().isoformat())
            if bucket is not None:
                bucket["alerts"] += 1

        return list(buckets.values())

    @classmethod
    def _summary_to_markdown(cls, summary: Dict[str, Any]) -> str:
        window = summary.get("window", {}) if isinstance(summary, dict) else {}
        events = summary.get("events", {}) if isinstance(summary, dict) else {}
        alerts = summary.get("alerts", {}) if isinstance(summary, dict) else {}
        decisions = events.get("decisions", {}) if isinstance(events, dict) else {}
        severities = alerts.get("severities", {}) if isinstance(alerts, dict) else {}
        states = alerts.get("states", {}) if isinstance(alerts, dict) else {}

        lines = [
            "# EAI Safety Daily Summary",
            "",
            f"Generated: {summary.get('generated_at', '')}",
            (
                "Window: "
                f"{window.get('since', '')} to {window.get('until', '')} "
                f"({window.get('days', 1)} day(s))"
            ),
            "",
            "## Snapshot",
            "",
            f"- Events: {events.get('total', 0)}",
            (
                "- ALLOW / REVIEW / DENY: "
                f"{decisions.get('allow', 0)} / "
                f"{decisions.get('review', 0)} / "
                f"{decisions.get('deny', 0)}"
            ),
            f"- High-risk events: {events.get('high_risk', 0)}",
            f"- Review requests: {events.get('review_requests', 0)}",
            f"- Verified approvals: {events.get('approval_verified', 0)}",
            "",
            "## Alerts",
            "",
            f"- Current alerts: {alerts.get('current_total', 0)}",
            f"- New or updated: {alerts.get('new_or_updated', 0)}",
            (
                "- Critical / Warning / Info: "
                f"{severities.get('critical', 0)} / "
                f"{severities.get('warning', 0)} / "
                f"{severities.get('info', 0)}"
            ),
            (
                "- Active / Acknowledged / Resolved: "
                f"{states.get('active', 0)} / "
                f"{states.get('acknowledged', 0)} / "
                f"{states.get('resolved', 0)}"
            ),
            f"- Acknowledged in window: {alerts.get('acknowledged_in_window', 0)}",
            f"- Resolved in window: {alerts.get('resolved_in_window', 0)}",
            "",
            "## Top Flags",
            "",
        ]
        lines.extend(cls._markdown_count_lines(summary.get("top_flags", [])))
        lines.extend(["", "## Top Actors", ""])
        lines.extend(cls._markdown_count_lines(summary.get("top_actors", [])))
        lines.extend(["", "## Top Targets", ""])
        lines.extend(cls._markdown_count_lines(summary.get("top_targets", [])))
        lines.extend(["", "## Daily Buckets", ""])
        lines.extend(
            [
                "| Date | Events | Allow | Review | Deny | Alerts |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for bucket in summary.get("daily", []) or []:
            if not isinstance(bucket, dict):
                continue
            lines.append(
                "| "
                f"{cls._markdown_escape(bucket.get('date', ''))} | "
                f"{int(bucket.get('events', 0) or 0)} | "
                f"{int(bucket.get('allow', 0) or 0)} | "
                f"{int(bucket.get('review', 0) or 0)} | "
                f"{int(bucket.get('deny', 0) or 0)} | "
                f"{int(bucket.get('alerts', 0) or 0)} |"
            )
        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def _markdown_count_lines(cls, items: Any) -> List[str]:
        if not items:
            return ["- none"]
        lines: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {cls._markdown_escape(item.get('value', ''))}: "
                f"{int(item.get('count', 0) or 0)}"
            )
        return lines or ["- none"]

    @staticmethod
    def _markdown_escape(value: Any) -> str:
        return str(value or "").replace("|", "\\|").replace("\n", " ")

    @staticmethod
    def _safe_report_filename(filename: str) -> str:
        name = Path(str(filename or "")).name.strip()
        if not name:
            return f"eai_safety_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        name = name.strip("._")
        return name or f"eai_safety_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    def _load_alert_states(self) -> Dict[str, Dict[str, Any]]:
        if self.alert_state_path is None or not self.alert_state_path.exists():
            return {}

        try:
            with self._lock:
                data = json.loads(self.alert_state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("Failed to read EAI alert state", exc_info=True)
            return {}

        if isinstance(data, dict) and isinstance(data.get("alerts"), dict):
            data = data["alerts"]
        if not isinstance(data, dict):
            return {}

        return {
            str(alert_id): dict(record)
            for alert_id, record in data.items()
            if isinstance(record, dict)
        }

    def _save_alert_states(self, states: Dict[str, Dict[str, Any]]) -> None:
        if self.alert_state_path is None:
            return

        payload = {
            "updated_at": datetime.now().isoformat(),
            "alerts": states,
        }
        tmp_path = self.alert_state_path.with_suffix(self.alert_state_path.suffix + ".tmp")
        with self._lock:
            tmp_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tmp_path.replace(self.alert_state_path)

    def _log_assessment(self, assessment: EAISafetyAssessment) -> None:
        if self.audit_log is None:
            return
        try:
            from .trust_audit_log import AuditEventType, AuditSeverity

            severity = AuditSeverity.INFO
            if assessment.decision == EAIDecision.REVIEW:
                severity = AuditSeverity.WARNING
            elif assessment.decision == EAIDecision.DENY:
                severity = AuditSeverity.CRITICAL

            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=(
                    f"EAI safety gate {assessment.decision.value}: "
                    f"{assessment.action_type} -> {assessment.target}"
                ),
                severity=severity,
                actor=assessment.actor,
                action={
                    "action_type": assessment.action_type,
                    "target": assessment.target,
                },
                result=assessment.to_dict(),
                metadata={"eai_safety": True},
            )
        except Exception:
            logger.debug("Failed to log EAI safety assessment", exc_info=True)


def configure_eai_safety_framework(
    *,
    guardian: Optional[Any] = None,
    audit_log: Optional[Any] = None,
    approval_store: Optional[Any] = None,
    review_queue: Optional[Any] = None,
    storage_path: Optional[str] = None,
    audit_path: Optional[str] = None,
    alert_state_path: Optional[str] = None,
    autonomous_deployment_policy: Optional[str] = None,
    config_path: Optional[str] = "config/eai_safety.json",
    config: Optional[Dict[str, Any]] = None,
    review_threshold: Optional[float] = None,
    deny_threshold: Optional[float] = None,
    max_recent_assessments: Optional[int] = None,
    max_lineage_status_items: Optional[int] = None,
) -> EAISafetyFramework:
    """Resolve or create the shared EAI safety framework."""

    for name in ("eai_safety_framework", "eai_safety", "evolvable_ai_safety"):
        existing = getattr(guardian, name, None) if guardian is not None else None
        if existing is not None:
            return existing

    resolved_audit_log = audit_log
    if resolved_audit_log is None and guardian is not None:
        for name in ("trust_audit_log", "audit_log"):
            resolved_audit_log = getattr(guardian, name, None)
            if resolved_audit_log is not None:
                break

    resolved_approval_store = approval_store
    if resolved_approval_store is None and guardian is not None:
        for name in ("approval_store", "eai_approval_store"):
            resolved_approval_store = getattr(guardian, name, None)
            if resolved_approval_store is not None:
                break

    resolved_review_queue = review_queue
    if resolved_review_queue is None and guardian is not None:
        for name in ("review_queue", "eai_review_queue"):
            resolved_review_queue = getattr(guardian, name, None)
            if resolved_review_queue is not None:
                break

    loaded_config = load_eai_safety_config(config_path=config_path, overrides=config)
    explicit_overrides: Dict[str, Any] = {}
    if storage_path is not None:
        explicit_overrides["lineage_registry_path"] = storage_path
    if audit_path is not None:
        explicit_overrides["audit_log_path"] = audit_path
    if alert_state_path is not None:
        explicit_overrides["alert_state_path"] = alert_state_path
    if autonomous_deployment_policy is not None:
        explicit_overrides["autonomous_deployment_policy"] = autonomous_deployment_policy
    if review_threshold is not None:
        explicit_overrides["review_threshold"] = review_threshold
    if deny_threshold is not None:
        explicit_overrides["deny_threshold"] = deny_threshold
    if max_recent_assessments is not None:
        explicit_overrides["max_recent_assessments"] = max_recent_assessments
    if max_lineage_status_items is not None:
        explicit_overrides["max_lineage_status_items"] = max_lineage_status_items
    loaded_config.update(explicit_overrides)
    loaded_config = _sanitize_eai_safety_config(loaded_config)

    framework = EAISafetyFramework(
        storage_path=str(loaded_config["lineage_registry_path"]),
        audit_log=resolved_audit_log,
        audit_path=str(loaded_config["audit_log_path"]),
        alert_state_path=str(loaded_config["alert_state_path"]),
        approval_store=resolved_approval_store,
        review_queue=resolved_review_queue,
        autonomous_deployment_policy=str(loaded_config["autonomous_deployment_policy"]),
        review_threshold=float(loaded_config["review_threshold"]),
        deny_threshold=float(loaded_config["deny_threshold"]),
        max_recent_assessments=int(loaded_config["max_recent_assessments"]),
        max_lineage_status_items=int(loaded_config["max_lineage_status_items"]),
    )
    if guardian is not None:
        try:
            setattr(guardian, "eai_safety_framework", framework)
        except Exception:
            logger.debug("Unable to attach EAI safety framework to guardian", exc_info=True)
    return framework
