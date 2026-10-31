"""Regressions for privileged-control bypasses A–D (Codex verification).

Intercepts cycle/dream/learning; never runs real autonomy, learning, or providers.
"""

from __future__ import annotations

import json
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

AUTONOMY_PATH = _ROOT / "config" / "autonomy.json"


class _Orch:
    def __init__(self, autonomy_config=None, *, contained=False):
        self.config = {}
        if autonomy_config is not None:
            self.config["autonomy_config"] = dict(autonomy_config)
        if contained:
            self.config["contained_startup"] = True
        self.cycle_calls = 0
        self.dream_calls = 0
        self.memory_save_calls = 0
        self.dreams = types.SimpleNamespace(dream_cycle=self._dream)
        self.memory = types.SimpleNamespace(save=self._save)

    def _load_autonomy_config(self):
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

    def _dream(self):
        self.dream_calls += 1

    def _save(self):
        self.memory_save_calls += 1


def _panel(orch, host="127.0.0.1") -> UIControlPanel:
    return UIControlPanel(orchestrator=orch, host=host, port=5000)


def _auth(panel: UIControlPanel):
    return {
        "X-Elysia-Identity": "dashboard-operator",
        "X-Elysia-Token": panel._dashboard_operator_token(),
    }


@pytest.fixture
def autonomy_file_guard():
    """Prevent lasting mutation of config/autonomy.json during configure tests."""
    existed = AUTONOMY_PATH.exists()
    backup = AUTONOMY_PATH.read_text(encoding="utf-8") if existed else None
    try:
        yield AUTONOMY_PATH
    finally:
        if backup is not None:
            AUTONOMY_PATH.write_text(backup, encoding="utf-8")
        elif AUTONOMY_PATH.exists() and not existed:
            AUTONOMY_PATH.unlink()


class TestBypassAEnableThenExecute:
    def test_unauth_enable_writes_nothing_then_execute_denied(self, autonomy_file_guard):
        before = autonomy_file_guard.read_text(encoding="utf-8") if autonomy_file_guard.exists() else None
        orch = _Orch({"enabled": False})
        panel = _panel(orch)
        client = panel.app.test_client()

        enable = client.post("/api/autonomy", json={"enabled": True})
        assert enable.status_code == 401
        after = autonomy_file_guard.read_text(encoding="utf-8") if autonomy_file_guard.exists() else None
        assert after == before
        assert orch.cycle_calls == 0

        # Even with auth, still disabled (no successful enable)
        exe = client.post("/api/autonomy/execute-cycle", headers=_auth(panel))
        assert exe.status_code == 403
        assert orch.cycle_calls == 0

    def test_sequence_a_closed_unauth_enable_cannot_unlock_execute(self, autonomy_file_guard):
        orch = _Orch(None)  # file-backed style once enable would succeed
        orch.config = {}
        panel = _panel(orch)
        client = panel.app.test_client()
        enable = client.post("/api/autonomy", json={"enabled": True})
        assert enable.status_code == 401
        # Simulate what a successful unauth enable used to allow: file says enabled
        # but without a successful write, inject enabled and show auth execute needs
        # both auth AND that enable never happened via unauth path.
        assert orch.cycle_calls == 0
        exe_unauth = client.post("/api/autonomy/execute-cycle")
        assert exe_unauth.status_code in (401, 403)
        assert orch.cycle_calls == 0


