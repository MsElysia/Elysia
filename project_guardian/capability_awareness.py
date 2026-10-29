"""Read-only capability discovery for the Windows contained pilot.

Installed / available / authorized / operational are distinct.
Operational requires process-local verified execution evidence.
Discovery never activates tools, changes permissions, or writes durable state.
Dashboard and model-facing catalogs derive from the same policy snapshot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
import threading
from typing import Any, Dict, List, Mapping, Optional

from project_guardian.local_memory_chat import (
    ChatBoundaryError,
    LocalOllama,
    ManualAuthorization,
    configured_local_model_name,
    capability_catalog as _legacy_capability_catalog,
)


SCHEMA = "elysia.capability-snapshot.v1"
OLLAMA_ENDPOINT = "http://127.0.0.1:11434"

# Capabilities that may receive process-local execution evidence in this phase.
EVIDENCE_CAPABILITY_IDS = frozenset(
    {
        "intelligence.ollama.chat",
        "memory.retrieve",
        "memory.teach",
        "memory.correct",
        "tools.calculator.labor",
    }
)


@dataclass(frozen=True)
class ExecutionEvidence:
    capability_id: str
    success: bool
    verification_method: str
    timestamp_utc: str
    process_id: int
    failure_reason: Optional[str] = None

    def public_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "success": self.success,
            "verification_method": self.verification_method,
            "timestamp_utc": self.timestamp_utc,
            "process_id": self.process_id,
            "failure_reason": self.failure_reason,
        }


class ExecutionEvidenceStore:
    """Process-local, non-durable execution evidence. Never grants authorization."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: Dict[str, ExecutionEvidence] = {}
        self._process_id = os.getpid()

    @property
    def process_id(self) -> int:
        return self._process_id

    def clear(self) -> None:
        with self._lock:
            self._by_id.clear()

    def record_success(self, capability_id: str, *, verification_method: str) -> None:
        if capability_id not in EVIDENCE_CAPABILITY_IDS:
            return
        method = _sanitize_reason(verification_method, limit=80) or "verified_execution"
        entry = ExecutionEvidence(
            capability_id=capability_id,
            success=True,
            verification_method=method,
            timestamp_utc=_utc_now(),
            process_id=self._process_id,
            failure_reason=None,
        )
        with self._lock:
            self._by_id[capability_id] = entry

    def record_failure(self, capability_id: str, *, verification_method: str, reason: str) -> None:
        if capability_id not in EVIDENCE_CAPABILITY_IDS:
            return
        method = _sanitize_reason(verification_method, limit=80) or "failed_execution"
        fail = _sanitize_reason(reason, limit=160) or "execution failed"
        entry = ExecutionEvidence(
            capability_id=capability_id,
            success=False,
            verification_method=method,
            timestamp_utc=_utc_now(),
            process_id=self._process_id,
            failure_reason=fail,
        )
        with self._lock:
            self._by_id[capability_id] = entry

    def get(self, capability_id: str) -> Optional[ExecutionEvidence]:
        with self._lock:
            return self._by_id.get(capability_id)

    def operational_map(self) -> Dict[str, Optional[bool]]:
        """True=verified, False=degraded/failed, absent=unknown."""
        with self._lock:
            out: Dict[str, Optional[bool]] = {}
            for cid, entry in self._by_id.items():
                out[cid] = True if entry.success else False
            return out

    def public_records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [entry.public_dict() for entry in self._by_id.values()]


_EVIDENCE_STORE = ExecutionEvidenceStore()


def get_execution_evidence_store() -> ExecutionEvidenceStore:
    return _EVIDENCE_STORE


def reset_execution_evidence_for_tests() -> None:
    """Test helper: clear process-local evidence without affecting authorization."""
    _EVIDENCE_STORE.clear()


def record_capability_success(capability_id: str, *, verification_method: str) -> None:
    _EVIDENCE_STORE.record_success(capability_id, verification_method=verification_method)


