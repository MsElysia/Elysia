"""Unit tests for control-panel payment provider status helper."""

import pytest

from project_guardian.ui_control_panel import _build_payment_provider_status


class _Harvest:
    def __init__(self, gum: bool, stripe: bool):
        self.gumroad_client = object() if gum else None
        self.stripe_client = object() if stripe else None


class _Unified:
    def __init__(self, harvest: _Harvest | None):
        self.modules = {}
        if harvest is not None:
            self.modules["harvest_engine"] = harvest


def test_payment_status_no_env_no_unified(monkeypatch):
    monkeypatch.delenv("GUMROAD_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PUBLISHABLE_KEY", raising=False)
    out = _build_payment_provider_status(None)
    assert out["gumroad"]["access_token_env"] is False
    assert out["gumroad"]["harvest_client_bound"] is False
    assert out["gumroad"]["summary"] == "not_configured"
    assert out["stripe"]["secret_key_env"] is False
    assert out["stripe"]["publishable_key_env"] is False
    assert out["stripe"]["secret_key_mode"] == "unset"
    assert out["stripe"]["publishable_key_mode"] == "unset"
    assert out["stripe"]["summary"] == "not_configured"


def test_payment_status_env_and_harvest_bound(monkeypatch):
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "x")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")
    u = _Unified(_Harvest(gum=True, stripe=True))
    out = _build_payment_provider_status(u)
    assert out["gumroad"]["summary"] == "ok"
    assert out["stripe"]["secret_key_mode"] == "test"
    assert out["stripe"]["publishable_key_mode"] == "test"
    assert out["stripe"]["summary"] == "ok"


def test_payment_status_env_only_without_harvest_client(monkeypatch):
    monkeypatch.setenv("GUMROAD_ACCESS_TOKEN", "x")
    u = _Unified(_Harvest(gum=False, stripe=False))
    out = _build_payment_provider_status(u)
    assert out["gumroad"]["access_token_env"] is True
    assert out["gumroad"]["harvest_client_bound"] is False
    assert out["gumroad"]["summary"] == "env_only_restart_may_be_needed"
