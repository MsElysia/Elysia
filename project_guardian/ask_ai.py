# project_guardian/ask_ai.py
# AskAI: Unified Interface for Multiple AI Services
# Based on Conversation 3 (elysia 4 sub a) design specifications

import logging
from dataclasses import dataclass, field
import os
from typing import Dict, Any, List, Optional
from enum import Enum
import json
import time
import urllib.error
import urllib.request

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    # Graceful degradation - don't warn unless actually trying to use OpenAI

try:
    from .ai_tool_registry_engine import (
        HuggingFaceInferenceToolAdapter,
        ToolMetadata,
        ToolRegistry,
    )
except ImportError:
    from ai_tool_registry_engine import (
        HuggingFaceInferenceToolAdapter,
        ToolMetadata,
        ToolRegistry,
    )

logger = logging.getLogger(__name__)

_ANTHROPIC_MESSAGES_API = "https://api.anthropic.com/v1/messages"
_GROK_CHAT_API = "https://api.x.ai/v1/chat/completions"
_DEFAULT_HTTP_TIMEOUT_SEC = 60.0
_DEFAULT_USER_AGENT = "ProjectGuardian-AskAI/1.0"


class AIProvider(Enum):
    """Supported AI providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROK = "grok"
    HUGGINGFACE = "huggingface"
    CUSTOM = "custom"


@dataclass
class AIRequest:
    """Standardized AI request format."""
    prompt: str
    provider: AIProvider = AIProvider.OPENAI
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    """Standardized AI response format."""
    content: str
    provider: str
    model: str
    tokens_used: Optional[int] = None
    cost: Optional[float] = None
    latency_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _clamp_timeout(timeout_sec: Optional[float]) -> float:
    try:
        raw = float(timeout_sec or _DEFAULT_HTTP_TIMEOUT_SEC)
    except (TypeError, ValueError):
        raw = _DEFAULT_HTTP_TIMEOUT_SEC
    return max(5.0, min(raw, 180.0))


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        if isinstance(payload.get("error"), dict):
            nested = payload["error"]
            if nested.get("message"):
                return str(nested["message"])
            if nested.get("type"):
                return str(nested["type"])
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(payload, list) and payload:
        return _extract_error_message(payload[0], fallback)
    return fallback


def _decode_json_response(response) -> Dict[str, Any]:
    raw = response.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Provider returned non-object JSON payload")
    return data


def _read_http_error(e: urllib.error.HTTPError) -> Dict[str, Any]:
    try:
        raw = e.read().decode("utf-8", errors="replace")
    except Exception:
        raw = str(e)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"message": raw or str(e)}
    if not isinstance(parsed, dict):
        parsed = {"message": raw or str(e)}
    return parsed


def _extract_anthropic_text(data: Dict[str, Any]) -> str:
    parts: List[str] = []
    for item in data.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _extract_chat_text(data: Dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _extract_huggingface_text(data: Any) -> str:
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        for key in ("generated_text", "summary_text", "translation_text", "answer", "text"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        generated = data.get("generated_text")
        if isinstance(generated, list):
            return _extract_huggingface_text(generated)
    if isinstance(data, list):
        parts: List[str] = []
        for item in data:
            txt = _extract_huggingface_text(item)
            if txt:
                parts.append(txt)
        return "\n".join(parts).strip()
    return ""


class OpenAIAdapter:
    """Adapter for OpenAI API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required")
        
        if OPENAI_AVAILABLE:
            openai.api_key = self.api_key
        else:
            logger.warning("OpenAI library not installed")
    
    def generate(
        self,
        prompt: str,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate response using OpenAI API."""
        if not OPENAI_AVAILABLE:
            return {
                "success": False,
                "error": "OpenAI library not installed"
            }
        
        try:
            import time
            start_time = time.time()
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            latency_ms = (time.time() - start_time) * 1000
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if hasattr(response, 'usage') else None
            
            return {
                "success": True,
                "content": content,
                "tokens": tokens,
                "latency_ms": latency_ms,
                "model": model
            }
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {
                "success": False,
                "error": str(e)
            }


class AnthropicAdapter:
    """Adapter for Anthropic's Messages API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key required")

    def generate(
        self,
        prompt: str,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            start_time = time.time()
            body: Dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens or 1024,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                body["system"] = system_prompt

            request = urllib.request.Request(
                _ANTHROPIC_MESSAGES_API,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                    "User-Agent": _DEFAULT_USER_AGENT,
                },
                method="POST",
            )

            with urllib.request.urlopen(
                request,
                timeout=_clamp_timeout(_DEFAULT_HTTP_TIMEOUT_SEC),
            ) as response:
                data = _decode_json_response(response)

            latency_ms = (time.time() - start_time) * 1000
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            input_tokens = _safe_int(usage.get("input_tokens"))
            output_tokens = _safe_int(usage.get("output_tokens"))
            tokens_used = None
            if input_tokens is not None or output_tokens is not None:
                tokens_used = (input_tokens or 0) + (output_tokens or 0)

            return {
                "success": True,
                "content": _extract_anthropic_text(data),
                "tokens": tokens_used,
                "latency_ms": latency_ms,
                "model": str(data.get("model") or model),
                "metadata": {
                    "usage": usage,
                    "stop_reason": data.get("stop_reason"),
                },
            }
        except urllib.error.HTTPError as e:
            payload = _read_http_error(e)
            message = _extract_error_message(payload, str(e))
            logger.warning("Anthropic API HTTP %s: %s", getattr(e, "code", "?"), message)
            return {"success": False, "error": message, "metadata": {"status_code": getattr(e, "code", None)}}
        except urllib.error.URLError as e:
            logger.warning("Anthropic API network error: %s", e)
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error("Anthropic API error: %s", e)
            return {"success": False, "error": str(e)}


class GrokAdapter:
    """Adapter for xAI / Grok's OpenAI-compatible chat completions API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key
            or os.getenv("XAI_API_KEY")
            or os.getenv("GROK_API_KEY")
        )
        if not self.api_key:
            raise ValueError("xAI API key required")

    def generate(
        self,
        prompt: str,
        model: str = "grok-4",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            start_time = time.time()
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            body: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                body["max_tokens"] = max_tokens

            request = urllib.request.Request(
                _GROK_CHAT_API,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": _DEFAULT_USER_AGENT,
                },
                method="POST",
            )

            with urllib.request.urlopen(
                request,
                timeout=_clamp_timeout(_DEFAULT_HTTP_TIMEOUT_SEC),
            ) as response:
                data = _decode_json_response(response)

            latency_ms = (time.time() - start_time) * 1000
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            tokens_used = _safe_int(usage.get("total_tokens"))

            return {
                "success": True,
                "content": _extract_chat_text(data),
                "tokens": tokens_used,
                "latency_ms": latency_ms,
                "model": str(data.get("model") or model),
                "metadata": {
                    "usage": usage,
                    "system_fingerprint": data.get("system_fingerprint"),
                },
            }
        except urllib.error.HTTPError as e:
            payload = _read_http_error(e)
            message = _extract_error_message(payload, str(e))
            logger.warning("Grok API HTTP %s: %s", getattr(e, "code", "?"), message)
            return {"success": False, "error": message, "metadata": {"status_code": getattr(e, "code", None)}}
        except urllib.error.URLError as e:
            logger.warning("Grok API network error: %s", e)
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error("Grok API error: %s", e)
            return {"success": False, "error": str(e)}


class HuggingFaceAdapter:
    """Adapter for Hugging Face Inference API chat/text generation style calls."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key
            or os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACE_HUB_TOKEN")
            or os.getenv("HUGGINGFACE_API_TOKEN")
        )
        if not self.api_key:
            raise ValueError("Hugging Face API token required")

    def generate(
        self,
        prompt: str,
        model: str = "gpt2",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        endpoint = f"https://api-inference.huggingface.co/models/{model}"
        metadata = ToolMetadata(
            name=f"hf_{model.replace('/', '__')}",
            description=f"Hugging Face inference for {model}",
            provider="huggingface",
            api_endpoint=endpoint,
            api_key=self.api_key,
            api_key_env="HF_TOKEN",
            metadata={"model_id": model, "api_endpoint": endpoint},
        )
        adapter = HuggingFaceInferenceToolAdapter(metadata)
        payload: Dict[str, Any] = {
            "inputs": f"{system_prompt.strip()}\n\n{prompt}".strip() if system_prompt else prompt,
        }
        parameters: Dict[str, Any] = {}
        if max_tokens is not None:
            parameters["max_new_tokens"] = int(max_tokens)
        if temperature is not None:
            parameters["temperature"] = float(temperature)
        if parameters:
            payload["parameters"] = parameters

        started = time.time()
        result = adapter.call("generate", payload=payload, timeout_sec=_DEFAULT_HTTP_TIMEOUT_SEC)
        latency_ms = (time.time() - started) * 1000
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Hugging Face inference failed"),
                "metadata": {"status_code": result.get("status_code")},
            }

        data = result.get("data")
        return {
            "success": True,
            "content": _extract_huggingface_text(data),
            "latency_ms": latency_ms,
            "model": model,
            "metadata": {
                "raw": data,
                "status_code": result.get("status_code"),
            },
        }


