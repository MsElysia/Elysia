from __future__ import annotations


def test_get_api_key_manager_returns_singleton_instance(monkeypatch):
    import project_guardian.api_key_manager as akm

    monkeypatch.setattr(akm, "_global_manager", None)
    first = akm.get_api_key_manager()
    second = akm.get_api_key_manager()
    assert first is second
