# project_guardian/local_planner_breaker.py
"""Circuit breaker for local Ollama/Mistral planner to avoid long autonomy-loop stalls."""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_open_until: float = 0.0
_failures: int = 0
_last_failure_ts: float = 0.0
_last_success_ts: float = 0.0
_last_log_open: float = 0.0

FAILURES_TO_OPEN = 2
COOLDOWN_SEC = 90.0
MAX_COOLDOWN_SEC = 600.0
RECHECK_SEC = 25.0


def _now() -> float:
    return time.time()


def is_planner_circuit_open() -> bool:
    return _now() < _open_until


def allow_planner_call() -> bool:
    """False during cooldown — skip blocking HTTP to Ollama for this autonomy cycle."""
    return not is_planner_circuit_open()


def note_planner_success() -> None:
    global _failures, _open_until, _last_success_ts
    with _lock:
        was_open = _now() < _open_until
        _failures = 0
        _open_until = 0.0
        _last_success_ts = _now()
        if was_open:
            logger.info("[PlannerBreaker] Local planner circuit CLOSED (recovered after success)")


def note_planner_failure(reason: str = "", is_timeout: bool = False) -> None:
    global _open_until, _failures, _last_failure_ts, _last_log_open
    now = _now()
    with _lock:
        _failures = min(_failures + 1, 20)
        _last_failure_ts = now
        cd = min(MAX_COOLDOWN_SEC, COOLDOWN_SEC * (1.6 ** min(_failures - 1, 5)))
        if _failures >= FAILURES_TO_OPEN:
            _open_until = max(_open_until, now + cd)
            if now - _last_log_open > 30.0:
                _last_log_open = now
                logger.warning(
                    "[PlannerBreaker] Local planner circuit OPEN for %.0fs (failures=%d timeout=%s reason=%s)",
                    cd,
                    _failures,
                    is_timeout,
                    (reason or "")[:120],
                )


def circuit_breaker_snapshot() -> Dict[str, object]:
    """Compact status for dashboards."""
    now = _now()
    with _lock:
        return {
            "circuit_open": now < _open_until,
            "open_until_ts": _open_until,
            "failures": _failures,
            "last_failure_ts": _last_failure_ts,
            "last_success_ts": _last_success_ts,
            "recheck_sec": RECHECK_SEC,
        }


def maybe_probe_recovery_window() -> bool:
    """
    After RECHECK_SEC since open, allow a single health-style attempt (caller decides).
    Returns True if a probe attempt is reasonable (half-open hint).
    """
    if not is_planner_circuit_open():
        return True
    return (_now() - _last_failure_ts) >= RECHECK_SEC
