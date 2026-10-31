"""Dashboard Plan & Progress wiring uses existing composition APIs (no new engines)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_plan_progress_panel_present_in_dashboard_source():
    src = (ROOT / "project_guardian" / "ui_control_panel.py").read_text(encoding="utf-8")
    assert 'id="plan-progress-panel"' in src
    assert "proposeCapabilityPlan" in src
    assert "proposeReplanForSelectedStep" in src
    assert "applyProposedReplan" in src
    assert "rankCapabilitiesForGoal" in src
    assert "/api/composition/propose" in src
    assert "/api/composition/propose-replan" in src
    assert "/api/composition/apply-replan" in src
    assert "/api/composition/rank-capabilities" in src
    assert "/api/composition/evaluate-step" in src
    # Authorization separation messaging
    assert "not an execution grant" in src.casefold() or "Validated plan is not an execution grant" in src
    assert "authorize-step-calculator" in src
    assert "authorize-step-record" in src


def test_plan_progress_does_not_add_allow_everything_control():
    src = (ROOT / "project_guardian" / "ui_control_panel.py").read_text(encoding="utf-8")
    panel_start = src.index('id="plan-progress-panel"')
    panel_chunk = src[panel_start : panel_start + 4500]
    assert "allow everything" not in panel_chunk.casefold()
    assert "authorize_all" not in panel_chunk.casefold()


def test_rc_disposable_bat_uses_normal_launcher():
    start = (ROOT / "pilot" / "START_ELYSIA_RC_DISPOSABLE.bat").read_text(encoding="utf-8")
    stop = (ROOT / "pilot" / "STOP_ELYSIA_RC_DISPOSABLE.bat").read_text(encoding="utf-8")
    assert "launch_verified_pilot.py" in start
    assert "ELYSIA_PILOT_DATA_ROOT" in start
    assert "stop_verified_pilot.py" in stop
    # Must not assign the operator store; REM warnings mentioning it are OK.
    assert "set ELYSIA_PILOT_DATA_ROOT=C:\\Users\\Owner\\Elysia-Windows-Integration-Data" not in start
    assert "elysia-rc-disposable" in start.casefold() or "%TEMP%" in start


def test_pilot_paths_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ELYSIA_PILOT_DATA_ROOT", str(tmp_path / "rc-store"))
    monkeypatch.setenv("ELYSIA_PREFERRED_UI_PORT", "5086")
    monkeypatch.setenv("ELYSIA_PILOT_MARKER", "elysia-rc-test")
    # Re-import module fresh
    import importlib
    import sys

    sys.path.insert(0, str(ROOT / "pilot"))
    if "pilot_paths" in sys.modules:
        del sys.modules["pilot_paths"]
    import pilot_paths as pp

    importlib.reload(pp)
    assert pp.PILOT_DATA_ROOT == (tmp_path / "rc-store").resolve()
    assert pp.PREFERRED_UI_PORT == 5086
    assert pp.PILOT_MARKER == "elysia-rc-test"
    assert pp.RUNTIME_DIR == pp.PILOT_DATA_ROOT / "runtime"
