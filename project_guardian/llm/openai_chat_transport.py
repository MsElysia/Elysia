"""Unified transport boundary for OpenAI chat completion calls."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx


def sdk_chat_completion_text(
    client: Any,
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float = 0.3,
) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = (resp.choices[0].message.content or "").strip()
    return content


def build_openai_chat_url(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    return f"{base}/chat/completions"


def post_openai_chat_completion_sync(
    *,
    base_url: str,
    api_key: str,
    body: Dict[str, Any],
    timeout_sec: float,
) -> Dict[str, Any]:
    url = build_openai_chat_url(base_url)
    with httpx.Client(timeout=httpx.Timeout(timeout_sec)) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def post_openai_chat_completion_async(
    *,
    base_url: str,
    api_key: str,
    body: Dict[str, Any],
    timeout_sec: float,
) -> Dict[str, Any]:
    url = build_openai_chat_url(base_url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        return response.json()
