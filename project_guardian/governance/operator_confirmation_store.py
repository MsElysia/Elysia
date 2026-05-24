"""Data-only operator confirmation records for future live-execution gates.

The store persists structured confirmation records and validates record state
such as expiry, single use, trace/action binding, and governance exclusions.
It does not execute tools, wire autonomy, call models, or contact services.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


DEFAULT_CONFIRMATIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "runtime"
    / "operator_confirmations.jsonl"
)

CONFIRMATION_NOT_FOUND = "confirmation_not_found"
CONFIRMATION_EXPIRED = "confirmation_expired"
CONFIRMATION_ALREADY_USED = "confirmation_already_used"
CONFIRMATION_REVOKED = "confirmation_revoked"
DRY_RUN_TRACE_MISMATCH = "dry_run_trace_mismatch"
CONFIRMED_ACTION_MISMATCH = "confirmed_action_mismatch"
HIGH_RISK_DENIED = "high_risk_denied"
BLOCKED_RISK_DENIED = "blocked_risk_denied"
AUTONOMY_CONTEXT_DENIED = "autonomy_context_denied"
SELF_MODIFICATION_SEPARATE_WORKFLOW_REQUIRED = (
    "self_modification_separate_workflow_required"
)
MEDIUM_RISK_APPROVAL_REQUIRED = "medium_risk_approval_required"
INVALID_TIMESTAMP = "invalid_timestamp"

_VALID_RISK = frozenset({"low", "medium", "high", "blocked"})
_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|credential)\s*[:=]\s*([^\s,;]+)"
)
_BEARER_SECRET_RE = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+([^\s,;]+)")
_SK_SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
    "authorization",
    "message",
    "prompt",
    "content",
    "raw",
)


@dataclass(frozen=True)
class OperatorConfirmationRecord:
    confirmation_id: str
    created_at: str
    expires_at: str
    dry_run_trace_id: str
    dry_run_trace_completed_at: str
    confirmed_action_id: str
    requested_action_summary: str
    requested_tool_name: str
    requested_action_type: str
    risk_level: str = "blocked"
    medium_risk_approved: bool = False
    executor_allowlist: Tuple[str, ...] = field(default_factory=tuple)
    rollback_available: bool = False
    rollback_plan_id: str = ""
    self_modification: bool = False
    self_modification_workflow_id: str = ""
    autonomy_context: bool = False
    conversation_id: str = ""
    source_entrypoint: str = "operator_chat"
    operator_id: str = ""
    status: str = "pending"
    used_at: str = ""
    revoked_at: str = ""
    revoke_reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def operator_confirmation_id(self) -> str:
        return self.confirmation_id

    @property
    def action_summary(self) -> str:
        return self.requested_action_summary

    @property
    def action_type(self) -> str:
        return self.requested_action_type

    @property
    def tool_name(self) -> str:
        return self.requested_tool_name

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["executor_allowlist"] = list(self.executor_allowlist)
        data["metadata"] = dict(self.metadata or {})
        data["operator_confirmation_id"] = self.confirmation_id
        data["action_summary"] = self.requested_action_summary
        data["action_type"] = self.requested_action_type
        data["tool_name"] = self.requested_tool_name
        return data

    def to_live_guard_context_fields(self) -> Dict[str, Any]:
        """Return context keys already understood by the live-execution guard."""
        return {
            "operator_confirmed": True,
            "operator_confirmation_id": self.confirmation_id,
            "dry_run_trace_id": self.dry_run_trace_id,
            "dry_run_trace_completed_at": self.dry_run_trace_completed_at,
            "live_execution_request_id": self.confirmation_id,
            "live_execution_risk_level": self.risk_level,
            "risk_level": self.risk_level,
            "live_execution_action_type": self.requested_action_type,
            "live_execution_target": self.requested_action_summary,
            "requested_action_summary": self.requested_action_summary,
            "live_execution_executor": self.requested_tool_name,
            "live_execution_tool_name": self.requested_tool_name,
            "executor_allowlist": list(self.executor_allowlist),
            "executor_allowlisted": bool(
                self.requested_tool_name and self.requested_tool_name in self.executor_allowlist
            ),
            "explicit_medium_risk_approval": self.medium_risk_approved,
            "medium_risk_approved": self.medium_risk_approved,
            "rollback_available": self.rollback_available,
            "rollback_plan_id": self.rollback_plan_id,
            "is_self_modification": self.self_modification,
            "self_modification": self.self_modification,
            "is_autonomy_context": self.autonomy_context,
            "autonomy_context": self.autonomy_context,
            "source_entrypoint": self.source_entrypoint,
        }


@dataclass(frozen=True)
class OperatorConfirmationValidation:
    valid: bool
    reasons: Tuple[str, ...] = field(default_factory=tuple)
    confirmation_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_risk(value: Any) -> str:
    risk = str(value or "blocked").strip().lower()
    return risk if risk in _VALID_RISK else "blocked"


def redact_confirmation_text(value: Any, *, limit: int = 2000) -> str:
    text = str(value or "")
    text = _KEY_VALUE_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _BEARER_SECRET_RE.sub("Authorization: Bearer [REDACTED]", text)
    text = _SK_SECRET_RE.sub("sk-[REDACTED]", text)
    return text[:limit]


def _is_sensitive_key(key: str) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def sanitize_confirmation_value(key: str, value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if _is_sensitive_key(key):
        return None if value is None else "[redacted]"
    if isinstance(value, str):
        return redact_confirmation_text(value, limit=2000)
    if isinstance(value, Mapping):
        return {
            str(k)[:80]: sanitize_confirmation_value(str(k), v, depth=depth + 1)
            for k, v in list(value.items())[:50]
        }
    if isinstance(value, (list, tuple)):
        return [
            sanitize_confirmation_value(key, item, depth=depth + 1)
            for item in list(value)[:50]
        ]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return redact_confirmation_text(value, limit=500)


def _record_from_dict(data: Mapping[str, Any]) -> OperatorConfirmationRecord:
    allowlist = data.get("executor_allowlist") or ()
    if isinstance(allowlist, str):
        allowlist = (allowlist,)
    elif isinstance(allowlist, Iterable):
        allowlist = tuple(str(item) for item in allowlist if str(item).strip())
    else:
        allowlist = ()
    metadata = data.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    return OperatorConfirmationRecord(
        confirmation_id=str(data.get("confirmation_id") or data.get("operator_confirmation_id") or ""),
        created_at=str(data.get("created_at") or ""),
        expires_at=str(data.get("expires_at") or ""),
        dry_run_trace_id=str(data.get("dry_run_trace_id") or ""),
        dry_run_trace_completed_at=str(data.get("dry_run_trace_completed_at") or ""),
        confirmed_action_id=str(data.get("confirmed_action_id") or ""),
        requested_action_summary=str(data.get("requested_action_summary") or data.get("action_summary") or ""),
        requested_tool_name=str(data.get("requested_tool_name") or data.get("tool_name") or ""),
        requested_action_type=str(data.get("requested_action_type") or data.get("action_type") or ""),
        risk_level=_normalize_risk(data.get("risk_level")),
        medium_risk_approved=bool(data.get("medium_risk_approved")),
        executor_allowlist=tuple(allowlist),
        rollback_available=bool(data.get("rollback_available")),
        rollback_plan_id=str(data.get("rollback_plan_id") or ""),
        self_modification=bool(data.get("self_modification")),
        self_modification_workflow_id=str(data.get("self_modification_workflow_id") or ""),
        autonomy_context=bool(data.get("autonomy_context")),
        conversation_id=str(data.get("conversation_id") or ""),
        source_entrypoint=str(data.get("source_entrypoint") or "operator_chat"),
        operator_id=str(data.get("operator_id") or ""),
        status=str(data.get("status") or "pending"),
        used_at=str(data.get("used_at") or ""),
        revoked_at=str(data.get("revoked_at") or ""),
        revoke_reason=str(data.get("revoke_reason") or ""),
        metadata=dict(metadata),
    )


class OperatorConfirmationStore:
    """Append-only JSONL store for operator confirmation records."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path or DEFAULT_CONFIRMATIONS_PATH)
        self.store_path = self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create_operator_confirmation(
        self,
        *,
        operator_id: str,
        conversation_id: str,
        dry_run_trace_id: str,
        confirmed_action_id: str,
        action_summary: str,
        action_type: str,
        tool_name: str,
        risk_level: str = "low",
        executor_allowlisted: bool = False,
        rollback_available: bool = False,
        prompt_contract_valid: bool = True,
        ttl_seconds: float = 900.0,
        now: Optional[Any] = None,
        confirmation_id: Optional[str] = None,
        medium_risk_approved: bool = False,
        autonomy_context: bool = False,
        self_modification: bool = False,
        allow_self_modification_workflow: bool = False,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[Optional[OperatorConfirmationRecord], List[str]]:
        errors: List[str] = []
        risk = _normalize_risk(risk_level)
        if risk in {"high", "blocked"}:
            errors.append("risk_not_confirmable")
        if autonomy_context:
            errors.append("autonomy_context")
        if self_modification and not allow_self_modification_workflow:
            errors.append("self_modification")
        if not prompt_contract_valid:
            errors.append("prompt_contract_invalid")
        if errors:
            return None, errors

        executor_allowlist = [tool_name] if executor_allowlisted else []
        record = self.create_confirmation(
            dry_run_trace_id=dry_run_trace_id,
            confirmed_action_id=confirmed_action_id,
            requested_action_summary=action_summary,
            requested_tool_name=tool_name,
            requested_action_type=action_type,
            risk_level=risk,
            ttl_seconds=int(ttl_seconds),
            now=now,
            confirmation_id=confirmation_id,
            medium_risk_approved=medium_risk_approved,
            executor_allowlist=executor_allowlist,
            rollback_available=rollback_available,
            self_modification=self_modification,
            self_modification_workflow_id="separate_workflow_ack"
            if self_modification and allow_self_modification_workflow
            else "",
            autonomy_context=autonomy_context,
            conversation_id=conversation_id,
            source_entrypoint="operator_chat",
            operator_id=operator_id,
            metadata=metadata,
        )
        return record, []

    def get_operator_confirmation(
        self,
        confirmation_id: str,
        *,
        now: Optional[Any] = None,
    ) -> Optional[OperatorConfirmationRecord]:
        _ = now
        return self.get_confirmation(confirmation_id)

    def mark_operator_confirmation_used(
        self,
        confirmation_id: str,
        *,
        now: Optional[Any] = None,
    ) -> Tuple[Optional[OperatorConfirmationRecord], str]:
        record = self.mark_used(confirmation_id, used_at=now)
        return record, "ok" if record is not None else "not_found"

    def revoke_operator_confirmation(
        self,
        confirmation_id: str,
        *,
        now: Optional[Any] = None,
        reason: str = "",
    ) -> Tuple[Optional[OperatorConfirmationRecord], str]:
        record = self.revoke(confirmation_id, revoked_at=now, reason=reason)
        return record, "ok" if record is not None else "not_found"

    def is_confirmation_valid_for_request(
        self,
        confirmation_id: str,
        *,
        dry_run_trace_id: str,
        confirmed_action_id: str,
        medium_risk_approved: Optional[bool] = None,
        allow_self_modification_workflow: bool = False,
        now: Optional[Any] = None,
    ) -> Tuple[bool, str]:
        record = self.get_confirmation(confirmation_id)
        if record is None:
            return False, "not_found"
        validation = self.validate_confirmation(
            confirmation_id,
            dry_run_trace_id=dry_run_trace_id,
            confirmed_action_id=confirmed_action_id,
            now=now,
            allow_self_modification_workflow=allow_self_modification_workflow,
            medium_risk_approved=medium_risk_approved,
        )
        if validation.valid:
            return True, "valid"
        return False, _public_reason(validation.reasons[0])

    def list_operator_confirmations(
        self,
        *,
        conversation_id: str = "",
        limit: int = 50,
        now: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        _ = now
        rows = self.list_confirmations(sanitized=True)
        if conversation_id:
            rows = [
                row for row in rows if str(row.get("conversation_id") or "") == conversation_id
            ]
        return rows[: max(0, int(limit or 0))]

    def create_confirmation(
        self,
        *,
        dry_run_trace_id: str,
        confirmed_action_id: str,
        requested_action_summary: str,
        requested_tool_name: str,
        requested_action_type: str = "capability_invoke",
        risk_level: str = "low",
        ttl_seconds: int = 900,
        now: Optional[Any] = None,
        expires_at: Optional[Any] = None,
        dry_run_trace_completed_at: Optional[Any] = None,
        confirmation_id: Optional[str] = None,
        medium_risk_approved: bool = False,
        executor_allowlist: Optional[Iterable[str]] = None,
        rollback_available: bool = False,
        rollback_plan_id: str = "",
        self_modification: bool = False,
        self_modification_workflow_id: str = "",
        autonomy_context: bool = False,
        conversation_id: str = "",
        source_entrypoint: str = "operator_chat",
        operator_id: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> OperatorConfirmationRecord:
        base_time = _coerce_datetime(now) or _utc_now()
        expires_dt = _coerce_datetime(expires_at) or (
            base_time + timedelta(seconds=max(1, int(ttl_seconds or 1)))
        )
        trace_dt = _coerce_datetime(dry_run_trace_completed_at) or base_time
        cid = str(confirmation_id or f"conf_{uuid.uuid4().hex[:24]}")[:120]
        allowlist = tuple(str(item)[:120] for item in (executor_allowlist or ()) if str(item).strip())
        record = OperatorConfirmationRecord(
            confirmation_id=cid,
            created_at=_iso(base_time),
            expires_at=_iso(expires_dt),
            dry_run_trace_id=str(dry_run_trace_id or "")[:120],
            dry_run_trace_completed_at=_iso(trace_dt),
            confirmed_action_id=str(confirmed_action_id or "")[:160],
            requested_action_summary=redact_confirmation_text(requested_action_summary, limit=1000),
            requested_tool_name=redact_confirmation_text(requested_tool_name, limit=120),
            requested_action_type=redact_confirmation_text(requested_action_type, limit=120),
            risk_level=_normalize_risk(risk_level),
            medium_risk_approved=bool(medium_risk_approved),
            executor_allowlist=allowlist,
            rollback_available=bool(rollback_available),
            rollback_plan_id=redact_confirmation_text(rollback_plan_id, limit=120),
            self_modification=bool(self_modification),
            self_modification_workflow_id=redact_confirmation_text(
                self_modification_workflow_id, limit=120
            ),
            autonomy_context=bool(autonomy_context),
            conversation_id=redact_confirmation_text(conversation_id, limit=120),
            source_entrypoint=redact_confirmation_text(source_entrypoint, limit=120)
            or "operator_chat",
            operator_id=redact_confirmation_text(operator_id, limit=120),
            metadata=sanitize_confirmation_value("metadata", dict(metadata or {})),
        )
        self._append_event("created", record.to_dict())
        return record

    def get_confirmation(self, confirmation_id: str) -> Optional[OperatorConfirmationRecord]:
        return self._load_records().get(str(confirmation_id or ""))

    def mark_used(
        self,
        confirmation_id: str,
        *,
        used_at: Optional[Any] = None,
    ) -> Optional[OperatorConfirmationRecord]:
        existing = self.get_confirmation(confirmation_id)
        if existing is None:
            return None
        stamp = _iso(_coerce_datetime(used_at) or _utc_now())
        self._append_event("used", {"confirmation_id": existing.confirmation_id, "used_at": stamp})
        return self.get_confirmation(confirmation_id)

    def revoke(
        self,
        confirmation_id: str,
        *,
        revoked_at: Optional[Any] = None,
        reason: str = "",
    ) -> Optional[OperatorConfirmationRecord]:
        existing = self.get_confirmation(confirmation_id)
        if existing is None:
            return None
        stamp = _iso(_coerce_datetime(revoked_at) or _utc_now())
        self._append_event(
            "revoked",
            {
                "confirmation_id": existing.confirmation_id,
                "revoked_at": stamp,
                "revoke_reason": redact_confirmation_text(reason, limit=500),
            },
        )
        return self.get_confirmation(confirmation_id)

    def validate_confirmation(
        self,
        confirmation_id: str,
        *,
        dry_run_trace_id: str,
        confirmed_action_id: str,
        allow_self_modification_workflow: bool = False,
        medium_risk_approved: Optional[bool] = None,
        now: Optional[Any] = None,
    ) -> OperatorConfirmationValidation:
        record = self.get_confirmation(confirmation_id)
        cid = str(confirmation_id or "")
        if record is None:
            return OperatorConfirmationValidation(False, (CONFIRMATION_NOT_FOUND,), cid)

        reasons: List[str] = []
        expires_at = _coerce_datetime(record.expires_at)
        check_time = _coerce_datetime(now) or _utc_now()
        if expires_at is None:
            reasons.append(INVALID_TIMESTAMP)
        elif check_time > expires_at:
            reasons.append(CONFIRMATION_EXPIRED)

        if record.used_at:
            reasons.append(CONFIRMATION_ALREADY_USED)
        if record.revoked_at or record.status == "revoked":
            reasons.append(CONFIRMATION_REVOKED)
        if str(dry_run_trace_id or "") != record.dry_run_trace_id:
            reasons.append(DRY_RUN_TRACE_MISMATCH)
        if str(confirmed_action_id or "") != record.confirmed_action_id:
            reasons.append(CONFIRMED_ACTION_MISMATCH)
        if record.risk_level == "high":
            reasons.append(HIGH_RISK_DENIED)
        elif record.risk_level == "blocked":
            reasons.append(BLOCKED_RISK_DENIED)
        elif record.risk_level == "medium" and not (
            record.medium_risk_approved or bool(medium_risk_approved)
        ):
            reasons.append(MEDIUM_RISK_APPROVAL_REQUIRED)
        if record.autonomy_context or record.source_entrypoint.strip().lower() == "autonomy":
            reasons.append(AUTONOMY_CONTEXT_DENIED)
        if record.self_modification and not (
            record.self_modification_workflow_id or allow_self_modification_workflow
        ):
            reasons.append(SELF_MODIFICATION_SEPARATE_WORKFLOW_REQUIRED)

        unique = tuple(dict.fromkeys(reasons))
        return OperatorConfirmationValidation(
            valid=not unique,
            reasons=unique,
            confirmation_id=record.confirmation_id,
        )

    def list_confirmations(self, *, sanitized: bool = True) -> List[Dict[str, Any]]:
        rows = [record.to_dict() for record in self._load_records().values()]
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        if not sanitized:
            return rows
        return [sanitize_confirmation_record(row) for row in rows]

    def _append_event(self, event: str, payload: Mapping[str, Any]) -> None:
        row = {
            "event": str(event or ""),
            "recorded_at": _iso(_utc_now()),
            **dict(payload),
        }
        safe_row = sanitize_confirmation_record(row)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(safe_row, sort_keys=True) + "\n")

    def _load_records(self) -> Dict[str, OperatorConfirmationRecord]:
        records: Dict[str, OperatorConfirmationRecord] = {}
        with self._lock:
            if not self.path.exists():
                return records
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = str(row.get("event") or "")
                cid = str(row.get("confirmation_id") or row.get("operator_confirmation_id") or "")
                if not cid:
                    continue
                if event == "created" or not event:
                    records[cid] = _record_from_dict(row)
                elif event == "used" and cid in records:
                    data = records[cid].to_dict()
                    data["used_at"] = str(row.get("used_at") or "")
                    data["status"] = "used"
                    records[cid] = _record_from_dict(data)
                elif event == "revoked" and cid in records:
                    data = records[cid].to_dict()
                    data["revoked_at"] = str(row.get("revoked_at") or "")
                    data["revoke_reason"] = str(row.get("revoke_reason") or "")
                    data["status"] = "revoked"
                    records[cid] = _record_from_dict(data)
        return records


def sanitize_confirmation_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    out = {
        str(key)[:80]: sanitize_confirmation_value(str(key), value)
        for key, value in record.items()
    }
    if "confirmation_id" in out and "operator_confirmation_id" not in out:
        out["operator_confirmation_id"] = out["confirmation_id"]
    return out


def _public_reason(reason: str) -> str:
    mapping = {
        CONFIRMATION_NOT_FOUND: "not_found",
        CONFIRMATION_EXPIRED: "expired",
        CONFIRMATION_ALREADY_USED: "already_used",
        CONFIRMATION_REVOKED: "revoked",
        DRY_RUN_TRACE_MISMATCH: "dry_run_trace_mismatch",
        CONFIRMED_ACTION_MISMATCH: "confirmed_action_mismatch",
        HIGH_RISK_DENIED: "risk_not_confirmable",
        BLOCKED_RISK_DENIED: "risk_not_confirmable",
        AUTONOMY_CONTEXT_DENIED: "autonomy_context",
        SELF_MODIFICATION_SEPARATE_WORKFLOW_REQUIRED: "self_modification",
        MEDIUM_RISK_APPROVAL_REQUIRED: "medium_risk_approval_required",
        INVALID_TIMESTAMP: "invalid_timestamp",
    }
    return mapping.get(reason, str(reason or "invalid"))


def confirmation_to_guard_context(
    record: OperatorConfirmationRecord,
    *,
    source_entrypoint: str = "operator_chat",
) -> Dict[str, Any]:
    context = record.to_live_guard_context_fields()
    context["source_entrypoint"] = source_entrypoint
    return context


def create_operator_confirmation(
    *,
    store_path: Optional[Path] = None,
    **kwargs: Any,
) -> Tuple[Optional[OperatorConfirmationRecord], List[str]]:
    return OperatorConfirmationStore(store_path).create_operator_confirmation(**kwargs)


def get_operator_confirmation(
    confirmation_id: str,
    *,
    store_path: Optional[Path] = None,
    now: Optional[Any] = None,
) -> Optional[OperatorConfirmationRecord]:
    return OperatorConfirmationStore(store_path).get_operator_confirmation(
        confirmation_id, now=now
    )


def mark_operator_confirmation_used(
    confirmation_id: str,
    *,
    store_path: Optional[Path] = None,
    now: Optional[Any] = None,
) -> Tuple[Optional[OperatorConfirmationRecord], str]:
    return OperatorConfirmationStore(store_path).mark_operator_confirmation_used(
        confirmation_id, now=now
    )


def revoke_operator_confirmation(
    confirmation_id: str,
    *,
    store_path: Optional[Path] = None,
    now: Optional[Any] = None,
    reason: str = "",
) -> Tuple[Optional[OperatorConfirmationRecord], str]:
    return OperatorConfirmationStore(store_path).revoke_operator_confirmation(
        confirmation_id, now=now, reason=reason
    )


def is_confirmation_valid_for_request(
    confirmation_id: str,
    *,
    store_path: Optional[Path] = None,
    dry_run_trace_id: str,
    confirmed_action_id: str,
    medium_risk_approved: Optional[bool] = None,
    allow_self_modification_workflow: bool = False,
    now: Optional[Any] = None,
) -> Tuple[bool, str]:
    return OperatorConfirmationStore(store_path).is_confirmation_valid_for_request(
        confirmation_id,
        dry_run_trace_id=dry_run_trace_id,
        confirmed_action_id=confirmed_action_id,
        medium_risk_approved=medium_risk_approved,
        allow_self_modification_workflow=allow_self_modification_workflow,
        now=now,
    )


def list_operator_confirmations(
    *,
    store_path: Optional[Path] = None,
    conversation_id: str = "",
    limit: int = 50,
    now: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    return OperatorConfirmationStore(store_path).list_operator_confirmations(
        conversation_id=conversation_id, limit=limit, now=now
    )