class AskAI:
    """
    Unified interface for multiple AI services (OpenAI, Claude, Grok).
    Provides redundancy and fallback capabilities.
    """
    
    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        default_provider: AIProvider = AIProvider.OPENAI,
        openai_api_key: Optional[str] = None,
        claude_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        grok_api_key: Optional[str] = None,
        xai_api_key: Optional[str] = None,
        huggingface_api_key: Optional[str] = None,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.default_provider = default_provider
        self._configured_api_keys: Dict[AIProvider, Optional[str]] = {
            AIProvider.OPENAI: openai_api_key,
            AIProvider.ANTHROPIC: anthropic_api_key or claude_api_key,
            AIProvider.GROK: xai_api_key or grok_api_key,
            AIProvider.HUGGINGFACE: huggingface_api_key,
        }
        
        # Provider adapters
        self.adapters: Dict[AIProvider, Any] = {}
        self._initialize_adapters()
    
    def _initialize_adapters(self):
        """Initialize adapters for available providers."""
        # OpenAI
        try:
            openai_key = self._configured_api_keys.get(AIProvider.OPENAI) or os.getenv("OPENAI_API_KEY")
            if openai_key and OPENAI_AVAILABLE:
                self.adapters[AIProvider.OPENAI] = OpenAIAdapter(openai_key)
                logger.info("OpenAI adapter initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI adapter: {e}")

        try:
            anthropic_key = self._configured_api_keys.get(AIProvider.ANTHROPIC) or os.getenv("ANTHROPIC_API_KEY")
            if anthropic_key:
                self.adapters[AIProvider.ANTHROPIC] = AnthropicAdapter(anthropic_key)
                logger.info("Anthropic adapter initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Anthropic adapter: {e}")

        try:
            grok_key = (
                self._configured_api_keys.get(AIProvider.GROK)
                or os.getenv("XAI_API_KEY")
                or os.getenv("GROK_API_KEY")
            )
            if grok_key:
                self.adapters[AIProvider.GROK] = GrokAdapter(grok_key)
                logger.info("Grok adapter initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Grok adapter: {e}")

        try:
            huggingface_key = (
                self._configured_api_keys.get(AIProvider.HUGGINGFACE)
                or os.getenv("HF_TOKEN")
                or os.getenv("HUGGINGFACE_HUB_TOKEN")
                or os.getenv("HUGGINGFACE_API_TOKEN")
            )
            if huggingface_key:
                self.adapters[AIProvider.HUGGINGFACE] = HuggingFaceAdapter(huggingface_key)
                logger.info("Hugging Face adapter initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Hugging Face adapter: {e}")
    
    def ask(
        self,
        prompt: str,
        provider: Optional[AIProvider] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        fallback: bool = True
    ) -> AIResponse:
        """
        Ask a question to an AI provider.
        
        Args:
            prompt: Question or prompt
            provider: AI provider (defaults to configured default)
            model: Model name (defaults to provider's default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            system_prompt: System-level instructions
            fallback: If True, try fallback providers on failure
            
        Returns:
            AIResponse object
        """
        provider = provider or self.default_provider
        
        # Try primary provider
        result = self._try_provider(
            provider=provider,
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt
        )
        
        # If failed and fallback enabled, try other providers
        if not result.success and fallback:
            for fallback_provider in [p for p in AIProvider if p != provider]:
                if fallback_provider in self.adapters:
                    logger.info(f"Trying fallback provider: {fallback_provider.value}")
                    result = self._try_provider(
                        provider=fallback_provider,
                        prompt=prompt,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        system_prompt=system_prompt
                    )
                    if result.success:
                        break
        
        return result

    async def ask_async(
        self,
        prompt: str,
        provider: Optional[AIProvider] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        fallback: bool = True
    ) -> AIResponse:
        """Async wrapper for call sites that need non-blocking compatibility."""
        import asyncio

        return await asyncio.to_thread(
            self.ask,
            prompt,
            provider,
            model,
            temperature,
            max_tokens,
            system_prompt,
            fallback,
        )
    
    def _try_provider(
        self,
        provider: AIProvider,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> AIResponse:
        """Try to get response from a specific provider."""
        adapter = self.adapters.get(provider)
        if not adapter:
            return AIResponse(
                content="",
                provider=provider.value,
                model=model or "unknown",
                success=False,
                error=f"Provider {provider.value} not available"
            )
        
        # Default models per provider
        if not model:
            model_map = {
                AIProvider.OPENAI: "gpt-4",
                AIProvider.ANTHROPIC: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                AIProvider.GROK: os.getenv("GROK_MODEL") or os.getenv("XAI_MODEL") or "grok-4",
                AIProvider.HUGGINGFACE: os.getenv("HF_MODEL") or os.getenv("HUGGINGFACE_MODEL") or "gpt2",
            }
            model = model_map.get(provider, "default")
        
        # Call adapter
        try:
            if provider in (AIProvider.OPENAI, AIProvider.ANTHROPIC, AIProvider.GROK, AIProvider.HUGGINGFACE):
                result = adapter.generate(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt
                )
            elif hasattr(adapter, "generate"):
                result = adapter.generate(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                )
            elif hasattr(adapter, "call"):
                call_result = adapter.call(
                    "generate",
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                )
                if call_result.get("success"):
                    data = call_result.get("data")
                    content = ""
                    if isinstance(data, dict):
                        content = str(data.get("text") or data.get("content") or "")
                    elif isinstance(data, str):
                        content = data
                    result = {
                        "success": True,
                        "content": content,
                        "model": model,
                        "metadata": {"raw": data},
                    }
                else:
                    result = {
                        "success": False,
                        "error": call_result.get("error", "Custom adapter call failed"),
                        "metadata": {"raw": call_result},
                    }
            else:
                result = {
                    "success": False,
                    "error": f"Provider {provider.value} adapter does not support generate() or call()",
                }
            
            if result.get("success"):
                return AIResponse(
                    content=result.get("content", ""),
                    provider=provider.value,
                    model=result.get("model", model),
                    tokens_used=result.get("tokens"),
                    latency_ms=result.get("latency_ms"),
                    success=True,
                    metadata=result.get("metadata") or {}
                )
            else:
                return AIResponse(
                    content="",
                    provider=provider.value,
                    model=model,
                    success=False,
                    error=result.get("error", "Unknown error"),
                    metadata=result.get("metadata") or {}
                )
        except Exception as e:
            logger.error(f"Error calling {provider.value}: {e}")
            return AIResponse(
                content="",
                provider=provider.value,
                model=model,
                success=False,
                error=str(e)
            )
    
    def compare_providers(
        self,
        prompt: str,
        providers: Optional[List[AIProvider]] = None,
        model: Optional[str] = None
    ) -> Dict[str, AIResponse]:
        """
        Compare responses from multiple providers.
        
        Args:
            prompt: Question to ask
            providers: List of providers to compare (defaults to all available)
            model: Model to use (if supported by provider)
            
        Returns:
            Dictionary mapping provider name -> AIResponse
        """
        providers = providers or list(self.adapters.keys())
        results = {}
        
        for provider in providers:
            if provider in self.adapters:
                response = self.ask(
                    prompt=prompt,
                    provider=provider,
                    model=model,
                    fallback=False  # Don't fallback when comparing
                )
                results[provider.value] = response
        
        return results
    
    def get_available_providers(self) -> List[str]:
        """Get list of available providers."""
        return [p.value for p in self.adapters.keys()]
    
    def register_provider(
        self,
        provider: AIProvider,
        adapter: Any,
        api_key: Optional[str] = None
    ):
        """Register a custom provider adapter."""
        self.adapters[provider] = adapter
        logger.info(f"Registered provider: {provider.value}")


# Example usage
if __name__ == "__main__":
    askai = AskAI()
    
    # Ask a question
    response = askai.ask(
        prompt="What is the capital of France?",
        provider=AIProvider.OPENAI
    )
    
    if response.success:
        print(f"Response: {response.content}")
        print(f"Tokens: {response.tokens_used}")
        print(f"Latency: {response.latency_ms:.0f}ms")
    else:
        print(f"Error: {response.error}")

