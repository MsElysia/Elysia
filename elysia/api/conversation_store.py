"""
Compatibility shim for the canonical conversation store.

All logic lives in :mod:`project_guardian.conversation_store`.
Import from here only when convenient inside ``elysia.api``; do not duplicate behavior.
"""

from __future__ import annotations

from project_guardian.conversation_store import (  # noqa: F401
    CHAT_LIST_MESSAGES_DEFAULT,
    CHAT_MAX_MESSAGES_PER_CONVERSATION,
    CHAT_TEXT_LIMIT,
    DEFAULT_CONVERSATIONS_DIR,
    LEGACY_IMPORT_MARKER,
    ConversationMessage,
    ConversationStore,
    build_recent_transcript,
    conversation_message_from_row,
    format_transcript_for_prompt,
    get_default_conversation_store,
    redact_chat_text,
    reset_default_conversation_store_for_tests,
    sanitize_conversation_id,
)

__all__ = [
    "CHAT_LIST_MESSAGES_DEFAULT",
    "CHAT_MAX_MESSAGES_PER_CONVERSATION",
    "CHAT_TEXT_LIMIT",
    "DEFAULT_CONVERSATIONS_DIR",
    "LEGACY_IMPORT_MARKER",
    "ConversationMessage",
    "ConversationStore",
    "build_recent_transcript",
    "conversation_message_from_row",
    "format_transcript_for_prompt",
    "get_default_conversation_store",
    "redact_chat_text",
    "reset_default_conversation_store_for_tests",
    "sanitize_conversation_id",
]
