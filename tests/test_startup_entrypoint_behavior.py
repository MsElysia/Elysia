"""Behavioral tests for the canonical CLI entry point without importing live services."""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _entrypoint(monkeypatch, validator):
    package = types.ModuleType("isolated_runtime")
    package.__path__ = []
    orchestrator_module = types.ModuleType("isolated_runtime.system_orchestrator")
    validator_module = types.ModuleType("isolated_runtime.config_validator")
    logging_module = types.ModuleType("isolated_runtime.logging_config")
    calls = []

    class FakeOrchestrator:
        def __init__(self, config):
            calls.append("constructed")
            self._running = False

        async def initialize(self):
            calls.append("initialized")
            return True

        async def start(self):
            calls.append("started")

        async def shutdown(self):
            calls.append("shutdown")

    orchestrator_module.SystemOrchestrator = FakeOrchestrator
    validator_module.ConfigValidator = validator
    logging_module.setup_logging = lambda **kwargs: None
    logging_module.configure_module_logging = lambda config: None
    for name, module in (
        ("isolated_runtime", package),
        ("isolated_runtime.system_orchestrator", orchestrator_module),
        ("isolated_runtime.config_validator", validator_module),
        ("isolated_runtime.logging_config", logging_module),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "isolated_runtime.__main__", ROOT / "project_guardian" / "__main__.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


@pytest.mark.parametrize("failure", [ImportError("missing dependency"), RuntimeError("broken validator")])
def test_validator_failure_prevents_orchestrator_construction(tmp_path, monkeypatch, failure):
    monkeypatch.chdir(tmp_path)

    class FailingValidator:
        def __init__(self, **kwargs):
            raise failure

    entrypoint, calls = _entrypoint(monkeypatch, FailingValidator)
    assert asyncio.run(entrypoint.main()) == 1
    assert calls == []


def test_clean_preflight_reaches_start_and_shutdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class PassingValidator:
        def __init__(self, **kwargs):
            assert kwargs["read_only"] is True

        def validate_all(self):
            return {"valid": True, "errors": []}

    entrypoint, calls = _entrypoint(monkeypatch, PassingValidator)
    assert asyncio.run(entrypoint.main()) == 0
    assert calls == ["constructed", "initialized", "started", "shutdown"]
