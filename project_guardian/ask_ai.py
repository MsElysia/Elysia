# project_guardian/ask_ai.py
# AskAI: Unified Interface for Multiple AI Services
# Based on Conversation 3 (elysia 4 sub a) design specifications

import logging
from dataclasses import dataclass
import os
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum
import json

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    # Graceful degradation - don't warn unless actually trying to use OpenAI

try:
    from .ai_tool_registry_engine import ToolRegistry
except ImportError:
    from ai_tool_registry_engine import ToolRegistry

logger = logging.getLogger(__name__)


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
    metadata: Dict[str, Any] = None


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
    metadata: Dict[str, Any] = None


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


class AskAI:
    """
    Unified interface for multiple AI services (OpenAI, Claude, Grok).
    Provides redundancy and fallback capabilities.
    """
    
    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        default_provider: AIProvider = AIProvider.OPENAI
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.default_provider = default_provider
        
        # Provider adapters
        self.adapters: Dict[AIProvider, Any] = {}
        self._initialize_adapters()
    
    def _initialize_adapters(self):
        """Initialize adapters for available providers."""
        # OpenAI
        try:
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key and OPENAI_AVAILABLE:
                self.adapters[AIProvider.OPENAI] = OpenAIAdapter(openai_key)
                logger.info("OpenAI adapter initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI adapter: {e}")
        
        # Other providers would be initialized here
        # Claude, Grok, etc.
    
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
                AIProvider.ANTHROPIC: "claude-3-opus",
                AIProvider.GROK: "grok-beta"
            }
            model = model_map.get(provider, "default")
        
        # Call adapter
        try:
            if provider == AIProvider.OPENAI:
                result = adapter.generate(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt
                )
            else:
                # Other providers would have similar calls
                result = {"success": False, "error": "Provider not implemented"}
            
            if result.get("success"):
                return AIResponse(
                    content=result.get("content", ""),
                    provider=provider.value,
                    model=result.get("model", model),
                    tokens_used=result.get("tokens"),
                    latency_ms=result.get("latency_ms"),
                    success=True,
                    metadata=result.get("metadata")
                )
            else:
                return AIResponse(
                    content="",
                    provider=provider.value,
                    model=model,
                    success=False,
                    error=result.get("error", "Unknown error")
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

