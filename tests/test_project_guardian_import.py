"""The package import must reach GuardianCore.

main referenced module activity and the planner routine loggers without
shipping them, so ``import project_guardian`` died before the dashboard
launcher could run.
"""

import datetime as dt
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_ACTIVITY_PATH = _ROOT / "project_guardian" / "module_activity.py"


def _load_activity():
    spec = importlib.util.spec_from_file_location("elysia_module_activity_under_test", _ACTIVITY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_activity_file_exists_and_aliases_income_bundle():
    activity = _load_activity()
    used = {}
    stamp = activity.mark_module_activity(
        used,
        "income_modules",
        when=dt.datetime(2026, 4, 18, 20, 0, 0),
    )
    assert stamp is not None
    assert used["income_generator"] == stamp
    assert used["wallet"] == stamp
    assert used["financial_manager"] == stamp
    assert activity.get_module_last_activity(used, "revenue_creator") == stamp
    assert activity.activity_age_minutes(
        used,
        "income_generator",
        now=dt.datetime(2026, 4, 18, 21, 0, 0),
    ) == 60.0


def test_project_guardian_package_imports_dashboard():
    pytest.importorskip("openai")
    pytest.importorskip("requests")
    pytest.importorskip("pyttsx3")
    for name in list(sys.modules):
        if name == "project_guardian" or name.startswith("project_guardian."):
            del sys.modules[name]
    import project_guardian
    from project_guardian import GuardianCore
    from project_guardian.ui_control_panel import UIControlPanel
    from project_guardian.planner_readiness import (
        log_autonomy_exploration_routine,
        log_autonomy_routine,
    )

    assert project_guardian.GuardianCore is GuardianCore
    assert UIControlPanel.__name__ == "UIControlPanel"
    assert callable(log_autonomy_routine)
    assert callable(log_autonomy_exploration_routine)


def test_autonomy_routine_log_level_follows_readiness(monkeypatch):
    pytest.importorskip("openai")
    pytest.importorskip("requests")
    pytest.importorskip("pyttsx3")
    import project_guardian.planner_readiness as readiness

    class Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(record)

    capture = Capture()
    logger = logging.getLogger("pg_test_autonomy_routine_import")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(capture)

    monkeypatch.delenv("ELYSIA_EXPLORATION_INFO_WHEN_READY", raising=False)
    monkeypatch.delenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", raising=False)
    monkeypatch.setattr(readiness, "compute_readiness_label", lambda: "ready")
    readiness.log_autonomy_routine(logger, "tick %s", "a")
    assert capture.records[-1].levelno == logging.DEBUG

    monkeypatch.setattr(readiness, "compute_readiness_label", lambda: "degraded")
    readiness.log_autonomy_exploration_routine(logger, "[Exploration] tick %s", "b")
    assert capture.records[-1].levelno == logging.INFO

    monkeypatch.setattr(readiness, "compute_readiness_label", lambda: "ready")
    monkeypatch.setenv("ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY", "1")
    readiness.log_autonomy_routine(logger, "tick %s", "c")
    assert capture.records[-1].levelno == logging.INFO
