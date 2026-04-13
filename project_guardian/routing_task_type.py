# project_guardian/routing_task_type.py
# Map free-text goals to small canonical task_type strings that align with builtin
# tool capability tags (fetch/http/web, script/exec/run, completion/chat/llm) so TaskRouter
# can get strict_capability_tag_matches > 0 without redesigning the router.

from __future__ import annotations

import re
from typing import Tuple

# Builtin ToolRegistry stubs expose these exact strings in `capabilities`:
# - web: web, http, fetch  → elysia_builtin_web
# - bounded_browse only → elysia_bounded_browser (multi-page read; not fetch)
# - social_moltbook_observe → elysia_social_intel (observe+draft+ gated speak; Moltbook-first)
# - moltbook_browse only → elysia_moltbook_browser (moltbook.com allowlist)
# - exec: exec, run, script
# - llm: llm, chat, completion
_CANONICAL_WEB = "fetch"  # listed on elysia_builtin_web
_CANONICAL_BOUNDED_BROWSE = "bounded_browse"  # listed on elysia_bounded_browser only (multi-page read)
_CANONICAL_SOCIAL_MOLTBOOK = "social_moltbook_observe"  # elysia_social_intel only
_CANONICAL_MOLTBOOK_BROWSE = "moltbook_browse"  # listed on elysia_moltbook_browser only
_CANONICAL_EXEC = "script"  # listed on elysia_builtin_exec
_CANONICAL_LLM = "completion"  # listed on elysia_builtin_llm
_FALLBACK = "self_task"


def infer_canonical_routing_task_type(
    goal: str,
    *,
    archetype: str = "",
    extra_context: str = "",
) -> Tuple[str, str]:
    """
    Infer a TaskRouter task_type that can match a single builtin via explicit capability tag.

    Returns:
        (task_type, reason_code) — reason_code is for logs only.
    """
    blob = f"{goal or ''} {archetype or ''} {extra_context or ''}".lower()
    blob = re.sub(r"\s+", " ", blob).strip()
    if not blob:
        return _FALLBACK, "empty_input"

    # Exec / run / shell (high-signal first to avoid misclassifying "run a summary" if we check LLM first — we check exec before LLM)
    exec_patterns = (
        r"\bshell\b",
        r"\bbash\b",
        r"\bpowershell\b",
        r"\bsubprocess\b",
        r"\bexec\(",
        r"\brun (this |the )?command",
        r"\bpython -c\b",
        r"\bconda \b",
        r"\bnpm run\b",
        r"\bmake \w+",
        r"\bcompile and run\b",
        r"\bexecute (the )?script\b",
        r"\brun (a )?script\b",
    )
    for pat in exec_patterns:
        if re.search(pat, blob):
            return _CANONICAL_EXEC, "keyword_exec"

    # Social-intelligence Moltbook (before plain moltbook browse)
    social_molt_patterns = (
        r"\bsocial\b.*\bmoltbook\b",
        r"\bmoltbook\b.*\bsocial\b",
        r"\bobserve\b.*\bmoltbook\b",
        r"\bmoltbook\b.*\bobserve\b",
        r"\bsocial_intel\b",
        r"\bsocial intelligence\b.*\bmoltbook\b",
        r"\bmoltbook\b.*\bsocial intelligence\b",
        r"\belysia social\b.*\bmoltbook\b",
        r"\bmoltbook\b.*\belysia social\b",
        r"\bsocial_moltbook_observe\b",
        r"\bthread(s)?\b.*\bmoltbook\b",
        r"\bmoltbook\b.*\bthread(s)?\b",
    )
    for pat in social_molt_patterns:
        if re.search(pat, blob):
            return _CANONICAL_SOCIAL_MOLTBOOK, "keyword_social_moltbook_observe"

    # Moltbook site-only browse (before generic bounded_browse / URL → fetch)
    if re.search(r"\bmoltbook\b", blob) or re.search(r"\bmoltbook\.com\b", blob):
        return _CANONICAL_MOLTBOOK_BROWSE, "keyword_moltbook"

    # Multi-page / exploration (before plain URL → fetch; keeps simple fetch as default)
    bounded_patterns = (
        r"\bbounded browse\b",
        r"\bweb research session\b",
        r"\bexplore (the |this |that )?(site|website|page)\b",
        r"\bexplore https?://",
        r"\bfollow (relevant )?links\b",
        r"\bmulti-?page\b",
        r"\bscroll through\b",
        r"\bdeep(er)? (read|scan) (of |on )?(the )?(site|page|url)\b",
    )
    for pat in bounded_patterns:
        if re.search(pat, blob):
            return _CANONICAL_BOUNDED_BROWSE, "keyword_bounded_browse"

    # Web / fetch / URL
    web_patterns = (
        r"https?://",
        r"\bwww\.",
        r"\bfetch (the )?(url|page|site)",
        r"\bopen (the )?url\b",
        r"\bweb search\b",
        r"\bscrape\b",
        r"\bcurl\b",
        r"\bdownload (the )?page\b",
        r"\bbrowse (to |the )?",
        r"\bhttp fetch\b",
    )
    for pat in web_patterns:
        if re.search(pat, blob):
            return _CANONICAL_WEB, "keyword_web"

    # LLM / text
    llm_patterns = (
        r"\bsummarize\b",
        r"\bexplain\b",
        r"\btranslate\b",
        r"\bproofread\b",
        r"\bdraft (a |an )?",
        r"\bcompose\b",
        r"\bwrite (a |an )?",
        r"\bchat\b",
        r"\breason(ing)?\b",
        r"\banalyze (this )?text\b",
        r"\bllm\b",
        r"\bprompt\b",
        r"\bunified chat\b",
    )
    for pat in llm_patterns:
        if re.search(pat, blob):
            return _CANONICAL_LLM, "keyword_llm"

    return _FALLBACK, "fallback_generic"
