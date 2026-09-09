"""BrowserAgentMemoryStore: low_value_hosts TTL."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from project_guardian.bounded_browser.memory_store import BrowserAgentMemoryStore


def test_low_value_host_expires_after_ttl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "browser_agent_state.json"
    monkeypatch.setenv("ELYSIA_BROWSER_LOW_VALUE_HOST_TTL_SEC", "2")
    store = BrowserAgentMemoryStore(path=p)
    store.mark_low_value_host("moltbook.com", "thin")
    assert store.is_host_deprioritized("moltbook.com") is True
    time.sleep(2.2)
    assert store.is_host_deprioritized("moltbook.com") is False
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "moltbook.com" not in (data.get("low_value_hosts") or {})


def test_ttl_zero_never_expires(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    monkeypatch.setenv("ELYSIA_BROWSER_LOW_VALUE_HOST_TTL_SEC", "0")
    store = BrowserAgentMemoryStore(path=p)
    store._data["low_value_hosts"] = {"old.test": {"reason": "x", "ts": 1.0}}
    store._save()
    store2 = BrowserAgentMemoryStore(path=p)
    assert store2.is_host_deprioritized("old.test") is True


def test_load_prunes_stale_hosts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ELYSIA_BROWSER_LOW_VALUE_HOST_TTL_SEC", "60")
    p = tmp_path / "state2.json"
    old_ts = time.time() - 120.0
    p.write_text(
        json.dumps({"low_value_hosts": {"gone.test": {"reason": "thin", "ts": old_ts}}}),
        encoding="utf-8",
    )
    BrowserAgentMemoryStore(path=p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "gone.test" not in (data.get("low_value_hosts") or {})
