import datetime as dt
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace

from project_guardian.capability_registry import CapabilityRegistry
from project_guardian.consensus import ConsensusEngine
from project_guardian.core import GuardianCore


class _MemoryStub:
    def remember(self, *_args, **_kwargs):
        return None

    def get_memory_stats(self):
        return {"total_memories": 1}

    def get_memory_state(self, load_if_needed=False):
        return {"json_loaded": True, "memory_loaded": True}


def _load_root_elysia_module():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("elysia_root_status_inventory", root / "elysia.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_consensus_agent_stats_include_agent_inventory():
    memory = _MemoryStub()
    consensus = ConsensusEngine(memory)

    assert consensus.register_agent("memory_core", "memory", weight=1.2, capabilities=["recall"])
    assert consensus.register_agent("safety_engine", "safety", weight=1.0, capabilities=["validate"])

    stats = consensus.get_agent_stats()

    assert stats["total_agents"] == 2
    assert stats["agent_types"]["memory"] == 1
    assert stats["agent_types"]["safety"] == 1
    assert [agent["name"] for agent in stats["agents"]] == ["memory_core", "safety_engine"]
    assert stats["agents"][0]["capabilities"] == ["recall"]


def test_guardian_core_status_includes_module_inventory():
    core = GuardianCore.__new__(GuardianCore)
    core.start_time = dt.datetime.now() - dt.timedelta(seconds=5)
    core.memory = _MemoryStub()
    core.tasks = SimpleNamespace(get_task_stats=lambda: {"active_tasks": 1})
    core.trust = SimpleNamespace(get_trust_report=lambda: {"average_trust": 1.0})
    core.consensus = SimpleNamespace(
        agents={"memory_core": {"name": "memory_core"}},
        get_agent_stats=lambda: {"total_agents": 1, "agents": [{"name": "memory_core"}]},
    )
    core.safety = SimpleNamespace(get_safety_report=lambda: {"safety_level": "high"})
    core.monitor = SimpleNamespace(get_system_health=lambda: {"status": "healthy"})
    core.reflector = SimpleNamespace(summarize_self=lambda: {"identity": "guardian"})
    core.get_startup_operational_state = lambda: {"deferred_init_complete": True}
    core._module_last_invoked = {"fractalmind": "2026-04-18T19:30:00"}
    core._modules = {
        "fractalmind": object(),
        "tool_registry": SimpleNamespace(),
    }

    status = core.get_system_status()

    assert "module_inventory" in status
    assert status["module_inventory"]["fractalmind"]["available"] is True
    assert status["module_inventory"]["fractalmind"]["last_invoked"] == "2026-04-18T19:30:00"
    assert status["module_inventory"]["tool_registry"]["class"] == "SimpleNamespace"
    assert status["module_inventory"]["tool_registry"]["health"] == "ok"


def test_guardian_core_status_resolves_income_bundle_last_invoked_aliases():
    core = GuardianCore.__new__(GuardianCore)
    core.start_time = dt.datetime.now() - dt.timedelta(seconds=5)
    core.memory = _MemoryStub()
    core.tasks = SimpleNamespace(get_task_stats=lambda: {"active_tasks": 1})
    core.trust = SimpleNamespace(get_trust_report=lambda: {"average_trust": 1.0})
    core.consensus = SimpleNamespace(
        agents={"memory_core": {"name": "memory_core"}},
        get_agent_stats=lambda: {"total_agents": 1, "agents": [{"name": "memory_core"}]},
    )
    core.safety = SimpleNamespace(get_safety_report=lambda: {"safety_level": "high"})
    core.monitor = SimpleNamespace(get_system_health=lambda: {"status": "healthy"})
    core.reflector = SimpleNamespace(summarize_self=lambda: {"identity": "guardian"})
    core.get_startup_operational_state = lambda: {"deferred_init_complete": True}
    core._module_last_invoked = {"income_modules": "2026-04-18T19:30:00"}
    core._modules = {"income_generator": SimpleNamespace()}

    status = core.get_system_status()

    assert status["module_inventory"]["income_generator"]["last_invoked"] == "2026-04-18T19:30:00"


def test_guardian_core_module_inventory_uses_runtime_health_from_status():
    core = GuardianCore.__new__(GuardianCore)
    core.start_time = dt.datetime.now() - dt.timedelta(seconds=5)
    core.memory = _MemoryStub()
    core.tasks = SimpleNamespace(get_task_stats=lambda: {"active_tasks": 1})
    core.trust = SimpleNamespace(get_trust_report=lambda: {"average_trust": 1.0})
    core.consensus = SimpleNamespace(
        agents={"memory_core": {"name": "memory_core"}},
        get_agent_stats=lambda: {"total_agents": 1, "agents": [{"name": "memory_core"}]},
    )
    core.safety = SimpleNamespace(get_safety_report=lambda: {"safety_level": "high"})
    core.monitor = SimpleNamespace(get_system_health=lambda: {"status": "healthy"})
    core.reflector = SimpleNamespace(summarize_self=lambda: {"identity": "guardian"})
    core.get_startup_operational_state = lambda: {"deferred_init_complete": True}
    core._module_last_invoked = {}
    core._modules = {
        "hestia_bridge": SimpleNamespace(connected=False),
    }

    status = core.get_system_status()

    assert status["module_inventory"]["hestia_bridge"]["available"] is True
    assert status["module_inventory"]["hestia_bridge"]["health"] == "disconnected"


def test_guardian_core_module_inventory_does_not_call_generic_get_status():
    class _BlockingStatusModule:
        def get_status(self):
            raise AssertionError("generic get_status must not be called during status serialization")

    core = GuardianCore.__new__(GuardianCore)
    core.start_time = dt.datetime.now() - dt.timedelta(seconds=5)
    core.memory = _MemoryStub()
    core.tasks = SimpleNamespace(get_task_stats=lambda: {"active_tasks": 1})
    core.trust = SimpleNamespace(get_trust_report=lambda: {"average_trust": 1.0})
    core.consensus = SimpleNamespace(
        agents={"memory_core": {"name": "memory_core"}},
        get_agent_stats=lambda: {"total_agents": 1, "agents": [{"name": "memory_core"}]},
    )
    core.safety = SimpleNamespace(get_safety_report=lambda: {"safety_level": "high"})
    core.monitor = SimpleNamespace(get_system_health=lambda: {"status": "healthy"})
    core.reflector = SimpleNamespace(summarize_self=lambda: {"identity": "guardian"})
    core.get_startup_operational_state = lambda: {"deferred_init_complete": True}
    core._module_last_invoked = {}
    core._modules = {"custom_module": _BlockingStatusModule()}

    status = core.get_system_status()

    assert status["module_inventory"]["custom_module"]["health"] == "ok"


def test_guardian_core_module_inventory_does_not_touch_descriptor_properties():
    class _DescriptorModule:
        @property
        def status(self):
            raise AssertionError("descriptor status must not be touched during status serialization")

    core = GuardianCore.__new__(GuardianCore)
    core.start_time = dt.datetime.now() - dt.timedelta(seconds=5)
    core.memory = _MemoryStub()
    core.tasks = SimpleNamespace(get_task_stats=lambda: {"active_tasks": 1})
    core.trust = SimpleNamespace(get_trust_report=lambda: {"average_trust": 1.0})
    core.consensus = SimpleNamespace(
        agents={"memory_core": {"name": "memory_core"}},
        get_agent_stats=lambda: {"total_agents": 1, "agents": [{"name": "memory_core"}]},
    )
    core.safety = SimpleNamespace(get_safety_report=lambda: {"safety_level": "high"})
    core.monitor = SimpleNamespace(get_system_health=lambda: {"status": "healthy"})
    core.reflector = SimpleNamespace(summarize_self=lambda: {"identity": "guardian"})
    core.get_startup_operational_state = lambda: {"deferred_init_complete": True}
    core._module_last_invoked = {}
    core._modules = {"custom_module": _DescriptorModule()}

    status = core.get_system_status()

    assert status["module_inventory"]["custom_module"]["health"] == "ok"


def test_elysia_status_excludes_task_router_from_integrated_module_count():
    elysia_mod = _load_root_elysia_module()
    system = elysia_mod.UnifiedElysiaSystem.__new__(elysia_mod.UnifiedElysiaSystem)
    system.start_time = dt.datetime.now() - dt.timedelta(seconds=10)
    system.running = True
    system.architect = None
    system.runtime_loop = object()
    system.guardian = SimpleNamespace(
        get_startup_operational_state=lambda: {},
        get_system_status=lambda: {},
    )
    system.modules = {
        "tool_registry": SimpleNamespace(),
        "task_router": SimpleNamespace(),
        "fractalmind": SimpleNamespace(),
    }

    status = system.get_status()

    assert status["components"]["integrated_modules"] == 2
    assert status["components"]["integrated_helpers"] == 1
    assert status["integrated_helper_names"] == ["task_router"]
    assert status["integrated_module_inventory"]["task_router"]["helper"] is True
    assert status["integrated_module_inventory"]["fractalmind"]["helper"] is False


def test_elysia_status_surfaces_module_health():
    elysia_mod = _load_root_elysia_module()
    system = elysia_mod.UnifiedElysiaSystem.__new__(elysia_mod.UnifiedElysiaSystem)
    system.start_time = dt.datetime.now() - dt.timedelta(seconds=10)
    system.running = True
    system.architect = None
    system.runtime_loop = object()
    system.guardian = SimpleNamespace(
        get_startup_operational_state=lambda: {},
        get_system_status=lambda: {},
    )
    system.modules = {
        "hestia_bridge": SimpleNamespace(connected=False),
        "task_router": SimpleNamespace(),
    }

    status = system.get_status()

    assert status["integrated_module_inventory"]["hestia_bridge"]["health"] == "disconnected"
    assert status["integrated_module_inventory"]["task_router"]["health"] == "ok"


def test_elysia_status_does_not_call_generic_get_status():
    class _BlockingStatusModule:
        def get_status(self):
            raise AssertionError("generic get_status must not be called during status serialization")

    elysia_mod = _load_root_elysia_module()
    system = elysia_mod.UnifiedElysiaSystem.__new__(elysia_mod.UnifiedElysiaSystem)
    system.start_time = dt.datetime.now() - dt.timedelta(seconds=10)
    system.running = True
    system.architect = None
    system.runtime_loop = object()
    system.guardian = SimpleNamespace(
        get_startup_operational_state=lambda: {},
        get_system_status=lambda: {},
    )
    system.modules = {"custom_module": _BlockingStatusModule()}

    status = system.get_status()

    assert status["integrated_module_inventory"]["custom_module"]["health"] == "ok"


def test_elysia_status_does_not_touch_descriptor_properties():
    class _DescriptorModule:
        @property
        def status(self):
            raise AssertionError("descriptor status must not be touched during status serialization")

    elysia_mod = _load_root_elysia_module()
    system = elysia_mod.UnifiedElysiaSystem.__new__(elysia_mod.UnifiedElysiaSystem)
    system.start_time = dt.datetime.now() - dt.timedelta(seconds=10)
    system.running = True
    system.architect = None
    system.runtime_loop = object()
    system.guardian = SimpleNamespace(
        get_startup_operational_state=lambda: {},
        get_system_status=lambda: {},
    )
    system.modules = {"custom_module": _DescriptorModule()}

    status = system.get_status()

    assert status["integrated_module_inventory"]["custom_module"]["health"] == "ok"


def test_elysia_fast_status_skips_deep_guardian_and_openclaw_probes():
    class _Guardian:
        ui_panel = SimpleNamespace(port=5000)

        def get_startup_operational_state(self):
            return {"dashboard_ready": True, "deferred_init_state": "complete"}

        def get_system_status(self):
            raise AssertionError("fast status must not call deep guardian status")

    class _OpenClaw:
        enabled = True
        default_skills = ["file_scan"]

        def is_available(self):
            raise AssertionError("fast status must not probe OpenClaw")

        def list_skills(self):
            raise AssertionError("fast status must not fetch OpenClaw skills")

    elysia_mod = _load_root_elysia_module()
    system = elysia_mod.UnifiedElysiaSystem.__new__(elysia_mod.UnifiedElysiaSystem)
    system.start_time = dt.datetime.now() - dt.timedelta(seconds=10)
    system.running = True
    system.architect = None
    system.runtime_loop = object()
    system.guardian = _Guardian()
    system.openclaw = _OpenClaw()
    system.last_openclaw_task = None
    system.last_openclaw_error = None
    system.modules = {"task_router": SimpleNamespace(), "fractalmind": SimpleNamespace()}

    status = system.get_status_fast()

    assert status["system"] == "Unified Elysia System"
    assert status["startup_phase"] == "running"
    assert status["dashboard_ready"] is True
    assert status["openclaw_enabled"] is True
    assert status["openclaw_available"] is None
    assert status["openclaw_skills_count"] == 1
    assert "mission_purpose_state" in status
    assert isinstance(status["mission_purpose_state"], dict)


def test_capability_registry_does_not_warn_before_tool_registry_exists(caplog):
    registry = CapabilityRegistry()
    guardian = SimpleNamespace(
        module_registry=SimpleNamespace(get_registry_status=lambda: {"total_modules": 1, "module_names": ["memory"]}),
        _modules={},
        consensus=SimpleNamespace(agents={}),
        missions=SimpleNamespace(get_active_missions=lambda: []),
    )

    with caplog.at_level(logging.WARNING):
        snapshot = registry.refresh(guardian)

    assert snapshot["tool_registry_count"] == 0
    assert "tool_registry" not in snapshot["plugin_module_names"]
    assert not any("toolsurface: tools=0 reason=no_tool_registry_module" in rec.message for rec in caplog.records)
