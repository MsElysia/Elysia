# project_guardian/openai_degraded.py
"""Stateful cooldown when OpenAI returns 429 / insufficient_quota — avoid hammering the API."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_until_ts: float = 0.0
_strikes: int = 0
_last_reason: str = ""

# Embedding-only: repeated 429s → hour-scale local-only (independent of chat/reasoning strikes)
_embedding_long_until_ts: float = 0.0
_embed_429_times: list[float] = []

# Chat/reasoning completions: repeated 429s → longer cooldown; blocks OpenAI for reasoning routes only (see multi_api_router)
_reasoning_long_until_ts: float = 0.0
_reasoning_429_times: list[float] = []

# Hard block: insufficient_quota on chat/reasoning — immediate OpenAI skip for reasoning routes (stronger than short degraded)
_quota_reasoning_until_ts: float = 0.0

BASE_COOLDOWN_SEC = 120.0
MAX_COOLDOWN_SEC = 1800.0  # 30m ceiling after repeated hits


def _forced_openai() -> bool:
    return os.environ.get("ELYSIA_FORCE_OPENAI", "").strip().lower() in ("1", "true", "yes")


def _detect_insufficient_quota(msg: str) -> bool:
    m = (msg or "").lower()
    if "insufficient_quota" in m:
        return True
    if "exceeded your current quota" in m:
        return True
    if "you exceeded your quota" in m or "exceeded your quota" in m:
        return True
    if "billing_hard_limit" in m or "hard limit has been reached" in m:
        return True
    if "quota" in m and ("exceed" in m or "billing" in m or "plan" in m):
        return True
    if "billing" in m and "quota" in m and ("429" in m or "exceeded" in m):
        return True
    if "do not have enough credits" in m or "no credits" in m:
        return True
    return False


def _insufficient_quota_reasoning_block_sec() -> float:
    try:
        return float(os.environ.get("ELYSIA_INSUFFICIENT_QUOTA_REASONING_BLOCK_SEC", str(2 * 3600)))
    except ValueError:
        return 7200.0


def _set_insufficient_quota_reasoning_block(source: str) -> None:
    """Immediately block OpenAI for reasoning/longform routes (prefer OpenRouter/local)."""
    global _quota_reasoning_until_ts
    now = time.time()
    sec = _insufficient_quota_reasoning_block_sec()
    with _lock:
        _quota_reasoning_until_ts = max(_quota_reasoning_until_ts, now + sec)
        until = _quota_reasoning_until_ts
    logger.warning(
        "[OpenAI insufficient_quota] reasoning quota block SET for %.0fs source=%s active_until_epoch=%.0f "
        "(openai_usable_for_routing=False for reasoning until expiry)",
        sec,
        (source or "")[:120],
        until,
    )


def openai_insufficient_quota_block_until_epoch() -> float:
    """Monotonic-ish wall epoch seconds until hard reasoning quota block ends; 0.0 if inactive."""
    now = time.time()
    with _lock:
        global _quota_reasoning_until_ts
        if _quota_reasoning_until_ts <= 0 or now >= _quota_reasoning_until_ts:
            return 0.0
        return float(_quota_reasoning_until_ts)


def openai_insufficient_quota_reasoning_blocked() -> bool:
    """True while insufficient_quota hard block is active for reasoning (independent of short degraded cooldown)."""
    now = time.time()
    with _lock:
        global _quota_reasoning_until_ts
        if _quota_reasoning_until_ts <= 0:
            return False
        if now >= _quota_reasoning_until_ts:
            logger.info(
                "[OpenAI insufficient_quota] reasoning block expired (was until epoch=%.0f)",
                _quota_reasoning_until_ts,
            )
            _quota_reasoning_until_ts = 0.0
            return False
        return True


def note_openai_rate_limit(source: str = "", status_code: Optional[int] = None, detail: Optional[str] = None) -> None:
    """Call when OpenAI (or compatible) signals quota/rate limits."""
    global _until_ts, _strikes, _last_reason
    combined = f"{source or ''} {detail or ''}"
    if _detect_insufficient_quota(combined):
        _set_insufficient_quota_reasoning_block("note_openai_rate_limit")
    now = time.time()
    cooldown = BASE_COOLDOWN_SEC
    with _lock:
        _strikes = min(_strikes + 1, 12)
        cooldown = min(MAX_COOLDOWN_SEC, BASE_COOLDOWN_SEC * (1.35 ** min(_strikes, 6)))
        _until_ts = max(_until_ts, now + cooldown)
        _last_reason = (source or "rate_limit")[:200]
    logger.warning(
        "[OpenAI degraded] entering cooldown=%.0fs strikes=%d status=%s detail=%s; embeddings/chat will prefer local until expiry",
        cooldown,
        _strikes,
        status_code,
        _last_reason,
    )


def note_openai_embedding_failure(exc: BaseException, context: str = "embedding") -> None:
    """
    Record embedding-route 429/quota failures without extending general chat degradation.
    After N failures inside a 2h window, applies a long local-only embedding cooldown.
    """
    if _forced_openai():
        return
    msg = str(exc).lower()
    code = getattr(exc, "status_code", None)
    try:
        from openai import APIStatusError

        if isinstance(exc, APIStatusError):
            code = getattr(exc, "status_code", code)
    except Exception:
        pass
    if code != 429 and "429" not in msg and "insufficient_quota" not in msg and "rate_limit" not in msg:
        return
    now = time.time()
    try:
        long_sec = float(os.environ.get("ELYSIA_EMBED_LONG_COOLDOWN_SEC", str(4 * 3600)))
    except ValueError:
        long_sec = 4 * 3600.0
    window = 7200.0
    with _lock:
        global _embedding_long_until_ts, _embed_429_times
        _embed_429_times.append(now)
        _embed_429_times = [t for t in _embed_429_times if now - t <= window]
        if len(_embed_429_times) >= 3:
            _embedding_long_until_ts = max(_embedding_long_until_ts, now + long_sec)
            logger.warning(
                "[OpenAI embedding] persistent quota pattern (%d× in %.0fh) — long embedding cooldown %.0fs "
                "(local/ST fallback only; does not use short chat cooldown strikes)",
                len(_embed_429_times),
                window / 3600.0,
                long_sec,
            )
        else:
            logger.debug(
                "[OpenAI embedding] rate-limit event %d/%d in 2h window (context=%s)",
                len(_embed_429_times),
                3,
                (context or "")[:80],
            )


def note_openai_embedding_success_clear_streak() -> None:
    """Reset embedding failure window after a successful OpenAI embedding call."""
    with _lock:
        global _embed_429_times
        if _embed_429_times:
            _embed_429_times.clear()


def _is_rate_limit_signal(*, msg: str, code: Optional[int]) -> bool:
    m = (msg or "").lower()
    if code == 429:
        return True
    if "429" in m or "insufficient_quota" in m or "rate_limit" in m:
        return True
    if _detect_insufficient_quota(m):
        return True
    return False


def note_openai_reasoning_rate_limit(
    exc_or_msg: Any = None,
    *,
    status_code: Optional[int] = None,
    context: str = "chat_completion",
) -> None:
    """
    Record chat/reasoning completion 429 or quota signals toward a long reasoning-only cooldown.
    Independent of embedding streaks; complements short global cooldown from note_openai_rate_limit.
    """
    if _forced_openai():
        return
    msg = ""
    code = status_code
    try:
        if isinstance(exc_or_msg, BaseException):
            msg = str(exc_or_msg).lower()
            code = getattr(exc_or_msg, "status_code", code)
            try:
                from openai import APIStatusError

                if isinstance(exc_or_msg, APIStatusError):
                    code = getattr(exc_or_msg, "status_code", code)
            except Exception:
                pass
        elif exc_or_msg is not None:
            msg = str(exc_or_msg).lower()
    except Exception:
        msg = ""
    if not _is_rate_limit_signal(msg=msg, code=int(code) if code is not None else None):
        return
    if _detect_insufficient_quota(msg):
        _set_insufficient_quota_reasoning_block(f"note_openai_reasoning_rate_limit:{context}")
    now = time.time()
    try:
        long_sec = float(os.environ.get("ELYSIA_REASONING_LONG_COOLDOWN_SEC", str(2 * 3600)))
    except ValueError:
        long_sec = 7200.0
    window = 7200.0
    need = 3
    try:
        need = max(1, int(os.environ.get("ELYSIA_REASONING_LONG_COOLDOWN_HITS", "3")))
    except ValueError:
        need = 3
    with _lock:
        global _reasoning_long_until_ts, _reasoning_429_times
        _reasoning_429_times.append(now)
        _reasoning_429_times = [t for t in _reasoning_429_times if now - t <= window]
        if len(_reasoning_429_times) >= need:
            _reasoning_long_until_ts = max(_reasoning_long_until_ts, now + long_sec)
            logger.warning(
                "[OpenAI reasoning] persistent 429/quota pattern (%d× in %.0fh) — reasoning-long cooldown %.0fs "
                "(reasoning/longform/planning routes prefer OpenRouter/local; embeddings unchanged)",
                len(_reasoning_429_times),
                window / 3600.0,
                long_sec,
            )
        else:
            logger.debug(
                "[OpenAI reasoning] rate-limit event %d/%d in 2h window (context=%s)",
                len(_reasoning_429_times),
                need,
                (context or "")[:80],
            )


def note_openai_reasoning_success_clear_streak(*, clear_insufficient_quota_block: bool = False) -> None:
    """
    Reset reasoning 429 streak after a successful OpenAI chat completion.
    insufficient_quota hard block is only cleared when clear_insufficient_quota_block=True
    (e.g. verified long/reasoning completion succeeded — not a short/simple chat).
    """
    with _lock:
        global _reasoning_429_times, _quota_reasoning_until_ts
        if _reasoning_429_times:
            _reasoning_429_times.clear()
        if clear_insufficient_quota_block and _quota_reasoning_until_ts > 0:
            _quota_reasoning_until_ts = 0.0


def openai_reasoning_long_cooldown_active() -> bool:
    """True while hour-scale reasoning backoff is active (clears when expired, like embedding long cooldown)."""
    if _forced_openai():
        return False
    now = time.time()
    with _lock:
        global _reasoning_long_until_ts
        if _reasoning_long_until_ts <= 0:
            return False
        if now >= _reasoning_long_until_ts:
            logger.info(
                "[OpenAI reasoning] long cooldown expired (was until epoch=%.0f); OpenAI re-eligible for reasoning routes",
                _reasoning_long_until_ts,
            )
            _reasoning_long_until_ts = 0.0
            return False
        return True


def openai_embedding_in_long_backoff() -> bool:
    """Read-only: True if hour-scale embedding backoff window is still active."""
    if _forced_openai():
        return False
    with _lock:
        return time.time() < _embedding_long_until_ts


def embedding_long_cooldown_active() -> bool:
    """True while hour-scale embedding backoff is active (checked/cleared here)."""
    if _forced_openai():
        return False
    now = time.time()
    with _lock:
        global _embedding_long_until_ts
        if _embedding_long_until_ts <= 0:
            return False
        if now >= _embedding_long_until_ts:
            logger.info(
                "[OpenAI embedding] long cooldown expired (was until epoch=%.0f); OpenAI embeddings re-eligible",
                _embedding_long_until_ts,
            )
            _embedding_long_until_ts = 0.0
            return False
        return True


def note_openai_transport_failure(exc: BaseException, context: str = "") -> None:
    """Inspect exception / message for 429 and insufficient_quota."""
    if _forced_openai():
        return
    ctx = (context or "").lower()
    if "vector_openai_embed" in ctx or "openai_embed" in ctx:
        note_openai_embedding_failure(exc, context=context)
        return
    msg = str(exc).lower()
    code = getattr(exc, "status_code", None)
    try:
        resp = getattr(exc, "response", None)
        if code is None and resp is not None:
            code = getattr(resp, "status_code", None)
    except Exception:
        pass
    try:
        from openai import APIStatusError

        if isinstance(exc, APIStatusError):
            code = getattr(exc, "status_code", code)
    except Exception:
        pass
    if (
        code == 429
        or "429" in msg
        or "insufficient_quota" in msg
        or "rate_limit" in msg
        or _detect_insufficient_quota(msg)
    ):
        note_openai_rate_limit(
            source=f"{context}:{msg[:120]}",
            status_code=int(code) if code is not None else None,
            detail=msg,
        )
        try:
            note_openai_reasoning_rate_limit(
                exc,
                status_code=int(code) if code is not None else (429 if "429" in msg else None),
                context=context or "openai_transport",
            )
        except Exception:
            pass


def is_openai_degraded_active() -> bool:
    global _strikes, _until_ts
    if _forced_openai():
        return False
    now = time.time()
    with _lock:
        if now >= _until_ts:
            if _strikes > 0:
                logger.info("[OpenAI degraded] cooldown elapsed; resuming normal provider selection")
            _strikes = 0
            _until_ts = 0.0
            return False
        return True


def skip_openai_embeddings() -> bool:
    if _forced_openai():
        return False
    if embedding_long_cooldown_active():
        return True
    return is_openai_degraded_active()


def prefer_local_chat_over_openai() -> bool:
    return is_openai_degraded_active() and not _forced_openai()
