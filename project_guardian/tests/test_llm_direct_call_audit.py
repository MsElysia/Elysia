"""
Guardrail: track remaining direct OpenAI chat SDK usage outside the unified router.

Update ALLOWLIST_CHAT_COMPLETION_RELATIVE_PATHS only when intentionally adding a new site.
Embeddings / api_key_manager factories are out of scope here.
"""

from __future__ import annotations

from pathlib import Path

import project_guardian


ALLOWLIST_CHAT_COMPLETION_RELATIVE_PATHS = frozenset(
    {
        "llm/openai_chat_transport.py",
    }
)
ALLOWLIST_OPENAI_HTTP_CHAT_RELATIVE_PATHS = frozenset(
    {
        "llm/openai_chat_transport.py",
    }
)


def _project_guardian_root() -> Path:
    return Path(project_guardian.__file__).resolve().parent


def test_chat_completions_create_allowlist():
    root = _project_guardian_root()
    needle = "chat.completions.create"
    offenders: list[str] = []
    for p in root.rglob("*.py"):
        if "tests" in p.parts:
            continue
        rel = p.relative_to(root)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle not in text:
            continue
        rel_s = rel.as_posix()
        if rel_s not in ALLOWLIST_CHAT_COMPLETION_RELATIVE_PATHS:
            offenders.append(rel_s)

    assert not offenders, (
        "New chat.completions.create site(s) detected outside allowlist — route via unified/registry or extend "
        "ALLOWLIST_CHAT_COMPLETION_RELATIVE_PATHS with justification: "
        + ", ".join(offenders)
    )


def test_embeddings_api_is_distinct_from_chat_audit():
    """Sanity: embedding client usage exists but must not use chat.completions."""
    root = _project_guardian_root()
    mv = root / "memory_vector.py"
    assert mv.is_file()
    t = mv.read_text(encoding="utf-8", errors="replace")
    assert "embeddings.create" in t
    assert "chat.completions.create" not in t


def test_openai_http_chat_endpoint_allowlist():
    """
    Guardrail for direct HTTP POST to OpenAI /chat/completions.

    OpenRouter/Grok endpoint constants are intentionally out-of-scope.
    """
    root = _project_guardian_root()
    offenders: list[str] = []
    for p in root.rglob("*.py"):
        if "tests" in p.parts:
            continue
        rel = p.relative_to(root)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "/chat/completions" not in text:
            continue
        if "openrouter.ai/api/v1/chat/completions" in text:
            continue
        looks_openai_http = "OPENAI_BASE_URL" in text or "api.openai.com" in text
        if not looks_openai_http:
            continue
        rel_s = rel.as_posix()
        if rel_s not in ALLOWLIST_OPENAI_HTTP_CHAT_RELATIVE_PATHS:
            offenders.append(rel_s)

    assert not offenders, (
        "New direct OpenAI HTTP /chat/completions site(s) detected outside allowlist — route via unified/registry "
        "or extend ALLOWLIST_OPENAI_HTTP_CHAT_RELATIVE_PATHS with justification: "
        + ", ".join(offenders)
    )
