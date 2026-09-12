"""Revenue sharing ledger-mode helpers."""

from types import SimpleNamespace

import pytest

from project_guardian.master_slave_controller import MasterSlaveController
from project_guardian.revenue_sharing import configure_revenue_sharing, revenue_ledger_only_mode
from project_guardian.trust_registry import TrustRegistry


def test_revenue_ledger_only_mode_default(monkeypatch):
    monkeypatch.delenv("ELYSIA_REVENUE_LEDGER_ONLY", raising=False)
    assert revenue_ledger_only_mode() is True


def test_revenue_ledger_only_mode_off(monkeypatch):
    monkeypatch.setenv("ELYSIA_REVENUE_LEDGER_ONLY", "0")
    assert revenue_ledger_only_mode() is False


def test_configure_revenue_sharing_requires_master_slave(tmp_path):
    with pytest.raises(ValueError, match="master_slave"):
        configure_revenue_sharing(storage_path=str(tmp_path / "rev.json"))


def test_configure_revenue_sharing_resolves_from_guardian(tmp_path):
    trust = TrustRegistry(storage_path=str(tmp_path / "trust.json"))
    ms = MasterSlaveController(
        master_id="test_master",
        storage_path=str(tmp_path / "ms.json"),
        trust_registry=trust,
    )
    guardian = SimpleNamespace(master_slave_controller=ms)
    rs = configure_revenue_sharing(guardian=guardian, storage_path=str(tmp_path / "rev.json"))
    assert rs.master_slave is ms
