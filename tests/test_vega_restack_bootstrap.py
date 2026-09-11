"""Safe #23 partial-port probes; never construct the operational runtime."""
import ast
import builtins
import inspect
from pathlib import Path

import elysia_sub_guardian as bootstrap


def test_audit_does_not_import_runtime(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith("project_guardian"), "audit imported runtime"
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    for _ in range(2):
        result = bootstrap.describe_guardian_bootstrap()
        assert result.mode == "audit"
        assert not result.runtime_constructed
        assert not result.runtime_wiring_verified


def test_audit_honors_background_disable():
    result = bootstrap.describe_guardian_bootstrap({"enable_background_services": False})
    for key in ("enable_resource_monitoring", "enable_runtime_health_monitoring", "enable_upstream_routing_live_probes"):
        assert result.config[key] is False
    assert result.config["ui_config"]["auto_start"] is False


def test_audit_ignores_environment(monkeypatch):
    monkeypatch.setenv("ELYSIA_MEMORY_LIMIT", "0.1")
    assert bootstrap.describe_guardian_bootstrap().config["resource_limits"]["memory_limit"] == 0.92


def test_existing_backend_call_matches_bootstrap_signature():
    # Bind the actual call shape without importing elysia or invoking any runtime.
    tree = ast.parse((Path(__file__).parents[1] / "elysia.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "init_guardian_core"]
    assert calls
    for call in calls:
        inspect.signature(bootstrap.init_guardian_core).bind(
            *[None for _ in call.args], **{kw.arg: None for kw in call.keywords}
        )
