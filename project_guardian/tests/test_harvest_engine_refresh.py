# project_guardian/tests/test_harvest_engine_refresh.py
from __future__ import annotations


def test_refresh_harvest_engine_in_modules_replaces_entry(monkeypatch):
    import elysia_sub_modules as esm

    class _Fake:
        def __init__(self, a=None, b=None):
            self.a = a
            self.b = b

    def _fake_build():
        return _Fake(1, 2), "gum", "sk"

    monkeypatch.setattr(esm, "build_harvest_engine_from_current_keys", _fake_build)
    mods: dict = {}
    out = esm.refresh_harvest_engine_in_modules(mods)
    assert out.get("ok") is True
    assert out.get("gumroad_bound") is True
    assert out.get("stripe_bound") is True
    assert isinstance(mods.get("harvest_engine"), _Fake)
