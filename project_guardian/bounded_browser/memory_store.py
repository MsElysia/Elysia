# Persistent browse memory: visits, findings, deprioritized hosts.

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_NAME = "browser_agent_state.json"


class BrowserAgentMemoryStore:
    """JSON-backed store (read-only agent; this file is the integration surface for recall)."""

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

    def is_host_deprioritized(self, host: str) -> bool:
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
