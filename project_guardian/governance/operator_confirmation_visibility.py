# project_guardian/governance/operator_confirmation_visibility.py
"""Read-only operator confirmation and live-execution governance diagnostics.

No confirmation creation, consumption, guard mutation, LLM, or external API calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from project_guardian.brain.config import BrainPipelineConfig, get_brain_pipeline_config
from project_guardian.governance.operator_confirmation_store import (
    OperatorConfirmationStore,
    is_confirmation_valid_for_request,
    sanitize_confirmation_record,
)

try:
    from project_guardian.governance.operator_confirmation_store import DEFAULT_STORE_PATH
except ImportError:
    from project_guardian.governance.operator_confirmation_store import (
        DEFAULT_CONFIRMATIONS_PATH as DEFAULT_STORE_PATH,
    )

_DEFAULT_LIST_LIMIT = 25
_MAX_LIST_LIMIT = 50

_FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "message",
        "text",
        "prompt",
        "content",
        "observation",
        "raw_input",
        "trace",
        "think_decide_act_trace",
        "evidence",
        "tda_trace",
        "unified_export",
        "rendered_prompt",
        "system_prompt",
        "llm_output",
        "model_output",
        "metadata",
    }
)

_STATUS_BUCKETS = ("pending", "used", "expired", "revoked", "invalid")


def resolve_live_execution_governance_flags(
    brain_cfg: Optional[BrainPipelineConfig] = None,
) -> Dict[str, bool]:
    """Read config only; does not enable live execution."""
    cfg = brain_cfg or get_brain_pipeline_config()
    entrypoints = cfg.entrypoints or {}
    return {
        "brain_pipeline_enabled": bool(cfg.enabled),
        "dry_run": bool(cfg.dry_run),
        "live_execution_enabled": bool(
            cfg.enabled
            and entrypoints.get("operator_chat_live_execution", False)
            and not cfg.dry_run
        ),
        "autonomy_enabled": bool(cfg.enabled and entrypoints.get("autonomy", False)),
        "operator_chat_enabled": bool(cfg.enabled and entrypoints.get("operator_chat", False)),
    }


def _normalize_limit(limit: Optional[int]) -> int:
    try:
        value = int(limit if limit is not None else _DEFAULT_LIST_LIMIT)
    except (TypeError, ValueError):
        value = _DEFAULT_LIST_LIMIT
    return max(1, min(value, _MAX_LIST_LIMIT))


def _public_path(store_path: Optional[Path] = None) -> str:
    path = store_path or DEFAULT_STORE_PATH
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _record_id(record: Mapping[str, Any]) -> str:
    return str(record.get("operator_confirmation_id") or record.get("confirmation_id") or "").strip()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _effective_status(record: Mapping[str, Any], *, now: datetime) -> str:
    """Derive display status without mutating the store."""
    status = str(record.get("status") or "").strip().lower()
    if status in ("used", "revoked", "expired"):
        return status
    expires = _parse_iso(str(record.get("expires_at") or ""))
    if expires is not None and now > expires:
        return "expired"
    return status or "pending"


def _validation_notes_for_record(
    record: Mapping[str, Any],
    *,
    store_path: Path,
    now: Optional[datetime] = None,
) -> Tuple[bool, List[str]]:
    when = now or datetime.now(timezone.utc)
    conf_id = _record_id(record)
    if not conf_id:
        return False, ["missing_confirmation_id"]

    status = _effective_status(record, now=when)
    if status in ("used", "revoked", "expired"):
        return False, [f"status_{status}"]

    if status != "pending":
        return False, [f"status_{status or 'unknown'}"]

    valid, reason = is_confirmation_valid_for_request(
        conf_id,
        store_path=store_path,
        dry_run_trace_id=str(record.get("dry_run_trace_id") or ""),
        confirmed_action_id=str(record.get("confirmed_action_id") or ""),
        medium_risk_approved=record.get("medium_risk_approved"),
        now=when,
    )
    if valid:
        return True, []
    return False, [str(reason)[:120]]


def _summarize_record(
    raw: Mapping[str, Any],
    *,
    store_path: Path,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    clean = sanitize_confirmation_record(dict(raw))
    if "operator_confirmation_id" not in clean and clean.get("confirmation_id"):
        clean["operator_confirmation_id"] = clean.get("confirmation_id")
    when = now or datetime.now(timezone.utc)
    display_status = _effective_status(clean, now=when)
    valid_now, notes = _validation_notes_for_record(clean, store_path=store_path, now=when)
    summary: Dict[str, Any] = {
        "operator_confirmation_id": _record_id(clean)[:64],
        "status": display_status[:16],
        "created_at": str(clean.get("created_at") or "")[:40],
        "expires_at": str(clean.get("expires_at") or "")[:40],
        "dry_run_trace_id": str(clean.get("dry_run_trace_id") or "")[:120],
        "confirmed_action_id": str(clean.get("confirmed_action_id") or "")[:120],
        "action_summary": str(
            clean.get("action_summary") or clean.get("requested_action_summary") or ""
        )[:500],
        "action_type": str(clean.get("action_type") or clean.get("requested_action_type") or "")[
            :120
        ],
        "tool_name": str(clean.get("tool_name") or clean.get("requested_tool_name") or "")[:120],
        "risk_level": str(clean.get("risk_level") or "")[:32],
        "medium_risk_approved": bool(clean.get("medium_risk_approved")),
        "executor_allowlisted": bool(
            clean.get("executor_allowlisted")
            or bool(clean.get("executor_allowlist"))
        ),
        "rollback_available": bool(clean.get("rollback_available")),
        "prompt_contract_valid": clean.get("prompt_contract_valid", True) is not False,
        "valid_now": bool(valid_now),
        "validation_notes": [str(n)[:120] for n in notes[:8]],
    }
    if clean.get("used_at"):
        summary["used_at"] = str(clean.get("used_at"))[:40]
    return summary


def _count_by_status(records: List[Mapping[str, Any]], *, now: datetime) -> Dict[str, int]:
    counts = {key: 0 for key in _STATUS_BUCKETS}
    for row in records:
        status = _effective_status(row, now=now)
        if status in ("pending", "used", "expired", "revoked"):
            counts[status] += 1
        else:
            counts["invalid"] += 1
    return counts


def build_operator_confirmations_list_payload(
    *,
    store_path: Optional[Path] = None,
    limit: Optional[int] = None,
    conversation_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    brain_cfg: Optional[BrainPipelineConfig] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Read-only list payload; does not mutate store or run live execution."""
    path = Path(store_path) if store_path else DEFAULT_STORE_PATH
    when = now or datetime.now(timezone.utc)
    lim = _normalize_limit(limit)
    warnings: List[str] = []

    if not path.is_file():
        warnings.append("confirmation_store_missing")
        flags = resolve_live_execution_governance_flags(brain_cfg)
        return {
            "available": True,
            "read_only": True,
            **flags,
            "confirmation_store_path": _public_path(path),
            "counts": {k: 0 for k in _STATUS_BUCKETS},
            "total": 0,
            "returned": 0,
            "limit": lim,
            "confirmations": [],
            "warnings": warnings,
        }

    store = OperatorConfirmationStore(path)
    list_kwargs: Dict[str, Any] = {"limit": 10_000, "now": when}
    if conversation_id:
        list_kwargs["conversation_id"] = conversation_id
    all_rows = store.list_operator_confirmations(**list_kwargs)
    if status_filter:
        want = str(status_filter).strip().lower()
        all_rows = [_row for _row in all_rows if _effective_status(_row, now=when) == want]
    all_rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    counts = _count_by_status(all_rows, now=when)
    trimmed = all_rows[:lim]
    confirmations = [_summarize_record(row, store_path=path, now=when) for row in trimmed]
    flags = resolve_live_execution_governance_flags(brain_cfg)
    return {
        "available": True,
        "read_only": True,
        **flags,
        "confirmation_store_path": _public_path(path),
        "counts": counts,
        "total": len(all_rows),
        "returned": len(confirmations),
        "limit": lim,
        "confirmations": confirmations,
        "warnings": warnings,
    }


