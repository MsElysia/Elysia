"""Boot catalog placeholders must never become executable tool candidates."""
import socket
from types import SimpleNamespace
from unittest.mock import patch

from core_modules.elysia_core_comprehensive.ai_tool_registry import ToolRegistry
from project_guardian.capability_execution import capability_action_string, execute_capability_kind
from project_guardian.capability_registry import CapabilityRegistry


def test_boot_stubs_are_catalog_only_and_never_selected(tmp_path):
    boot = ToolRegistry()
    boot.ensure_minimal_builtin_tools()
    guardian = SimpleNamespace(_modules={"tool_registry": boot})
    registry = CapabilityRegistry(tmp_path)
    snapshot = {"plugin_module_names": ["tool_registry"]}
    stubs = {name for name in boot.list_tools() if boot.get_tool(name)["builtin_stub"]}
    assert len(stubs) == 6
    assert not callable(getattr(boot, "call_tool", None))

    rows = {
        row["name"]: row for row in registry._build_capability_entries(guardian, snapshot)
        if row["type"] == "tool"
    }
    ranked = registry.get_relevant_capabilities("call tools fetch web run script", guardian, snapshot)
    candidates = []
    registry.append_dynamic_capability_candidates(candidates, ranked, guardian, {})
    assert stubs.isdisjoint({row["metadata"]["capability_exec_name"] for row in candidates})
    assert stubs.isdisjoint({row["name"] for row in ranked})
    assert registry.action_is_executable("tool_registry_pulse", guardian)
    assert set(rows) == stubs
    for name, row in rows.items():
        assert row["executable"] is False
        assert row["health"] == "unavailable"
        assert not row["callable"]
        assert not registry.action_is_executable(capability_action_string("tool", name), guardian)

    # Check direct invocation independently of selection. Explicit bounded handlers
    # still validate operator input, and empty input requires no network.
    with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")) as connect:
        for name in sorted(stubs):
            out = execute_capability_kind(guardian, "tool", name)
            assert out["success"] is False
            expected = (
                "missing_goal" if name in {
                    "elysia_bounded_browser", "elysia_moltbook_browser", "elysia_social_intel",
                } else "tool_registry has no call_tool"
            )
            assert out["error"] == expected
        connect.assert_not_called()


def test_callable_non_stub_still_becomes_executable_candidate(tmp_path):
    class LocalRegistry(ToolRegistry):
        def call_tool(self, name, method, **payload):
            return {"success": name == "local_example" and method == "execute", "value": payload["value"]}

    boot = LocalRegistry()
    boot.add_tool("local_example", {"provider": "local"})
    guardian = SimpleNamespace(_modules={"tool_registry": boot})
    registry = CapabilityRegistry(tmp_path)
    snapshot = {"plugin_module_names": ["tool_registry"]}
    ranked = registry.get_relevant_capabilities("call local example", guardian, snapshot)
    candidates = []
    registry.append_dynamic_capability_candidates(candidates, ranked, guardian, {})
    assert any(row["action"] == "use_capability/tool/local_example" for row in candidates)
    assert execute_capability_kind(guardian, "tool", "local_example", {"value": 42}) == {
        "success": True, "result": {"success": True, "value": 42},
    }
