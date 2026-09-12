# project_guardian/tests/test_control_panel_js_smoke.py
"""String-level smoke tests for embedded control panel JavaScript."""

from __future__ import annotations

import re

import pytest


def _template() -> str:
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("UIControlPanel not available")
    return CONTROL_PANEL_TEMPLATE


def test_open_tab_and_focus_defined_once():
    html = _template()
    matches = re.findall(r"window\.openTabAndFocus\s*=\s*function", html)
    assert len(matches) == 1, f"expected one openTabAndFocus definition, found {len(matches)}"


def test_no_concatenated_duplicate_open_tab_definition():
    html = _template()
    assert "function(tabName, elementId) {        window.openTabAndFocus" not in html


def test_required_ui_functions_exist():
    html = _template()
    for name in (
        "refreshApiChatHistory",
        "renderApiChatHistory",
        "refreshBrainTrace",
        "refreshSelfImprovementProposals",
        "refreshBrainTraceVisibility",
        "refreshBackendLogs",
    ):
        assert f"window.{name}" in html or f"function {name}" in html, f"missing {name}"


def test_brain_visibility_markers_present_once():
    html = _template()
    assert html.count("brain-visibility-review-only-start") == 1
    assert html.count("brain-visibility-review-only-end") == 1


def test_logs_tab_uses_live_backend_log_endpoint():
    html = _template()
    assert "/api/logs/recent" in html
    assert "backend-log-lines" in html
    assert "elysia_unified.log" in html
    assert "unified_autonomous_system.log" in html
    assert "legacy trial history" in html
