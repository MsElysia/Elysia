# project_guardian/orchestration/adapters/ollama.py
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class OllamaAdapter:
    """Ollama /api/chat with verified fallback to /api/generate when chat is unavailable."""

    def __init__(self, model: str, base_url: Optional[str] = None) -> None:
        self.model_name = model
        self.provider_name = "ollama"
        from ...ollama_health import normalize_ollama_base, verify_ollama_runtime

        raw = base_url or os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        self._base = normalize_ollama_base(raw)
        self._chat_url = f"{self._base}/api/chat"
        self._gen_url = f"{self._base}/api/generate"
        self._health = verify_ollama_runtime(self._base, self.model_name, timeout=12.0)
        self._prefer_generate = bool(self._health.prefer_generate)
        if not self._health.ok:
            logger.error(
                "[OllamaAdapter] Local model=%s not reachable: %s",
                self.model_name,
                self._health.detail,
            )

    async def generate(self, prompt: str, system: str | None = None, **kwargs: object) -> str:
        from ...ollama_health import messages_to_prompt
        from ...prompts.prompt_builder import log_legacy_llm_call

        log_legacy_llm_call(
            "",
            caller="OllamaAdapter.generate",
            reason="orchestration_ollama_adapter_transport",
        )

        if not self._health.ok:
            raise RuntimeError(self._health.detail)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "stream": False,
            "messages": messages,
            "options": {},
        }
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            payload["options"]["temperature"] = float(kwargs["temperature"])  # type: ignore[arg-type]
        if "num_predict" in kwargs and kwargs["num_predict"] is not None:
            payload["options"]["num_predict"] = int(kwargs["num_predict"])  # type: ignore[arg-type]
        fmt = kwargs.get("format")
        if fmt is not None:
            payload["format"] = fmt
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                if not self._prefer_generate:
                    r = await client.post(self._chat_url, json=payload)
                    r.raise_for_status()
                    data = r.json()
                else:
                    gen_body: Dict[str, Any] = {
                        "model": self.model_name,
                        "prompt": messages_to_prompt(messages),
                        "stream": False,
                        "options": payload.get("options") or {},
                    }
                    if "format" in payload:
                        gen_body["format"] = payload["format"]
                    r = await client.post(self._gen_url, json=gen_body)
                    r.raise_for_status()
                    gj = r.json()
                    data = {"message": {"content": (gj.get("response") or "").strip()}}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404 and not self._prefer_generate:
                logger.warning("[OllamaAdapter] /api/chat 404; retrying with /api/generate")
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                    gen_body = {
                        "model": self.model_name,
                        "prompt": messages_to_prompt(messages),
                        "stream": False,
                        "options": payload.get("options") or {},
                    }
                    if "format" in payload:
                        gen_body["format"] = payload["format"]
                    r2 = await client.post(self._gen_url, json=gen_body)
                    r2.raise_for_status()
                    gj = r2.json()
                    data = {"message": {"content": (gj.get("response") or "").strip()}}
                    self._prefer_generate = True
            else:
                logger.debug("[OllamaAdapter] HTTP error: %s", e)
                raise
        except Exception as e:
            logger.debug("[OllamaAdapter] %s", e)
            raise
        _ = time.perf_counter() - t0
        content = data.get("message", {}).get("content", "")
        if isinstance(content, dict):
            return json.dumps(content)
        return (content or "").strip()

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0