class TestBypassBNonLoopbackAuth:
    def test_non_loopback_enabled_unauth_does_not_invoke_cycle(self):
        orch = _Orch({"enabled": True, "allowed_actions": ["consider_learning"]})
        panel = _panel(orch, host="0.0.0.0")
        response = panel.app.test_client().post("/api/autonomy/execute-cycle")
        assert response.status_code == 401
        assert response.get_json().get("error") == "unauthorized"
        assert orch.cycle_calls == 0

    def test_non_loopback_enabled_with_auth_inert_ok(self):
        orch = _Orch({"enabled": True, "allowed_actions": ["consider_learning"]})
        panel = _panel(orch, host="0.0.0.0")
        response = panel.app.test_client().post(
            "/api/autonomy/execute-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 200
        assert orch.cycle_calls == 1


class TestBypassCDreamCycle:
    def test_dream_unauth_while_disabled_zero_side_effects(self):
        orch = _Orch({"enabled": False})
        panel = _panel(orch)
        response = panel.app.test_client().post("/api/control/dream-cycle")
        assert response.status_code in (401, 403)
        assert orch.dream_calls == 0
        assert orch.memory_save_calls == 0

    def test_dream_auth_while_disabled_zero_side_effects(self):
        orch = _Orch({"enabled": False})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/control/dream-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert orch.dream_calls == 0
        assert orch.memory_save_calls == 0

    def test_dream_auth_enabled_inert_ok(self):
        orch = _Orch({"enabled": True})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/control/dream-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 200
        assert orch.dream_calls == 1
        assert orch.memory_save_calls == 1


class TestBypassDLearningStart:
    def test_learning_unauth_while_disabled_zero_calls(self, monkeypatch):
        hits = {"n": 0}

        def _no_learn(*args, **kwargs):
            hits["n"] += 1
            return {"saved": 0, "intercepted": True}

        import project_guardian.auto_learning as al

        monkeypatch.setattr(al, "run_learning_session", _no_learn)
        monkeypatch.setattr(al, "run_mistral_chained_learning_session", _no_learn)

        orch = _Orch({"enabled": False})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/learning/start",
            json={"platform": "reddit", "query": "MachineLearning", "max_items": 2},
        )
        assert response.status_code in (401, 403)
        assert hits["n"] == 0

    def test_learning_auth_while_disabled_zero_calls(self, monkeypatch):
        hits = {"n": 0}

        def _no_learn(*args, **kwargs):
            hits["n"] += 1
            return {"saved": 0, "intercepted": True}

        import project_guardian.auto_learning as al

        monkeypatch.setattr(al, "run_learning_session", _no_learn)
        monkeypatch.setattr(al, "run_mistral_chained_learning_session", _no_learn)

        orch = _Orch({"enabled": False})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/learning/start",
            json={"platform": "reddit", "query": "MachineLearning", "max_items": 2},
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert hits["n"] == 0


class TestContainedImmutableConfigure:
    def test_contained_enable_denied_with_auth_no_write(self, autonomy_file_guard):
        before = autonomy_file_guard.read_text(encoding="utf-8") if autonomy_file_guard.exists() else None
        orch = _Orch({"enabled": False}, contained=True)
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy",
            json={"enabled": True},
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert response.get_json().get("error") == "contained_immutable"
        after = autonomy_file_guard.read_text(encoding="utf-8") if autonomy_file_guard.exists() else None
        assert after == before
        assert orch._load_autonomy_config().get("enabled") is False

    def test_auth_alone_does_not_execute_when_disabled(self):
        orch = _Orch({"enabled": False}, contained=True)
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy/execute-cycle",
            headers=_auth(panel),
        )
        assert response.status_code == 403
        assert orch.cycle_calls == 0


class TestPermittedConfigureOutsideContained:
    def test_operator_can_enable_when_not_contained(self, autonomy_file_guard):
        orch = _Orch({"enabled": False})  # currently disabled; configure must still work
        # Outside contained: no contained_startup flag
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy",
            json={"enabled": True},
            headers=_auth(panel),
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body.get("success") is True
        assert body.get("enabled") is True
        # Configure ≠ execute: cycle still not invoked by enable alone
        assert orch.cycle_calls == 0


class TestInvalidAuth:
    def test_bad_token_denied_on_configure(self, autonomy_file_guard):
        before = autonomy_file_guard.read_text(encoding="utf-8") if autonomy_file_guard.exists() else None
        orch = _Orch({"enabled": False})
        panel = _panel(orch)
        response = panel.app.test_client().post(
            "/api/autonomy",
            json={"enabled": True},
            headers={
                "X-Elysia-Identity": "dashboard-operator",
                "X-Elysia-Token": "not-the-real-token-value-at-all",
            },
        )
        assert response.status_code == 401
        after = autonomy_file_guard.read_text(encoding="utf-8") if autonomy_file_guard.exists() else None
        assert after == before

    def test_missing_auth_on_execute_enabled(self):
        orch = _Orch({"enabled": True})
        panel = _panel(orch)
        response = panel.app.test_client().post("/api/autonomy/execute-cycle")
        assert response.status_code == 401
        assert orch.cycle_calls == 0
