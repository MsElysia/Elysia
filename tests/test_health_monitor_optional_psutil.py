# tests/test_health_monitor_optional_psutil.py
"""Focused tests for the optional-psutil boundary in project_guardian/health_monitor.py."""

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "project_guardian" / "health_monitor.py"


def _load_module(name):
    # Load by file path: the module is stdlib-only apart from the optional psutil import, and
    # ``import project_guardian`` currently fails on main at package import (tracked separately).
    spec = importlib.util.spec_from_file_location(name, _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hm_without_psutil(monkeypatch):
    # ``None`` in sys.modules makes ``import psutil`` raise ImportError, mirroring a host
    # where the optional dependency is not installed.
    monkeypatch.setitem(sys.modules, "psutil", None)
    return _load_module("health_monitor_no_psutil_under_test")


@pytest.fixture
def hm_with_psutil():
    pytest.importorskip("psutil")
    return _load_module("health_monitor_with_psutil_under_test")


def test_module_imports_without_psutil(hm_without_psutil):
    assert hm_without_psutil.PSUTIL_AVAILABLE is False
    assert hm_without_psutil.psutil is None


def test_resource_usage_degrades_without_psutil(hm_without_psutil):
    monitor = hm_without_psutil.HealthMonitor()
    resources = monitor._get_resource_usage()
    assert resources == {
        "cpu_percent": None,
        "memory_percent": None,
        "disk_percent": None,
        "error": "psutil not available",
    }


def test_system_health_without_psutil_uses_component_status(hm_without_psutil):
    hm = hm_without_psutil
    monitor = hm.HealthMonitor()
    monitor.check_component_health("memory", hm.HealthStatus.HEALTHY, "ok")

    health = monitor.get_system_health()
    assert health["status"] == hm.HealthStatus.HEALTHY.value
    assert health["resources"]["error"] == "psutil not available"
    assert health["components"]["memory"]["status"] == "healthy"


def test_critical_component_still_reported_without_psutil(hm_without_psutil):
    hm = hm_without_psutil
    monitor = hm.HealthMonitor()
    monitor.check_component_health("vector_store", hm.HealthStatus.CRITICAL, "index missing")

    response = monitor.get_health_endpoint_response()
    assert response["status"] == hm.HealthStatus.CRITICAL.value
    assert response["http_status"] == 503


def test_unhealthy_component_degrades_overall_without_psutil(hm_without_psutil):
    hm = hm_without_psutil
    monitor = hm.HealthMonitor()
    monitor.check_component_health("api", hm.HealthStatus.UNHEALTHY, "rate limited")

    response = monitor.get_health_endpoint_response()
    assert response["status"] == hm.HealthStatus.DEGRADED.value
    assert response["http_status"] == 200


def test_metrics_without_psutil(hm_without_psutil):
    hm = hm_without_psutil
    monitor = hm.HealthMonitor()
    monitor.check_component_health("memory", hm.HealthStatus.HEALTHY, "ok", {"items": 3})

    metrics = monitor.get_metrics()
    assert metrics["resources"]["error"] == "psutil not available"
    assert metrics["components"]["memory"]["metrics"] == {"items": 3}
    assert metrics["last_check"] is None


def test_module_reports_psutil_available_when_installed(hm_with_psutil):
    assert hm_with_psutil.PSUTIL_AVAILABLE is True
    assert hm_with_psutil.psutil is not None


def test_resource_usage_with_psutil_returns_metrics(hm_with_psutil):
    monitor = hm_with_psutil.HealthMonitor()
    resources = monitor._get_resource_usage()
    assert "error" not in resources
    for key in ("cpu_percent", "memory_percent", "memory_available_gb", "disk_percent", "disk_free_gb"):
        assert isinstance(resources[key], (int, float)), key
