"""Issue #23 adversarial tests: audit bootstrap must not activate Guardian.

These tests prove `init_guardian_core(mode=\"audit\")` is a pure configuration
descriptor. It must not construct GuardianCore, start monitoring/ElysiaLoop/
prompt-evolution, auto-start UI, schedule live probes, open sockets, or spawn
subprocesses. It does **not** prove live runtime wiring.

Marked ``no_guardian_core`` so root conftest does not import GuardianCore.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.no_guardian_core

from elysia_sub_guardian import (
    GuardianBootstrapAudit,
    describe_guardian_bootstrap,
    init_guardian_core,
)


class _ActivationForbidden(AssertionError):
    pass


def _fail(*_a, **_k):
    raise _ActivationForbidden("operational side effect attempted during audit")


def _purge_project_guardian_modules() -> None:
    for name in list(sys.modules):
        if name == "project_guardian" or name.startswith("project_guardian."):
            del sys.modules[name]


def _install_fake_singleton(*, get_core, ensure=None, schedule=None):
    """Install lightweight stubs so operational tests never import real GuardianCore."""
    pg = types.ModuleType("project_guardian")
    pg.__path__ = []  # mark as package
    singleton = types.ModuleType("project_guardian.guardian_singleton")
    singleton.get_guardian_core = get_core
    singleton.ensure_monitoring_started = ensure or MagicMock(side_effect=_fail)
    diagnostics = types.ModuleType("project_guardian.diagnostics")
    diagnostics.__path__ = []
    probe = types.ModuleType("project_guardian.diagnostics.upstream_routing_live_probe")
    probe.schedule_upstream_routing_live_probes = schedule or MagicMock(side_effect=_fail)
    return {
        "project_guardian": pg,
        "project_guardian.guardian_singleton": singleton,
        "project_guardian.diagnostics": diagnostics,
        "project_guardian.diagnostics.upstream_routing_live_probe": probe,
    }


@pytest.fixture
def forbid_activation():
    """Fail immediately on network/subprocess/thread activation surfaces."""
    with patch("socket.socket", side_effect=_fail), patch(
        "socket.create_connection", side_effect=_fail
    ), patch("subprocess.Popen", side_effect=_fail), patch(
        "subprocess.run", side_effect=_fail
    ), patch("subprocess.call", side_effect=_fail), patch(
        "threading.Thread", side_effect=_fail
    ):
        yield


def test_audit_mode_requires_explicit_keyword():
    with pytest.raises(TypeError):
        init_guardian_core({})  # type: ignore[call-arg]


def test_audit_returns_descriptor_not_core(forbid_activation):
    result = init_guardian_core({"enable_background_services": True}, mode="audit")
    assert isinstance(result, GuardianBootstrapAudit)
    assert result.mode == "audit"
    assert result.runtime_constructed is False
    assert result.runtime_wiring_verified is False
    assert "descriptor_only" in result.limitation
    assert isinstance(result.config, dict)


def test_describe_guardian_bootstrap_alias(forbid_activation):
    desc = describe_guardian_bootstrap({"ui_config": {"auto_start": True}})
    assert isinstance(desc, GuardianBootstrapAudit)
    assert desc.runtime_wiring_verified is False


def test_audit_does_not_load_project_guardian_package(forbid_activation):
    _purge_project_guardian_modules()
    init_guardian_core(
        {
            "enable_background_services": True,
            "enable_resource_monitoring": True,
            "enable_runtime_health_monitoring": True,
            "enable_upstream_routing_live_probes": True,
            "ui_config": {"enabled": True, "auto_start": True},
        },
        mode="audit",
    )
    loaded = [n for n in sys.modules if n == "project_guardian" or n.startswith("project_guardian.")]
    assert loaded == [], f"audit loaded project_guardian modules: {loaded}"


def test_audit_ignores_environment_for_limits(monkeypatch, forbid_activation):
    monkeypatch.setenv("ELYSIA_MEMORY_LIMIT", "0.55")
    monkeypatch.setenv("ELYSIA_CPU_LIMIT", "0.44")
    monkeypatch.setenv("ELYSIA_MEMORY_CLEANUP_THRESHOLD", "123")
    desc = init_guardian_core(mode="audit")
    assert desc.config["resource_limits"]["memory_limit"] == 0.92
    assert desc.config["resource_limits"]["cpu_limit"] == 0.9
    assert desc.config["memory_cleanup_threshold"] == 3500


def test_audit_twice_no_leaked_activation(forbid_activation):
    _purge_project_guardian_modules()
    a = init_guardian_core({"trust_file": "a.json"}, mode="audit")
    b = init_guardian_core({"trust_file": "b.json"}, mode="audit")
    assert a is not b
    assert a.config["trust_file"] == "a.json"
    assert b.config["trust_file"] == "b.json"
    assert a.runtime_constructed is False and b.runtime_constructed is False
    loaded = [n for n in sys.modules if n == "project_guardian" or n.startswith("project_guardian.")]
    assert loaded == []


def test_audit_malformed_partial_config_still_inert(forbid_activation):
    desc = init_guardian_core({"ui_config": {}, "resource_limits": {}}, mode="audit")
    assert desc.runtime_constructed is False
    assert "ui_config" in desc.config


def test_invalid_mode_rejected_before_activation(forbid_activation):
    with pytest.raises(ValueError, match="mode must be"):
        init_guardian_core(mode="inspect")  # type: ignore[arg-type]


def test_operational_disable_flags_skip_ensure_monitoring():
    """Caller disable of background services must remain disabled on operational path."""
    fake = MagicMock()
    fake.config = {"enable_background_services": False}
    get_core = MagicMock(return_value=fake)
    ensure = MagicMock(side_effect=_fail)
    schedule = MagicMock(side_effect=_fail)
    stubs = _install_fake_singleton(get_core=get_core, ensure=ensure, schedule=schedule)
    _purge_project_guardian_modules()
    with patch.dict(sys.modules, stubs):
        result = init_guardian_core(
            {"enable_background_services": False}, mode="operational"
        )
    assert result is fake
    get_core.assert_called_once()
    ensure.assert_not_called()
    schedule.assert_not_called()
