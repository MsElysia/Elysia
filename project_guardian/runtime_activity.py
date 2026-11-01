"""Bounded process-local operational events; never log prompts, paths or contents."""
from collections import deque
from datetime import datetime, timezone
import threading

_events = deque(maxlen=60)
_lock = threading.Lock()


def record(event):
    with _lock:
        _events.append({'time': datetime.now(timezone.utc).isoformat(), 'event': event})


def recent():
    with _lock:
        return list(_events)
