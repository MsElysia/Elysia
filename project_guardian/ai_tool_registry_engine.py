# project_guardian/ai_tool_registry_engine.py
# ToolRegistry: Auto-discovery and Management of External AI Tools
# Based on Conversation 3 (elysia 4 sub a) design specifications
#
# SECURITY: This module handles AI tool registration and should be used with caution.
# API keys are stored in metadata and should be encrypted in production.
# All network operations route through WebReader gateway.

import logging
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Optional, Callable, Set
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
import importlib
import inspect

logger = logging.getLogger(__name__)

_HF_MODELS_API = "https://huggingface.co/api/models"
_HF_DISCOVERY_USER_AGENT = "ProjectGuardian-ai_tool_registry_engine/1.0"
_OPENROUTER_MODELS_API = "https://openrouter.ai/api/v1/models"
_OPENROUTER_CHAT_API = "https://openrouter.ai/api/v1/chat/completions"
_UNIMPLEMENTED_DISCOVERY_SOURCES_LOGGED: Set[str] = set()


def _huggingface_api_token() -> str:
    return (
        (os.environ.get("HF_TOKEN") or "").strip()
        or (os.environ.get("HUGGINGFACE_HUB_TOKEN") or "").strip()
        or (os.environ.get("HUGGINGFACE_API_TOKEN") or "").strip()
    )


def _openrouter_api_token() -> str:
    return (os.environ.get("OPENROUTER_API_KEY") or "").strip()


def _safe_tool_name(prefix: str, raw_name: str) -> str:
    return prefix + str(raw_name).replace("/", "__").replace(".", "_").replace(" ", "_")[:96]


def _log_unimplemented_discovery_source_once(source: str) -> None:
    source_key = str(source).lower().strip()
    if not source_key or source_key in _UNIMPLEMENTED_DISCOVERY_SOURCES_LOGGED:
        return
    _UNIMPLEMENTED_DISCOVERY_SOURCES_LOGGED.add(source_key)
    logger.debug("Tool discovery for source %r is not implemented yet", source_key)