def build_operator_confirmation_detail_payload(
    operator_confirmation_id: str,
    *,
    store_path: Optional[Path] = None,
    brain_cfg: Optional[BrainPipelineConfig] = None,
    now: Optional[datetime] = None,
) -> Tuple[Dict[str, Any], int]:
    """Read-only detail; returns (body, http_status)."""
    path = Path(store_path) if store_path else DEFAULT_STORE_PATH
    when = now or datetime.now(timezone.utc)
    conf_id = str(operator_confirmation_id or "").strip()[:64]
    if not conf_id:
        return {"available": False, "error": "missing_confirmation_id"}, 400

    flags = resolve_live_execution_governance_flags(brain_cfg)
    if not path.is_file():
        return {
            "available": True,
            "read_only": True,
            "found": False,
            **flags,
            "confirmation_store_path": _public_path(path),
            "warnings": ["confirmation_store_missing"],
        }, 404

    store = OperatorConfirmationStore(path)
    record = store.get_operator_confirmation(conf_id, now=when)
    if record is None:
        return {
            "available": True,
            "read_only": True,
            "found": False,
            **flags,
            "confirmation_store_path": _public_path(path),
            "operator_confirmation_id": conf_id,
            "warnings": ["confirmation_not_found"],
        }, 404

    row = record.to_dict() if hasattr(record, "to_dict") else dict(record)
    if "operator_confirmation_id" not in row and row.get("confirmation_id"):
        row["operator_confirmation_id"] = row.get("confirmation_id")
    summary = _summarize_record(row, store_path=path, now=when)
    return {
        "available": True,
        "read_only": True,
        "found": True,
        **flags,
        "confirmation_store_path": _public_path(path),
        "confirmation": summary,
        "warnings": [],
    }, 200


def assert_response_has_no_forbidden_fields(payload: Mapping[str, Any]) -> None:
    """Test helper: ensure prompts/traces are not exposed."""

    def _walk(obj: Any, key: str = "") -> None:
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                lk = str(k).lower()
                assert lk not in _FORBIDDEN_RESPONSE_KEYS, f"forbidden key exposed: {k}"
                _walk(v, lk)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item, key)
        elif isinstance(obj, str):
            lowered = obj.lower()
            for token in ('"think_decide_act_trace"', '"raw_trace"', "system_prompt"):
                assert token not in lowered

    _walk(payload)
