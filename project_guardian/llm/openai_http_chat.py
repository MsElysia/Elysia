"""Compatibility wrappers over the unified OpenAI chat transport."""

from __future__ import annotations

from .openai_chat_transport import (
    build_openai_chat_url,
    post_openai_chat_completion_async,
    post_openai_chat_completion_sync,
)
