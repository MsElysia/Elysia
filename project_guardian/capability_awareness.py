"""Read-only capability discovery for the Windows contained pilot.

Installed / available / authorized / operational are distinct.
Discovery never activates tools, changes permissions, or writes durable state.
Dashboard and model-facing catalogs derive from the same policy snapshot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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

    def public_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Never expose internal paths as primary labels; dependencies stay high-level.
        return data


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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

    operational_hints may mark capabilities verified in this process (e.g. after
    a successful calculator run). Absence means operational=None (unknown).
    """
    hints = dict(operational_hints or {})
    probe = dict(ollama_probe) if ollama_probe is not None else _probe_ollama(configured_local_model_name())
    verified = probe.get("verified_utc") or _utc_now()
    caps: List[CapabilityDescriptor] = []

    # --- Intelligence ---
    ollama_available = bool(probe.get("reachable") and probe.get("model_installed"))
    ollama_auth = _scope_authorized(authorization, "local.chat")
    caps.append(
        CapabilityDescriptor(
            id="intelligence.ollama.chat",
            name="Local model conversation",
            description="Ask the installed local Ollama model with bounded durable-memory context.",
            category="intelligence",
            installed=True,
            available=ollama_available,
            authorized=ollama_auth,
            operational=hints.get("intelligence.ollama.chat"),
            permission_mode=_permission_mode(
                available=ollama_available, authorized=ollama_auth, per_request=False, disabled=False
            ),
            required_scope="local.chat",
            dependencies=("ollama_loopback", "ELYSIA_LOCAL_MODEL"),
            execution="local",
            cost_category="local_compute",
            last_verified_utc=verified,
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
            last_verified_utc=verified,
            unavailable_reason="Contained sessions pin one explicit local model; multi-model routing is disabled.",
            safe_next_action="Keep using the configured local model",
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
            last_verified_utc=verified,
            unavailable_reason="Cloud providers are disabled in the contained Windows pilot.",
            safe_next_action="Continue with local Ollama only",
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
        caps.append(
            CapabilityDescriptor(
                id=cid,
                name=name,
                description=desc,
                category="memory",
                installed=True,
                available=available,
                authorized=authorized,
                operational=hints.get(cid),
                permission_mode=_permission_mode(
                    available=available, authorized=authorized, per_request=per_req, disabled=False
                ),
                required_scope=scope if scope.startswith("memory.") else None,
                dependencies=("restricted_runtime_adapter", "MemoryCore"),
                execution="local",
                cost_category="none",
                last_verified_utc=verified,
                unavailable_reason=None if available else "Restricted memory runtime is not attached",
                safe_next_action=next_action if available else "Start the contained pilot so memory attaches",
                model_selectable=(cid == "memory.retrieve"),
                executable_binding=False,
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
            last_verified_utc=verified,
            unavailable_reason="No safe execution binding in this pilot; description only.",
            safe_next_action="Use explicit Save fact / inbox import instead",
            model_selectable=True,
            executable_binding=False,
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
        return CapabilityDescriptor(
            id=cap_id,
            name=label,
            description=str(row.get("description") or label),
            category=category,
            installed=installed,
            available=available,
            authorized=authorized,
            operational=hints.get(operational_key or cap_id),
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
            last_verified_utc=verified,
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
    caps.append(
        CapabilityDescriptor(
            id="system.runtime",
            name="Runtime status",
            description="Contained loopback runtime and ownership markers.",
            category="system",
            installed=True,
            available=True,
            authorized=True,
            operational=True if contained else hints.get("system.runtime"),
            permission_mode="allowed",
            required_scope=None,
            dependencies=("contained_startup",),
            execution="local",
            cost_category="none",
            last_verified_utc=verified,
            unavailable_reason=None,
            safe_next_action="Keep using the verified pilot launcher",
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
            last_verified_utc=verified,
            unavailable_reason="Background workers are disabled in contained startup.",
            safe_next_action="Leave background missions off",
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
            last_verified_utc=verified,
            unavailable_reason="Autonomy remains disabled; dashboard cannot enable it.",
            safe_next_action="Do not enable autonomy from this panel",
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
            operational=True,
            permission_mode="allowed",
            required_scope=None,
            dependencies=("contained_startup", "local_ollama_transport"),
            execution="local",
            cost_category="none",
            last_verified_utc=verified,
            unavailable_reason=None,
            safe_next_action="Keep cloud fallbacks disabled",
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
                "last_verified_utc": verified,
                "unavailable_reason": "Malformed or unsafe capability descriptor",
                "safe_next_action": "Use other capabilities; report this descriptor",
                "model_selectable": False,
                "executable_binding": False,
            }
        public_caps.append(row)

    summary = {
        "installed": sum(1 for c in public_caps if c.get("installed")),
        "available": sum(1 for c in public_caps if c.get("available")),
        "authorized": sum(1 for c in public_caps if c.get("authorized")),
        "operational_true": sum(1 for c in public_caps if c.get("operational") is True),
        "operational_unknown": sum(1 for c in public_caps if c.get("operational") is None),
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
        "generated_utc": verified,
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
        "summary": summary,
        "capabilities": public_caps,
        "safe_next_actions": next_actions,
        "policy_note": (
            "Authorization is host-supplied per request. Discovery cannot grant "
            "permission, enable autonomy, or activate cloud providers."
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
