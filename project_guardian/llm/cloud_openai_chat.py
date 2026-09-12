"""Compatibility wrapper over the unified OpenAI chat transport."""

from __future__ import annotations

from typing import Any, Dict, List

from .openai_chat_transport import sdk_chat_completion_text


def openai_chat_completion(
    client: Any,
    *,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    temperature: float = 0.3,
) -> tuple[str, str]:
    """Return ``(content, error_string)``."""
    try:
        content = sdk_chat_completion_text(
            client,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return content, ""
    except Exception as e:
        return "", str(e)
