# Persistent browse memory: visits, findings, deprioritized hosts.

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_NAME = "browser_agent_state.json"

# After this many seconds, a host in low_value_hosts is treated as fresh again (bounded browser).
# Set ELYSIA_BROWSER_LOW_VALUE_HOST_TTL_SEC=0 to disable expiry (legacy: deprioritization never auto-clears).
_DEFAULT_LOW_VALUE_HOST_TTL_SEC = 86400.0


def _low_value_host_ttl_seconds() -> float:
    raw = os.environ.get("ELYSIA_BROWSER_LOW_VALUE_HOST_TTL_SEC", "").strip()
    if raw == "":
        return _DEFAULT_LOW_VALUE_HOST_TTL_SEC
    try:
        v = float(raw)
    except ValueError:
        return _DEFAULT_LOW_VALUE_HOST_TTL_SEC
    if v <= 0:
        return 0.0
    return v


class BrowserAgentMemoryStore:
    """JSON-backed store (read-only agent; this file is the integration surface for recall).

    ``low_value_hosts`` entries expire after ``ELYSIA_BROWSER_LOW_VALUE_HOST_TTL_SEC`` seconds
    (default 86400). Set to ``0`` to disable auto-expiry.
    """

    def __init__(self, path: Optional[Path] = None):
        root = Path(__file__).resolve().parent.parent.parent
        self.path = path or (root / DEFAULT_STATE_NAME)
        self._data: Dict[str, Any] = {
            "visited_urls": [],
            "low_value_hosts": {},
            "sessions": [],
            "findings_log": [],
        }
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data.update({k: raw.get(k, v) for k, v in self._data.items()})
            self._prune_expired_low_value_hosts()
        except Exception as e:
            logger.warning("Browser agent state load failed: %s", e)

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("Browser agent state save failed: %s", e)

    def record_visit(self, url: str) -> None:
        v = self._data.setdefault("visited_urls", [])
        if url not in v:
            v.append(url)
        self._save()

    def mark_low_value_host(self, host: str, reason: str = "") -> None:
        h = self._data.setdefault("low_value_hosts", {})
        h[host] = {"reason": reason, "ts": time.time()}
        self._save()

    def _prune_expired_low_value_hosts(self) -> None:
        ttl = _low_value_host_ttl_seconds()
        if ttl <= 0:
            return
        h = self._data.get("low_value_hosts")
        if not isinstance(h, dict) or not h:
            return
        now = time.time()
        removed = False
        for key in list(h.keys()):
            ent = h.get(key)
            ts: Optional[float] = None
            if isinstance(ent, dict):
                try:
                    ts = float(ent["ts"]) if ent.get("ts") is not None else None
                except (TypeError, ValueError):
                    ts = None
            if ts is None or (now - ts) > ttl:
                try:
                    del h[key]
                    removed = True
                except KeyError:
                    pass
        if removed:
            self._save()
            logger.info(
                "[BrowserAgentMemoryStore] pruned expired low_value_hosts (ttl=%ss)",
                int(ttl),
            )

    def is_host_deprioritized(self, host: str) -> bool:
        self._prune_expired_low_value_hosts()
        return host in (self._data.get("low_value_hosts") or {})

    def append_finding(self, url: str, snippet: str, relevance: float) -> None:
        fl = self._data.setdefault("findings_log", [])
        fl.append(
            {
                "url": url,
                "snippet": snippet[:2000],
                "relevance": relevance,
                "ts": time.time(),
            }
        )
        fl[:] = fl[-500:]
        self._save()

    def record_session(self, goal: str, summary: str, step_dicts: List[Dict[str, Any]], stop_reason: str) -> None:
        sess = self._data.setdefault("sessions", [])
        sess.append(
            {
                "goal": goal,
                "summary": summary[:8000],
                "steps": step_dicts[-50:],
                "stop_reason": stop_reason,
                "ts": time.time(),
            }
        )
        sess[:] = sess[-30:]
        self._save()
