"""Regression: legacy POST /api/autonomy/execute-cycle must not invoke a cycle when autonomy is off.

Intercepts run_autonomous_cycle; never executes a real autonomy cycle.
"""

import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _ensure_guardian_submodules():
    if "project_guardian.ui_control_panel" in sys.modules:
        return
    if "project_guardian" not in sys.modules:
        package = types.ModuleType("project_guardian")
        package.__path__ = [str(_ROOT / "project_guardian")]
        package.__package__ = "project_guardian"
        sys.modules["project_guardian"] = package


_ensure_guardian_submodules()

from project_guardian.ui_control_panel import UIControlPanel


class _Orchestrator:
    def __init__(self, autonomy_config=None, *, load_raises=False, load_returns=None):
        self.config = {}
        if autonomy_config is not None:
            self.config["autonomy_config"] = autonomy_config
        self._load_raises = load_raises
        self._load_returns = load_returns
        self.cycle_calls = 0

    def _load_autonomy_config(self):
        if self._load_raises:
            raise RuntimeError("autonomy state unavailable")
        if self._load_returns is not None:
            return self._load_returns
        override = self.config.get("autonomy_config")
        if isinstance(override, dict):
            return dict(override)
        return {"enabled": False}

    def run_autonomous_cycle(self):
        self.cycle_calls += 1
        return {
            "executed": False,
            "action": None,
            "reason": "inert-fixture",
            "ask_user_question": None,
        }


def _panel(orch, host="127.0.0.1") -> UIControlPanel:
    return UIControlPanel(orchestrator=orch, host=host, port=5000)


def _auth(panel: UIControlPanel):
    return {
        "X-Elysia-Identity": "dashboard-operator",
        "X-Elysia-Token": panel._dashboard_operator_token(),
    }


class TestAutonomyExecuteCycleGate:
    def test_unauthenticated_disabled_does_not_invoke_cycle(self):
        orch = _Orchestrator({"enabled": False, "allowed_actions": ["consider_learning"]})
        panel = _panel(orch)
        response = panel.app.test_client().post("/api/autonomy/execute-cycle")
        assert response.status_code == 403
        body = response.get_json()
        assert body.get("success") is False
        assert body.get("error") == "autonomy_disabled"
        assert orch.cycle_calls == 0

    def test_disabled_with_valid_auth_still_denied(self):
        orch = _Orchestrator({"enabled": False})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy/execute-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert response.get_json().get("error") == "autonomy_disabled"
        assert orch.cycle_calls == 0

    def test_missing_autonomy_state_denied(self):
        orch = _Orchestrator(load_returns="not-a-dict")
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy/execute-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert response.get_json().get("error") == "autonomy_state_invalid"
        assert orch.cycle_calls == 0

    def test_unavailable_autonomy_state_denied(self):
        orch = _Orchestrator(load_raises=True)
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy/execute-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert response.get_json().get("error") == "autonomy_state_unavailable"
        assert orch.cycle_calls == 0

    def test_enabled_missing_key_treated_as_invalid(self):
        orch = _Orchestrator(load_returns={"allowed_actions": []})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy/execute-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert response.get_json().get("error") == "autonomy_state_missing_enabled"
        assert orch.cycle_calls == 0

    def test_enabled_without_auth_on_loopback_denied(self):
        orch = _Orchestrator({"enabled": True, "allowed_actions": ["consider_learning"]})
        panel = _panel(orch)
        response = panel.app.test_client().post("/api/autonomy/execute-cycle")
        assert response.status_code == 401
        assert response.get_json().get("error") == "unauthorized"
        assert orch.cycle_calls == 0

    def test_enabled_with_auth_invokes_inert_cycle_once(self):
        orch = _Orchestrator({"enabled": True, "allowed_actions": ["consider_learning"]})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy/execute-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body.get("success") is True
        assert body.get("reason") == "inert-fixture"
        assert orch.cycle_calls == 1

    def test_non_loopback_disabled_still_denied_without_auth_requirement(self):
        orch = _Orchestrator({"enabled": False})
        panel = _panel(orch, host="0.0.0.0")
        response = panel.app.test_client().post("/api/autonomy/execute-cycle")
        assert response.status_code == 403
        assert orch.cycle_calls == 0
