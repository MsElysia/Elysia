# project_guardian/orchestration/adapters/openai.py
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Rough blended $/1k tokens for budgeting telemetry only (not billing truth).
_DEFAULT_INPUT_1K = 0.00015
_DEFAULT_OUTPUT_1K = 0.0006


class OpenAIAdapter:
    """Minimal OpenAI chat.completions over HTTP."""

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self.model_name = model
        self.provider_name = "openai"
        ak = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        if not ak:
            try:
                from ...api_key_manager import get_api_key_manager

                ak = (get_api_key_manager().keys.openai or "").strip()
            except Exception:
                ak = ""
        self._api_key = ak
        self._base = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def generate(self, prompt: str, system: str | None = None, **kwargs: object) -> str:
        from ...prompts.prompt_builder import log_legacy_llm_call

        log_legacy_llm_call(
            "",
            caller="OpenAIAdapter.generate",
            reason="orchestration_openai_adapter_transport",
        )
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not set; cloud adapter unavailable")
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": float(kwargs.get("temperature", 0.2) or 0.2),
        }
        if kwargs.get("response_format_json"):
            body["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            r = await client.post(
                f"{self._base}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=body,
            )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response is not None and e.response.status_code == 429:
                    try:
                        from ...openai_degraded import note_openai_rate_limit, note_openai_reasoning_rate_limit

                        body = ""
                        try:
                            body = (e.response.text or "")[:800]
                        except Exception:
                            body = ""
                        note_openai_rate_limit(
                            "orchestration_openai_chat", status_code=429, detail=body
                        )
                        note_openai_reasoning_rate_limit(
                            body or str(e), status_code=429, context="orchestration_openai_chat"
                        )
                    except Exception:
                        pass
                raise
            data = r.json()
        _ = time.perf_counter() - t0
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = "".join(parts)
        return (content or "").strip()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens / 1000.0) * _DEFAULT_INPUT_1K + (output_tokens / 1000.0) * _DEFAULT_OUTPUT_1K