def record_capability_failure(
    capability_id: str, *, verification_method: str, reason: str
) -> None:
    _EVIDENCE_STORE.record_failure(
        capability_id, verification_method=verification_method, reason=reason
    )


def _sanitize_reason(value: str, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    lowered = text.casefold()
    for tok in ("password", "api_key", "token=", "secret=", "bearer ", "sk-"):
        if tok in lowered:
            return "redacted_failure_detail"
    return text[:limit]


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    name: str
    description: str
    category: str
    installed: bool
    available: bool
    authorized: bool
    operational: Optional[bool]
    permission_mode: str
    required_scope: Optional[str]
    dependencies: tuple[str, ...]
    execution: str
    cost_category: str
    last_verified_utc: Optional[str]
    unavailable_reason: Optional[str]
    safe_next_action: str
    model_selectable: bool = False
    executable_binding: bool = False
    runtime_status: str = "unknown"
    last_failure_reason: Optional[str] = None

    def public_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Never expose internal paths as primary labels; dependencies stay high-level.
        return data


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runtime_status(
    *,
    installed: bool,
    available: bool,
    authorized: bool,
    operational: Optional[bool],
    per_request: bool,
    disabled: bool,
) -> str:
    if disabled:
        return "unavailable"
    if not installed:
        return "unavailable"
    if not available:
        return "unavailable"
    # Verified/degraded reflect execution evidence independently of current auth.
    if operational is True:
        return "verified_operational"
    if operational is False:
        return "degraded"
    if per_request and not authorized:
        return "authorization_required"
    return "not_yet_verified"


def _apply_evidence(
    capability_id: str,
    *,
    installed: bool,
    available: bool,
    authorized: bool,
    per_request: bool = False,
    disabled: bool = False,
    fallback_operational: Optional[bool] = None,
) -> tuple[Optional[bool], Optional[str], Optional[str], str]:
    """Return operational, last_verified_utc, last_failure_reason, runtime_status."""
    evidence = _EVIDENCE_STORE.get(capability_id)
    operational = fallback_operational
    last_verified: Optional[str] = None
    last_failure: Optional[str] = None
    if evidence is not None and evidence.process_id == _EVIDENCE_STORE.process_id:
        operational = True if evidence.success else False
        if evidence.success:
            last_verified = evidence.timestamp_utc
        else:
            last_failure = evidence.failure_reason
            last_verified = None
    status = _runtime_status(
        installed=installed,
        available=available,
        authorized=authorized,
        operational=operational,
        per_request=per_request,
        disabled=disabled,
    )
    return operational, last_verified, last_failure, status


def _scope_authorized(authorization: ManualAuthorization, scope: Optional[str]) -> bool:
    if not scope:
        return False
    try:
        authorization.require(scope)
        return True
    except ChatBoundaryError:
        return False


def _probe_ollama(model_name: Optional[str]) -> Dict[str, Any]:
    """Bounded loopback probe. Failures degrade only local-model capability."""
    result: Dict[str, Any] = {
        "configured": bool(model_name),
        "model": model_name,
        "endpoint": OLLAMA_ENDPOINT,
        "reachable": False,
        "model_installed": False,
        "installed_models": [],
        "error": None,
        "verified_utc": _utc_now(),
    }
    if not model_name:
        result["error"] = "ELYSIA_LOCAL_MODEL is not configured"
        return result
    try:
        client = LocalOllama(model_name, endpoint=OLLAMA_ENDPOINT)
        models = client.installed_models()
        result["reachable"] = True
        result["installed_models"] = models[:20]
        result["model_installed"] = model_name in models
        if not result["model_installed"]:
            result["error"] = "configured model is not installed in local Ollama"
    except ChatBoundaryError as exc:
        result["error"] = str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        result["error"] = "local model probe failed"
        del exc
    return result


def _permission_mode(*, available: bool, authorized: bool, per_request: bool, disabled: bool) -> str:
    if disabled:
        return "disabled"
    if not available:
        return "unavailable"
    if per_request:
        return "per_request" if not authorized else "allowed_this_request"
    if authorized:
        return "allowed"
    return "not_authorized"


def discover_capabilities(
    authorization: ManualAuthorization,
    *,
    contained: bool = True,
    memory_attached: bool = False,
    memory_filepath: Optional[str] = None,
    ollama_probe: Optional[Mapping[str, Any]] = None,
    operational_hints: Optional[Mapping[str, bool]] = None,
) -> Dict[str, Any]:
    """Build a read-only capability snapshot from runtime + authorization.

    Operational status comes from process-local execution evidence only.
    operational_hints are ignored when evidence exists; they remain for tests
    that inject synthetic maps without mutating the store.
    """
    hints = dict(operational_hints or {})
    probe = dict(ollama_probe) if ollama_probe is not None else _probe_ollama(configured_local_model_name())
    snapshot_utc = probe.get("verified_utc") or _utc_now()
    caps: List[CapabilityDescriptor] = []

    # --- Intelligence ---
    ollama_available = bool(probe.get("reachable") and probe.get("model_installed"))
    ollama_auth = _scope_authorized(authorization, "local.chat")
    # Probe reachability can mark degraded only when evidence already failed or
    # when probe says unreachable — never invent operational success from probe.
    ollama_op, ollama_verified, ollama_fail, ollama_status = _apply_evidence(
        "intelligence.ollama.chat",
        installed=True,
        available=ollama_available,
        authorized=ollama_auth,
        fallback_operational=hints.get("intelligence.ollama.chat"),
    )
    if not ollama_available and ollama_op is not False:
        # Dependency down: do not keep a misleading healthy claim.
        ollama_op = False if _EVIDENCE_STORE.get("intelligence.ollama.chat") else None
        if probe.get("error"):
            ollama_fail = _sanitize_reason(str(probe.get("error")), limit=160)
        ollama_verified = None
        ollama_status = _runtime_status(
            installed=True,
            available=False,
            authorized=ollama_auth,
            operational=ollama_op if ollama_op is False else None,
            per_request=False,
            disabled=False,
        )
        if ollama_op is not False:
            ollama_status = "unavailable"
    caps.append(
        CapabilityDescriptor(
            id="intelligence.ollama.chat",
            name="Local model conversation",
            description="Ask the installed local Ollama model with bounded durable-memory context.",
            category="intelligence",
            installed=True,
            available=ollama_available,
            authorized=ollama_auth,
            operational=ollama_op,
            permission_mode=_permission_mode(
                available=ollama_available, authorized=ollama_auth, per_request=False, disabled=False
            ),
            required_scope="local.chat",
            dependencies=("ollama_loopback", "ELYSIA_LOCAL_MODEL"),
            execution="local",
            cost_category="local_compute",
            last_verified_utc=ollama_verified,
            unavailable_reason=None if ollama_available else (probe.get("error") or "local model unavailable"),
            safe_next_action=(
                "Ask a question with Ask local model"
                if ollama_available and ollama_auth
                else "Start Ollama on 127.0.0.1:11434 and set ELYSIA_LOCAL_MODEL"
                if not ollama_available
                else "Authenticate / open a contained session before chatting"
            ),
            model_selectable=False,
            executable_binding=False,
            runtime_status=ollama_status,
            last_failure_reason=ollama_fail,
        )
    )
    caps.append(
        CapabilityDescriptor(
            id="intelligence.model_routing",
            name="Model routing",
            description="Select among local models; cloud routing stays disabled in contained mode.",
            category="intelligence",
            installed=True,
            available=False,
            authorized=False,
            operational=False,
            permission_mode="disabled",
            required_scope=None,
            dependencies=("provider_policy",),
            execution="local",
            cost_category="none",
            last_verified_utc=None,
            unavailable_reason="Contained sessions pin one explicit local model; multi-model routing is disabled.",
            safe_next_action="Keep using the configured local model",
            runtime_status="unavailable",
        )
    )
    caps.append(
        CapabilityDescriptor(
            id="intelligence.cloud_models",
            name="Cloud models",
            description="Paid cloud LLM providers (OpenAI/OpenRouter/etc.).",
            category="intelligence",
            installed=True,
            available=False,
            authorized=False,
            operational=False,
            permission_mode="disabled",
            required_scope=None,
            dependencies=("cloud_credentials", "provider_policy"),
            execution="cloud",
            cost_category="paid_api",
            last_verified_utc=None,
            unavailable_reason="Cloud providers are disabled in the contained Windows pilot.",
            safe_next_action="Continue with local Ollama only",
            runtime_status="unavailable",
        )
    )

    # --- Memory ---
    mem_ok = bool(memory_attached)
    mem_auth_read = _scope_authorized(authorization, "memory.read")
    # Teach/correct/history use restricted principal permissions; treat as allowed when
    # adapter is attached in contained mode (dashboard operator already authenticated).
    for cid, name, desc, scope, per_req, next_action in (
        (
            "memory.retrieve",
            "Durable memory retrieval",
            "Retrieve current restricted facts with different wording.",
            "memory.read",
            False,
            "Use Retrieve on the Memory tab or Ask local model",
        ),
        (
            "memory.teach",
            "Explicit memory teaching",
            "Save a new fictional/restricted fact through the existing teach path.",
            "facts.save",
            False,
            "Save a fact on the Memory tab",
        ),
        (
            "memory.correct",
            "Memory correction",
            "Correct a current fact; prior revisions remain in history.",
            "facts.correct",
            False,
            "Select a fact and submit a correction",
        ),
        (
            "memory.history",
            "Revision history",
            "Show prior revisions of a restricted fact.",
            "facts.history",
            False,
            "Use Show history on the Memory tab",
        ),
    ):
        authorized = mem_auth_read if scope == "memory.read" else mem_ok
        available = mem_ok
        if cid in {"memory.retrieve", "memory.teach", "memory.correct"}:
            op, last_v, last_f, rstatus = _apply_evidence(
                cid,
                installed=True,
                available=available,
                authorized=authorized,
                fallback_operational=hints.get(cid),
            )
        else:
            op, last_v, last_f, rstatus = (
                hints.get(cid),
                None,
                None,
                _runtime_status(
                    installed=True,
                    available=available,
                    authorized=authorized,
                    operational=hints.get(cid),
                    per_request=per_req,
                    disabled=False,
                ),
            )
        caps.append(
            CapabilityDescriptor(
                id=cid,
                name=name,
                description=desc,
                category="memory",
                installed=True,
                available=available,
                authorized=authorized,
                operational=op,
                permission_mode=_permission_mode(
                    available=available, authorized=authorized, per_request=per_req, disabled=False
                ),
                required_scope=scope if scope.startswith("memory.") else None,
                dependencies=("restricted_runtime_adapter", "MemoryCore"),
                execution="local",
                cost_category="none",
                last_verified_utc=last_v,
                unavailable_reason=None if available else "Restricted memory runtime is not attached",
                safe_next_action=next_action if available else "Start the contained pilot so memory attaches",
                model_selectable=(cid == "memory.retrieve"),
                executable_binding=False,
                runtime_status=rstatus,
                last_failure_reason=last_f,
            )
        )
    caps.append(
        CapabilityDescriptor(
            id="memory.ingest",
            name="Memory ingestion",
            description="Bulk review/approve new memory sources.",
            category="memory",
            installed=True,
            available=False,
            authorized=False,
            operational=False,
            permission_mode="unavailable",
            required_scope="memory.write",
            dependencies=("memory_ingest_binding",),
            execution="local",
            cost_category="none",
            last_verified_utc=None,
            unavailable_reason="No safe execution binding in this pilot; description only.",
            safe_next_action="Use explicit Save fact / inbox import instead",
            model_selectable=True,
            executable_binding=False,
            runtime_status="unavailable",
        )
    )

    # --- Tools (shared with model catalog policy) ---
    # Reuse the same tool/authorization projection as converse_bundle.
    tool_rows = _legacy_capability_catalog(authorization)
    by_name = {row["name"]: row for row in tool_rows if isinstance(row, dict)}

    def _tool_cap(
        tool_name: str,
        *,
        cap_id: str,
        label: str,
        category: str = "tools",
        per_request: bool = False,
        operational_key: Optional[str] = None,
    ) -> CapabilityDescriptor:
        row = by_name.get(tool_name) or {}
        installed = True
        available = bool(row.get("available"))
        authorized = bool(row.get("authorized"))
        reason = None
        if not available:
            reason = row.get("prerequisites") or "No safe execution binding"
        elif not authorized:
            reason = "Operator authorization required for this request"
        key = operational_key or cap_id
        if cap_id == "tools.calculator.labor":
            op, last_v, last_f, rstatus = _apply_evidence(
                cap_id,
                installed=installed,
                available=available,
                authorized=authorized,
                per_request=per_request,
                fallback_operational=hints.get(key),
            )
        else:
            op = hints.get(key)
            last_v, last_f = None, None
            rstatus = _runtime_status(
                installed=installed,
                available=available,
                authorized=authorized,
                operational=op,
                per_request=per_request,
                disabled=False,
            )
        return CapabilityDescriptor(
            id=cap_id,
            name=label,
            description=str(row.get("description") or label),
            category=category,
            installed=installed,
            available=available,
            authorized=authorized,
            operational=op,
            permission_mode=_permission_mode(
                available=available,
                authorized=authorized,
                per_request=per_request,
                disabled=False,
            ),
            required_scope=row.get("required_scope"),
            dependencies=tuple(
                sorted(
                    {
                        *(["local_ollama"] if tool_name == "calculator.labor" else []),
                        *(["usd_hourly_rate_memory"] if tool_name == "calculator.labor" else []),
                        "tool_registry_projection",
                    }
                )
            ),
            execution="local" if row.get("available") else "none",
            cost_category=str(row.get("cost") or "none"),
            last_verified_utc=last_v,
            unavailable_reason=reason,
            safe_next_action=(
                "Check Allow the labor calculator, then ask a labor estimate"
                if tool_name == "calculator.labor" and available and not authorized
                else "Ask a labor estimate with the calculator checkbox enabled"
                if tool_name == "calculator.labor" and available and authorized
                else "Do not expect this tool to run in the current pilot"
            ),
            model_selectable=True,
            executable_binding=bool(available and tool_name == "calculator.labor"),
            runtime_status=rstatus,
            last_failure_reason=last_f,
        )

    caps.append(
        _tool_cap(
            "calculator.labor",
            cap_id="tools.calculator.labor",
            label="Labor calculator",
            per_request=True,
        )
    )
    caps.append(
        _tool_cap("finance.summary", cap_id="tools.finance", label="Finance summary")
    )
    caps.append(_tool_cap("email.search", cap_id="tools.email", label="Email search"))
    caps.append(_tool_cap("web.search", cap_id="tools.web_search", label="Web search"))
    caps.append(
        _tool_cap("calendar.read", cap_id="tools.calendar", label="Calendar")
    )
    caps.append(
        _tool_cap("documents.read", cap_id="tools.documents", label="Document processing")
    )

    # --- System ---
    # Not in the first execution-evidence set: remain not_yet_verified / unavailable.
    caps.append(
        CapabilityDescriptor(
            id="system.runtime",
            name="Runtime status",
            description="Contained loopback runtime and ownership markers.",
            category="system",
            installed=True,
            available=bool(contained),
            authorized=True,
            operational=None,
            permission_mode="allowed" if contained else "unavailable",
            required_scope=None,
            dependencies=("contained_startup",),
            execution="local",
            cost_category="none",
            last_verified_utc=None,
            unavailable_reason=None if contained else "Not a contained session",
            safe_next_action="Keep using the verified pilot launcher",
            runtime_status="not_yet_verified" if contained else "unavailable",
        )
    )
    caps.append(
        CapabilityDescriptor(
            id="system.background_missions",
            name="Background missions",
            description="Background workers and online learning loops.",
            category="system",
            installed=True,
            available=False,
            authorized=False,
            operational=False,
            permission_mode="disabled",
            required_scope=None,
            dependencies=("background_workers",),
            execution="local",
            cost_category="none",
            last_verified_utc=None,
            unavailable_reason="Background workers are disabled in contained startup.",
            safe_next_action="Leave background missions off",
            runtime_status="unavailable",
        )
    )
    caps.append(
        CapabilityDescriptor(
            id="system.autonomy",
            name="Autonomous execution",
            description="Unattended autonomy / execute-cycle privileged control.",
            category="system",
            installed=True,
            available=False,
            authorized=False,
            operational=False,
            permission_mode="disabled",
            required_scope=None,
            dependencies=("autonomy_config", "privileged_control_gate"),
            execution="local",
            cost_category="none",
            last_verified_utc=None,
            unavailable_reason="Autonomy remains disabled; dashboard cannot enable it.",
            safe_next_action="Do not enable autonomy from this panel",
            runtime_status="unavailable",
        )
    )
    caps.append(
        CapabilityDescriptor(
            id="system.provider_policy",
            name="Provider policy enforcement",
            description="Fail-closed refusal of cloud/provider fallbacks.",
            category="system",
            installed=True,
            available=True,
            authorized=True,
            operational=None,
            permission_mode="allowed",
            required_scope=None,
            dependencies=("contained_startup", "local_ollama_transport"),
            execution="local",
            cost_category="none",
            last_verified_utc=None,
            unavailable_reason=None,
            safe_next_action="Keep cloud fallbacks disabled",
            runtime_status="not_yet_verified",
        )
    )

    # Drop accidental secret-shaped *values* only (not dependency names like cloud_credentials).
    _SECRET_VALUE_RE = (
        "api_key",
        "password",
        "token=",
        "secret=",
        "bearer ",
        "sk-",
    )
    public_caps = []
    for cap in caps:
        row = cap.public_dict()
        value_blob = " ".join(
            str(v).casefold()
            for k, v in row.items()
            if k
            not in {
                "id",
                "name",
                "description",
                "category",
                "dependencies",
                "safe_next_action",
                "unavailable_reason",
                "required_scope",
                "permission_mode",
                "execution",
                "cost_category",
                "runtime_status",
                "last_failure_reason",
            }
        )
        if any(tok in value_blob for tok in _SECRET_VALUE_RE):
            # Fail closed for that row only; leave unrelated capabilities intact.
            row = {
                "id": cap.id,
                "name": cap.name,
                "description": "Capability metadata omitted due to unsafe field content.",
                "category": cap.category,
                "installed": False,
                "available": False,
                "authorized": False,
                "operational": False,
                "permission_mode": "unavailable",
                "required_scope": None,
                "dependencies": [],
                "execution": "none",
                "cost_category": "none",
                "last_verified_utc": None,
                "unavailable_reason": "Malformed or unsafe capability descriptor",
                "safe_next_action": "Use other capabilities; report this descriptor",
                "model_selectable": False,
                "executable_binding": False,
                "runtime_status": "unavailable",
                "last_failure_reason": None,
            }
        public_caps.append(row)

    summary = {
        "installed": sum(1 for c in public_caps if c.get("installed")),
        "available": sum(1 for c in public_caps if c.get("available")),
        "authorized": sum(1 for c in public_caps if c.get("authorized")),
        "operational_true": sum(1 for c in public_caps if c.get("operational") is True),
        "operational_unknown": sum(1 for c in public_caps if c.get("operational") is None),
        "verified_operational": sum(
            1 for c in public_caps if c.get("runtime_status") == "verified_operational"
        ),
        "degraded": sum(1 for c in public_caps if c.get("runtime_status") == "degraded"),
        "not_yet_verified": sum(
            1 for c in public_caps if c.get("runtime_status") == "not_yet_verified"
        ),
        "disabled_or_unavailable": sum(
            1
            for c in public_caps
            if c.get("permission_mode") in ("disabled", "unavailable", "not_authorized")
            or not c.get("available")
        ),
    }
    next_actions = []
    for c in public_caps:
        if c.get("available") and c.get("authorized") and c.get("safe_next_action"):
            next_actions.append({"capability": c["id"], "action": c["safe_next_action"]})
        elif c.get("available") and c.get("permission_mode") == "per_request":
            next_actions.append({"capability": c["id"], "action": c["safe_next_action"]})
    next_actions = next_actions[:6]

    # Never include raw memory filepath contents — only a boolean presence flag.
    return {
        "ok": True,
        "schema": SCHEMA,
        "read_only": True,
        "activates_tools": False,
        "cloud_fallback": False,
        "contained": bool(contained),
        "generated_utc": snapshot_utc,
        "process_id": _EVIDENCE_STORE.process_id,
        "local_model": {
            "configured": bool(probe.get("configured")),
            "model": probe.get("model"),
            "endpoint": OLLAMA_ENDPOINT,
            "reachable": bool(probe.get("reachable")),
            "installed": bool(probe.get("model_installed")),
            "error": probe.get("error"),
            "installed_models": list(probe.get("installed_models") or [])[:20],
        },
        "memory": {
            "attached": bool(memory_attached),
            "store_present": bool(memory_filepath),
        },
        "execution_evidence": _EVIDENCE_STORE.public_records(),
        "summary": summary,
        "capabilities": public_caps,
        "safe_next_actions": next_actions,
        "policy_note": (
            "Authorization is host-supplied per request. Discovery and execution "
            "evidence cannot grant permission, enable autonomy, or activate cloud providers. "
            "Operational means verified in this process only."
        ),
    }


def model_facing_catalog(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Sanitized catalog for the local model: availability + auth, no secrets."""
    out: List[Dict[str, Any]] = []
    for cap in snapshot.get("capabilities") or []:
        if not isinstance(cap, dict) or not cap.get("model_selectable"):
            continue
        out.append(
            {
                "name": cap.get("id"),
                "tool": _tool_name_for_capability(cap.get("id")),
                "description": cap.get("description"),
                "available": bool(cap.get("available")),
                "authorized": bool(cap.get("authorized")),
                "executable": bool(cap.get("executable_binding") and cap.get("authorized")),
                "required_scope": cap.get("required_scope"),
                "permission_mode": cap.get("permission_mode"),
                "unavailable_reason": cap.get("unavailable_reason"),
                "cost": "no paid calls permitted",
                "execution": cap.get("execution"),
            }
        )
    return out


def _tool_name_for_capability(cap_id: Optional[str]) -> Optional[str]:
    mapping = {
        "tools.calculator.labor": "calculator.labor",
        "tools.finance": "finance.summary",
        "tools.email": "email.search",
        "tools.web_search": "web.search",
        "tools.calendar": "calendar.read",
        "tools.documents": "documents.read",
        "memory.retrieve": "memory.search",
        "memory.ingest": "memory.ingest",
    }
    return mapping.get(cap_id or "")


def capability_catalog_from_snapshot(
    authorization: ManualAuthorization,
    *,
    snapshot: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Authoritative model catalog: same policy as discover_capabilities + legacy fields."""
    # Keep legacy calculator argument schema while aligning authorized/available flags.
    legacy = _legacy_capability_catalog(authorization)
    if snapshot is None:
        return legacy
    by_tool = {}
    for row in model_facing_catalog(snapshot):
        tool = row.get("tool")
        if tool:
            by_tool[tool] = row
    merged = []
    for row in legacy:
        name = row.get("name")
        overlay = by_tool.get(name) or {}
        merged.append(
            {
                **row,
                "available": overlay.get("available", row.get("available")),
                "authorized": overlay.get("authorized", row.get("authorized")),
                "permission_mode": overlay.get("permission_mode"),
                "unavailable_reason": overlay.get("unavailable_reason"),
                "executable": overlay.get("executable", False),
            }
        )
    return merged