def discover_huggingface_hub_models(
    *,
    limit: int = 25,
    search: Optional[str] = None,
    timeout_sec: float = 20.0,
) -> List[Dict[str, Any]]:
    """
    List models from Hugging Face Hub ``GET /api/models`` (read-only, no inference).

    Uses ``HF_TOKEN``, ``HUGGINGFACE_HUB_TOKEN``, or ``HUGGINGFACE_API_TOKEN`` when set
    (higher rate limits). Works without a token for small ``limit`` values.
    """
    lim = max(1, min(int(limit or 25), 100))
    params: List[tuple[str, str]] = [("limit", str(lim))]
    if search and str(search).strip():
        params.append(("search", str(search).strip()[:160]))
    url = _HF_MODELS_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _HF_DISCOVERY_USER_AGENT},
        method="GET",
    )
    token = _huggingface_api_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        logger.warning("Hugging Face Hub models API HTTP %s: %s", getattr(e, "code", "?"), e)
        return []
    except urllib.error.URLError as e:
        logger.warning("Hugging Face Hub models API network error: %s", e)
        return []
    except Exception as e:
        logger.warning("Hugging Face Hub models API failed: %s", e)
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Hugging Face Hub models API returned non-JSON")
        return []
    if not isinstance(data, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in data:
        if len(out) >= lim:
            break
        if not isinstance(row, dict):
            continue
        mid = (row.get("modelId") or row.get("id") or "").strip()
        if not mid:
            continue
        pipeline = row.get("pipeline_tag") or row.get("library_name") or ""
        pipeline_s = str(pipeline).strip() if pipeline else ""
        likes = row.get("likes", 0)
        downloads = row.get("downloads", 0)
        safe = _safe_tool_name("hf_", mid)
        desc = (
            f"Hugging Face Hub model `{mid}`."
            + (f" Pipeline: {pipeline_s}." if pipeline_s else "")
            + " Inference via HF Inference API (token required for most models)."
        )
        out.append(
            {
                "name": safe,
                "provider": "huggingface",
                "description": desc,
                "api_endpoint": f"https://api-inference.huggingface.co/models/{mid}",
                "requires_registration": True,
                "model_id": mid,
                "pipeline_tag": pipeline_s or None,
                "likes": likes,
                "downloads": downloads,
                "api_key_env": "HF_TOKEN",
            }
        )
    return out


def discover_openrouter_models(
    *,
    limit: int = 25,
    search: Optional[str] = None,
    timeout_sec: float = 20.0,
) -> List[Dict[str, Any]]:
    """
    List models from OpenRouter ``GET /api/v1/models``.

    The endpoint is public, but ``OPENROUTER_API_KEY`` is sent when available to stay
    consistent with the rest of the tool registry metadata.
    """
    lim = max(1, min(int(limit or 25), 100))
    req = urllib.request.Request(
        _OPENROUTER_MODELS_API,
        headers={"User-Agent": _HF_DISCOVERY_USER_AGENT},
        method="GET",
    )
    token = _openrouter_api_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        logger.warning("OpenRouter models API HTTP %s: %s", getattr(e, "code", "?"), e)
        return []
    except urllib.error.URLError as e:
        logger.warning("OpenRouter models API network error: %s", e)
        return []
    except Exception as e:
        logger.warning("OpenRouter models API failed: %s", e)
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("OpenRouter models API returned non-JSON")
        return []

    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []

    search_l = (search or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if len(out) >= lim:
            break
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("id") or row.get("canonical_slug") or "").strip()
        if not model_id:
            continue
        display_name = str(row.get("name") or model_id).strip()
        description = str(row.get("description") or "").strip()
        if search_l:
            haystack = " ".join(
                [
                    model_id.lower(),
                    display_name.lower(),
                    description.lower(),
                ]
            )
            if search_l not in haystack:
                continue
        top_provider = row.get("top_provider") if isinstance(row.get("top_provider"), dict) else {}
        context_length = row.get("context_length") or top_provider.get("context_length")
        modality = ""
        architecture = row.get("architecture") if isinstance(row.get("architecture"), dict) else {}
        if architecture:
            modality = str(architecture.get("modality") or "").strip()
        desc = description or f"OpenRouter model `{model_id}`."
        if context_length:
            desc += f" Context length: {context_length}."
        if modality:
            desc += f" Modality: {modality}."
        out.append(
            {
                "name": _safe_tool_name("openrouter_", model_id),
                "provider": "openrouter",
                "description": desc,
                "api_endpoint": _OPENROUTER_CHAT_API,
                "requires_registration": True,
                "model_id": model_id,
                "display_name": display_name,
                "context_length": context_length,
                "api_key_env": "OPENROUTER_API_KEY",
            }
        )
    return out


@dataclass
class ToolMetadata:
    """Metadata for an AI tool."""
    name: str
    description: str
    provider: str  # e.g., "openai", "anthropic", "huggingface"
    api_endpoint: str
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None  # Environment variable name
    capabilities: List[str] = field(default_factory=list)
    rate_limit: Optional[Dict[str, Any]] = None
    cost_per_request: Optional[float] = None
    adapter_class: Optional[str] = None  # Generated adapter class name
    adapter_path: Optional[str] = None  # Path to adapter module
    registered_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
            "api_endpoint": self.api_endpoint,
            "api_key": self.api_key,  # In production, encrypt this
            "api_key_env": self.api_key_env,
            "capabilities": self.capabilities,
            "rate_limit": self.rate_limit,
            "cost_per_request": self.cost_per_request,
            "adapter_class": self.adapter_class,
            "adapter_path": self.adapter_path,
            "registered_at": self.registered_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolMetadata":
        """Create ToolMetadata from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            provider=data["provider"],
            api_endpoint=data["api_endpoint"],
            api_key=data.get("api_key"),
            api_key_env=data.get("api_key_env"),
            capabilities=data.get("capabilities", []),
            rate_limit=data.get("rate_limit"),
            cost_per_request=data.get("cost_per_request"),
            adapter_class=data.get("adapter_class"),
            adapter_path=data.get("adapter_path"),
            registered_at=datetime.fromisoformat(data.get("registered_at", datetime.now().isoformat())),
            last_used=datetime.fromisoformat(data["last_used"]) if data.get("last_used") else None,
            usage_count=data.get("usage_count", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            metadata=data.get("metadata", {})
        )


class ToolAdapter:
    """
    Base adapter for AI tools.
    Provides standardized interface for different AI providers.
    """
    
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata
        self.api_key = self._get_api_key()
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from metadata or environment."""
        if self.metadata.api_key:
            return self.metadata.api_key
        
        if self.metadata.api_key_env:
            import os
            return os.getenv(self.metadata.api_key_env)
        
        return None
    
    def call(self, method: str, **kwargs) -> Dict[str, Any]:
        """
        Call a method on the tool.
        
        Args:
            method: Method name
            **kwargs: Method arguments
            
        Returns:
            Response dictionary with 'success' and 'data'/'error' keys
        """
        try:
            # This is a base implementation
            # Subclasses should override with provider-specific logic
            logger.warning(f"Base ToolAdapter.call() called - should be overridden")
            return {
                "success": False,
                "error": "Base adapter - implement provider-specific logic"
            }
        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def test_connection(self, web_reader) -> bool:
        """Test if the tool is accessible."""
        try:
            response = web_reader.request_json(
                method="GET",
                url=self.metadata.api_endpoint,
                timeout_s=5,
                caller_identity="ToolAdapter",
                task_id=None
            )
            return response.get("status_code", 0) < 400
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


class HuggingFaceInferenceToolAdapter(ToolAdapter):
    """Provider adapter for the Hugging Face Inference API."""

    _SUPPORTED_METHODS = {"call", "generate", "inference", "predict", "run"}

    def _resolve_endpoint(self) -> str:
        metadata_endpoint = self.metadata.metadata.get("api_endpoint")
        if isinstance(metadata_endpoint, str) and metadata_endpoint.strip():
            return metadata_endpoint.strip()
        return str(self.metadata.api_endpoint or "").strip()

    def _build_payload(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        if "payload" in kwargs and isinstance(kwargs["payload"], dict):
            return dict(kwargs["payload"])
        if "data" in kwargs and isinstance(kwargs["data"], dict):
            return dict(kwargs["data"])
        payload = dict(kwargs)
        payload.pop("timeout_sec", None)
        return payload

    def call(self, method: str, **kwargs) -> Dict[str, Any]:
        method_name = str(method or "").strip().lower()
        if method_name not in self._SUPPORTED_METHODS:
            return {
                "success": False,
                "error": f"Unsupported Hugging Face inference method: {method}",
            }

        endpoint = self._resolve_endpoint()
        if not endpoint:
            return {"success": False, "error": "Hugging Face inference endpoint is not configured"}

        token = self.api_key or _huggingface_api_token()
        if not token:
            return {
                "success": False,
                "error": "Hugging Face token not configured (expected HF_TOKEN or equivalent)",
            }

        try:
            from ..unified_api_budget import (
                can_spend,
                enabled as _ub,
                flat_units_for_channel,
                opportunistic_surplus_available,
                remaining_units,
            )

            if _ub():
                _hf_flat = flat_units_for_channel("huggingface_inference")
                _hf_ok = can_spend(_hf_flat)
                if (
                    not _hf_ok
                    and opportunistic_surplus_available()
                    and remaining_units() > 0
                ):
                    _hf_ok = can_spend(min(_hf_flat, remaining_units()))
                if not _hf_ok:
                    return {"success": False, "error": "unified_budget_exhausted"}
        except Exception:
            pass

        payload = self._build_payload(kwargs)
        if not isinstance(payload, dict):
            payload = {}
        if "inputs" not in payload:
            ti = str(
                kwargs.get("inputs")
                or kwargs.get("prompt")
                or kwargs.get("text")
                or kwargs.get("query")
                or ""
            ).strip()
            if ti:
                payload = {"inputs": ti}
        if not payload:
            return {"success": False, "error": "Provide payload=/data= or inputs=/prompt=/query="}

        timeout_sec = max(1.0, min(float(kwargs.get("timeout_sec", 30.0) or 30.0), 120.0))
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": _HF_DISCOVERY_USER_AGENT,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw_bytes = resp.read()
                content_type = ""
                headers = getattr(resp, "headers", None)
                if headers is not None:
                    content_type = str(headers.get("Content-Type") or "")
                body = raw_bytes.decode("utf-8", errors="replace")
                data: Any
                if "json" in content_type.lower():
                    data = json.loads(body)
                else:
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        data = body
                try:
                    from ..api_usage_meter import record_transport

                    record_transport("huggingface_inference", True)
                except Exception:
                    pass
                return {
                    "success": True,
                    "data": data,
                    "status_code": getattr(resp, "status", 200),
                }
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = str(e)
            try:
                parsed = json.loads(error_body)
                error_message = parsed.get("error") or parsed.get("message") or error_body
            except json.JSONDecodeError:
                error_message = error_body or str(e)
            logger.warning(
                "Hugging Face inference HTTP %s for %s: %s",
                getattr(e, "code", "?"),
                endpoint,
                error_message,
            )
            return {
                "success": False,
                "error": str(error_message).strip() or str(e),
                "status_code": getattr(e, "code", None),
            }
        except urllib.error.URLError as e:
            logger.warning("Hugging Face inference network error for %s: %s", endpoint, e)
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error("Hugging Face inference call failed for %s: %s", endpoint, e)
            return {"success": False, "error": str(e)}


class OpenRouterChatToolAdapter(ToolAdapter):
    """Chat completions via OpenRouter (OpenAI-compatible ``/api/v1/chat/completions``)."""

    _SUPPORTED = {"call", "chat", "generate", "completion", "run", "inference"}

    def call(self, method: str, **kwargs) -> Dict[str, Any]:
        m = str(method or "").strip().lower()
        if m not in self._SUPPORTED:
            return {"success": False, "error": f"Unsupported OpenRouter method: {method}"}
        token = self.api_key or _openrouter_api_token()
        if not token:
            return {"success": False, "error": "OPENROUTER_API_KEY not set"}
        meta = self.metadata.metadata if isinstance(self.metadata.metadata, dict) else {}
        model = str(meta.get("model_id") or kwargs.get("model") or "").strip()
        if not model:
            return {"success": False, "error": "OpenRouter model_id missing in tool metadata"}
        messages = kwargs.get("messages")
        if not isinstance(messages, list) or not messages:
            blob = str(
                kwargs.get("prompt")
                or kwargs.get("task")
                or kwargs.get("query")
                or kwargs.get("content")
                or ""
            ).strip()[:12000]
            if not blob:
                return {"success": False, "error": "Provide messages= or prompt=/task=/query=/content="}
            messages = [{"role": "user", "content": blob}]
        body = {
            "model": model,
            "messages": messages,
            "temperature": float(kwargs.get("temperature", 0.2) or 0.2),
        }
        timeout_sec = max(5.0, min(float(kwargs.get("timeout_sec", 60.0) or 60.0), 120.0))
        req = urllib.request.Request(
            _OPENROUTER_CHAT_API,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/project-guardian/elysia",
                "X-Title": "Project Guardian ToolRegistry",
                "User-Agent": _HF_DISCOVERY_USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            txt = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
            return {"success": True, "data": {"raw": data, "text": txt}}
        except urllib.error.HTTPError as e:
            err = ""
            try:
                err = e.read().decode("utf-8", errors="replace")[:800]
            except Exception:
                err = str(e)
            return {
                "success": False,
                "error": err or str(e),
                "status_code": getattr(e, "code", None),
            }
        except urllib.error.URLError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error("OpenRouter chat call failed: %s", e)
            return {"success": False, "error": str(e)}


def _default_capabilities_for_discovered_provider(provider: str) -> List[str]:
    p = (provider or "").strip().lower()
    if p == "huggingface":
        return ["llm", "completion", "inference", "hf_inference", "chat"]
    if p == "openrouter":
        return ["llm", "chat", "completion", "openrouter_chat"]
    return ["llm", "chat"]


class ToolRegistry:
    """
    Auto-discovers, registers, and manages external AI tools and APIs.
    Supports auto-generation of adapters for new APIs.
    """
    
    def __init__(self, storage_path: str = "data/tool_registry.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.tools: Dict[str, ToolMetadata] = {}  # name -> ToolMetadata
        self.adapters: Dict[str, ToolAdapter] = {}  # name -> ToolAdapter
        self.load()
    
    def ensure_minimal_builtin_tools(self) -> None:
        """
        Ensure catalog lists llm / web / exec surfaces so orchestration can treat the registry as usable.
        Builtin metadata distinguishes operational bridges, gated surfaces, and dependency-gated tools.
        """
        builtin_metadata = {
            "elysia_builtin_llm": {
                "builtin": True,
                "capability_state": "operational",
                "execution_surface": "capability_execution",
            },
            "elysia_builtin_web": {
                "builtin": True,
                "capability_state": "operational",
                "execution_surface": "capability_execution",
            },
            "elysia_builtin_exec": {
                "builtin": True,
                "capability_state": "gated",
                "requires_approval": True,
                "execution_surface": "capability_execution",
            },
            "elysia_bounded_browser": {
                "builtin": True,
                "capability_state": "fallback_operational",
                "preferred_dependency": "playwright",
                "fallback_backend": "urllib_static",
                "execution_surface": "capability_execution",
            },
            "elysia_moltbook_browser": {
                "builtin": True,
                "capability_state": "fallback_operational",
                "preferred_dependency": "playwright",
                "fallback_backend": "urllib_static",
                "execution_surface": "capability_execution",
            },
            "elysia_social_intel": {
                "builtin": True,
                "capability_state": "operational",
                "execution_surface": "capability_execution",
            },
            "revenue_executor": {
                "builtin": True,
                "capability_state": "operational",
                "execution_surface": "capability_execution",
            },
            "artifact_synthesizer": {
                "builtin": True,
                "capability_state": "operational",
                "execution_surface": "capability_execution",
            },
            "opportunity_ranker": {
                "builtin": True,
                "capability_state": "operational",
                "execution_surface": "capability_execution",
            },
        }
        builtins = [
            (
                "elysia_builtin_llm",
                "Builtin LLM/chat surface (routes via unified LLM stack)",
                "builtin",
                "local://llm",
                ["llm", "chat", "completion"],
            ),
            (
                "elysia_builtin_web",
                "Builtin web/read surface (routes via WebReader when used)",
                "builtin",
                "local://web",
                ["web", "http", "fetch"],
            ),
            (
                "elysia_builtin_exec",
                "Builtin local execution surface (gated; no shell without approval)",
                "builtin",
                "local://exec",
                ["exec", "run", "script"],
            ),
            (
                "revenue_executor",
                "Local revenue / execution-plan bridge (uses income_generator + artifacts)",
                "builtin",
                "local://revenue_executor",
                ["revenue", "execution_plan", "finance"],
            ),
            (
                "artifact_synthesizer",
                "Merge latest JSON operator artifacts from disk",
                "builtin",
                "local://artifact_synthesizer",
                ["artifacts", "reports", "synthesis"],
            ),
            (
                "opportunity_ranker",
                "Rank opportunities from latest revenue brief files",
                "builtin",
                "local://opportunity_ranker",
                ["ranking", "opportunities", "revenue"],
            ),
            (
                "elysia_bounded_browser",
                "Bounded read-only browser (Playwright when available, urllib fallback)",
                "builtin",
                "local://bounded_browser",
                ["bounded_browse"],
            ),
            (
                "elysia_moltbook_browser",
                "Domain-locked Moltbook browser with deeper same-domain navigation",
                "builtin",
                "local://moltbook_browser",
                ["moltbook_browse", "moltbook_interact"],
            ),
            (
                "elysia_social_intel",
                "Moltbook social interaction: observe, summarize, rank, draft, and gated outbound queue",
                "builtin",
                "local://social_intel",
                ["social_moltbook_observe", "moltbook_full_interaction"],
            ),
        ]
        for name, desc, prov, ep, caps in builtins:
            if name in self.tools:
                continue
            try:
                self.register_tool(
                    name,
                    desc,
                    prov,
                    ep,
                    capabilities=list(caps),
                    metadata=dict(builtin_metadata.get(name, {"builtin": True, "capability_state": "unknown"})),
                )
            except Exception as e:
                logger.debug("ensure_minimal_builtin_tools %s: %s", name, e)

    def register_tool(
        self,
        name: str,
        description: str,
        provider: str,
        api_endpoint: str,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        rate_limit: Optional[Dict[str, Any]] = None,
        cost_per_request: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Register a new AI tool.
        
        Args:
            name: Tool name (unique identifier)
            description: Tool description
            provider: Provider name (e.g., "openai", "anthropic")
            api_endpoint: API endpoint URL
            api_key: API key (or use api_key_env)
            api_key_env: Environment variable name for API key
            capabilities: List of capabilities this tool provides
            rate_limit: Rate limit configuration
            cost_per_request: Cost per API call
            metadata: Additional metadata
            
        Returns:
            Tool name (for confirmation)
        """
        if name in self.tools:
            logger.warning(f"Tool {name} already registered, updating...")
        
        tool = ToolMetadata(
            name=name,
            description=description,
            provider=provider,
            api_endpoint=api_endpoint,
            api_key=api_key,
            api_key_env=api_key_env,
            capabilities=capabilities or [],
            rate_limit=rate_limit,
            cost_per_request=cost_per_request,
            metadata=metadata or {}
        )
        
        self.tools[name] = tool
        
        # Create adapter
        adapter = self._create_adapter(tool)
        if adapter:
            self.adapters[name] = adapter
        
        self.save()
        logger.info(f"Registered tool: {name} ({provider})")
        
        return name

    def register_from_discovery_item(
        self,
        item: Dict[str, Any],
        *,
        extra_capabilities: Optional[List[str]] = None,
    ) -> str:
        """
        Register a single row returned by ``discover_tools`` (Hugging Face / OpenRouter).

        Copies model metadata into ``ToolMetadata.metadata`` for adapters. Does not
        overwrite an existing tool with the same ``name`` without ``register_tool``'s
        built-in update path.
        """
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("discovery item missing name")
        desc = str(item.get("description") or name).strip()
        provider = str(item.get("provider") or "").strip().lower()
        endpoint = str(item.get("api_endpoint") or "").strip()
        if not endpoint:
            raise ValueError("discovery item missing api_endpoint")
        skip = {
            "name",
            "description",
            "provider",
            "api_endpoint",
            "requires_registration",
            "api_key_env",
        }
        meta: Dict[str, Any] = {}
        for k, v in item.items():
            if k in skip or str(k).startswith("_"):
                continue
            meta[k] = v
        caps = list(dict.fromkeys((extra_capabilities or []) + _default_capabilities_for_discovered_provider(provider)))
        return self.register_tool(
            name,
            desc,
            provider,
            endpoint,
            api_key_env=item.get("api_key_env"),
            capabilities=caps,
            metadata=meta,
        )

    def _create_adapter(self, tool: ToolMetadata) -> Optional[ToolAdapter]:
        """Create an adapter for a tool."""
        try:
            endpoint = str(tool.api_endpoint or "").strip().lower()
            provider = str(tool.provider or "").strip().lower()
            if provider == "huggingface" and "api-inference.huggingface.co" in endpoint:
                return HuggingFaceInferenceToolAdapter(tool)
            if provider == "openrouter" and "openrouter.ai" in endpoint:
                return OpenRouterChatToolAdapter(tool)
            return ToolAdapter(tool)
        except Exception as e:
            logger.error(f"Failed to create adapter for {tool.name}: {e}")
            return None
    
    def get_tool(self, name: str) -> Optional[ToolAdapter]:
        """Get a tool adapter by name."""
        return self.adapters.get(name)
    
    def get_tool_metadata(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name."""
        return self.tools.get(name)
    
    def list_tools(self, provider: Optional[str] = None) -> List[str]:
        """List registered tool names, optionally filtered by provider."""
        if provider:
            return [
                name for name, tool in self.tools.items()
                if tool.provider == provider
            ]
        return list(self.tools.keys())
    
    def discover_tools(
        self,
        sources: Optional[List[str]] = None,
        *,
        limit_per_source: int = 25,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Discover tools from external sources.

        Args:
            sources: Sources to query: ``huggingface`` (Hub model list API), ``openrouter``
                (public models API), ``rapidapi``, ``edenai`` (latter two reserved).
            limit_per_source: Max items per source (capped at 100 for HF).
            search: Optional Hub search string (passed to HF ``search`` query param).

        Returns:
            List of dicts suitable for review or ``register_tool`` (not auto-registered).
        """
        sources = [str(s).lower().strip() for s in (sources or ["huggingface"]) if str(s).strip()]
        if not sources:
            sources = ["huggingface"]
        discovered: List[Dict[str, Any]] = []
        logger.info("Discovering tools from sources: %s", sources)

        for src in sources:
            if src == "huggingface":
                try:
                    rows = discover_huggingface_hub_models(
                        limit=limit_per_source,
                        search=search,
                    )
                    discovered.extend(rows)
                    logger.info(
                        "Hugging Face Hub discovery: %d model(s) (limit=%s)",
                        len(rows),
                        limit_per_source,
                    )
                except Exception as e:
                    logger.error("Hugging Face discovery failed: %s", e)
            elif src == "openrouter":
                try:
                    rows = discover_openrouter_models(
                        limit=limit_per_source,
                        search=search,
                    )
                    discovered.extend(rows)
                    logger.info(
                        "OpenRouter discovery: %d model(s) (limit=%s)",
                        len(rows),
                        limit_per_source,
                    )
                except Exception as e:
                    logger.error("OpenRouter discovery failed: %s", e)
            elif src in ("rapidapi", "edenai"):
                _log_unimplemented_discovery_source_once(src)
            else:
                logger.debug("Unknown discovery source %r skipped", src)

        return discovered
    
    def call_tool(
        self,
        tool_name: str,
        method: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call a registered tool.
        
        Args:
            tool_name: Tool name
            method: Method to call
            **kwargs: Method arguments
            
        Returns:
            Response dictionary
        """
        adapter = self.get_tool(tool_name)
        if not adapter:
            logger.info(
                "[ToolUtil] call_tool skipped tool=%s reason=no_adapter",
                tool_name,
            )
            return {
                "success": False,
                "error": f"Tool {tool_name} not found"
            }
        
        tool = self.tools.get(tool_name)
        if not tool:
            logger.info(
                "[ToolUtil] call_tool skipped tool=%s reason=no_metadata",
                tool_name,
            )
            return {
                "success": False,
                "error": f"Tool metadata for {tool_name} not found"
            }
        
        logger.info(
            "[ToolUtil] call_tool invoke tool=%s method=%s arg_keys=%s",
            tool_name,
            method,
            list(kwargs.keys())[:16],
        )
        # Update usage stats
        tool.usage_count += 1
        tool.last_used = datetime.now()

        t0 = time.perf_counter()
        result = adapter.call(method, **kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Update success/failure stats
        if result.get("success"):
            tool.success_count += 1
        else:
            tool.failure_count += 1
        logger.info(
            "[ToolUtil] call_tool done tool=%s success=%s err=%s",
            tool_name,
            bool(result.get("success")),
            (result.get("error") or "")[:200],
        )
        try:
            from .capability_registry import log_tool_registry_call_outcome

            log_tool_registry_call_outcome(
                tool_name=tool_name,
                method=str(method or "call"),
                success=bool(result.get("success")),
                latency_ms=latency_ms,
                extra={"provider": tool.provider},
            )
        except Exception as e:
            logger.debug("call_tool outcome log: %s", e)

        self.save()
        return result
    
    def revoke_tool(self, name: str) -> bool:
        """Revoke/remove a tool from registry."""
        if name not in self.tools:
            return False
        
        del self.tools[name]
        if name in self.adapters:
            del self.adapters[name]
        
        self.save()
        logger.info(f"Revoked tool: {name}")
        return True
    
    def export_config(self, filepath: Optional[str] = None) -> str:
        """
        Export tool configurations to JSON file.
        
        Args:
            filepath: Optional custom file path
            
        Returns:
            Path to exported file
        """
        path = Path(filepath) if filepath else self.storage_path.parent / "tool_registry_export.json"
        
        data = {
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "exported_at": datetime.now().isoformat()
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(self.tools)} tools to {path}")
        return str(path)
    
    def save(self):
        """Save tool registry to disk."""
        data = {
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load tool registry from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            for tool_data in data.get("tools", []):
                tool = ToolMetadata.from_dict(tool_data)
                self.tools[tool.name] = tool
                
                # Recreate adapter
                adapter = self._create_adapter(tool)
                if adapter:
                    self.adapters[tool.name] = adapter
            
            logger.info(f"Loaded {len(self.tools)} tools from registry")
        except Exception as e:
            logger.error(f"Error loading tool registry: {e}")


# Example usage
if __name__ == "__main__":
    registry = ToolRegistry()
    
    # Register a tool
    registry.register_tool(
        name="openai_gpt4",
        description="OpenAI GPT-4 API",
        provider="openai",
        api_endpoint="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        capabilities=["text_generation", "chat", "embeddings"],
        rate_limit={"max_requests": 100, "window_seconds": 60},
        cost_per_request=0.03
    )
    
    # List tools
    tools = registry.list_tools()
    print(f"Registered tools: {tools}")
    
    # Export config
    export_path = registry.export_config()
    print(f"Exported to: {export_path}")

