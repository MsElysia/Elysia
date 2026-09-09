from __future__ import annotations

import logging


def test_api_key_manager_logs_info_once_per_same_availability_state(monkeypatch, caplog):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_LAST_KEY_AVAILABILITY_SIGNATURE", None)
    monkeypatch.setattr(akm.Path, "exists", lambda self: False)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    caplog.set_level(logging.DEBUG)

    akm.APIKeyManager()
    akm.APIKeyManager()

    infos = [r for r in caplog.records if r.levelno == logging.INFO and "API keys loaded." in r.message]
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and "unchanged availability state" in r.message]
    assert len(infos) == 1
    assert len(debugs) >= 1
