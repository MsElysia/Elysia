"""Lightweight event bus for the unified runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """Runtime event emitted by subsystems."""

    ts: datetime
    source: str
    type: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event for APIs/CLI."""
        return {
            "ts": self.ts.isoformat(),
            "source": self.source,
            "type": self.type,
            "payload": self.payload,
        }


class EventBus:
    """Fan-out publish/subscribe bus with a small in-memory buffer."""

    def __init__(self, buffer_size: int = 200):
        self._buffer_size = buffer_size
        self._lock = Lock()
        self._subscribers: List[Callable[[Event], None]] = []
        self._buffer: List[Event] = []

    def subscribe(self, handler: Callable[[Event], None]) -> None:
        """Register a subscriber that receives every event."""
        with self._lock:
            self._subscribers.append(handler)

    def publish(self, event: Event) -> None:
        """Deliver an already constructed event."""
        with self._lock:
            self._buffer.append(event)
            if len(self._buffer) > self._buffer_size:
                self._buffer = self._buffer[-self._buffer_size :]
            subscribers = list(self._subscribers)

        for handler in subscribers:
            try:
                handler(event)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Event handler error for %s", event)

    def emit(self, source: str, type_: str, payload: Dict[str, Any]) -> None:
        """Convenience wrapper to create and publish an event."""
        event = Event(
            ts=datetime.now(timezone.utc),
            source=source,
            type=type_,
            payload=payload,
        )
        self.publish(event)

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the latest events (newest last)."""
        with self._lock:
            snapshot = [evt.to_dict() for evt in self._buffer[-limit:]]
        return snapshot

