# project_guardian/ollama_health.py
"""Sync Ollama endpoint verification: /api/chat vs /api/generate, base URL normalization."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class OllamaHealthResult:
    ok: bool
    base_url: str
    chat_url: str
    generate_url: str
    prefer_generate: bool
    detail: str
    tags_status: Optional[int] = None


def list_ollama_installed_model_names(
    base_url: Optional[str] = None,
    *,
    timeout: float = 8.0,
) -> Tuple[List[str], Optional[str]]:
    """
    GET /api/tags → model names (e.g. mistral:latest). Returns (names, error_message).
    error_message is None on HTTP success (names may still be empty).
    """
    try:
        import requests
    except ImportError as e:
        return [], f"requests not installed: {e}"

    base = normalize_ollama_base(base_url)
    tags_url = f"{base}/api/tags"
    try:
        tr = requests.get(tags_url, timeout=min(timeout, 12.0))
    except Exception as e:
        return [], f"tags_unreachable: {e}"
    if tr.status_code not in (200, 201):
        return [], f"tags_http_{tr.status_code}"
    try:
        data = tr.json()
    except Exception as e:
        return [], f"tags_json: {e}"
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return [], "tags_no_models_array"
    names: List[str] = []
    for m in models:
        if isinstance(m, dict):
            n = (m.get("name") or "").strip()
            if n:
                names.append(n)
    return names, None


def normalize_ollama_base(url: Optional[str]) -> str:
    raw = (url or os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").strip().rstrip("/")
    if "/api/" in raw:
        raw = raw.split("/api/")[0].rstrip("/")
    if not raw.startswith("http"):
        raw = f"http://{raw}"
    return raw


def _chat_payload(model: str, probe: bool = True) -> Dict[str, Any]:
    if probe:
        return {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": "."}],
            "options": {"temperature": 0.1, "num_predict": 3},
        }
    raise NotImplementedError


def verify_ollama_runtime(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 12.0,
) -> OllamaHealthResult:
    """
    Probe Ollama: GET /api/tags, then POST /api/chat, then POST /api/generate if chat returns 404.
    Does not claim success unless at least one generation path works.
    """
    try:
        import requests
    except ImportError as e:
        return OllamaHealthResult(
            ok=False,
            base_url="",
            chat_url="",
            generate_url="",
            prefer_generate=False,
            detail=f"requests not installed: {e}",
        )

    from .ollama_model_config import get_canonical_ollama_model

    m_probe = (model or "").strip() or get_canonical_ollama_model(log_once=False)

    base = normalize_ollama_base(base_url)
    chat_url = f"{base}/api/chat"
    gen_url = f"{base}/api/generate"
    try:
        from .planner_readiness import should_short_circuit_verify_ollama_for_bad_tag

        sc, why = should_short_circuit_verify_ollama_for_bad_tag(m_probe)
        if sc:
            return OllamaHealthResult(
                ok=False,
                base_url=base,
                chat_url=chat_url,
                generate_url=gen_url,
                prefer_generate=False,
                detail=f"skipped:{why}",
                tags_status=None,
            )
    except Exception:
        pass
    tags_url = f"{base}/api/tags"
    tags_st: Optional[int] = None
    try:
        tr = requests.get(tags_url, timeout=min(timeout, 8.0))
        tags_st = tr.status_code
    except Exception as e:
        logger.warning("[Ollama] GET /api/tags failed: %s", e)
        return OllamaHealthResult(
            ok=False,
            base_url=base,
            chat_url=chat_url,
            generate_url=gen_url,
            prefer_generate=False,
            detail=f"unreachable: {e}",
            tags_status=tags_st,
        )

    if tags_st not in (200, 201):
        logger.warning(
            "[Ollama] /api/tags HTTP %s — host may not be Ollama or wrong port (base=%s)",
            tags_st,
            base,
        )

    # Try /api/chat
    chat_ok = False
    chat_err = ""
    try:
        r = requests.post(chat_url, json=_chat_payload(m_probe), timeout=timeout)
        if r.status_code == 200:
            chat_ok = True
        elif r.status_code == 404:
            chat_err = "chat_404"
        else:
            chat_err = f"chat_http_{r.status_code}"
            logger.warning("[Ollama] /api/chat HTTP %s body_sample=%s", r.status_code, (r.text or "")[:120])
    except Exception as e:
        chat_err = str(e)
        logger.warning("[Ollama] /api/chat request failed: %s", e)

    if chat_ok:
        logger.info(
            "[Ollama] healthy: /api/chat OK (model=%s base=%s tags=%s)",
            m_probe,
            base,
            tags_st,
        )
        return OllamaHealthResult(
            ok=True,
            base_url=base,
            chat_url=chat_url,
            generate_url=gen_url,
            prefer_generate=False,
            detail="chat_ok",
            tags_status=tags_st,
        )

    # Try /api/generate (older layouts, proxies, some custom servers)
    gen_ok = False
    try:
        gr = requests.post(
            gen_url,
            json={
                "model": m_probe,
                "prompt": ".",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 3},
            },
            timeout=timeout,
        )
        if gr.status_code == 200:
            gen_ok = True
        else:
            logger.warning("[Ollama] /api/generate HTTP %s sample=%s", gr.status_code, (gr.text or "")[:120])
    except Exception as e:
        logger.warning("[Ollama] /api/generate failed: %s", e)

    if gen_ok:
        logger.warning(
            "[Ollama] /api/chat unavailable (%s); using /api/generate for model=%s base=%s",
            chat_err or "no_chat",
            m_probe,
            base,
        )
        return OllamaHealthResult(
            ok=True,
            base_url=base,
            chat_url=chat_url,
            generate_url=gen_url,
            prefer_generate=True,
            detail="generate_fallback_ok",
            tags_status=tags_st,
        )

    msg = (
        f"local Ollama not usable: chat failed ({chat_err}) and /api/generate not ok. "
        f"Check OLLAMA_BASE_URL={base}, model pull (`ollama pull {m_probe}`), and server logs."
    )
    logger.error("[Ollama] %s", msg)
    return OllamaHealthResult(
        ok=False,
        base_url=base,
        chat_url=chat_url,
        generate_url=gen_url,
        prefer_generate=False,
        detail=msg,
        tags_status=tags_st,
    )


def messages_to_prompt(messages: list) -> str:
    parts = []
    for m in messages or []:
        role = (m.get("role") or "user").strip()
        content = m.get("content") or ""
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False)
        parts.append(f"{role.upper()}:\n{content}")
    return "\n\n".join(parts).strip() or "."
